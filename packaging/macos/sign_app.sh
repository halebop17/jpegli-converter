#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 2 ]]; then
  echo "Usage: $0 <app_path> <codesign_identity>" >&2
  exit 1
fi

APP_PATH="$1"
IDENTITY="$2"

if [[ ! -d "$APP_PATH" ]]; then
  echo "App not found: $APP_PATH" >&2
  exit 1
fi

find "$APP_PATH" -type f \( -perm -111 -o -name '*.dylib' -o -name '*.so' \) -print0 |
while IFS= read -r -d '' file; do
  codesign --force --options runtime --timestamp --sign "$IDENTITY" "$file"
done

codesign --force --deep --options runtime --timestamp --sign "$IDENTITY" "$APP_PATH"

codesign --verify --deep --strict --verbose=2 "$APP_PATH"
spctl --assess --type execute --verbose "$APP_PATH"

echo
echo "Signed app: $APP_PATH"