#!/bin/bash
# System resource monitor - logs stats every 5 seconds to catch pre-freeze state
# Keeps last 2 hours of logs (rolling)

LOG_DIR="$HOME/skylight-dashboard/logs"
LOG_FILE="$LOG_DIR/system-monitor.log"
MAX_SIZE_MB=10

mkdir -p "$LOG_DIR"

# Rotate log if too big
rotate_log() {
    if [ -f "$LOG_FILE" ]; then
        size=$(du -m "$LOG_FILE" 2>/dev/null | cut -f1)
        if [ "${size:-0}" -ge "$MAX_SIZE_MB" ]; then
            mv "$LOG_FILE" "$LOG_FILE.old"
        fi
    fi
}

log_stats() {
    echo "========================================"
    echo "TIMESTAMP: $(date '+%Y-%m-%d %H:%M:%S')"
    echo "========================================"
    
    # Uptime and load
    echo -e "\n--- LOAD ---"
    uptime
    
    # Memory
    echo -e "\n--- MEMORY ---"
    free -h
    
    # CPU temps (if available)
    echo -e "\n--- TEMPERATURES ---"
    if command -v sensors &>/dev/null; then
        sensors 2>/dev/null | grep -E "Core|temp|Tctl" | head -10
    else
        echo "(sensors not installed)"
    fi
    
    # Top CPU processes
    echo -e "\n--- TOP CPU PROCESSES ---"
    ps aux --sort=-%cpu | head -8
    
    # Top memory processes
    echo -e "\n--- TOP MEMORY PROCESSES ---"
    ps aux --sort=-%mem | head -8
    
    # Disk I/O (if iotop data available)
    echo -e "\n--- DISK I/O ---"
    if [ -f /proc/diskstats ]; then
        cat /proc/diskstats | grep -E "sda |nvme" | head -5
    fi
    
    # GPU info (Intel integrated)
    echo -e "\n--- GPU ---"
    if command -v intel_gpu_top &>/dev/null; then
        timeout 1 intel_gpu_top -s 1 2>/dev/null | head -5 || echo "(gpu stats unavailable)"
    elif [ -d /sys/class/drm/card0 ]; then
        cat /sys/class/drm/card0/device/power/runtime_status 2>/dev/null || echo "(no gpu stats)"
    fi
    
    # Swap usage
    echo -e "\n--- SWAP ---"
    swapon --show 2>/dev/null || echo "No swap"
    
    # Open file descriptors (can cause hangs if exhausted)
    echo -e "\n--- FILE DESCRIPTORS ---"
    echo "System-wide: $(cat /proc/sys/fs/file-nr)"
    
    # Zombie processes
    echo -e "\n--- ZOMBIES ---"
    ps aux | awk '$8 ~ /Z/ {print}' | head -5 || echo "None"
    
    echo -e "\n"
}

echo "Starting system monitor (logging every 5s to $LOG_FILE)..."
echo "Press Ctrl+C to stop"

while true; do
    rotate_log
    log_stats >> "$LOG_FILE" 2>&1
    sleep 5
done
