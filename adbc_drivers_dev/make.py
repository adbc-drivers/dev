#!/usr/bin/env python3
# Copyright (c) 2025 ADBC Drivers Contributors
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
A build script for ADBC drivers using doit.

See: https://pydoit.org/
"""

import os
import platform
import shlex
import subprocess
import sys
from pathlib import Path

import doit
import packaging.version

match platform.system():
    case "Darwin":
        EXT = "dylib"
    case "Linux":
        EXT = "so"
    case "Windows":
        EXT = "dll"
    case _:
        raise RuntimeError(f"Unsupported platform: {platform.system()}")


DOIT_CONFIG = {
    "default_tasks": ["build"],
}


def to_bool(value: str | bool) -> bool:
    if value is None:
        return False
    elif isinstance(value, bool):
        return value
    value = value.lower()
    if value in {"1", "true", "yes"}:
        return True
    elif value in {"0", "false", "no"}:
        return False
    raise ValueError(f"Cannot convert {value!r} to bool")


def is_verbose() -> bool:
    return to_bool(get_var("VERBOSE", "False"))


def append_flags(env: dict[str, str], var: str, flags: str) -> None:
    if var in env:
        env[var] += " " + flags
    else:
        env[var] = flags


def architecture() -> str:
    match platform.machine():
        case "AMD64":
            return "amd64"
        case "aarch64":
            return "arm64"
        case "arm64v8":
            return "arm64"
        case "x86_64":
            return "amd64"
        case _:
            raise ValueError(f"{platform.machine()} is not a recognized architecture")


def _check_call(f, *args, **kwargs) -> str:
    extra_env = kwargs.pop("env", {})
    if extra_env:
        env = os.environ.copy()
        for k, v in extra_env.items():
            if k in {"CGO_CFLAGS", "CGO_LDFLAGS"}:
                if k in env:
                    env[k] += " " + v
                else:
                    env[k] = v
            elif k in {
                "ADBC_DRIVER_BUILD_VERSION",
                "ARCH",
                "MACOSX_DEPLOYMENT_TARGET",
                "SOURCE_ROOT",
            }:
                env[k] = v
            else:
                raise TypeError(f"Unsupported env var override {k}")
        env.update(extra_env)
        kwargs["env"] = env

    if is_verbose():
        # TODO: use log, color
        if kwargs.get("cwd") is not None:
            cwd = kwargs["cwd"]
        else:
            cwd = "."
        print(
            "*",
            f"[{cwd}]",
            " ".join(shlex.quote(arg) for arg in args[0]),
            file=sys.stderr,
        )
        if extra_env:
            for k, v in extra_env.items():
                print("*", "[env]", f"{k}={v}", file=sys.stderr)
    return f(*args, **kwargs, text=True)


def check_call(*args, **kwargs) -> str:
    return _check_call(subprocess.check_call, *args, **kwargs)


def check_output(*args, **kwargs) -> str:
    return _check_call(subprocess.check_output, *args, **kwargs).strip()


def info(*args, **kwargs):
    print("!", *args, **kwargs, file=sys.stderr)


def detect_version(
    driver_root: Path,
    *,
    strict: bool = False,
) -> str:
    if not any((driver_root / name).is_file() for name in ("Cargo.toml", "go.mod")):
        raise ValueError(f"{driver_root} does not contain a Cargo.toml or go.mod")

    repo_root = driver_root
    while not (repo_root / ".git").is_dir():
        if repo_root.parent == repo_root:
            raise ValueError(f"{driver_root} is not in a git repository")
        repo_root = repo_root.parent

    prefix = str(driver_root.relative_to(repo_root))
    if prefix == ".":
        prefix = "v"
    else:
        prefix = f"{prefix}/v"

    tags = check_output(
        [
            "git",
            "tag",
            "-l",
            "--no-column",
            "--no-format",
            "--no-color",
            "--sort",
            "-v:refname",
            f"{prefix}*",
        ],
        cwd=repo_root,
    ).splitlines()

    if not tags:
        if strict:
            raise ValueError(f"No tags found for driver {driver_root}")
        version = "unknown"
    else:
        tag = tags[0]
        version = tag[len(prefix) - 1 :]
        # If we are not on the tag, append the commit count and hash
        count = int(
            check_output(["git", "rev-list", f"{tag}..HEAD", "--count"], cwd=repo_root)
        )
        if count > 0:
            if strict:
                raise ValueError(
                    f"Driver {driver_root} is not on tag {tag}, but has {count} commits since"
                )
            rev = check_output(["git", "rev-parse", "--short", "HEAD"], cwd=repo_root)
            version += f"-dev.{count}.{rev}"

    # Append -dirty if there are uncommitted changes
    dirty = check_output(["git", "status", "--porcelain"], cwd=repo_root).splitlines()
    # Ignore untracked files
    if any(not line.startswith("?? ") for line in dirty):
        if strict:
            info(repo_root, "has uncommitted changes. `git status --porcelain`:")
            for line in dirty:
                info("> ", line)
            raise ValueError(f"{repo_root} has uncommitted changes")
        version += "-dirty"

    return version


def get_var(name: str, default: str) -> str:
    value = os.environ.get(name)
    if value is not None:
        return value
    value = doit.get_var(name, default)
    return value


def build_go(
    repo_root: Path,
    driver_root: Path,
    driver: str,
    target: str,
    *,
    ci: bool = False,
) -> None:
    version = detect_version(driver_root)
    (repo_root / "build").mkdir(exist_ok=True)

    # Embed the version in the library
    prop = "github.com/adbc-drivers/driverbase-go/driverbase.infoDriverVersion"
    ldflags = " ".join(
        [
            "-s",
            "-w",
            f"-X {prop}={version}",
        ]
    )

    tags = ["driverlib"]
    if to_bool(get_var("DEBUG", "False")):
        tags.append("assert")

    extra_tags = get_var("BUILD_TAGS", "")
    if extra_tags:
        extra_tags = extra_tags.split(",")
        extra_tags = [tag.strip() for tag in extra_tags]
        extra_tags = [tag for tag in extra_tags if tag]
        tags.extend(extra_tags)

    tags = ",".join(tags)
    tags = "-tags=" + tags

    info("Building", target, "version", version)

    env = {}

    smuggle_vars = ("CGO_CFLAGS", "CGO_LDFLAGS")
    for var in smuggle_vars:
        if var in os.environ:
            env[var] = os.environ[var]

    if platform.system() == "Darwin":
        append_flags(env, "CGO_CFLAGS", "-mmacosx-version-min=11.0")
        append_flags(env, "CGO_LDFLAGS", "-mmacosx-version-min=11.0")

    if ci and platform.system() == "Linux":
        env["SOURCE_ROOT"] = str(repo_root)
        env["ARCH"] = architecture()

        check_call(["go", "mod", "vendor"], cwd=driver_root)

        smuggle_env = ""
        for var in smuggle_vars:
            if var in env:
                smuggle_env += f'{var}="{shlex.quote(env[var])}" '

        ldflags += (
            " -linkmode external -extldflags=-Wl,--version-script=/only-export-adbc.ld"
        )
        command = [
            "docker",
            "compose",
            "run",
            "--rm",
            "--user",
            str(os.getuid()),
            "manylinux",
            "--",
            "bash",
            "-c",
            f'cd /source/{driver_root.relative_to(repo_root)} && env {smuggle_env} go build -buildmode=c-shared {tags} -o /source/build/{target} -ldflags "{ldflags}" ./pkg',
        ]
        check_call(command, cwd=Path(__file__).parent, env=env)
    else:
        check_call(
            [
                "go",
                "build",
                "-buildmode=c-shared",
                tags,
                "-o",
                f"{repo_root / 'build' / target}",
                "-ldflags",
                ldflags,
                "./pkg",
            ],
            cwd=driver_root,
            env=env,
        )

    output = (repo_root / "build" / target).resolve()
    output.chmod(0o755)
    header = output.with_suffix(".h")
    header.unlink(missing_ok=True)


def build_rust(
    repo_root: Path,
    driver_root: Path,
    driver: str,
    target: str,
    *,
    ci: bool = False,
) -> None:
    version = detect_version(driver_root)
    (repo_root / "build").mkdir(exist_ok=True)

    debug = to_bool(get_var("DEBUG", "False"))

    # Note: version embedded in library is determined by Cargo.toml
    # TODO: check that it matches git tag?
    args = []
    if not debug:
        args.append("--release")

    features = []
    extra_features = get_var("FEATURES", "")
    if extra_features:
        extra_features = extra_features.split(",")
        extra_features = [tag.strip() for tag in extra_features]
        extra_features = [tag for tag in extra_features if tag]
        features.extend(extra_features)

    if features:
        args.append("--features")
        args.append(",".join(features))

    info("Building", target, "version", version, "features", features)

    env = {}
    # Some env vars need to be explicitly propagated into Docker
    smuggle_vars = {"PROTOC"}

    if platform.system() == "Darwin":
        # https://doc.rust-lang.org/nightly/rustc/platform-support/apple-darwin.html#os-version
        env["MACOSX_DEPLOYMENT_TARGET"] = "11.0"

    if ci and platform.system() == "Linux":
        env["SOURCE_ROOT"] = str(repo_root)
        env["ARCH"] = architecture()

        volumes = get_var("ADDITIONAL_VOLUMES", "")
        if volumes:
            volumes = volumes.split(",")

        smuggle_env = ""
        for var in smuggle_vars:
            if var in env:
                smuggle_env += f'{var}="{shlex.quote(env[var])}" '
            elif var in os.environ:
                smuggle_env += f'{var}="{shlex.quote(os.environ[var])}" '

        command = [
            "docker",
            "compose",
            "run",
            "--rm",
            "--user",
            str(os.getuid()),
        ]

        for volume in volumes:
            command.extend(["-v", volume])

        command.extend(
            [
                "manylinux-rust",
                "--",
                "bash",
                "-c",
                f"cd /source/{driver_root.relative_to(repo_root)} && env {smuggle_env} cargo build {' '.join(args)}",
            ]
        )
        check_call(command, cwd=Path(__file__).parent, env=env)
    else:
        check_call(
            [
                "cargo",
                "build",
                *args,
            ],
            cwd=driver_root,
            env=env,
        )

    lib = driver_root / "target"
    if debug:
        lib = lib / "debug"
    else:
        lib = lib / "release"

    source_target = target
    if platform.system() == "Windows":
        source_target = target.removeprefix("lib")
    lib = lib / source_target

    lib.rename(repo_root / "build" / target)
    output = (repo_root / "build" / target).resolve()
    output.chmod(0o755)


def check_linux(binary: Path) -> None:
    symbols = check_output(
        [
            "nm",
            "--demangle",
            "--dynamic",
            str(binary),
        ]
    ).splitlines()

    # TODO(https://github.com/adbc-drivers/dev/issues/36): check exported symbols
    bad_symbols = []
    for symbol in symbols:
        if " T " not in symbol:
            continue
        _, _, name = symbol.partition(" T ")
        if not name.startswith("Adbc"):
            bad_symbols.append(name)
    if bad_symbols:
        raise RuntimeError(
            f"{', '.join(bad_symbols[:3])}... ({len(bad_symbols)} symbols total) should not be exported from {binary}"
        )

    # Like upstream.  Match manylinux2014's versions.
    # https://peps.python.org/pep-0599/#the-manylinux2014-policy
    glibc_max = "2.17"
    glibcxx_max = "3.14.19"

    for symbol in symbols:
        if "@GLIBC_" in symbol:
            version = packaging.version.Version(symbol.partition("@")[2][6:])
            if version > packaging.version.Version(glibc_max):
                raise RuntimeError(
                    f"{symbol} requires too new a glibc (max {glibc_max})"
                )
        elif "@GLIBCXX_" in symbol:
            version = packaging.version.Version(symbol.partition("@")[2][8:])
            if version > packaging.version.Version(glibcxx_max):
                raise RuntimeError(
                    f"{symbol} requires too new a glibcxx (max {glibcxx_max})"
                )


def check_macos(binary: Path) -> None:
    output = check_output(["otool", "-l", str(binary)]).splitlines()
    minos = None
    for line in output:
        line = line.strip()
        if not line.startswith("minos"):
            continue
        _, _, minos = line.partition(" ")
        break

    if minos is None:
        raise RuntimeError("Could not determine minimum macOS version")

    minos = packaging.version.Version(minos)
    maxos = packaging.version.Version("11.0")

    if minos > maxos:
        raise RuntimeError(
            f"{binary} requires macOS {minos} but {maxos} was expected at most"
        )


def check(binary: Path) -> None:
    if platform.system() == "Linux":
        check_linux(binary)
    elif platform.system() == "Darwin":
        check_macos(binary)


def task_build():
    driver = get_var("DRIVER", "")
    if not driver:
        raise ValueError("Must specify DRIVER=driver")

    ci = get_var("CI", False)
    lang = get_var("IMPL_LANG", "go").strip().lower()

    repo_root = Path(".").resolve().absolute()
    driver_root = Path(driver)
    if driver_root.is_dir():
        driver_root = driver_root.resolve()
    elif Path("./go.mod").is_file() or Path("./Cargo.toml").is_file():
        driver_root = Path(".").resolve()

    # Compute dependencies
    file_deps = []
    extensions = [".go", ".c", ".cc", ".cpp", ".h", ".rs"]
    for dirname, _, filenames in driver_root.walk():
        for filename in filenames:
            if filename in {"go.mod", "go.sum", "Cargo.toml", "Cargo.lock"}:
                file_deps.append(Path(dirname) / filename)
            elif any(filename.endswith(ext) for ext in extensions):
                file_deps.append(Path(dirname) / filename)

    target = f"libadbc_driver_{driver}.{EXT}"

    if lang == "go":
        actions = [
            lambda: build_go(repo_root, driver_root, driver, target, ci=ci),
        ]
    elif lang == "rust":
        actions = [
            lambda: build_rust(repo_root, driver_root, driver, target, ci=ci),
        ]
    else:
        raise ValueError(f"Unsupported LANG={lang}")

    return {
        "actions": actions,
        "file_dep": [str(p) for p in file_deps],
        "targets": [repo_root / "build" / target],
    }


def task_check():
    driver = get_var("DRIVER", "")
    if not driver:
        raise ValueError("Must specify DRIVER=driver")

    repo_root = Path(".").resolve()
    target = repo_root / "build" / f"libadbc_driver_{driver}.{EXT}"

    return {
        "actions": [
            lambda: check(target),
        ],
        "file_dep": [target],
        "targets": [],
    }


def main():
    doit.run(globals())


if __name__ == "__main__":
    main()
