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

"""Generate test documentation from validation tests."""

from pathlib import Path

from adbc_drivers_validation.generate_documentation import generate

from . import {driver_id}


if __name__ == "__main__":
    validation_dir = Path(__file__).parent.parent
    test_results = validation_dir / "validation-report.xml"
    driver_template = validation_dir / "driver-template.md"
    output_dir = validation_dir / "docs"

    if not test_results.exists():
        print(f"Error: {{test_results}} does not exist")
        print("Run the validation tests first: adbc-validation run")
        exit(1)

    if not driver_template.exists():
        print(f"Error: {{driver_template}} does not exist")
        print(f"Create a driver template file at {{driver_template}}")
        exit(1)

    output_dir.mkdir(exist_ok=True)
    generate({driver_id}.QUIRKS, test_results, driver_template, output_dir)
