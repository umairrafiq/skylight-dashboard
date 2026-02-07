#!/bin/bash
# Skylight Dashboard Launcher
# Opens the dashboard in fullscreen browser
# Server runs as systemd user service (skylight-server.service)

URL="http://localhost:8765/index.html?v=$(date +%s)"

# Ensure server is running
if ! systemctl --user is-active --quiet skylight-server; then
    systemctl --user start skylight-server
    sleep 1
fi

# Check if server is responding
if ! curl -s --max-time 2 "$URL" > /dev/null 2>&1; then
    systemctl --user restart skylight-server
    sleep 2
fi

# Kill any existing dashboard windows
pkill -f "skylight-chrome" 2>/dev/null
sleep 0.5

# Launch browser in fullscreen kiosk mode
# Note: Using separate profile so --kiosk works even if Chrome is already open
PROFILE_DIR="$HOME/.config/skylight-chrome"
if command -v google-chrome &> /dev/null; then
    nohup google-chrome --user-data-dir="$PROFILE_DIR" --kiosk --noerrdialogs --disable-infobars --no-first-run --disk-cache-size=1 --aggressive-cache-discard "$URL" >/dev/null 2>&1 &
elif command -v chromium-browser &> /dev/null; then
    nohup chromium-browser --user-data-dir="$PROFILE_DIR" --kiosk --noerrdialogs --disable-infobars --no-first-run --disk-cache-size=1 "$URL" >/dev/null 2>&1 &
elif command -v chromium &> /dev/null; then
    nohup chromium --user-data-dir="$PROFILE_DIR" --kiosk --noerrdialogs --disable-infobars --no-first-run --disk-cache-size=1 "$URL" >/dev/null 2>&1 &
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
