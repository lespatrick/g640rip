#!/usr/bin/env bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=== Building G640 RIP Native macOS App (Release) ==="
swift build -c release

APP_NAME="G640 RIP.app"
OUTPUT_DIR="$SCRIPT_DIR/build"
APP_DIR="$OUTPUT_DIR/$APP_NAME"
CONTENTS_DIR="$APP_DIR/Contents"
MACOS_DIR="$CONTENTS_DIR/MacOS"
FRAMEWORKS_DIR="$CONTENTS_DIR/Frameworks"
RESOURCES_DIR="$CONTENTS_DIR/Resources"

rm -rf "$APP_DIR"
mkdir -p "$MACOS_DIR" "$FRAMEWORKS_DIR" "$RESOURCES_DIR"

# Copy compiled binary
cp "$SCRIPT_DIR/.build/release/G640RIP" "$MACOS_DIR/G640 RIP"

# Bundle liblcms2 dylib for complete standalone portability
LCMS_LIB="$(pkg-config --variable=libdir lcms2)/liblcms2.2.dylib"
if [ -f "$LCMS_LIB" ]; then
    cp "$LCMS_LIB" "$FRAMEWORKS_DIR/"
    install_name_tool -change "$LCMS_LIB" "@rpath/liblcms2.2.dylib" "$MACOS_DIR/G640 RIP" || true
    install_name_tool -add_rpath "@executable_path/../Frameworks" "$MACOS_DIR/G640 RIP" || true
fi

# Create Info.plist
cat <<EOF > "$CONTENTS_DIR/Info.plist"
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>CFBundleExecutable</key>
    <string>G640 RIP</string>
    <key>CFBundleIdentifier</key>
    <string>com.lespatrick.g640rip</string>
    <key>CFBundleName</key>
    <string>G640 RIP</string>
    <key>CFBundlePackageType</key>
    <string>APPL</string>
    <key>CFBundleShortVersionString</key>
    <string>1.0.0</string>
    <key>CFBundleVersion</key>
    <string>1</string>
    <key>LSMinimumSystemVersion</key>
    <string>14.0</string>
    <key>NSHighResolutionCapable</key>
    <true/>
    <key>NSSupportsAutomaticGraphicsSwitching</key>
    <true/>
    <key>CFBundleDocumentTypes</key>
    <array>
        <dict>
            <key>CFBundleTypeName</key>
            <string>Image</string>
            <key>CFBundleTypeRole</key>
            <string>Viewer</string>
            <key>LSHandlerRank</key>
            <string>Alternate</string>
            <key>LSItemContentTypes</key>
            <array>
                <string>public.image</string>
                <string>public.tiff</string>
                <string>public.jpeg</string>
                <string>public.png</string>
            </array>
        </dict>
    </array>
</dict>
</plist>
EOF

echo "=== Successfully built $APP_DIR ==="
echo "You can launch the app with: open '$APP_DIR'"
