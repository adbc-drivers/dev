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
import typing
from pathlib import Path

import jinja2
import tomllib


def generate(
    root: Path, template, filename: str, params: dict[str, typing.Any]
) -> None:
    test = template.render(**params)
    sink = root / ".github/workflows" / filename
    with sink.open("w") as f:
        f.write(test)
    print("Wrote", sink)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("repository", type=Path)

    args = parser.parse_args()

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
    generate(
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
    generate(
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
        generate(
            args.repository,
            template,
            dev,
            {
                **params,
            },
        )
