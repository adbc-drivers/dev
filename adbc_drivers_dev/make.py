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

HOST_PLATFORM_NAMES = {
    "Darwin": "macos",
    "Linux": "linux",
    "Windows": "windows",
}

PLATFORM_EXTENSIONS = {
    "macos": "dylib",
    "linux": "so",
    "windows": "dll",
}

ARCH_ALIASES = {
    "amd64": "amd64",
    "x86_64": "amd64",
    "x64": "amd64",
    "aarch64": "arm64",
    "arm64": "arm64",
    "arm64v8": "arm64",
}

HOST_SYSTEM = platform.system()
try:
    PLATFORM = HOST_PLATFORM_NAMES[HOST_SYSTEM]
except KeyError as err:
    raise RuntimeError(f"Unsupported platform: {HOST_SYSTEM}") from err


DOIT_CONFIG = {
    "default_tasks": ["build"],
}
SMUGGLE_VARS = {"CGO_CFLAGS", "CGO_LDFLAGS", "GOWORK", "PROTOC"}


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


def normalize_arch(value: str) -> str:
    try:
        return ARCH_ALIASES[value.lower()]
    except KeyError as err:
        raise ValueError(f"{value} is not a recognized architecture") from err


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
                "DOCKER_DEFAULT_PLATFORM",
                "GOWORK",
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
        # use a version that dbc will still accept, not "unknown" like we used to
        version = "v0.0.1-dev"
    else:
        # sort tags, then find distance from all tags to HEAD
        # the assumption is that this is monotonically increasing, else we have a problem
        versions = []
        for tag in tags:
            version_str = tag[len(prefix) - 1 :]
            version = packaging.version.parse(version_str)
            distance = int(
                check_output(
                    ["git", "rev-list", f"{tag}..HEAD", "--count"], cwd=repo_root
                )
            )
            versions.append((version_str, version, distance, tag))

        versions.sort(key=lambda v: v[1], reverse=True)
        for v, prev in zip(versions, versions[1:]):
            if v[2] > prev[2]:
                raise ValueError(
                    f"Tag {v[0]} is further from HEAD than {prev[0]}, but has a newer version"
                )

        version, parsed_version, count, tag = versions[0]
        if count > 0:
            if strict:
                raise ValueError(
                    f"Driver {driver_root} is not on tag {tag}, but has {count} commits since"
                )
            if parsed_version.is_prerelease or parsed_version.is_devrelease:
                # This is a weird edge case, but just use the previous version (or dev version)
                for v in versions:
                    if not (v[1].is_prerelease or v[1].is_devrelease):
                        version, parsed_version, count, tag = v
                        break
                else:
                    version = "v0.0.1"
                    count = int(
                        check_output(
                            ["git", "rev-list", "HEAD", "--count"], cwd=repo_root
                        )
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


def target_platform() -> str:
    target = get_var("TARGET", "").strip().lower()
    if not target:
        return PLATFORM
    target = target.replace("/", "-")
    platform_name, _, _ = target.partition("-")
    if platform_name != "linux":
        raise ValueError(
            "Cross-compilation only supports Linux targets. "
            f"Got: {platform_name!r}. Use TARGET=linux, TARGET=linux-amd64, or TARGET=linux-arm64"
        )
    return platform_name


def target_architecture() -> str:
    target = get_var("TARGET", "").strip().lower()
    if not target:
        return normalize_arch(platform.machine())
    target = target.replace("/", "-")
    _, sep, arch = target.partition("-")
    if not sep:
        return "amd64"
    return normalize_arch(arch)


def target_extension() -> str:
    try:
        return PLATFORM_EXTENSIONS[target_platform()]
    except KeyError as err:
        raise ValueError(f"Unsupported target platform: {target_platform()}") from err


def should_use_docker() -> bool:
    target = get_var("TARGET", "").strip()
    explicit = get_var("USE_DOCKER", "").strip()

    if target:
        if explicit and not to_bool(explicit):
            raise ValueError(
                "Linux cross-compilation requires Docker; USE_DOCKER=false is not supported with TARGET=linux*"
            )
        return target_platform() == "linux"

    if explicit:
        if to_bool(explicit):
            if platform.system() != "Linux":
                raise ValueError(
                    "USE_DOCKER=true without TARGET is only supported on Linux hosts"
                )
            return True
        return False

    if to_bool(get_var("DEBUG", "False")):
        return False

    # CI on Linux: use Docker (original behavior)
    return to_bool(get_var("CI", False)) and platform.system() == "Linux"


def docker_platform() -> str:
    return f"{target_platform()}/{target_architecture()}"


def docker_env(repo_root: Path) -> dict[str, str]:
    return {
        "SOURCE_ROOT": str(repo_root),
        "DOCKER_DEFAULT_PLATFORM": docker_platform(),
    }


def maybe_build_docker(
    *,
    repo_root: Path,
    driver_root: Path,
    env: dict[str, str],
    args: list[str],
    container: str,
) -> None:
    if not should_use_docker():
        check_call(args, cwd=driver_root, env=env)
        return

    env = env.copy()
    env["SOURCE_ROOT"] = str(repo_root)
    env["ARCH"] = target_architecture()
    env["DOCKER_DEFAULT_PLATFORM"] = docker_platform()

    volumes = get_var("ADDITIONAL_VOLUMES", "")
    if volumes:
        volumes = volumes.split(",")

    # Some env vars need to be explicitly propagated into Docker
    smuggle_env = ""
    for var in SMUGGLE_VARS:
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
            container,
            "--",
            "bash",
            "-c",
            f"cd /source/{driver_root.relative_to(repo_root)} && env {smuggle_env} {' '.join(shlex.quote(arg) for arg in args)}",
        ]
    )
    check_call(command, cwd=Path(__file__).parent, env=env)


def read_linux_symbols(binary: Path) -> list[str]:
    return check_output(
        [
            "nm",
            "--demangle",
            "--dynamic",
            str(binary),
        ]
    ).splitlines()


def read_linux_symbols_in_docker(repo_root: Path, binary: Path) -> list[str]:
    rel_binary = binary.resolve().relative_to(repo_root.resolve())
    return check_output(
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "manylinux",
            "nm",
            "--demangle",
            "--dynamic",
            f"/source/{rel_binary.as_posix()}",
        ],
        cwd=Path(__file__).parent,
        env=docker_env(repo_root),
    ).splitlines()


def build_go(
    repo_root: Path,
    driver_root: Path,
    driver: str,
    target: str,
) -> None:
    strict = to_bool(get_var("RELEASE", "false"))
    version = detect_version(driver_root, strict=strict)
    (repo_root / "build").mkdir(exist_ok=True)
    target_name = target_platform()

    # Embed the version in the library
    prop = "github.com/adbc-drivers/driverbase-go/driverbase.infoDriverVersion"
    ldflags = " ".join(
        [
            # Don't exclude symbols (-s) so panics will have symbol information
            # This will exclude DWARF debug tables (-w).
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
    for var in SMUGGLE_VARS:
        if var in os.environ:
            env[var] = os.environ[var]

    if platform.system() == "Darwin" and target_name == "macos":
        append_flags(env, "CGO_CFLAGS", "-mmacosx-version-min=11.0")
        append_flags(env, "CGO_LDFLAGS", "-mmacosx-version-min=11.0")

    if should_use_docker():
        vendor_env = {"GOWORK": "off"}
        check_call(["go", "mod", "vendor"], cwd=driver_root, env=vendor_env)
        ldflags += (
            " -linkmode external -extldflags=-Wl,--version-script=/only-export-adbc.ld"
        )

        # Command differs under Docker so don't invoke this otherwise
        maybe_build_docker(
            repo_root=repo_root,
            driver_root=driver_root,
            env=env | vendor_env,
            args=[
                "go",
                "build",
                "-buildmode=c-shared",
                tags,
                "-o",
                f"/source/build/{target}",
                "-ldflags",
                ldflags,
                "./pkg",
            ],
            container="manylinux",
        )
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
) -> None:
    strict = to_bool(get_var("RELEASE", "false"))
    version = detect_version(driver_root, strict=strict)
    (repo_root / "build").mkdir(exist_ok=True)

    debug = to_bool(get_var("DEBUG", "False"))
    target_name = target_platform()

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
    if platform.system() == "Darwin" and target_name == "macos":
        # https://doc.rust-lang.org/nightly/rustc/platform-support/apple-darwin.html#os-version
        env["MACOSX_DEPLOYMENT_TARGET"] = "11.0"

    maybe_build_docker(
        repo_root=repo_root,
        driver_root=driver_root,
        env=env,
        args=["cargo", "build", *args],
        container="manylinux-rust",
    )

    lib = driver_root / "target"
    if debug:
        lib = lib / "debug"
    else:
        lib = lib / "release"

    source_target = target
    # Exclusion basically just for Databricks - their crate name is not
    # "adbc_driver_databricks" but rather "databricks_adbc"
    if target_name := get_var("TARGET_NAME", ""):
        source_target = f"lib{target_name}.{target_extension()}"
    if target_platform() == "windows":
        source_target = source_target.removeprefix("lib")
    lib = lib / source_target
    info("Copying", lib, "to", repo_root / "build" / target)

    lib.rename(repo_root / "build" / target)
    output = (repo_root / "build" / target).resolve()
    output.chmod(0o755)


def build_script(
    repo_root: Path,
    driver_root: Path,
    driver: str,
    target: str,
    *,
    ci: bool = False,
) -> None:
    strict = to_bool(get_var("RELEASE", "false"))
    version = detect_version(driver_root, strict=strict)
    (repo_root / "build").mkdir(exist_ok=True)

    debug = to_bool(get_var("DEBUG", "False"))
    target_name = target_platform()

    args = []
    if debug:
        args.append("test")
    else:
        args.append("release")
    args.append(target_name)
    args.append(target_architecture())

    info("Building", target, "version", version)

    env = {}
    if platform.system() == "Darwin" and target_name == "macos":
        env["MACOSX_DEPLOYMENT_TARGET"] = "11.0"

    args = ["./ci/scripts/build.sh", *args]
    if ci and target_name == "windows":
        # Force use of Git Bash on GitHub Actions
        args = [r"C:\Program Files\Git\bin\bash.EXE", *args]

    toolchain = get_var("TOOLCHAIN", "")
    if not toolchain:
        raise ValueError("Must specify TOOLCHAIN=toolchain for script-based build")

    container = {
        "cpp": "manylinux-cpp",
        "go": "manylinux",
        "rust": "manylinux-rust",
    }.get(toolchain)
    if container is None:
        raise ValueError(f"Unsupported TOOLCHAIN={toolchain} for script-based build")

    # if we're using a script, don't invoke docker for Go; the script itself
    # will invoke docker

    if should_use_docker() and toolchain == "go":
        check_call(args, cwd=driver_root, env=env)
    else:
        maybe_build_docker(
            repo_root=repo_root,
            driver_root=driver_root,
            env=env,
            args=args,
            container=container,
        )

    output = (repo_root / "build" / target).resolve()
    output.chmod(0o755)


def check_linux(binary: Path) -> None:
    check_linux_symbols(read_linux_symbols(binary), binary)


def check_linux_symbols(symbols: list[str], binary: Path) -> None:
    # Make sure only 'Adbc*' symbols are exported
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
    manylinux = get_var("MANYLINUX", "manylinux2014").lower()
    if manylinux == "manylinux2014":
        glibc_max = "2.17"
        glibcxx_max = "3.4.19"
    elif manylinux == "manylinux_2_28":
        glibc_max = "2.28"
        glibcxx_max = "3.4.32"

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
    if target_platform() == "linux":
        if platform.system() != "Linux":
            if should_use_docker():
                repo_root = Path(".").resolve()
                check_linux_symbols(
                    read_linux_symbols_in_docker(repo_root, binary),
                    binary,
                )
            else:
                info(
                    "Skipping Linux compatibility checks on non-Linux host (no Docker)"
                )
            return
        check_linux(binary)
    elif target_platform() == "macos":
        if platform.system() != "Darwin":
            info("Skipping macOS compatibility checks on non-macOS host")
            return
        check_macos(binary)


def task_build():
    driver = get_var("DRIVER", "")
    if not driver:
        raise ValueError("Must specify DRIVER=driver")

    ci = to_bool(get_var("CI", False))
    lang = get_var("IMPL_LANG", "go").strip().lower()

    repo_root = Path(".").resolve().absolute()
    driver_root = Path(driver)
    if driver_root.is_dir():
        driver_root = driver_root.resolve()
    elif (
        Path("./go.mod").is_file() or Path("./Cargo.toml").is_file() or lang == "script"
    ):
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

    target = f"libadbc_driver_{driver}.{target_extension()}"

    if lang == "go":
        actions = [
            lambda: build_go(repo_root, driver_root, driver, target),
        ]
    elif lang == "rust":
        actions = [
            lambda: build_rust(repo_root, driver_root, driver, target),
        ]
    elif lang == "script":
        actions = [
            lambda: build_script(repo_root, driver_root, driver, target, ci=ci),
        ]
    else:
        raise ValueError(f"Unsupported LANG={lang}")

    targets = [repo_root / "build" / target]

    result = {
        "actions": actions,
        "file_dep": [str(p) for p in file_deps],
        "targets": targets,
    }

    # Force rebuild when cross-compiling (don't use doit cache)
    if get_var("TARGET", "").strip():
        result["uptodate"] = [False]  # codespell:ignore uptodate

    return result


def task_check():
    driver = get_var("DRIVER", "")
    if not driver:
        raise ValueError("Must specify DRIVER=driver")

    repo_root = Path(".").resolve()
    target = repo_root / "build" / f"libadbc_driver_{driver}.{target_extension()}"

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
