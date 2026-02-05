#!/usr/bin/env python3
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

"""
Comand to generate ADBC validation suite structure for a driver.
"""

import argparse
import re
import subprocess
import sys
from pathlib import Path


TEMPLATES_DIR = Path(__file__).parent / "templates" / "validation"


def load_template(template_name: str) -> str:
    """Load a template file from the templates/validation directory."""
    template_path = TEMPLATES_DIR / template_name
    return template_path.read_text()


def get_git_repo_name(path: Path) -> str:
    """Get the name of the git repository root directory."""
    try:
        result = subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            cwd=path,
            capture_output=True,
            text=True,
            check=True,
        )
        repo_root = Path(result.stdout.strip())
        name = repo_root.name
        # Replace any non-lowercase letter or underscore with underscore
        name = re.sub(r'[^a-z_]', '_', name.lower())
        # Remove leading/trailing underscores
        name = name.strip('_')
        return name if name else None
    except (subprocess.CalledProcessError, FileNotFoundError):
        return None


def validate_driver_id(driver_id: str) -> bool:
    """Validate driver ID: lowercase with underscores only in middle."""
    pattern = r'^[a-z]+(_[a-z]+)*$'
    return bool(re.match(pattern, driver_id))


def prompt_driver_id(default: str) -> str:
    """Prompt user for driver ID with validation."""
    while True:
        if default:
            response = input(f"Driver ID [{default}]: ").strip()
            driver_id = response if response else default
        else:
            driver_id = input("Driver ID: ").strip()

        if not driver_id:
            print("Driver ID cannot be empty")
            continue

        if validate_driver_id(driver_id):
            return driver_id
        else:
            print("Invalid driver ID. Use lowercase letters and underscores (not at ends).")


def create_pytest_ini(validation_dir: Path) -> None:
    """Create pytest.ini file."""
    content = load_template("pytest.ini")
    (validation_dir / "pytest.ini").write_text(content)


def create_readme(validation_dir: Path, driver_id: str) -> None:
    """Create README.md file."""
    content = load_template("README.md").format(
        driver_id=driver_id,
        driver_id_upper=driver_id.upper()
    )
    (validation_dir / "README.md").write_text(content)


def create_init_py(tests_dir: Path) -> None:
    """Create tests/__init__.py file."""
    content = load_template("__init__.py")
    (tests_dir / "__init__.py").write_text(content)


def create_conftest_py(tests_dir: Path, driver_id: str) -> None:
    """Create tests/conftest.py file."""
    class_name = driver_id.title().replace('_', '')
    content = load_template("conftest.py").format(
        driver_id=driver_id,
        class_name=class_name
    )
    (tests_dir / "conftest.py").write_text(content)


def create_driver_py(tests_dir: Path, driver_id: str) -> None:
    """Create tests/{driver_id}.py file."""
    class_name = driver_id.title().replace('_', '')
    content = load_template("driver.py").format(
        driver_id=driver_id,
        driver_id_upper=driver_id.upper(),
        class_name=class_name
    )
    (tests_dir / f"{driver_id}.py").write_text(content)


def create_test_file(tests_dir: Path, test_name: str, driver_id: str) -> None:
    """Create a test file that imports from the validation suite."""
    test_class_name = test_name.title().replace('_', '')
    content = load_template("test_file.py").format(
        test_name=test_name,
        test_class_name=test_class_name,
        driver_id=driver_id
    )
    (tests_dir / f"test_{test_name}.py").write_text(content)



def create_driver_test_uri(driver_dir: Path, driver_id: str) -> None:
    """Create tests/{driver_id}/test_uri.py file."""
    content = load_template("driver_test_uri.py")
    (driver_dir / "test_uri.py").write_text(content)


def create_generate_documentation(tests_dir: Path, driver_id: str) -> None:
    """Create tests/generate_documentation.py file."""
    content = load_template("generate_documentation.py").format(
        driver_id=driver_id
    )
    (tests_dir / "generate_documentation.py").write_text(content)


def create_gitkeep(directory: Path) -> None:
    """Create .gitkeep file in empty directory."""
    (directory / ".gitkeep").write_text("")


def create_driver_template(validation_dir: Path, driver_id: str) -> None:
    """Create driver-template.md file."""
    driver_name = driver_id.replace('_', ' ').title()
    content = load_template("driver-template.md").format(
        driver_name=driver_name
    )
    (validation_dir / "driver-template.md").write_text(content)


def generate_validation_structure(target_dir: Path, driver_id: str) -> None:
    """Generate the validation folder structure."""
    validation_dir = target_dir / "validation"

    # Create main directories
    validation_dir.mkdir(parents=True)
    queries_dir = validation_dir / "queries"
    tests_dir = validation_dir / "tests"
    queries_dir.mkdir()
    tests_dir.mkdir()

    # Create queries structure
    ingest_dir = queries_dir / "ingest"
    ingest_dir.mkdir()
    create_gitkeep(ingest_dir)

    type_dir = queries_dir / "type"
    type_dir.mkdir()

    bind_dir = type_dir / "bind"
    bind_dir.mkdir()
    create_gitkeep(bind_dir)

    literal_dir = type_dir / "literal"
    literal_dir.mkdir()
    create_gitkeep(literal_dir)

    select_dir = type_dir / "select"
    select_dir.mkdir()
    create_gitkeep(select_dir)

    # Create root files
    create_pytest_ini(validation_dir)
    create_readme(validation_dir, driver_id)
    create_driver_template(validation_dir, driver_id)

    # Create test files
    create_init_py(tests_dir)
    create_conftest_py(tests_dir, driver_id)
    create_driver_py(tests_dir, driver_id)
    create_generate_documentation(tests_dir, driver_id)

    # Create test suite imports
    create_test_file(tests_dir, "connection", driver_id)
    create_test_file(tests_dir, "ingest", driver_id)
    create_test_file(tests_dir, "query", driver_id)
    create_test_file(tests_dir, "statement", driver_id)

    # Create driver-specific test directory
    driver_dir = tests_dir / driver_id
    driver_dir.mkdir()
    create_driver_test_uri(driver_dir, driver_id)

    print(f"✓ Created validation suite structure at {validation_dir}")
    print(f"✓ Driver ID: {driver_id}")
    print("\nNext steps:")
    print("  1. Build your driver shared library:")
    print(f"     The validation suite expects your driver to be in: build/libadbc_driver_{driver_id}.{{so,dylib,dll}}.")
    print("     You can customize this in validation/tests/conftest.py")
    print(f"  2. Optional. Update validation/tests/{driver_id}.py with driver-specific feature and quirks")
    print("  3. Run validation suite with: adbc-validation run")
    print("  4. Generate documentation with: adbc-validation docs")

    return 0


def init_command(args: argparse.Namespace) -> int:
    target_dir = Path(args.path).resolve()

    if not target_dir.exists():
        print(f"Error: {target_dir} does not exist")
        return 1

    # Check if validation directory already exists
    validation_dir = target_dir / "validation"
    if validation_dir.exists():
        print(f"Error: {validation_dir} already exists")
        return 1

    # Get default driver ID from git repo name
    default_driver_id = get_git_repo_name(target_dir)

    # Prompt for driver ID
    driver_id = prompt_driver_id(default_driver_id)

    return generate_validation_structure(target_dir, driver_id)


def run_command(args: argparse.Namespace) -> int:
    target_dir = Path(args.path).resolve()
    validation_dir = target_dir / "validation"
    tests_dir = validation_dir / "tests"

    if not validation_dir.exists():
        print(f"Error: {validation_dir} does not exist")
        print("Run 'adbc-validation init' first to create the validation structure")
        return 1

    # Build pytest command with standard validation flags
    cmd = [
        "pytest",
        "-vvs",
        "--junit-xml=validation-report.xml",
        "-rfEsxX",
        str(tests_dir),
    ]

    # Add any additional pytest args
    if args.pytest_args:
        cmd.extend(args.pytest_args)

    # Run pytest in the validation directory
    try:
        result = subprocess.run(
            cmd,
            cwd=validation_dir,
            check=False,
        )
        return result.returncode
    except FileNotFoundError:
        print("Error: pytest not found. Install it with 'pip install pytest' or use 'pixi run validate'")
        return 1


def docs_command(args: argparse.Namespace) -> int:
    """Handle the docs subcommand."""
    target_dir = Path(args.path).resolve()
    validation_dir = target_dir / "validation"
    generate_script = validation_dir / "tests" / "generate_documentation.py"

    if not generate_script.exists():
        print(f"Error: {generate_script} does not exist")
        print("Run 'adbc-validation init' first to create the validation structure")
        return 1

    # Run the documentation generation script as a module to support relative imports
    try:
        result = subprocess.run(
            [sys.executable, "-m", "tests.generate_documentation"],
            cwd=validation_dir,
            check=False,
        )
        if result.returncode == 0:
            print(f"✓ Documentation generated in {validation_dir / 'docs'}")
        return result.returncode
    except Exception as e:
        print(f"Error running documentation generation: {e}")
        return 1


def main():
    parser = argparse.ArgumentParser(
        description="ADBC validation suite suite management"
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    # Init subcommand
    init_parser = subparsers.add_parser(
        "init",
        help="Initialize validation folder structure"
    )
    init_parser.add_argument(
        "--path",
        type=str,
        default=".",
        help="Target directory (default: current directory)"
    )

    # Run subcommand
    run_parser = subparsers.add_parser(
        "run",
        help="Run the validation test suite"
    )
    run_parser.add_argument(
        "--path",
        type=str,
        default=".",
        help="Target directory (default: current directory)"
    )
    run_parser.add_argument(
        "pytest_args",
        nargs="*",
        help="Additional arguments to pass to pytest"
    )

    # Docs subcommand
    docs_parser = subparsers.add_parser(
        "docs",
        help="Generate documentation from validation tests"
    )
    docs_parser.add_argument(
        "--path",
        type=str,
        default=".",
        help="Target directory (default: current directory)"
    )

    args = parser.parse_args()

    if args.command == "init":
        return init_command(args)
    elif args.command == "run":
        return run_command(args)
    elif args.command == "docs":
        return docs_command(args)

    return 0


if __name__ == "__main__":
    sys.exit(main())
