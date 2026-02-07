#!/bin/bash
# Skylight Dashboard Uninstaller

APPS_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons"
SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="skylight-dashboard.service"

echo "Uninstalling Skylight Dashboard..."

# Stop and disable systemd service
if [ -f "$SYSTEMD_DIR/$SERVICE_NAME" ]; then
    systemctl --user stop "$SERVICE_NAME" 2>/dev/null
    systemctl --user disable "$SERVICE_NAME" 2>/dev/null
    rm -f "$SYSTEMD_DIR/$SERVICE_NAME"
    systemctl --user daemon-reload
    echo "Removed systemd service"
fi

# Stop any running instance (legacy)
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
