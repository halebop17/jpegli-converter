#!/usr/bin/env bash
set -euo pipefail

if [[ $# -lt 3 ]]; then
  echo "Usage: $0 <app_path> <keychain_profile_name> <zip_path>" >&2
  exit 1
fi

APP_PATH="$1"
PROFILE_NAME="$2"
ZIP_PATH="$3"

ditto -c -k --keepParent "$APP_PATH" "$ZIP_PATH"
xcrun notarytool submit "$ZIP_PATH" --keychain-profile "$PROFILE_NAME" --wait
xcrun stapler staple "$APP_PATH"
spctl --assess --type execute --verbose "$APP_PATH"

echo
echo "Notarized and stapled app: $APP_PATH"