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

import argparse
import fnmatch
import io
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

import platformdirs
import requests

RAT_VERSION = "0.16.1"


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("root", type=Path, help="Root directory of repository")

    args = parser.parse_args()
    root = args.root.resolve()
    print("Checking licenses for", root)

    # ------------------------------------------------------------
    # Download RAT if not present
    # ------------------------------------------------------------
    cache_dir = Path(
        platformdirs.user_cache_dir("adbc-drivers-dev", "ADBC Driver Foundry")
    )
    cache_dir.mkdir(parents=True, exist_ok=True)

    rat_path = cache_dir / f"apache-rat-{RAT_VERSION}.jar"
    if not rat_path.is_file():
        url = f"https://repo1.maven.org/maven2/org/apache/rat/apache-rat/{RAT_VERSION}/apache-rat-{RAT_VERSION}.jar"
        with requests.get(url, stream=True) as response:
            response.raise_for_status()
            try:
                with rat_path.open("wb") as sink:
                    for chunk in response.iter_content(chunk_size=8192):
                        sink.write(chunk)
            except Exception:
                rat_path.unlink(missing_ok=True)
                raise

    print("Using Apache RAT:", rat_path)

    # ------------------------------------------------------------
    # RAT does not respect .gitignore.  Create and check a tarball instead.
    # ------------------------------------------------------------
    commit = subprocess.check_output(
        ["git", "stash", "create"], cwd=root, text=True
    ).strip()
    if not commit:
        # No unstaged changes.
        commit = subprocess.check_output(
            ["git", "rev-parse", "HEAD"], cwd=root, text=True
        ).strip()

    # ------------------------------------------------------------
    # Load the exclusion file if present
    # ------------------------------------------------------------
    exclusion_file = root / ".rat-excludes"
    exclusions = []
    if exclusion_file.is_file():
        with exclusion_file.open("r") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#"):
                    exclusions.append(line)

    with tempfile.TemporaryDirectory() as scratch:
        scratch = Path(scratch).resolve()
        archive = scratch / "rat.tar"
        subprocess.check_call(
            ["git", "archive", "--format=tgz", f"--output={archive}", commit], cwd=root
        )

        # ------------------------------------------------------------
        # Invoke RAT
        # ------------------------------------------------------------
        report = io.StringIO(
            subprocess.check_output(
                [
                    "java",
                    "-jar",
                    str(rat_path),
                    str(archive),
                    "-x",
                ],
                text=True,
            )
        )

        root = ET.parse(report).getroot()
        unapproved = 0
        for resource in root.findall("resource"):
            approvals = resource.findall("license-approval")
            if not approvals:
                continue
            if approvals[0].attrib["name"] == "true":
                continue

            filename = resource.attrib["name"]
            if any(fnmatch.fnmatch(filename, exclusion) for exclusion in exclusions):
                continue

            if unapproved == 0:
                print("Files without licenses or with unapproved licenses found:")
            unapproved += 1
            print("-", filename)

    return unapproved
