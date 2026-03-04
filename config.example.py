# Local configuration template
# Copy this file to config.py and update with your values

# Home Assistant connection
HA_URL = "https://YOUR_HA_IP:8123"
HA_TOKEN = "YOUR_LONG_LIVED_ACCESS_TOKEN"

# Server settings
PORT = 8765

# MQTT Settings (optional - leave MQTT_ENABLED = False to disable)
MQTT_ENABLED = False
MQTT_BROKER = "YOUR_HA_IP"           # Usually same as HA_URL host (without https://)
MQTT_PORT = 1883
MQTT_USERNAME = ""                   # Leave empty if no auth
MQTT_PASSWORD = ""
MQTT_DEVICE_ID = "skylight_living"   # Unique identifier (no spaces)
MQTT_DEVICE_NAME = "Living Room Dashboard"  # Friendly name for Home Assistant

# WebSocket port for MQTT bridge (browser connects here)
WS_PORT = 8766
