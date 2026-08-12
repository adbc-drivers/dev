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

from pathlib import Path

import pytest

from adbc_drivers_dev import make_checks


def test_check_required_symbols() -> None:
    make_checks.check_required_symbols(
        [
            "AdbcDatabaseNew",
            "AdbcConnectionInit",
            "AdbcDriverMultiwordnameInit",
            "AdbcDriverInit",
            "bad_symbol",
        ],
        Path("driver.so"),
        "multiwordname",
    )

    with pytest.raises(RuntimeError, match="AdbcDriverInit"):
        make_checks.check_required_symbols(
            [
                "AdbcDatabaseNew",
                "AdbcConnectionInit",
                "AdbcDriverMultiwordnameInit",
                "bad_symbol",
            ],
            Path("driver.so"),
            "multiwordname",
        )

    with pytest.raises(RuntimeError, match="AdbcDriverMultiwordnameInit"):
        make_checks.check_required_symbols(
            ["AdbcDatabaseNew", "AdbcConnectionInit", "AdbcDriverInit", "bad_symbol"],
            Path("driver.so"),
            "multiwordname",
        )


def test_check_disallowed_symbols() -> None:
    make_checks.check_disallowed_symbols(
        [],
        Path("driver.so"),
        "driver",
    )
    make_checks.check_disallowed_symbols(
        ["AdbcFooBar"],
        Path("driver.so"),
        "driver",
    )

    with pytest.raises(RuntimeError, match="bad_symbol"):
        make_checks.check_disallowed_symbols(
            ["AdbcFooBar", "bad_symbol"],
            Path("driver.so"),
            "driver",
        )


def test_extract_exported_linux_symbols() -> None:
    symbols = [
        "000000 T AdbcDriverInit",
        "000000 T AdbcDriverDriverInit",
        "         U external_symbol",
        "000000 B _cgo_runtime",
    ]
    exported_symbols = make_checks._extract_exported_linux_symbols(symbols)
    assert exported_symbols == ["AdbcDriverInit", "AdbcDriverDriverInit"]


def test_extract_exported_macos_symbols() -> None:
    symbols = [
        "000000 T _AdbcDriverMultiwordnameInit",
        "000000 U _external_symbol",
        "000000 D __cgo_runtime",
    ]
    exported = make_checks._extract_exported_macos_symbols(symbols)
    assert exported == ["AdbcDriverMultiwordnameInit"]


def test_extract_windows_symbols() -> None:
    symbols = [
        "Dump of file driver.dll",
        "",
        "File Type: DLL",
        "",
        "    ordinal hint RVA      name",
        "",
        "          1    0 00001000 AdbcDriverInit",
        "          2    1 00001010 AdbcDriverMultiwordnameInit",
        "          3    2 00001020 bad_symbol = internal_symbol",
        "",
        "  Summary",
        "        1000 .data",
        "        6000 .text",
    ]
    exported = make_checks._extract_exported_windows_symbols(symbols)
    assert exported == ["AdbcDriverInit", "AdbcDriverMultiwordnameInit", "bad_symbol"]


def test_check_linux_libc_requirement() -> None:
    make_checks.check_linux_libc_requirement(
        [
            " U function@GLIBC_2.17",
            " U function@GLIBCXX_3.4.19",
        ],
        "manylinux2014",
    )

    make_checks.check_linux_libc_requirement(
        [
            " U function@GLIBC_2.28",
            " U function@GLIBCXX_3.4.32",
        ],
        "manylinux_2_28",
    )

    with pytest.raises(RuntimeError, match="GLIBC_2.18"):
        make_checks.check_linux_libc_requirement(
            [" U function@GLIBC_2.18"], "manylinux2014"
        )

    with pytest.raises(RuntimeError, match="GLIBCXX_3.4.20"):
        make_checks.check_linux_libc_requirement(
            [" U function@GLIBCXX_3.4.20"], "manylinux2014"
        )

    with pytest.raises(RuntimeError, match="GLIBC_2.29"):
        make_checks.check_linux_libc_requirement(
            [" U function@GLIBC_2.29"], "manylinux_2_28"
        )

    with pytest.raises(RuntimeError, match="GLIBCXX_3.4.33"):
        make_checks.check_linux_libc_requirement(
            [" U function@GLIBCXX_3.4.33"], "manylinux_2_28"
        )

    with pytest.raises(ValueError, match="Unsupported manylinux policy"):
        make_checks.check_linux_libc_requirement([], "unknown")


def test_check_macos_rejects_new_deployment_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        make_checks.subprocess,
        "check_output",
        lambda *args, **kwargs: "      minos 12.0\n",
    )
    with pytest.raises(RuntimeError, match="macOS 12.0"):
        make_checks._check_macos_deployment_target(Path("driver.dylib"))


def test_check_macos_accepts_supported_deployment_target(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        make_checks.subprocess,
        "check_output",
        lambda *args, **kwargs: "      minos 11.0\n",
    )
    make_checks._check_macos_deployment_target(Path("driver.dylib"))
