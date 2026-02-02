#!/bin/bash
# Skylight Dashboard Installer
# Sets up the desktop application for Ubuntu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_FILE="$SCRIPT_DIR/skylight-dashboard.desktop"
LAUNCHER="$SCRIPT_DIR/skylight-dashboard.sh"
ICON="$SCRIPT_DIR/skylight-dashboard.svg"
APPS_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons"

echo "Installing Skylight Dashboard..."

# Install Python dependencies
if [ -f "$SCRIPT_DIR/requirements.txt" ]; then
    echo "Installing Python dependencies..."
    pip3 install --user -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null || \
    pip install --user -r "$SCRIPT_DIR/requirements.txt" 2>/dev/null || \
    echo "Warning: Could not install Python dependencies. MQTT features may not work."
    echo "You can manually install with: pip install paho-mqtt websockets"
fi

# Make launcher executable
chmod +x "$LAUNCHER"
echo "Made launcher executable"

# Create directories if they don't exist
mkdir -p "$APPS_DIR"
mkdir -p "$ICONS_DIR"

# Copy icon to icons directory
cp "$ICON" "$ICONS_DIR/skylight-dashboard.svg"
echo "Installed icon"

# Update desktop file with correct paths and copy
sed "s|Exec=.*|Exec=$LAUNCHER|g; s|Icon=.*|Icon=$ICONS_DIR/skylight-dashboard.svg|g" "$DESKTOP_FILE" > "$APPS_DIR/skylight-dashboard.desktop"
chmod +x "$APPS_DIR/skylight-dashboard.desktop"
echo "Installed desktop entry"

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$APPS_DIR" 2>/dev/null
fi

echo ""
echo "Installation complete!"
echo ""
echo "You can now:"
echo "  1. Search for 'Skylight Dashboard' in your application menu"
echo "  2. Or run: $LAUNCHER"
echo ""
echo "To uninstall, run: $SCRIPT_DIR/uninstall.sh"
