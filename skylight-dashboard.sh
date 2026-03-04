#!/bin/bash
# Skylight Dashboard Launcher
# Opens the dashboard in fullscreen browser
# Server runs as systemd user service (skylight-server.service)

URL="https://10.0.0.151:8765/index.html?v=$(date +%s)"

# No local server needed - using remote hosted service

# Kill any existing dashboard windows
pkill -f "skylight-chrome" 2>/dev/null
sleep 0.5

# Launch browser in fullscreen kiosk mode
# Note: Using separate profile so --kiosk works even if Chrome is already open
PROFILE_DIR="$HOME/.config/skylight-chrome"
if command -v google-chrome &> /dev/null; then
    nohup google-chrome --user-data-dir="$PROFILE_DIR" --kiosk --noerrdialogs --disable-infobars --no-first-run --disk-cache-size=1 --aggressive-cache-discard --disable-gpu-rasterization "$URL" >/dev/null 2>&1 &
elif command -v chromium-browser &> /dev/null; then
    nohup chromium-browser --user-data-dir="$PROFILE_DIR" --kiosk --noerrdialogs --disable-infobars --no-first-run --disk-cache-size=1 --disable-gpu-rasterization "$URL" >/dev/null 2>&1 &
elif command -v chromium &> /dev/null; then
    nohup chromium --user-data-dir="$PROFILE_DIR" --kiosk --noerrdialogs --disable-infobars --no-first-run --disk-cache-size=1 --disable-gpu-rasterization "$URL" >/dev/null 2>&1 &
elif command -v firefox &> /dev/null; then
    nohup firefox --kiosk "$URL" >/dev/null 2>&1 &
else
    notify-send "Skylight Dashboard" "No supported browser found"
    exit 1
fi

# Disable screen idle while dashboard is open (background watcher)
(
    sleep 2
    while pgrep -f "skylight-chrome" > /dev/null; do
        # Simulate activity every 4 minutes to prevent screen sleep
        dbus-send --session --type=method_call --dest=org.gnome.ScreenSaver /org/gnome/ScreenSaver org.gnome.ScreenSaver.SimulateUserActivity 2>/dev/null
        sleep 240
    done
) &

disown
