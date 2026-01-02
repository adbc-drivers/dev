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
import itertools
import re
import subprocess
import sys
import typing
from pathlib import Path

import jinja2
import packaging.version
import tomlkit

DEFAULT_PARAMS = {
    "driver": "(unknown)",
    "private": False,
    "lang": {},
    "permissions": {},
    "aws": {},
    "gcloud": {},
}

# TOML does not support nulls
MORE_DEFAULTS = {
    "environment": None,
    "secrets": {},
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

    for key, value in itertools.chain(DEFAULT_PARAMS.items(), MORE_DEFAULTS.items()):
        if key not in params:
            params[key] = value

    if params["aws"] or params["gcloud"]:
        params["permissions"]["id_token"] = True

    workflows = args.repository / ".github/workflows"

    if params["lang"].get("go"):
        template = env.get_template("test.yaml")
        write_workflow(
            workflows,
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
            workflows,
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
            workflows,
            template,
            dev,
            {
                **params,
            },
        )

    template = env.get_template("pixi.toml")

    retcode = 0
    for lang, enabled in params["lang"].items():
        if not enabled:
            continue
        write_workflow(
            args.repository / lang,
            template,
            "pixi.toml",
            {
                **params,
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
