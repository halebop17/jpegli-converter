#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT_DIR"

if [[ ! -x ".venv/bin/python3" ]]; then
  echo "Missing .venv/bin/python3" >&2
  exit 1
fi

.venv/bin/pip install pyinstaller >/dev/null

rm -rf build dist

.venv/bin/python3 -m PyInstaller converter_app.spec --noconfirm

echo
echo "Built app bundle:"
echo "  $ROOT_DIR/dist/TIFF to jpegli Converter.app"