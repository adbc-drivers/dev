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


def test_check_symbols_accepts_adbc_exports() -> None:
    make_checks.check_symbols(
        [
            "AdbcDatabaseNew",
            "AdbcConnectionInit",
            "AdbcDriverMultiwordnameInit",
            "AdbcDriverInit",
        ],
        Path("driver.so"),
        "multiwordname",
    )


def test_check_symbols_rejects_non_adbc_exports() -> None:
    with pytest.raises(RuntimeError, match="bad_symbol"):
        make_checks.check_symbols(
            [
                "AdbcDatabaseNew",
                "AdbcDriverDriverInit",
                "AdbcDriverInit",
                "bad_symbol",
            ],
            Path("driver.so"),
            "driver",
        )


def test_check_symbols_requires_driver_init() -> None:
    with pytest.raises(RuntimeError, match="AdbcDriverMultiwordnameInit"):
        make_checks.check_symbols(
            ["AdbcDriverMultiWordNameInit"],
            Path("libadbc_driver_multiwordname.so"),
            "multiwordname",
        )


def test_extract_linux_symbols() -> None:
    assert make_checks._extract_linux_symbols(
        [
            "000000 T AdbcDriverInit",
            "000000 T AdbcDriverDriverInit",
            "         U external_symbol",
            "000000 B _cgo_runtime",
        ]
    ) == ["AdbcDriverInit", "AdbcDriverDriverInit"]


def test_extract_macos_symbols() -> None:
    assert make_checks._extract_macos_symbols(
        [
            "000000 T _AdbcDriverMultiwordnameInit",
            "000000 U _external_symbol",
            "000000 D __cgo_runtime",
        ]
    ) == ["AdbcDriverMultiwordnameInit"]


def test_check_manylinux_symbols_enforces_limits() -> None:
    with pytest.raises(RuntimeError, match="GLIBC_2.18"):
        make_checks.check_manylinux_symbols([" U function@GLIBC_2.18"], "manylinux2014")

    make_checks.check_manylinux_symbols(
        [
            " U function@GLIBC_2.28",
            " U function@GLIBCXX_3.4.32",
        ],
        "manylinux_2_28",
    )


def test_check_manylinux_symbols_rejects_unknown_policy() -> None:
    with pytest.raises(ValueError, match="Unsupported manylinux policy"):
        make_checks.check_manylinux_symbols([], "unknown")


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
