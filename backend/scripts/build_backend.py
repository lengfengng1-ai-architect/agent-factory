#!/usr/bin/env python3
"""Build the Agent Factory backend into a single executable using PyInstaller."""

import subprocess
import sys
from pathlib import Path


def main() -> None:
    # Determine paths relative to this script
    scripts_dir = Path(__file__).resolve().parent
    backend_dir = scripts_dir.parent
    venv_python = backend_dir / ".venv" / "bin" / "python"
    spec_file = backend_dir / "agent-factory.spec"

    if not venv_python.exists():
        print(f"Error: Virtual environment Python not found at {venv_python}", file=sys.stderr)
        sys.exit(1)

    if not spec_file.exists():
        print(f"Error: Spec file not found at {spec_file}", file=sys.stderr)
        sys.exit(1)

    cmd = [
        str(venv_python),
        "-m", "PyInstaller",
        str(spec_file),
        "--clean",
        "--noconfirm",
    ]

    print(f"Running in: {backend_dir}")
    print(f"Command: {' '.join(cmd)}")
    print("-" * 60)

    result = subprocess.run(cmd, cwd=backend_dir)

    if result.returncode != 0:
        print("Build failed.", file=sys.stderr)
        sys.exit(result.returncode)

    output = backend_dir / "dist" / "agent-factory-backend"
    print("-" * 60)
    print(f"Build succeeded. Output: {output}")


if __name__ == "__main__":
    main()
