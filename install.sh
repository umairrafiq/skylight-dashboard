#!/bin/bash
# Skylight Dashboard Installer
# Sets up the desktop application and systemd service for Ubuntu

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DESKTOP_FILE="$SCRIPT_DIR/skylight-dashboard.desktop"
LAUNCHER="$SCRIPT_DIR/skylight-dashboard.sh"
ICON="$SCRIPT_DIR/skylight-dashboard.svg"
APPS_DIR="$HOME/.local/share/applications"
ICONS_DIR="$HOME/.local/share/icons"
SYSTEMD_DIR="$HOME/.config/systemd/user"
SERVICE_NAME="skylight-dashboard.service"

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
mkdir -p "$SYSTEMD_DIR"

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

# Create systemd user service
cat > "$SYSTEMD_DIR/$SERVICE_NAME" << EOF
[Unit]
Description=Skylight Dashboard Server
After=network.target

[Service]
Type=simple
WorkingDirectory=$SCRIPT_DIR
ExecStartPre=/bin/bash -c 'fuser -k 8765/tcp 8766/tcp 2>/dev/null || true; sleep 2'
ExecStart=/usr/bin/python3 -u server.py
Restart=always
RestartSec=10
Environment=PYTHONUNBUFFERED=1
KillMode=mixed
TimeoutStopSec=10

[Install]
WantedBy=default.target
EOF
echo "Created systemd service"

# Reload systemd and enable service
systemctl --user daemon-reload
systemctl --user enable "$SERVICE_NAME"
echo "Enabled systemd service"

# Start the service
systemctl --user start "$SERVICE_NAME"
echo "Started systemd service"

echo ""
echo "Installation complete!"
echo ""
echo "The dashboard server is now running as a systemd user service."
echo ""
echo "Service commands:"
echo "  Status:  systemctl --user status $SERVICE_NAME"
echo "  Logs:    journalctl --user -u $SERVICE_NAME -f"
echo "  Stop:    systemctl --user stop $SERVICE_NAME"
echo "  Start:   systemctl --user start $SERVICE_NAME"
echo "  Restart: systemctl --user restart $SERVICE_NAME"
echo ""
echo "You can also:"
echo "  1. Search for 'Skylight Dashboard' in your application menu"
echo "  2. Open http://localhost:8765/index.html in a browser"
echo ""
echo "To uninstall, run: $SCRIPT_DIR/uninstall.sh"
