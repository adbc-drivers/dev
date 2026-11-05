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

from unittest.mock import patch

import pytest
from packaging.version import Version

from adbc_drivers_dev.workflow import latest_action_version


@pytest.fixture
def remote_tags():
    latest_action_version.cache_clear()
    with patch("adbc_drivers_dev.workflow.subprocess.check_output") as ls_remote:
        yield ls_remote
    latest_action_version.cache_clear()


@pytest.mark.parametrize("prefix", ["", "v"])
@pytest.mark.parametrize("annotated", [False, True])
def test_latest_action_version_skips_invalid_tags(remote_tags, prefix, annotated):
    tag = f"{prefix}1.10.0"
    refs = [
        f"{'0' * 40}\trefs/tags/tag-for-git-describe",
        f"{'2' * 40}\trefs/tags/{tag}",
        f"{'1' * 40}\trefs/tags/{prefix}1.9.0",
    ]
    if annotated:
        refs.append(f"{'3' * 40}\trefs/tags/{tag}^{{}}")
    remote_tags.return_value = "\n".join(refs) + "\n"

    assert latest_action_version("msys2/setup-msys2") == (
        Version("1.10.0"),
        tag,
        "3" * 40 if annotated else "2" * 40,
    )


def test_latest_action_version_no_valid_tags(remote_tags):
    remote_tags.return_value = f"{'0' * 40}\trefs/tags/tag-for-git-describe\n"

    with pytest.raises(
        ValueError, match="No valid version tags found for msys2/setup-msys2"
    ):
        latest_action_version("msys2/setup-msys2")
