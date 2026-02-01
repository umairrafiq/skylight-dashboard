#!/bin/bash
# Skylight Dashboard Uninstaller

APPS_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons"

echo "Uninstalling Skylight Dashboard..."

# Stop any running instance
pkill -f "skylight-dashboard.sh" 2>/dev/null
pkill -f "python3 -m http.server 8765" 2>/dev/null

# Remove desktop entry
rm -f "$APPS_DIR/skylight-dashboard.desktop"
echo "Removed desktop entry"

# Remove icon
rm -f "$ICONS_DIR/skylight-dashboard.svg"
echo "Removed icon"

# Update desktop database
if command -v update-desktop-database &> /dev/null; then
    update-desktop-database "$APPS_DIR" 2>/dev/null
fi

# Clean up temp files
rm -f /tmp/skylight-dashboard.pid
rm -f /tmp/skylight-dashboard.log

echo ""
echo "Uninstallation complete!"
echo "Note: The application files in $(dirname "$0") were not removed."
