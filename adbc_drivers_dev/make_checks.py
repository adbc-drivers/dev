# Copyright (c) 2026 ADBC Drivers Contributors
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

"""Post-build checks for compiled driver binaries."""

import os
import subprocess
from pathlib import Path

import packaging.version

from .make_config import MakeConfig, MakeEnv


def _read_linux_symbols(binary: Path) -> list[str]:
    return (
        subprocess.check_output(
            ["nm", "--demangle", "--dynamic", str(binary)], text=True
        )
        .strip()
        .splitlines()
    )


def _read_macos_symbols(binary: Path) -> list[str]:
    return (
        subprocess.check_output(["nm", "-gU", str(binary)], text=True)
        .strip()
        .splitlines()
    )


def _read_windows_symbols(binary: Path) -> list[str]:
    return (
        subprocess.check_output(["dumpbin", "/exports", str(binary)], text=True)
        .strip()
        .splitlines()
    )


def _read_linux_symbols_in_docker(
    make_env: MakeEnv, make_config: MakeConfig, binary: Path
) -> list[str]:
    rel_binary = binary.resolve().relative_to(make_env.repo_root.resolve())
    env = {
        **os.environ,
        "SOURCE_ROOT": str(make_env.repo_root),
        "DOCKER_DEFAULT_PLATFORM": (
            f"{make_env.target_platform}/{make_env.target_architecture}"
        ),
        "MANYLINUX": make_config.manylinux,
    }
    return (
        subprocess.check_output(
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
            env=env,
            text=True,
        )
        .strip()
        .splitlines()
    )


def _extract_exported_linux_symbols(symbols: list[str]) -> list[str]:
    exported_symbols = []
    for symbol in symbols:
        if " T " not in symbol:
            continue
        _, _, name = symbol.partition(" T ")
        exported_symbols.append(name)
    return exported_symbols


def _extract_exported_macos_symbols(symbols: list[str]) -> list[str]:
    exported_symbols = []
    for symbol in symbols:
        if " T " not in symbol:
            continue
        _, _, name = symbol.partition(" T ")
        exported_symbols.append(name.removeprefix("_"))
    return exported_symbols


def _extract_exported_windows_symbols(symbols: list[str]) -> list[str]:
    exported_symbols = []
    name_column = None
    for symbol in symbols:
        if symbol.strip().split() == ["ordinal", "hint", "RVA", "name"]:
            name_column = symbol.index("name")
            continue
        if name_column is None:
            continue
        if symbol.strip() == "Summary":
            break

        name = symbol[name_column:].strip().partition(" ")[0]
        if name:
            exported_symbols.append(name)
    return exported_symbols


def check_required_symbols(
    exported_symbols: list[str], binary: Path, driver: str
) -> None:
    """Check that required symbols are present in exported symbols."""
    driver_init = f"AdbcDriver{driver.lower().capitalize()}Init"
    missing_symbols = set()
    for required_symbol in (driver_init, "AdbcDriverInit"):
        if required_symbol not in exported_symbols:
            missing_symbols.add(required_symbol)
    if missing_symbols:
        raise RuntimeError(
            f"{', '.join(missing_symbols)} should be exported from {binary}"
        )


def check_disallowed_symbols(
    exported_symbols: list[str], binary: Path, driver: str
) -> None:
    """Check that disallowed symbols are not exported."""
    bad_symbols = [
        symbol for symbol in exported_symbols if not symbol.startswith("Adbc")
    ]
    if bad_symbols:
        raise RuntimeError(
            f"{', '.join(bad_symbols[:3])}... ({len(bad_symbols)} symbols total) should not be exported from {binary}"
        )


def check_linux_libc_requirement(symbols: list[str], manylinux: str) -> None:
    """Check that required libc symbols are compatible with the manylinux policy."""
    limits = {
        "manylinux2014": ("2.17", "3.4.19"),
        "manylinux_2_28": ("2.28", "3.4.32"),
    }
    try:
        glibc_max, glibcxx_max = limits[manylinux.lower()]
    except KeyError as err:
        raise ValueError(f"Unsupported manylinux policy: {manylinux}") from err

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


def _check_linux(make_env: MakeEnv, make_config: MakeConfig, binary: Path) -> None:
    if make_env.host_platform == "linux":
        symbols = _read_linux_symbols(binary)
    elif make_env.use_docker:
        symbols = _read_linux_symbols_in_docker(make_env, make_config, binary)
    else:
        raise RuntimeError(
            "Cannot run Linux compatibility checks on non-Linux host without Docker"
        )
    exported_symbols = _extract_exported_linux_symbols(symbols)
    check_required_symbols(exported_symbols, binary, make_config.driver)
    check_disallowed_symbols(exported_symbols, binary, make_config.driver)
    check_linux_libc_requirement(symbols, make_config.manylinux)


def _check_macos_deployment_target(binary: Path) -> None:
    output = subprocess.check_output(["otool", "-l", str(binary)], text=True)
    minos = None
    for line in output.splitlines():
        line = line.strip()
        if line.startswith("minos"):
            _, _, minos = line.partition(" ")
            break

    if minos is None:
        raise RuntimeError("Could not determine minimum macOS version")

    version = packaging.version.Version(minos)
    max_version = packaging.version.Version("11.0")
    if version > max_version:
        raise RuntimeError(
            f"{binary} requires macOS {version} but {max_version} was expected at most"
        )


def _check_macos(make_config: MakeConfig, binary: Path) -> None:
    symbols = _read_macos_symbols(binary)
    exported_symbols = _extract_exported_macos_symbols(symbols)
    check_required_symbols(exported_symbols, binary, make_config.driver)
    check_disallowed_symbols(exported_symbols, binary, make_config.driver)
    _check_macos_deployment_target(binary)


def _check_windows(make_config: MakeConfig, binary: Path) -> None:
    symbols = _read_windows_symbols(binary)
    exported_symbols = _extract_exported_windows_symbols(symbols)
    check_required_symbols(exported_symbols, binary, make_config.driver)
    # Do not check disallowed symbols on Windows - we don't have a good way of
    # hiding symbols as we do on Linux/macOS


def check(make_env: MakeEnv, make_config: MakeConfig, binary: Path) -> None:
    if make_env.target_platform == "linux":
        _check_linux(make_env, make_config, binary)
    elif make_env.target_platform == "macos":
        _check_macos(make_config, binary)
    elif make_env.target_platform == "windows":
        _check_windows(make_config, binary)
    else:
        raise ValueError(f"Unknown target platform: {make_env.target_platform}")
