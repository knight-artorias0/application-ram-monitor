#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

MIN_PYTHON=311

python_version() {
  python3 -c 'import sys; print(f"{sys.version_info.major}{sys.version_info.minor:02d}")'
}

if ! command -v python3 >/dev/null 2>&1; then
  echo "error: python3 is required (>= 3.11)" >&2
  exit 1
fi

version="$(python_version)"
if (( version < MIN_PYTHON )); then
  echo "error: Python >= 3.11 required (found $(python3 --version))" >&2
  exit 1
fi

if command -v pipx >/dev/null 2>&1; then
  echo "Installing with pipx..."
  pipx install .
else
  echo "pipx not found; installing with pip --user..."
  python3 -m pip install --user .
fi

echo
echo "Installed. Run: appmon"
