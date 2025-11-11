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
import tomllib


def write_workflow(
    root: Path, template, filename: str, params: dict[str, typing.Any]
) -> None:
    test = template.render(**params)
    sink = root / ".github/workflows" / filename
    with sink.open("w") as f:
        f.write(test)
    print("Wrote", sink)


def generate_workflows(args) -> None:
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
    with config_path.open("rb") as f:
        params = tomllib.load(f)

    if "aws" not in params:
        params["aws"] = None

    if "gcloud" not in params:
        params["gcloud"] = None

    if "lang" not in params:
        params["lang"] = {}

    if params["aws"] or params["gcloud"]:
        params["permissions"] = {
            "id_token": True,
        }

    template = env.get_template("test.yaml")
    write_workflow(
        args.repository,
        template,
        "go_test.yaml",
        {
            **params,
            "pull_request_trigger_paths": [".github/workflows/go_test.yaml"],
            "release": False,
            "workflow_name": "Test",
        },
    )
    write_workflow(
        args.repository,
        template,
        "go_release.yaml",
        {
            **params,
            "pull_request_trigger_paths": [".github/workflows/go_release.yaml"],
            "release": True,
            "workflow_name": "Release",
        },
    )

    for dev in ["dev.yaml", "dev_issues.yaml", "dev_pr.yaml"]:
        template = env.get_template(dev)
        write_workflow(
            args.repository,
            template,
            dev,
            {
                **params,
            },
        )


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

                print(
                    f"  Updating {match.group(1)} from {match.group(2)} to {latest[2]} ({latest[1]})"
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
        generate_workflows(args)
        return 0
    elif args.subcommand == "update-actions":
        update_actions()
        return 0
    else:
        parser.print_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
