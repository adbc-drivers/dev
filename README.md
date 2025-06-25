<!--
  Copyright (c) 2025 ADBC Drivers Contributors

  Licensed under the Apache License, Version 2.0 (the "License");
  you may not use this file except in compliance with the License.
  You may obtain a copy of the License at

          http://www.apache.org/licenses/LICENSE-2.0

  Unless required by applicable law or agreed to in writing, software
  distributed under the License is distributed on an "AS IS" BASIS,
  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
  See the License for the specific language governing permissions and
  limitations under the License.
-->

# Developer Tools for ADBC Drivers

This repository contains common infrastructure (pre-commit hooks, reusable
workflows for GitHub Actions, etc.)

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md).

## Installation & Usage

### pre-commit: License Header Check

The [pre-commit](https://pre-commit.com/) hook runs [Apache
RAT](https://creadur.apache.org/rat/), which checks and ensures proper
copyright/license headers are present.

Add this repository to your `.pre-commit-config.yaml`:

```yaml
- repo: git@github.com:adbc-drivers/dev
  rev: "<latest rev on main>"
  hooks:
  - id: rat
```

### GitHub Actions

There are various [reusable workflows][reusable-workflow].  They can be used
by adding a `uses:` clause to your own workflow.  For example:

```yaml
jobs:
  lint:
    uses: adbc-drivers/dev/.github/workflows/dev.yaml@REVISION
```

- `dev.yaml`: runs `pre-commit` and checks that the PR title meets the
  [Conventional Commits](https://www.conventionalcommits.org/en/v1.0.0/)
  standard.
- `dev_issues.yaml`: intended to be run when a "take" comment is made on an
  issue.  Assigns the issue to the commenter.
- `release.yaml`: create a draft release on GitHub with an attached changelog.
- `test.yaml`: build and test a Go-based driver.  If tests pass, also create
  shared libraries for each platform/architecture.
- `validate.yaml`: run the validation suite.

### Utility Scripts

You can `pip install .` to install the utility scripts.  This should be done
with a virtual environment or Conda environment active.

[reusable-workflow]: https://docs.github.com/en/actions/sharing-automations/reusing-workflows
