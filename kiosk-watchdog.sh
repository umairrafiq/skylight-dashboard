#!/bin/bash
# Kiosk watchdog - detects white/blank screens and restarts Chrome
# Checks every 60 seconds

LOG_FILE="$HOME/skylight-dashboard/logs/kiosk-watchdog.log"
SCREENSHOT="/tmp/kiosk-check.png"
KIOSK_URL="https://10.0.0.151:8765/index.html"

mkdir -p "$(dirname "$LOG_FILE")"

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1" | tee -a "$LOG_FILE"
}

restart_kiosk() {
    log "Restarting Chrome kiosk..."
    pkill -f "chrome.*kiosk" 2>/dev/null
    sleep 3
    
    # Start Chrome kiosk
    DISPLAY=:0 /opt/google/chrome/chrome \
        --kiosk \
        --noerrdialogs \
        --disable-extensions \
        --disable-infobars \
        --disable-session-crashed-bubble \
        --disable-translate \
        --disable-features=TranslateUI \
        --disable-background-networking \
        --disable-sync \
        --disable-default-apps \
        --no-first-run \
        --start-fullscreen \
        --process-per-site \
        --disable-pinch \
        --overscroll-history-navigation=0 \
        --disable-gpu-rasterization \
        "$KIOSK_URL" &>/dev/null &
    
    sleep 5
    log "Chrome kiosk restarted"
}

check_screen() {
    # Take screenshot
    DISPLAY=:0 gnome-screenshot -f "$SCREENSHOT" 2>/dev/null
    
    if [ ! -f "$SCREENSHOT" ]; then
        log "ERROR: Could not take screenshot"
        return 1
    fi
    
    # Check if image is mostly white using ImageMagick
    # Get the mean color values (0-255 scale)
    if command -v convert &>/dev/null; then
        # Get percentage of white-ish pixels (RGB all > 250)
        WHITE_PCT=$(convert "$SCREENSHOT" -fuzz 5% -fill black +opaque white -format "%[fx:mean*100]" info: 2>/dev/null)
        
        # Alternative: check mean brightness
        MEAN=$(convert "$SCREENSHOT" -colorspace Gray -format "%[fx:mean*255]" info: 2>/dev/null)
        
        log "Screen check - Mean brightness: ${MEAN:-unknown}, White%: ${WHITE_PCT:-unknown}"
        
        # If mean brightness > 250 (very white), likely blank screen
        if [ -n "$MEAN" ]; then
            MEAN_INT=${MEAN%.*}
            if [ "${MEAN_INT:-0}" -gt 250 ]; then
                log "WARNING: Screen appears blank (brightness: $MEAN)"
                return 2
            fi
        fi
    else
        log "ImageMagick not installed, using fallback check"
        # Fallback: just check if Chrome is responding
        if ! curl -s --max-time 5 https://10.0.0.151:8765/api/ | grep -q "API running"; then
            log "WARNING: Server not responding"
            return 2
        fi
    fi
    
    rm -f "$SCREENSHOT"
    return 0
}

check_chrome_running() {
    if ! pgrep -f "chrome.*kiosk" > /dev/null; then
        log "WARNING: Chrome kiosk not running"
        return 1
    fi
    return 0
}

check_server_running() {
    if ! curl -s --max-time 5 https://10.0.0.151:8765/api/ | grep -q "API running"; then
        log "WARNING: Dashboard server not responding"
        return 1
    fi
    return 0
}

# Main loop
log "Kiosk watchdog started (checking every 60s)"

# Track consecutive failures
FAIL_COUNT=0
MAX_FAILS=2

while true; do
    sleep 60
    
    # Check if server is up
    if ! check_server_running; then
        log "Server down, skipping screen check"
        continue
    fi
    
    # Check if Chrome is running
    if ! check_chrome_running; then
        FAIL_COUNT=$((FAIL_COUNT + 1))
        if [ $FAIL_COUNT -ge $MAX_FAILS ]; then
            restart_kiosk
            FAIL_COUNT=0
        fi
        continue
    fi
    
    # Check for white screen
    check_screen
    RESULT=$?
    
    if [ $RESULT -eq 2 ]; then
        FAIL_COUNT=$((FAIL_COUNT + 1))
        log "Blank screen detected ($FAIL_COUNT/$MAX_FAILS)"
        
        if [ $FAIL_COUNT -ge $MAX_FAILS ]; then
            restart_kiosk
            FAIL_COUNT=0
        fi
    else
        FAIL_COUNT=0
    fi
done
