#!/bin/zsh
set -euo pipefail

PROJECT_DIR="${0:A:h:h}"
PRODUCT_NAME="MyVoiceDesktop"
BUNDLE_DIR="$PROJECT_DIR/dist/$PRODUCT_NAME.app"
EXECUTABLE="$BUNDLE_DIR/Contents/MacOS/$PRODUCT_NAME"
MODE="run"

for argument in "$@"; do
  case "$argument" in
    --debug) MODE="debug" ;;
    --logs) MODE="logs" ;;
    --telemetry) MODE="telemetry" ;;
    --verify) MODE="verify" ;;
    *) print -u2 "Unknown argument: $argument"; exit 2 ;;
  esac
done

pkill -x "$PRODUCT_NAME" 2>/dev/null || true
cd "$PROJECT_DIR"
swift build

mkdir -p "$BUNDLE_DIR/Contents/MacOS" "$BUNDLE_DIR/Contents/Resources"
cp "$PROJECT_DIR/.build/debug/$PRODUCT_NAME" "$EXECUTABLE"
chmod +x "$EXECUTABLE"

cat > "$BUNDLE_DIR/Contents/Info.plist" <<'PLIST'
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0"><dict>
<key>CFBundleDevelopmentRegion</key><string>ko</string>
<key>CFBundleExecutable</key><string>MyVoiceDesktop</string>
<key>CFBundleIdentifier</key><string>dev.myvoice.desktop</string>
<key>CFBundleInfoDictionaryVersion</key><string>6.0</string>
<key>CFBundleName</key><string>MyVoice</string>
<key>CFBundlePackageType</key><string>APPL</string>
<key>CFBundleShortVersionString</key><string>2.1.1</string>
<key>CFBundleVersion</key><string>211</string>
<key>LSMinimumSystemVersion</key><string>14.0</string>
<key>NSHighResolutionCapable</key><true/>
<key>NSPrincipalClass</key><string>NSApplication</string>
</dict></plist>
PLIST

if [[ "$MODE" == "verify" ]]; then
  test -x "$EXECUTABLE"
  plutil -lint "$BUNDLE_DIR/Contents/Info.plist"
  print "Verified $BUNDLE_DIR"
  exit 0
fi

/usr/bin/open -n "$BUNDLE_DIR"
if [[ "$MODE" == "debug" ]]; then
  sleep 1
  lldb -p "$(pgrep -x "$PRODUCT_NAME" | head -n 1)"
elif [[ "$MODE" == "logs" || "$MODE" == "telemetry" ]]; then
  /usr/bin/log stream --style compact --predicate "process == '$PRODUCT_NAME'"
fi
