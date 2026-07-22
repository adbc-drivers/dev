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

import subprocess
import typing
from pathlib import Path

import tomllib
from pydantic import BaseModel, Field

_GO_VERSION_FLAG = "github.com/adbc-drivers/driverbase-go/driverbase.infoDriverVersion"


class MakeEnv(BaseModel):
    ci: bool = Field(
        default=False, description="Whether to build the driver in CI mode"
    )
    debug: bool = Field(
        default=False, description="Whether to build the driver in debug mode"
    )
    host_platform: typing.Literal["linux", "macos", "windows"]
    host_architecture: typing.Literal["amd64", "arm64"]
    target_platform: typing.Literal["linux", "macos", "windows"]
    target_architecture: typing.Literal["amd64", "arm64"]
    repo_root: Path
    driver_root: Path
    version: str

    @property
    def shared_library_affix(self) -> tuple[str, str]:
        if self.target_platform == "linux":
            return ("lib", ".so")
        elif self.target_platform == "macos":
            return ("lib", ".dylib")
        elif self.target_platform == "windows":
            return ("", ".dll")
        else:
            raise ValueError(f"Unknown target platform: {self.target_platform}")

    def shared_library_name(self, driver: str) -> str:
        prefix, suffix = self.shared_library_affix
        output_name = f"{prefix}adbc_driver_{driver}{suffix}"
        return output_name

    @property
    def is_cross_compile(self) -> bool:
        return (
            self.host_platform != self.target_platform
            or self.host_architecture != self.target_architecture
        )

    @property
    def use_docker(self) -> bool:
        if self.target_platform == "linux":
            return not self.debug or self.is_cross_compile
        return False


class MakePlan(BaseModel):
    make_env: MakeEnv
    make_config: "MakeConfig"
    env_vars: dict[str, str] = Field(
        default_factory=dict,
        description="Environment variables to set when building the driver",
    )
    commands: list[list[str]] = Field(
        default_factory=list, description="The commands to run to build the driver"
    )
    artifact_path: Path | None
    docker_container: str | None

    @property
    def target_path(self) -> Path:
        output_dir = self.make_env.driver_root / "build"
        output_name = self.make_env.shared_library_name(self.make_config.driver)
        return output_dir / output_name

    def run(self) -> None:
        # TODO: docker, port over other stuff from make.py
        target_path = self.target_path
        target_path.parent.mkdir(parents=True, exist_ok=True)

        for command in self.commands:
            print("*", " ".join(command))
            subprocess.run(
                command,
                cwd=self.make_env.driver_root,
                env={**self.env_vars, **subprocess.os.environ},
                check=True,
            )

        if self.artifact_path is not None:
            self.artifact_path.rename(target_path)
        target_path.chmod(0o755)


class LangGo(BaseModel):
    model_config = {
        "extra": "forbid",
        "validate_by_name": True,
        "validate_by_alias": True,
    }

    lang: typing.Literal["go"]


class LangRust(BaseModel):
    model_config = {
        "extra": "forbid",
        "validate_by_name": True,
        "validate_by_alias": True,
    }

    lang: typing.Literal["rust"]
    features: typing.List[str] = Field(
        default_factory=list,
        description="The features to enable when building the Rust driver, e.g. ['static-linking', 'bundled']",
    )
    manifest_path: str | None = Field(
        default=None,
        alias="manifest-path",
    )


class LangScript(BaseModel):
    model_config = {
        "extra": "forbid",
        "validate_by_name": True,
        "validate_by_alias": True,
    }

    lang: typing.Literal["script"]
    toolchain: typing.Literal["cpp", "go", "rust"]

    @property
    def docker_container(self) -> str:
        if self.toolchain == "cpp":
            return "manylinux-cpp"
        elif self.toolchain == "go":
            return "manylinux"
        elif self.toolchain == "rust":
            return "manylinux-rust"
        else:
            raise ValueError(f"Unknown toolchain: {self.toolchain}")


class MakeConfig(BaseModel):
    model_config = {
        "extra": "forbid",
        "validate_by_name": True,
        "validate_by_alias": True,
    }

    driver: str = Field(description="The driver to build, e.g. 'spark', 'datafusion'")
    lang: typing.Union[LangGo | LangRust | LangScript] = Field(
        discriminator="lang", description="The implementation language"
    )
    manylinux: str = Field(
        default="manylinux2014",
        description="The manylinux version to use when verifying allowed symbols on Linux, e.g. 'manylinux2014', 'manylinux_2_28'",
    )

    def build_plan(self, config: MakeEnv) -> MakePlan:
        env_vars = default_build_env(config)

        if isinstance(self.lang, LangGo):
            ldflags = [
                # Don't exclude symbols so panics will have symbol information
                # "-s",
                # Exclude DWARF debug tables
                "-w",
                # Embed Go version
                f"-X {_GO_VERSION_FLAG}={config.version}",
            ]
            tags = ["driverlib"]
            if config.debug:
                tags.append("assert")

            # TODO: figure out what to do about extra tags, since some are injected dynamically
            # TODO: docker

            # TODO: rename config to make_env
            artifact_name = config.shared_library_name(self.driver)
            artifact_path = config.driver_root / "build" / artifact_name
            args = [
                "go",
                "build",
                "-buildmode=c-shared",
                f"-tags={','.join(tags)}",
                f"-ldflags={' '.join(ldflags)}",
                "-o",
                str(artifact_path),
                "./pkg",
            ]

            return MakePlan(
                make_env=config,
                make_config=self,
                env_vars=env_vars,
                commands=[args],
                artifact_path=None,
                docker_container=None,
            )

        elif isinstance(self.lang, LangRust):
            args = ["cargo", "build"]

            artifact_path = config.driver_root
            manifest_path = config.driver_root / "Cargo.toml"
            if self.lang.manifest_path:
                artifact_path /= self.lang.manifest_path
                manifest_path = artifact_path / "Cargo.toml"
                args.append("--manifest-path")
                args.append(str(manifest_path))

            artifact_path /= "target"
            if config.debug:
                artifact_path /= "debug"
            else:
                args.append("--release")
                artifact_path /= "release"

            if self.lang.features:
                args.append("--features")
                args.append(",".join(self.lang.features))

            with manifest_path.open("rb") as f:
                cargo_toml = tomllib.load(f)

            if "lib" in cargo_toml and "name" in cargo_toml["lib"]:
                lib_name = cargo_toml["lib"]["name"]
            else:
                lib_name = cargo_toml["package"]["name"].replace("-", "_")

            prefix, suffix = config.shared_library_affix
            artifact_path /= f"{prefix}{lib_name}{suffix}"

            docker_container = None
            if config.use_docker:
                docker_container = "manylinux-rust"

            return MakePlan(
                make_env=config,
                make_config=self,
                env_vars=env_vars,
                commands=[args],
                artifact_path=artifact_path,
                docker_container=docker_container,
            )

        elif isinstance(self.lang, LangScript):
            args = ["./ci/scripts/build.sh"]
            if config.debug:
                args.append("test")
            else:
                args.append("release")

            args.append(config.target_platform)
            args.append(config.target_architecture)

            if config.target_platform == "windows" and config.ci:
                # Force use of Git Bash on GitHub Actions
                args = [r"C:\Program Files\Git\bin\bash.EXE", *args]

            docker_container = None
            if config.use_docker:
                docker_container = self.lang.docker_container

            return MakePlan(
                make_env=config,
                make_config=self,
                env_vars=env_vars,
                commands=[args],
                artifact_path=None,
                docker_container=docker_container,
            )

        raise NotImplementedError(
            f"Build plan not implemented for lang={self.lang.lang}"
        )


def default_build_env(config: MakeEnv) -> dict[str, str]:
    env = {}
    if config.target_platform == "macos":
        # https://doc.rust-lang.org/nightly/rustc/platform-support/apple-darwin.html#os-version
        env["MACOSX_DEPLOYMENT_TARGET"] = "11.0"
        env["CGO_CFLAGS"] = "-mmacosx-version-min=11.0"
        env["CGO_LDFLAGS"] = "-mmacosx-version-min=11.0"

    return env
