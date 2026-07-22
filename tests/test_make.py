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

from adbc_drivers_dev.make_config import LangRust, MakeConfig, MakeEnv


def test_build_config(tmp_path: Path) -> None:
    config = MakeEnv(
        ci=False,
        debug=False,
        host_platform="linux",
        host_architecture="amd64",
        target_platform="linux",
        target_architecture="amd64",
        repo_root=tmp_path,
        driver_root=tmp_path / "rust",
    )
    assert config.shared_library_affix == ("lib", ".so")
    assert config.use_docker

    config = MakeEnv(
        ci=False,
        debug=True,
        host_platform="linux",
        host_architecture="amd64",
        target_platform="linux",
        target_architecture="amd64",
        repo_root=tmp_path,
        driver_root=tmp_path / "rust",
    )
    assert not config.use_docker

    config = MakeEnv(
        ci=False,
        debug=True,
        host_platform="macos",
        host_architecture="arm64",
        target_platform="linux",
        target_architecture="amd64",
        repo_root=tmp_path,
        driver_root=tmp_path / "rust",
    )
    assert config.use_docker

    config = MakeEnv(
        ci=False,
        debug=True,
        host_platform="macos",
        host_architecture="arm64",
        target_platform="macos",
        target_architecture="arm64",
        repo_root=tmp_path,
        driver_root=tmp_path / "rust",
    )
    assert not config.use_docker


def test_rust(tmp_path: Path) -> None:
    (tmp_path / "rust").mkdir(exist_ok=True, parents=True)
    with (tmp_path / "rust" / "Cargo.toml").open("w") as f:
        f.write(
            """
            [package]
            name = "adbc-driver-foobar"
            """
        )

    config = MakeEnv(
        ci=False,
        debug=False,
        host_platform="linux",
        host_architecture="amd64",
        target_platform="linux",
        target_architecture="amd64",
        repo_root=tmp_path,
        driver_root=tmp_path / "rust",
    )

    make_config = MakeConfig(driver="foobar", lang=LangRust(lang="rust", features=[]))
    plan = make_config.build_plan(config)
    assert plan.env_vars == {}
    assert plan.commands == [["cargo", "build", "--release"]]
    assert (
        plan.artifact_path
        == tmp_path / "rust" / "target" / "release" / "libadbc_driver_foobar.so"
    )
    assert plan.docker_container == "manylinux-rust"

    make_config = MakeConfig(
        driver="foobar", lang=LangRust(lang="rust", features=["foobar"])
    )
    plan = make_config.build_plan(config)
    assert plan.commands == [["cargo", "build", "--release", "--features", "foobar"]]


def test_rust_cross_compile(tmp_path: Path) -> None:
    pass
