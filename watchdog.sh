#!/bin/bash
# Skylight Dashboard Watchdog
# Checks if the server is responding and restarts if hung

TIMEOUT=5
URL="https://10.0.0.151:8765/index.html"
LOG="/tmp/skylight-watchdog.log"

# Check if server responds within timeout
if timeout $TIMEOUT curl -s -o /dev/null -w "%{http_code}" "$URL" | grep -q "200"; then
    # Server is healthy
    exit 0
fi

# Server is not responding - restart it
echo "$(date): Server unresponsive, restarting..." >> "$LOG"
systemctl --user restart skylight-dashboard.service

# Wait and verify
sleep 5
if timeout $TIMEOUT curl -s -o /dev/null "$URL"; then
    echo "$(date): Server restarted successfully" >> "$LOG"
else
    echo "$(date): Server restart failed!" >> "$LOG"
fi
