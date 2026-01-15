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

"""Generate workflows for a particular repository."""

import argparse
import functools
import re
import subprocess
import sys
import typing
from pathlib import Path

import jinja2
import packaging.version
import tomlkit


def _require_bool(value: typing.Any, path: list[str]) -> bool:
    if not isinstance(value, bool):
        raise TypeError(f"Expected bool at `{'.'.join(path)}`, got {type(value)}")
    return value


def _require_str_optional_nonempty(value: typing.Any, path: list[str]) -> str:
    if value is None:
        return value
    if not isinstance(value, str):
        raise TypeError(f"Expected bool at `{'.'.join(path)}`, got {type(value)}")
    if not value.strip():
        raise ValueError(f"Expected non-empty string at `{'.'.join(path)}`")
    return value


def _unknown_keys(path, keys) -> Exception:
    if path:
        return ValueError(f"Unknown keys in `{'.'.join(path)}`: {', '.join(keys)}")
    return ValueError(f"Unknown keys at root: {', '.join(keys)}")


class Params:
    def __init__(self, raw: dict[str, typing.Any]) -> None:
        self.driver: str = raw.pop("driver", "(unknown)")
        self.environment: str | None = _require_str_optional_nonempty(
            raw.pop("environment", None), ["environment"]
        )
        self.private: bool = _require_bool(raw.pop("private", False), ["private"])
        self.lang: dict[str, bool] = {}
        for lang, enabled in raw.pop("lang", {}).items():
            self.lang[lang] = _require_bool(enabled, ["lang", lang])

        self.secrets: dict[str, dict[str, str]] = {
            "build:release": {},
            "test": {},
            "validate": {},
        }
        for secret, secret_value in raw.pop("secrets", {}).items():
            if isinstance(secret_value, str):
                for context in self.secrets:
                    self.secrets[context][secret] = secret_value
            elif isinstance(secret_value, dict):
                name = secret_value.pop("secret")
                for scope in secret_value.pop("contexts", self.secrets.keys()):
                    self.secrets[scope][secret] = name

                if secret_value:
                    raise _unknown_keys(["secrets", secret], secret_value.keys())
            else:
                raise TypeError(
                    f"Secret {secret} must be a string or mapping, not {type(secret_value)}"
                )
        all_secrets = {}
        for context_secrets in self.secrets.values():
            all_secrets.update(context_secrets)
        self.secrets["all"] = all_secrets

        self.permissions: dict[str, bool] = {}

        self.aws = {}
        if aws := raw.pop("aws", {}):
            self.secrets["all"]["AWS_ROLE"] = "AWS_ROLE"
            self.secrets["all"]["AWS_ROLE_SESSION_NAME"] = "AWS_ROLE_SESSION_NAME"
            self.aws["region"] = aws.pop("region")
            if aws:
                raise _unknown_keys(["aws"], aws.keys())

        self.gcloud = _require_bool(raw.pop("gcloud", False), ["gcloud"])
        if self.gcloud:
            self.secrets["all"]["GCLOUD_SERVICE_ACCOUNT"] = "GCLOUD_SERVICE_ACCOUNT"
            self.secrets["all"]["GCLOUD_WORKLOAD_IDENTITY_PROVIDER"] = (
                "GCLOUD_WORKLOAD_IDENTITY_PROVIDER"
            )

        if self.aws or self.gcloud:
            # TODO: it might be better to have this be "write" but for now we
            # don't need the flexibility
            self.permissions["id_token"] = True

        self.validation = {
            "extra_dependencies": {},
        }
        if validation := raw.pop("validation", {}):
            if extra_deps := validation.pop("extra-dependencies", {}):
                self.validation["extra_dependencies"] = extra_deps

            if validation:
                raise ValueError(
                    f"Unknown validation parameters: {', '.join(validation.keys())}"
                )

        if raw:
            raise ValueError(f"Unknown parameters: {', '.join(raw.keys())}")

    def to_dict(self) -> dict[str, typing.Any]:
        return {
            "driver": self.driver,
            "environment": self.environment,
            "private": self.private,
            "lang": self.lang,
            "secrets": self.secrets,
            "permissions": self.permissions,
            "aws": self.aws,
            "gcloud": self.gcloud,
            "validation": self.validation,
        }

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Params):
            return NotImplemented
        return self.to_dict() == other.to_dict()


DEFAULT_PARAMS = {
    "driver": "(unknown)",
    "private": False,
    "lang": {},
}


def write_workflow(
    root: Path, template, filename: str, params: dict[str, typing.Any]
) -> None:
    rendered = template.render(**params)
    sink = root / filename
    with sink.open("w") as f:
        f.write(rendered)
        if not rendered.endswith("\n"):
            f.write("\n")
    print("Wrote", sink)


def generate_workflows(args) -> int:
    env = jinja2.Environment(
        loader=jinja2.PackageLoader("adbc_drivers_dev"),
        autoescape=jinja2.select_autoescape(),
        block_start_string="<%",
        block_end_string="%>",
        variable_start_string="<{",
        variable_end_string="}>",
        trim_blocks=True,
        undefined=jinja2.StrictUndefined,
    )

    config_path = args.repository / ".github/workflows/generate.toml"
    try:
        with config_path.open("rb") as f:
            params = tomlkit.load(f).unwrap()
    except FileNotFoundError:
        print(f"{config_path} not found.", file=sys.stderr)

        config_path.parent.mkdir(parents=True, exist_ok=True)
        with config_path.open("w") as f:
            tomlkit.dump(DEFAULT_PARAMS, f)
        print("Wrote out defaults, please fill it in.", file=sys.stderr)

        return 1

    params = Params(params)

    workflows = args.repository / ".github/workflows"

    if params.lang.get("go"):
        template = env.get_template("test.yaml")
        write_workflow(
            workflows,
            template,
            "go_test.yaml",
            {
                **params.to_dict(),
                "pull_request_trigger_paths": [".github/workflows/go_test.yaml"],
                "release": False,
                "workflow_name": "Test",
            },
        )
        write_workflow(
            workflows,
            template,
            "go_release.yaml",
            {
                **params.to_dict(),
                "pull_request_trigger_paths": [".github/workflows/go_release.yaml"],
                "release": True,
                "workflow_name": "Release",
            },
        )
        template = env.get_template("go_test_pr.yaml")
        if params.secrets["all"]:
            write_workflow(
                workflows,
                template,
                "go_test_pr.yaml",
                {
                    **params.to_dict(),
                },
            )

    for dev in ["dev.yaml", "dev_issues.yaml", "dev_pr.yaml"]:
        template = env.get_template(dev)
        write_workflow(
            workflows,
            template,
            dev,
            {
                **params.to_dict(),
            },
        )

    template = env.get_template("pixi.toml")

    retcode = 0
    for lang, enabled in params.lang.items():
        if not enabled:
            continue
        write_workflow(
            args.repository / lang,
            template,
            "pixi.toml",
            {
                **params.to_dict(),
            },
        )

        license_template = args.repository / lang / "license.tpl"
        if not license_template.is_file():
            print(f"Missing {license_template}", file=sys.stderr)
            retcode = 1

    return retcode


@functools.cache
def latest_action_version(action: str) -> (packaging.version.Version, str, str):
    # XXX: this won't work with repos that have multiple actions
    result = subprocess.check_output(
        [
            "git",
            "ls-remote",
            "--refs",
            "--tags",
            "--exit-code",
            "--quiet",
            f"https://github.com/{action}",
        ],
        text=True,
    )
    tags = []
    for line in result.strip().splitlines():
        sha, ref = line.split()
        tag = ref.removeprefix("refs/tags/")

        if tag == "master" or "-node" in tag or tag == "testEnableForGHES":
            # aws-actions/configure-aws-credentials, others have weird tags
            continue

        version = packaging.version.parse(tag.lstrip("v"))
        tags.append((version, tag, sha))

    tags.sort(key=lambda x: x[0])
    latest = tags[-1]
    return latest


def update_actions() -> None:
    root = Path(__file__).parent / "templates"
    templates = root.rglob("*.yaml")

    action_re = re.compile(r"uses: ([\w\-/]+)@([\w\-.]+)(\W*#.*)?")

    for template in templates:
        print("Updating", template)

        with template.open("r") as f:
            content = f.read()

            def replace_action(match: re.Match[str]) -> str:
                latest = latest_action_version(match.group(1))

                if match.group(2) == latest[2]:
                    print(f"  {match.group(1)} already at {latest[2]} ({latest[1]})")
                else:
                    print(
                        f"  {match.group(1)} updated from {match.group(2)} to {latest[2]} ({latest[1]})"
                    )
                return f"uses: {match.group(1)}@{latest[2]}  # {latest[1]}"

            new_content = action_re.sub(replace_action, content)

        with template.open("w") as f:
            f.write(new_content)


def main():
    parser = argparse.ArgumentParser()
    subcommand = parser.add_subparsers(dest="subcommand", required=True)

    generate = subcommand.add_parser("generate")
    generate.add_argument("repository", type=Path)

    subcommand.add_parser("update-actions")

    args = parser.parse_args()

    if args.subcommand == "generate":
        return generate_workflows(args)
    elif args.subcommand == "update-actions":
        update_actions()
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
