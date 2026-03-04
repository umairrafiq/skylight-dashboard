#!/usr/bin/env python3
"""
Home Assistant Dashboard Server
Serves the dashboard and proxies API requests to Home Assistant
Includes MQTT client for Home Assistant integration and WebSocket bridge
"""

import http.server
import socketserver
import urllib.request
import urllib.error
import urllib.parse
import ssl
import json
import os
import threading
import time
import asyncio
import subprocess
import sqlite3
import hashlib
import shutil
from datetime import datetime, timedelta

# Photo cache settings
PHOTO_CACHE_DIR = os.path.expanduser('~/.cache/skylight-photos')
PHOTO_CACHE_MAX_AGE = 7 * 24 * 3600  # 7 days
PHOTO_CACHE_MAX_SIZE_MB = 500  # Max cache size in MB
# Dashboard version - read from index.html so there's one source of truth
def get_dashboard_version():
    """Extract version from index.html DASHBOARD_VERSION constant"""
    try:
        index_path = os.path.join(os.path.dirname(__file__), 'index.html')
        with open(index_path, 'r') as f:
            content = f.read()
        # Look for: const DASHBOARD_VERSION = '1.3.2';
        import re
        match = re.search(r"const\s+DASHBOARD_VERSION\s*=\s*['\"]([^'\"]+)['\"]", content)
        if match:
            return match.group(1)
        return "unknown"
    except:
        return "unknown"

DASHBOARD_VERSION = get_dashboard_version()

# Import configuration from config.py
try:
    from config import HA_URL, HA_TOKEN, PORT
except ImportError:
    print("ERROR: config.py not found!")
    print("Copy config.example.py to config.py and update with your values")
    exit(1)

# Import optional MQTT configuration
try:
    from config import (
        MQTT_ENABLED, MQTT_BROKER, MQTT_PORT,
        MQTT_USERNAME, MQTT_PASSWORD,
        MQTT_DEVICE_ID, MQTT_DEVICE_NAME, WS_PORT
    )
except ImportError:
    MQTT_ENABLED = False
    MQTT_BROKER = ""
    MQTT_PORT = 1883
    MQTT_USERNAME = ""
    MQTT_PASSWORD = ""
    MQTT_DEVICE_ID = "skylight"
    MQTT_DEVICE_NAME = "Skylight Dashboard"
    WS_PORT = 8766

# Create SSL context that doesn't verify certificates (for self-signed certs)
ssl_context = ssl.create_default_context()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE

# Global state for MQTT bridge
mqtt_client = None
websocket_clients = set()
websocket_loop = None  # Reference to WebSocket event loop for cross-thread communication
dashboard_state = {
    "state": "online",
    "screensaver_active": False,
    "camera_active": False,
    "current_tab": "calendar",
    "volume": 70,
    "uptime_seconds": 0
}
start_time = time.time()

# Screenshot storage
latest_screenshot = None  # Base64 PNG data
screenshot_timestamp = 0
screenshot_lock = threading.Lock()

# ==================== WEATHER CACHE DATABASE ====================

WEATHER_DB_PATH = os.path.join(os.path.dirname(__file__), 'weather_cache.db')

def init_weather_db():
    """Initialize SQLite database for weather cache"""
    conn = sqlite3.connect(WEATHER_DB_PATH)
    cursor = conn.cursor()
    
    # Daily forecast cache
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS daily_forecast (
            date TEXT PRIMARY KEY,
            high REAL,
            low REAL,
            high_c REAL,
            low_c REAL,
            condition TEXT,
            icon TEXT,
            precipitation_probability REAL,
            cached_at TEXT
        )
    ''')
    
    # Hourly forecast cache
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS hourly_forecast (
            datetime TEXT PRIMARY KEY,
            date TEXT,
            hour INTEGER,
            temp REAL,
            temp_c REAL,
            condition TEXT,
            icon TEXT,
            precipitation_probability REAL,
            cached_at TEXT
        )
    ''')
    
    # Clean up old data
    daily_cutoff = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d')
    hourly_cutoff = (datetime.now() - timedelta(days=14)).strftime('%Y-%m-%d')
    cursor.execute('DELETE FROM daily_forecast WHERE date < ?', (daily_cutoff,))
    cursor.execute('DELETE FROM hourly_forecast WHERE date < ?', (hourly_cutoff,))
    
    conn.commit()
    conn.close()
    print(f"Weather cache database initialized: {WEATHER_DB_PATH}")

def save_daily_forecast(forecasts):
    """Save daily forecasts to cache"""
    conn = sqlite3.connect(WEATHER_DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    for f in forecasts:
        cursor.execute('''
            INSERT OR REPLACE INTO daily_forecast 
            (date, high, low, high_c, low_c, condition, icon, precipitation_probability, cached_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ''', (
            f.get('date'),
            f.get('high'),
            f.get('low'),
            f.get('high_c'),
            f.get('low_c'),
            f.get('condition'),
            f.get('icon'),
            f.get('precipitation_probability'),
            now
        ))
    
    conn.commit()
    conn.close()

def save_hourly_forecast(forecasts):
    """Save hourly forecasts to cache"""
    conn = sqlite3.connect(WEATHER_DB_PATH)
    cursor = conn.cursor()
    now = datetime.now().isoformat()
    
    for f in forecasts:
        dt = f.get('datetime', '')
        if dt:
            try:
                dt_obj = datetime.fromisoformat(dt.replace('Z', '+00:00'))
                date_str = dt_obj.strftime('%Y-%m-%d')
                hour = dt_obj.hour
            except:
                continue
                
            cursor.execute('''
                INSERT OR REPLACE INTO hourly_forecast 
                (datetime, date, hour, temp, temp_c, condition, icon, precipitation_probability, cached_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (
                dt,
                date_str,
                hour,
                f.get('temperature'),
                f.get('temp_c'),
                f.get('condition'),
                f.get('icon'),
                f.get('precipitation_probability'),
                now
            ))
    
    conn.commit()
    conn.close()

def get_cached_daily_forecast():
    """Get all cached daily forecasts"""
    conn = sqlite3.connect(WEATHER_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM daily_forecast ORDER BY date')
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

def get_cached_hourly_forecast():
    """Get all cached hourly forecasts"""
    conn = sqlite3.connect(WEATHER_DB_PATH)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM hourly_forecast ORDER BY datetime')
    rows = cursor.fetchall()
    conn.close()
    
    return [dict(row) for row in rows]

# Initialize weather database on module load
init_weather_db()


# ==================== MQTT CLIENT ====================

class SkylightMQTTClient:
    """MQTT client for Home Assistant integration"""

    def __init__(self):
        self.client = None
        self.connected = False
        self.device_id = MQTT_DEVICE_ID
        self.device_name = MQTT_DEVICE_NAME
        self.base_topic = f"skylight/{self.device_id}"

    def connect(self):
        """Connect to MQTT broker"""
        try:
            import paho.mqtt.client as mqtt
        except ImportError:
            print("MQTT: paho-mqtt not installed. Run: pip install paho-mqtt")
            return False

        self.client = mqtt.Client(
            mqtt.CallbackAPIVersion.VERSION2,
            client_id=f"skylight_{self.device_id}"
        )

        # Set callbacks
        self.client.on_connect = self._on_connect
        self.client.on_disconnect = self._on_disconnect
        self.client.on_message = self._on_message

        # Set authentication if configured
        if MQTT_USERNAME and MQTT_PASSWORD:
            self.client.username_pw_set(MQTT_USERNAME, MQTT_PASSWORD)

        # Set Last Will Testament (LWT) for offline detection
        self.client.will_set(
            f"{self.base_topic}/availability",
            payload="offline",
            qos=1,
            retain=True
        )

        try:
            print(f"MQTT: Connecting to {MQTT_BROKER}:{MQTT_PORT}...")
            self.client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.client.loop_start()
            return True
        except Exception as e:
            print(f"MQTT: Connection failed - {e}")
            return False

    def _on_connect(self, client, userdata, flags, reason_code, properties):
        """Called when connected to broker"""
        if reason_code == 0:
            self.connected = True
            print(f"MQTT: Connected to broker at {MQTT_BROKER}")

            # Subscribe to command topic
            command_topic = f"{self.base_topic}/command"
            client.subscribe(command_topic)
            print(f"MQTT: Subscribed to {command_topic}")

            # Subscribe to HA discovery topics for control
            client.subscribe(f"{self.base_topic}/screen/set")
            client.subscribe(f"{self.base_topic}/volume/set")
            client.subscribe(f"{self.base_topic}/screenshot/take")
            # Publish availability
            client.publish(
                f"{self.base_topic}/availability",
                payload="online",
                qos=1,
                retain=True
            )

            # Publish Home Assistant discovery configs
            self._publish_ha_discovery()

            # Publish initial state
            self.publish_state()
        else:
            print(f"MQTT: Connection failed with code {reason_code}")

    def _on_disconnect(self, client, userdata, flags, reason_code, properties):
        """Called when disconnected from broker"""
        self.connected = False
        print(f"MQTT: Disconnected (code: {reason_code})")
        if reason_code != 0:
            print("MQTT: Unexpected disconnect, will auto-reconnect...")

    def _on_message(self, client, userdata, msg):
        """Handle incoming MQTT messages"""
        try:
            topic = msg.topic
            payload = msg.payload.decode('utf-8')
            print(f"MQTT: Received on {topic}: {payload}")

            # Handle command topic
            if topic == f"{self.base_topic}/command":
                self._handle_command(payload)
            # Handle screen switch
            elif topic == f"{self.base_topic}/screen/set":
                if payload.upper() == "ON":
                    self._handle_command('{"command": "wake"}')
                else:
                    self._handle_command('{"command": "screensaver", "enabled": true}')
            # Handle volume control
            elif topic == f"{self.base_topic}/volume/set":
                try:
                    volume = int(float(payload))
                    self._handle_command(f'{{"command": "volume", "value": {volume}}}')
                except ValueError:
                    print(f"MQTT: Invalid volume value: {payload}")
            # Handle screenshot button
            elif topic == f"{self.base_topic}/screenshot/take":
                self._request_screenshot()

        except Exception as e:
            print(f"MQTT: Error handling message - {e}")

    def _handle_command(self, payload):
        """Process command payload and forward to WebSocket clients"""
        global dashboard_state

        try:
            cmd = json.loads(payload)
            command = cmd.get('command', '')

            print(f"MQTT: Processing command: {command}")

            # Forward all other commands to browser via WebSocket
            if websocket_loop and websocket_clients:
                asyncio.run_coroutine_threadsafe(broadcast_to_websockets(payload), websocket_loop)

            # Update local state based on command
            if command == 'wake':
                dashboard_state['screensaver_active'] = False
                self.publish_state()
            elif command == 'screensaver':
                dashboard_state['screensaver_active'] = cmd.get('enabled', True)
                self.publish_state()
            elif command == 'navigate':
                dashboard_state['current_tab'] = cmd.get('tab', 'calendar')
                self.publish_state()
            elif command == 'volume':
                dashboard_state['volume'] = cmd.get('value', 70)
                self.publish_state()

        except json.JSONDecodeError:
            print(f"MQTT: Invalid JSON payload: {payload}")
        except Exception as e:
            print(f"MQTT: Error processing command - {e}")

    def _request_screenshot(self):
        """Request screenshot from browser via WebSocket"""
        print("MQTT: Requesting screenshot from browser...")
        if websocket_loop and websocket_clients:
            message = json.dumps({'type': 'screenshot_request'})
            asyncio.run_coroutine_threadsafe(broadcast_to_websockets(message), websocket_loop)
        else:
            print("MQTT: No WebSocket clients connected for screenshot")

    def _publish_ha_discovery(self):
        """Publish Home Assistant MQTT discovery configurations"""
        device_info = {
            "ids": [f"skylight_{self.device_id}"],
            "name": self.device_name,
            "mf": "Skylight Dashboard",
            "mdl": "Web Dashboard",
            "sw": "1.0.0"
        }

        # Switch: Screen Wake/Sleep
        screen_config = {
            "name": "Screen",
            "uniq_id": f"skylight_{self.device_id}_screen",
            "cmd_t": f"{self.base_topic}/screen/set",
            "stat_t": f"{self.base_topic}/state",
            "val_tpl": "{{ 'OFF' if value_json.screensaver_active else 'ON' }}",
            "avty_t": f"{self.base_topic}/availability",
            "dev": device_info,
            "ic": "mdi:monitor"
        }
        self.client.publish(
            f"homeassistant/switch/skylight_{self.device_id}/screen/config",
            json.dumps(screen_config),
            qos=1,
            retain=True
        )

        # Sensor: Dashboard State
        state_config = {
            "name": "State",
            "uniq_id": f"skylight_{self.device_id}_state",
            "stat_t": f"{self.base_topic}/state",
            "val_tpl": "{{ value_json.state }}",
            "json_attr_t": f"{self.base_topic}/state",
            "avty_t": f"{self.base_topic}/availability",
            "dev": device_info,
            "ic": "mdi:tablet-dashboard"
        }
        self.client.publish(
            f"homeassistant/sensor/skylight_{self.device_id}/state/config",
            json.dumps(state_config),
            qos=1,
            retain=True
        )

        # Sensor: Current Tab
        tab_config = {
            "name": "Current Tab",
            "uniq_id": f"skylight_{self.device_id}_tab",
            "stat_t": f"{self.base_topic}/state",
            "val_tpl": "{{ value_json.current_tab }}",
            "avty_t": f"{self.base_topic}/availability",
            "dev": device_info,
            "ic": "mdi:tab"
        }
        self.client.publish(
            f"homeassistant/sensor/skylight_{self.device_id}/tab/config",
            json.dumps(tab_config),
            qos=1,
            retain=True
        )

        # Number: Volume Control
        volume_config = {
            "name": "Volume",
            "uniq_id": f"skylight_{self.device_id}_volume",
            "cmd_t": f"{self.base_topic}/volume/set",
            "stat_t": f"{self.base_topic}/state",
            "val_tpl": "{{ value_json.volume }}",
            "min": 0,
            "max": 100,
            "step": 5,
            "unit_of_meas": "%",
            "avty_t": f"{self.base_topic}/availability",
            "dev": device_info,
            "ic": "mdi:volume-high"
        }
        self.client.publish(
            f"homeassistant/number/skylight_{self.device_id}/volume/config",
            json.dumps(volume_config),
            qos=1,
            retain=True
        )

        # Binary Sensor: Camera Active
        camera_config = {
            "name": "Camera Active",
            "uniq_id": f"skylight_{self.device_id}_camera",
            "stat_t": f"{self.base_topic}/state",
            "val_tpl": "{{ 'ON' if value_json.camera_active else 'OFF' }}",
            "avty_t": f"{self.base_topic}/availability",
            "dev": device_info,
            "dev_cla": "running",
            "ic": "mdi:cctv"
        }
        self.client.publish(
            f"homeassistant/binary_sensor/skylight_{self.device_id}/camera/config",
            json.dumps(camera_config),
            qos=1,
            retain=True
        )

        # Camera: Screenshot
        screenshot_config = {
            "name": "Screenshot",
            "unique_id": f"skylight_{self.device_id}_screenshot",
            "topic": f"{self.base_topic}/screenshot",
            "availability_topic": f"{self.base_topic}/availability",
            "device": device_info,
            "icon": "mdi:monitor-screenshot"
        }
        self.client.publish(
            f"homeassistant/camera/skylight_{self.device_id}/screenshot/config",
            json.dumps(screenshot_config),
            qos=1,
            retain=True
        )

        # Button: Take Screenshot
        screenshot_btn_config = {
            "name": "Take Screenshot",
            "uniq_id": f"skylight_{self.device_id}_take_screenshot",
            "cmd_t": f"{self.base_topic}/screenshot/take",
            "avty_t": f"{self.base_topic}/availability",
            "dev": device_info,
            "ic": "mdi:camera"
        }
        self.client.publish(
            f"homeassistant/button/skylight_{self.device_id}/take_screenshot/config",
            json.dumps(screenshot_btn_config),
            qos=1,
            retain=True
        )

        print("MQTT: Published Home Assistant discovery configs")

    def publish_state(self):
        """Publish current dashboard state"""
        if not self.connected:
            return

        global dashboard_state
        dashboard_state['uptime_seconds'] = int(time.time() - start_time)

        self.client.publish(
            f"{self.base_topic}/state",
            json.dumps(dashboard_state),
            qos=0,
            retain=True
        )

    def update_state(self, updates):
        """Update dashboard state from WebSocket client"""
        global dashboard_state
        dashboard_state.update(updates)
        self.publish_state()

    def disconnect(self):
        """Gracefully disconnect from broker"""
        if self.client and self.connected:
            self.client.publish(
                f"{self.base_topic}/availability",
                payload="offline",
                qos=1,
                retain=True
            )
            self.client.loop_stop()
            self.client.disconnect()
            print("MQTT: Disconnected gracefully")

    def publish_screenshot(self, image_data):
        """Publish screenshot to MQTT as camera image"""
        if not self.connected:
            return
        
        # Publish to camera topic (raw base64 data without the data:image/png;base64, prefix)
        if image_data.startswith('data:'):
            image_data = image_data.split(',', 1)[1]
        
        import base64
        try:
            # Decode and republish as raw bytes for HA camera
            image_bytes = base64.b64decode(image_data)
            self.client.publish(
                f"{self.base_topic}/screenshot",
                payload=image_bytes,
                qos=0,
                retain=True
            )
            print(f"MQTT: Published screenshot ({len(image_bytes)} bytes)")
        except Exception as e:
            print(f"MQTT: Failed to publish screenshot - {e}")

    def publish_camera_discovery(self):
        """Publish MQTT discovery for screenshot camera"""
        camera_config = {
            "name": "Screenshot",
            "unique_id": f"skylight_{self.device_id}_screenshot",
            "topic": f"{self.base_topic}/camera/image",
            "device": self.device_info,
            "availability_topic": f"{self.base_topic}/availability",
            "icon": "mdi:monitor-screenshot"
        }
        self.client.publish(
            f"homeassistant/camera/skylight_{self.device_id}/screenshot/config",
            json.dumps(camera_config),
            qos=1,
            retain=True
        )
        print("MQTT: Published screenshot camera discovery")


# ==================== HOME ASSISTANT WEBSOCKET SUBSCRIPTION ====================

class HAWebSocketClient:
    """WebSocket client for subscribing to Home Assistant real-time events"""

    def __init__(self):
        self.ws = None
        self.connected = False
        self.authenticated = False
        self.message_id = 0
        self.subscriptions = {}
        self.reconnect_delay = 5
        self.running = False

    async def connect(self):
        """Connect to Home Assistant WebSocket API"""
        try:
            import websockets
        except ImportError:
            print("HA-WS: websockets not installed. Run: pip install websockets")
            return False

        # Convert HTTP URL to WebSocket URL
        ws_url = HA_URL.replace('https://', 'wss://').replace('http://', 'ws://')
        ws_url = f"{ws_url}/api/websocket"

        print(f"HA-WS: Connecting to {ws_url}...")

        try:
            # Create SSL context for self-signed certs
            import ssl
            ssl_ctx = ssl.create_default_context()
            ssl_ctx.check_hostname = False
            ssl_ctx.verify_mode = ssl.CERT_NONE

            self.ws = await websockets.connect(
                ws_url,
                ssl=ssl_ctx,
                ping_interval=30,
                ping_timeout=10
            )
            self.connected = True
            print("HA-WS: Connected")
            return True
        except Exception as e:
            print(f"HA-WS: Connection failed - {e}")
            return False

    async def authenticate(self):
        """Authenticate with Home Assistant"""
        if not self.ws:
            return False

        try:
            # Wait for auth_required message
            msg = await asyncio.wait_for(self.ws.recv(), timeout=10)
            data = json.loads(msg)

            if data.get('type') != 'auth_required':
                print(f"HA-WS: Unexpected message: {data}")
                return False

            # Send authentication
            await self.ws.send(json.dumps({
                'type': 'auth',
                'access_token': HA_TOKEN
            }))

            # Wait for auth response
            msg = await asyncio.wait_for(self.ws.recv(), timeout=10)
            data = json.loads(msg)

            if data.get('type') == 'auth_ok':
                self.authenticated = True
                print(f"HA-WS: Authenticated (HA version: {data.get('ha_version', 'unknown')})")
                return True
            else:
                print(f"HA-WS: Authentication failed: {data}")
                return False

        except Exception as e:
            print(f"HA-WS: Authentication error - {e}")
            return False

    def get_next_id(self):
        """Get next message ID"""
        self.message_id += 1
        return self.message_id

    async def subscribe_events(self, event_type=None):
        """Subscribe to Home Assistant events"""
        if not self.authenticated:
            return False

        msg_id = self.get_next_id()
        subscription = {
            'id': msg_id,
            'type': 'subscribe_events'
        }
        if event_type:
            subscription['event_type'] = event_type

        await self.ws.send(json.dumps(subscription))
        
        # Wait for confirmation
        msg = await asyncio.wait_for(self.ws.recv(), timeout=10)
        data = json.loads(msg)
        
        if data.get('success'):
            self.subscriptions[msg_id] = event_type or 'all'
            print(f"HA-WS: Subscribed to {event_type or 'all events'} (id: {msg_id})")
            return True
        else:
            print(f"HA-WS: Subscription failed: {data}")
            return False

    async def subscribe_to_calendar_events(self):
        """Subscribe to calendar-specific events"""
        # Try subscribing to various calendar event types
        calendar_events = [
            'calendar_event_created',
            'calendar_event_deleted', 
            'calendar_event_updated',
            'service_executed',  # Catch calendar.create_event calls
        ]
        for event_type in calendar_events:
            try:
                msg_id = self.get_next_id()
                await self.ws.send(json.dumps({
                    'id': msg_id,
                    'type': 'subscribe_events',
                    'event_type': event_type
                }))
                msg = await asyncio.wait_for(self.ws.recv(), timeout=5)
                data = json.loads(msg)
                if data.get('success'):
                    print(f"HA-WS: Subscribed to {event_type}")
            except Exception as e:
                pass  # Event type might not exist

    async def subscribe_to_notification_events(self):
        """Subscribe to persistent notification events (HA 2025+)"""
        notification_events = [
            'persistent_notification_updated',
            'persistent_notification_created', 
            'persistent_notification_removed',
        ]
        for event_type in notification_events:
            try:
                msg_id = self.get_next_id()
                await self.ws.send(json.dumps({
                    'id': msg_id,
                    'type': 'subscribe_events',
                    'event_type': event_type
                }))
                msg = await asyncio.wait_for(self.ws.recv(), timeout=5)
                data = json.loads(msg)
                if data.get('success'):
                    print(f"HA-WS: Subscribed to {event_type}")
            except Exception as e:
                pass  # Event type might not exist

    async def listen(self):
        """Listen for events and forward to browser clients"""
        if not self.ws:
            return

        self.running = True
        print("HA-WS: Listening for events...")

        while self.running:
            try:
                msg = await asyncio.wait_for(self.ws.recv(), timeout=60)
                data = json.loads(msg)

                if data.get('type') == 'event':
                    await self.handle_event(data.get('event', {}))

            except asyncio.TimeoutError:
                # Send a ping to keep connection alive
                try:
                    pong = await self.ws.ping()
                    await asyncio.wait_for(pong, timeout=10)
                except:
                    print("HA-WS: Connection lost, reconnecting...")
                    break

            except Exception as e:
                print(f"HA-WS: Error receiving message - {e}")
                break

        self.connected = False
        self.authenticated = False

    async def handle_event(self, event):
        """Process incoming HA event and forward to browsers"""
        event_type = event.get('event_type', '')
        event_data = event.get('data', {})
        
        # Debug: Log notification-related events and entity changes
        if 'notification' in event_type.lower() or 'notification' in str(event_data).lower():
            print(f"HA-WS DEBUG: Notification-related event: {event_type}")
            print(f"HA-WS DEBUG: Data: {event_data}")

        # Filter and forward relevant events
        entity_id = event_data.get('entity_id', '') or event_data.get('new_state', {}).get('entity_id', '')

        # Determine if this event should be forwarded
        forward = False
        event_category = None

        if event_type == 'state_changed':
            new_state = event_data.get('new_state', {})
            old_state = event_data.get('old_state', {})
            
            # Skip if no actual change
            if new_state and old_state and new_state.get('state') == old_state.get('state'):
                return

            # Categorize the event
            if entity_id.startswith('persistent_notification.'):
                forward = True
                event_category = 'notification'
            elif entity_id.startswith('sensor.mail_'):
                forward = True
                event_category = 'mail'
            elif entity_id.startswith('calendar.'):
                forward = True
                event_category = 'calendar'
            elif entity_id.startswith('todo.'):
                forward = True
                event_category = 'todo'
            elif entity_id.startswith('weather.'):
                forward = True
                event_category = 'weather'
            elif entity_id.startswith('binary_sensor.') and ('door' in entity_id or 'motion' in entity_id or 'doorbell' in entity_id):
                forward = True
                event_category = 'sensor'
            elif entity_id.startswith('switch.') or entity_id.startswith('light.'):
                forward = True
                event_category = 'control'
            elif entity_id.startswith('sensor.islamic_prayer'):
                forward = True
                event_category = 'prayer'

        elif event_type == 'persistent_notification_created':
            forward = True
            event_category = 'notification'
            print(f"HA-WS: Notification created - {event_data}")
        elif event_type == 'persistent_notification_removed':
            forward = True
            event_category = 'notification'
            print(f"HA-WS: Notification removed - {event_data}")
        elif event_type == 'persistent_notification_updated':
            forward = True
            event_category = 'notification'
            print(f"HA-WS: Notification updated - {event_data}")
        elif event_type in ['calendar_event_created', 'calendar_event_deleted', 'calendar_event_updated']:
            forward = True
            event_category = 'calendar'
        elif event_type == 'call_service':
            # Check if it's a notification service call
            # NOTE: Do NOT forward calendar call_service events - they create a feedback loop
            # (dashboard calls get_events -> HA fires call_service -> server broadcasts -> dashboard reloads -> repeat)
            # Calendar changes are already caught by calendar_event_created/deleted/updated events
            service_data = event_data.get('service_data', {})
            domain = event_data.get('domain', '')
            if domain == 'persistent_notification':
                forward = True
                event_category = 'notification'
                print(f"HA-WS: Notification service called - {event_data.get('service')}")

        # Forward to browser clients
        if forward and websocket_clients:
            message = json.dumps({
                'type': 'ha_event',
                'category': event_category,
                'event_type': event_type,
                'entity_id': entity_id,
                'data': event_data,
                'version': DASHBOARD_VERSION
            })
            print(f"HA-WS: Broadcasting {event_category} event to {len(websocket_clients)} clients")
            await broadcast_to_websockets(message)

    async def disconnect(self):
        """Disconnect from Home Assistant"""
        self.running = False
        if self.ws:
            await self.ws.close()
            print("HA-WS: Disconnected")


async def run_ha_websocket():
    """Run the HA WebSocket client with auto-reconnect"""
    ha_ws = HAWebSocketClient()

    while True:
        try:
            if await ha_ws.connect():
                if await ha_ws.authenticate():
                    # Subscribe to state changes
                    await ha_ws.subscribe_events('state_changed')
                    # Subscribe to call_service events (for notifications in HA 2025+)
                    await ha_ws.subscribe_events('call_service')
                    # Subscribe to calendar-specific events
                    await ha_ws.subscribe_to_calendar_events()
                    # Subscribe to notification events (HA 2025+)
                    await ha_ws.subscribe_to_notification_events()
                    # Listen for events
                    await ha_ws.listen()
        except Exception as e:
            print(f"HA-WS: Error - {e}")

        # Reconnect after delay
        print(f"HA-WS: Reconnecting in {ha_ws.reconnect_delay} seconds...")
        await asyncio.sleep(ha_ws.reconnect_delay)


def start_ha_websocket_thread():
    """Start HA WebSocket client in a background thread"""
    def run():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(run_ha_websocket())
        except Exception as e:
            print(f"HA-WS: Thread error - {e}")

    thread = threading.Thread(target=run, daemon=True)
    thread.start()
    print("HA-WS: Background subscription thread started")


# ==================== WEBSOCKET SERVER ====================

async def websocket_handler(websocket):
    """Handle WebSocket connections from browser"""
    global websocket_clients

    websocket_clients.add(websocket)
    print(f"WebSocket: Client connected ({len(websocket_clients)} total)")

    try:
        async for message in websocket:
            try:
                data = json.loads(message)
                msg_type = data.get('type', '')

                if msg_type == 'state_update':
                    # Browser reporting state change
                    if mqtt_client and mqtt_client.connected:
                        mqtt_client.update_state(data.get('state', {}))

                elif msg_type == 'ping':
                    await websocket.send(json.dumps({'type': 'pong', 'version': DASHBOARD_VERSION}))

                elif msg_type == 'screenshot_data':
                    # Browser sending screenshot data
                    global latest_screenshot, screenshot_timestamp
                    with screenshot_lock:
                        latest_screenshot = data.get('image', '')
                        screenshot_timestamp = time.time()
                    print(f"Screenshot: Received ({len(latest_screenshot)} bytes)")
                    # Publish to MQTT if connected
                    if mqtt_client and mqtt_client.connected:
                        mqtt_client.publish_screenshot(latest_screenshot)

            except json.JSONDecodeError:
                print(f"WebSocket: Invalid JSON: {message}")

    except Exception as e:
        print(f"WebSocket: Connection error - {e}")
    finally:
        websocket_clients.discard(websocket)
        print(f"WebSocket: Client disconnected ({len(websocket_clients)} remaining)")


async def broadcast_to_websockets(message):
    """Send message to all connected WebSocket clients"""
    if not websocket_clients:
        return

    disconnected = set()
    for ws in websocket_clients:
        try:
            await ws.send(message)
        except Exception:
            disconnected.add(ws)

    websocket_clients.difference_update(disconnected)


async def start_websocket_server():
    """Start the WebSocket server"""
    try:
        import websockets
    except ImportError:
        print("WebSocket: websockets not installed. Run: pip install websockets")
        return

    print(f"WebSocket: Starting server on ws://0.0.0.0:{WS_PORT}")
    async with websockets.serve(
        websocket_handler,
        "0.0.0.0",  # Bind to all interfaces for network access
        WS_PORT,
        ping_interval=30,
        ping_timeout=10
    ):
        await asyncio.Future()  # Run forever


def run_websocket_server():
    """Run WebSocket server in a thread"""
    global websocket_loop
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)
    websocket_loop = loop  # Store reference for cross-thread communication
    try:
        loop.run_until_complete(start_websocket_server())
    except Exception as e:
        print(f"WebSocket: Server error - {e}")


# ==================== HTTP SERVER ====================

class ProxyHandler(http.server.SimpleHTTPRequestHandler):
    def do_GET(self):
        if self.path.startswith('/api/local/browse'):
            self.handle_folder_browse()
        elif self.path.startswith('/api/local/'):
            self.handle_local_request()
        elif self.path.startswith('/api/synology/'):
            self.proxy_synology_request()
        elif self.path == '/api/notifications':
            self.handle_notifications_request()
        elif self.path == '/api/screenshot':
            self.handle_screenshot_request()
        elif self.path == '/api/screenshot/take':
            self.handle_take_screenshot()
        elif self.path == '/api/weather/cache':
            self.handle_get_weather_cache()
        elif self.path.startswith('/api/habits'):
            self.handle_habits_request()
        elif self.path.startswith('/api/'):
            self.proxy_request('GET')
        else:
            super().do_GET()

    def handle_get_weather_cache(self):
        """Return cached weather data"""
        try:
            data = {
                'daily': get_cached_daily_forecast(),
                'hourly': get_cached_hourly_forecast()
            }
            response = json.dumps(data).encode()
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', len(response))
            self.end_headers()
            self.wfile.write(response)
        except Exception as e:
            self.send_error(500, f'Error getting weather cache: {e}')

    def handle_screenshot_request(self):
        """Serve the latest screenshot"""
        global latest_screenshot, screenshot_timestamp
        with screenshot_lock:
            if latest_screenshot:
                import base64
                try:
                    # Strip data URL prefix if present
                    image_data = latest_screenshot
                    if image_data.startswith('data:'):
                        image_data = image_data.split(',', 1)[1]
                    image_bytes = base64.b64decode(image_data)
                    
                    self.send_response(200)
                    self.send_header('Content-Type', 'image/png')
                    self.send_header('Content-Length', len(image_bytes))
                    self.send_header('X-Screenshot-Timestamp', str(screenshot_timestamp))
                    self.end_headers()
                    self.wfile.write(image_bytes)
                except Exception as e:
                    self.send_error(500, f'Error decoding screenshot: {e}')
            else:
                self.send_error(404, 'No screenshot available')

    def handle_take_screenshot(self):
        """Request a new screenshot and return it"""
        if mqtt_client:
            mqtt_client._request_screenshot()
        # Return immediately - screenshot will be available via /api/screenshot
        self.send_response(202)
        self.send_header('Content-Type', 'application/json')
        self.end_headers()
        self.wfile.write(json.dumps({'status': 'requested'}).encode())

    def handle_notifications_request(self):
        """Fetch persistent notifications via HA WebSocket API"""
        try:
            import asyncio
            import websockets
            
            async def get_notifications():
                uri = f"wss://{HA_URL.replace('https://', '')}/api/websocket"
                ssl_ctx = ssl.create_default_context()
                ssl_ctx.check_hostname = False
                ssl_ctx.verify_mode = ssl.CERT_NONE
                
                async with websockets.connect(uri, ssl=ssl_ctx) as ws:
                    await ws.recv()  # auth_required
                    await ws.send(json.dumps({
                        "type": "auth",
                        "access_token": HA_TOKEN
                    }))
                    await ws.recv()  # auth_ok
                    
                    # Get persistent notifications
                    await ws.send(json.dumps({
                        "id": 1,
                        "type": "persistent_notification/get"
                    }))
                    result = await ws.recv()
                    data = json.loads(result)
                    return data.get('result', [])
            
            # Run in new event loop (since we're in a sync handler)
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            try:
                notifications = loop.run_until_complete(get_notifications())
            finally:
                loop.close()
            
            self.send_json_response({'success': True, 'notifications': notifications})
        except Exception as e:
            print(f"Error fetching notifications: {e}")
            self.send_json_response({'success': False, 'error': str(e)})

    def do_POST(self):
        if self.path == '/api/weather/cache/daily':
            self.handle_save_daily_forecast()
        elif self.path == '/api/weather/cache/hourly':
            self.handle_save_hourly_forecast()
        elif self.path.startswith('/api/habits'):
            self.handle_habits_request()
        elif self.path.startswith('/api/'):
            self.proxy_request('POST')
        else:
            self.send_error(405, "Method Not Allowed")

    def do_DELETE(self):
        if self.path.startswith('/api/habits'):
            self.handle_habits_request()
        else:
            self.send_error(405, "Method Not Allowed")

    def handle_save_daily_forecast(self):
        """Save daily forecast to cache"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            forecasts = data.get('forecasts', [])
            save_daily_forecast(forecasts)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'saved': len(forecasts)}).encode())
        except Exception as e:
            self.send_error(500, f'Error saving daily forecast: {e}')

    def handle_save_hourly_forecast(self):
        """Save hourly forecast to cache"""
        try:
            content_length = int(self.headers.get('Content-Length', 0))
            body = self.rfile.read(content_length)
            data = json.loads(body)
            forecasts = data.get('forecasts', [])
            save_hourly_forecast(forecasts)
            
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.end_headers()
            self.wfile.write(json.dumps({'status': 'ok', 'saved': len(forecasts)}).encode())
        except Exception as e:
            self.send_error(500, f'Error saving hourly forecast: {e}')

    def proxy_request(self, method):
        try:
            # Read request body for POST
            body = None
            if method == 'POST':
                content_length = int(self.headers.get('Content-Length', 0))
                body = self.rfile.read(content_length)

            # Build request to Home Assistant
            url = f"{HA_URL}{self.path}"
            req = urllib.request.Request(url, data=body, method=method)
            req.add_header('Authorization', f'Bearer {HA_TOKEN}')
            req.add_header('Content-Type', 'application/json')

            # Make request
            with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
                data = response.read()

                # Send response
                self.send_response(200)
                self.send_header('Content-Type', 'application/json')
                self.send_header('Access-Control-Allow-Origin', '*')
                self.send_header('Cache-Control', 'no-cache, no-store, must-revalidate')
                self.send_header('X-Dashboard-Version', DASHBOARD_VERSION)
                self.end_headers()
                self.wfile.write(data)

        except urllib.error.HTTPError as e:
            self.send_error(e.code, str(e.reason))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_folder_browse(self):
        """Handle folder browsing for photo source selection"""
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            current_path = params.get('path', [''])[0]

            # Default starting locations
            if not current_path:
                current_path = os.path.expanduser('~')

            # Normalize and resolve the path
            current_path = os.path.abspath(os.path.expanduser(current_path))

            # Check if path exists
            if not os.path.exists(current_path):
                self.send_json_response({
                    'success': False,
                    'error': f'Path does not exist: {current_path}'
                })
                return

            # If it's a file, go to parent directory
            if os.path.isfile(current_path):
                current_path = os.path.dirname(current_path)

            # Get parent path
            parent_path = os.path.dirname(current_path)

            # List directories and check for images
            entries = []
            has_images = False
            image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
            image_count = 0

            try:
                for entry in sorted(os.scandir(current_path), key=lambda e: e.name.lower()):
                    if entry.name.startswith('.'):
                        continue  # Skip hidden files/folders

                    if entry.is_dir():
                        # Check if directory is accessible
                        try:
                            os.listdir(entry.path)
                            entries.append({
                                'name': entry.name,
                                'path': entry.path,
                                'type': 'directory'
                            })
                        except PermissionError:
                            entries.append({
                                'name': entry.name,
                                'path': entry.path,
                                'type': 'directory',
                                'locked': True
                            })
                    elif entry.is_file():
                        ext = os.path.splitext(entry.name)[1].lower()
                        if ext in image_extensions:
                            has_images = True
                            image_count += 1
            except PermissionError:
                self.send_json_response({
                    'success': False,
                    'error': f'Permission denied: {current_path}'
                })
                return

            # Common mount points to show as quick links
            quick_links = []
            common_paths = [
                (os.path.expanduser('~'), 'Home'),
                (os.path.expanduser('~/Pictures'), 'Pictures'),
                (os.path.expanduser('~/Photos'), 'Photos'),
                ('/mnt', 'Mounts'),
                ('/media', 'Media'),
            ]
            for path, name in common_paths:
                if os.path.isdir(path):
                    quick_links.append({'name': name, 'path': path})

            self.send_json_response({
                'success': True,
                'current_path': current_path,
                'parent_path': parent_path if parent_path != current_path else None,
                'entries': entries,
                'has_images': has_images,
                'image_count': image_count,
                'quick_links': quick_links
            })

        except Exception as e:
            print(f"Folder browse error: {e}")
            self.send_json_response({
                'success': False,
                'error': str(e)
            })

    def handle_local_request(self):
        """Handle local folder photo requests"""
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            folder_path = params.get('path', [''])[0]

            if '/api/local/photos' in self.path:
                # List photos - CACHE FIRST to avoid blocking on slow NAS
                photos = []
                from_cache = False
                
                # Check if we have a valid cache (less than 1 hour old)
                cached_photos = self.get_cached_photo_list(folder_path)
                cache_file = os.path.join(PHOTO_CACHE_DIR, 'photo_list.json')
                cache_fresh = False
                if os.path.exists(cache_file):
                    cache_age = time.time() - os.path.getmtime(cache_file)
                    cache_fresh = cache_age < 86400  # 24 hours - avoid hitting NAS
                
                if cached_photos and cache_fresh:
                    # Use cache - don't hit NAS at all
                    photos = cached_photos
                    from_cache = True
                    print(f"Serving {len(photos)} photos from fresh cache")
                else:
                    # Cache is stale or missing - try to refresh from source
                    # But use a timeout to avoid blocking
                    source_available = folder_path and os.path.isdir(folder_path)
                    
                    if source_available:
                        image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
                        try:
                            for entry in os.scandir(folder_path):
                                if entry.is_file():
                                    ext = os.path.splitext(entry.name)[1].lower()
                                    if ext in image_extensions:
                                        stat = entry.stat()
                                        photos.append({
                                            'name': entry.name,
                                            'path': entry.path,
                                            'mtime': stat.st_mtime,
                                            'size': stat.st_size
                                        })
                            # Sort by modification time (newest first)
                            photos.sort(key=lambda x: x['mtime'], reverse=True)
                            # Save photo list to cache
                            self.save_photo_list_cache(folder_path, photos)
                            print(f"Refreshed photo list: {len(photos)} photos")
                        except (PermissionError, OSError) as e:
                            print(f"Source folder error: {e}, using stale cache")
                            source_available = False
                    
                    if not source_available or not photos:
                        # Fall back to stale cache
                        if cached_photos:
                            photos = cached_photos
                            from_cache = True
                            print(f"Serving {len(photos)} photos from stale cache")
                        else:
                            self.send_json_response({'success': False, 'error': 'Folder unavailable and no cache'})
                            return

                self.send_json_response({'success': True, 'photos': photos, 'cached': from_cache})

            elif '/api/local/image' in self.path:
                # Serve image file - CACHE FIRST to avoid blocking on slow NAS
                image_path = params.get('path', [''])[0]

                if not image_path:
                    self.send_error(404, "Image not found")
                    return

                # Determine content type
                ext = os.path.splitext(image_path)[1].lower()
                content_types = {
                    '.jpg': 'image/jpeg',
                    '.jpeg': 'image/jpeg',
                    '.png': 'image/png',
                    '.gif': 'image/gif',
                    '.webp': 'image/webp',
                    '.bmp': 'image/bmp'
                }
                content_type = content_types.get(ext, 'application/octet-stream')

                # ALWAYS try cache first (even stale) - NAS access can block
                data = self.get_cached_photo(image_path, ignore_age=True)
                
                if data is not None:
                    # Serve from cache immediately
                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', len(data))
                    self.send_header('Cache-Control', 'public, max-age=86400')
                    self.send_header('X-Cache', 'HIT')
                    self.end_headers()
                    self.wfile.write(data)
                    return
                
                # Not in cache - must read from source (may block)
                if not os.path.isfile(image_path):
                    self.send_error(404, "Image not found and not cached")
                    return
                
                try:
                    real_path = os.path.realpath(image_path)
                    with open(real_path, 'rb') as f:
                        data = f.read()
                    # Cache the photo for future use
                    self.cache_photo(image_path, data)
                    
                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', len(data))
                    self.send_header('Cache-Control', 'public, max-age=86400')
                    self.send_header('X-Cache', 'MISS')
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as e:
                    self.send_error(500, f"Cannot read image: {e}")
                    return

            else:
                self.send_error(404, "Local endpoint not found")

        except Exception as e:
            print(f"Local request error: {e}")
            self.send_error(500, str(e))

    def get_cache_path(self, image_path):
        """Get the cache file path for an image"""
        # Create a hash of the full path for the cache filename
        path_hash = hashlib.md5(image_path.encode()).hexdigest()
        ext = os.path.splitext(image_path)[1].lower()
        return os.path.join(PHOTO_CACHE_DIR, f"{path_hash}{ext}")

    def save_photo_list_cache(self, folder_path, photos):
        """Save photo list to cache for offline fallback"""
        try:
            os.makedirs(PHOTO_CACHE_DIR, exist_ok=True)
            cache_file = os.path.join(PHOTO_CACHE_DIR, 'photo_list.json')
            # Update paths to point to cache versions
            cached_list = []
            for photo in photos:
                cached_list.append({
                    'name': photo['name'],
                    'path': photo['path'],  # Original path
                    'cache_path': self.get_cache_path(photo['path']),
                    'mtime': photo['mtime'],
                    'size': photo['size']
                })
            with open(cache_file, 'w') as f:
                json.dump({'folder': folder_path, 'photos': cached_list}, f)
        except Exception as e:
            print(f"Error saving photo list cache: {e}")

    def get_cached_photo_list(self, folder_path):
        """Get photo list from cache, only including photos that are actually cached"""
        try:
            cache_file = os.path.join(PHOTO_CACHE_DIR, 'photo_list.json')
            if not os.path.exists(cache_file):
                return None
            
            with open(cache_file, 'r') as f:
                data = json.load(f)
            
            # Only return photos that are actually cached locally
            cached_photos = []
            for photo in data.get('photos', []):
                cache_path = photo.get('cache_path') or self.get_cache_path(photo['path'])
                if os.path.exists(cache_path):
                    # Return with original path (image handler will serve from cache)
                    cached_photos.append({
                        'name': photo['name'],
                        'path': photo['path'],
                        'mtime': photo.get('mtime', 0),
                        'size': photo.get('size', 0)
                    })
            
            return cached_photos if cached_photos else None
        except Exception as e:
            print(f"Error reading photo list cache: {e}")
            return None

    def get_cached_photo(self, image_path, ignore_age=False):
        """Get photo from cache if available and fresh"""
        try:
            cache_path = self.get_cache_path(image_path)
            if not os.path.exists(cache_path):
                return None
            
            # Check if cache is fresh (unless ignoring age)
            if not ignore_age:
                cache_age = time.time() - os.path.getmtime(cache_path)
                if cache_age > PHOTO_CACHE_MAX_AGE:
                    return None
            
            with open(cache_path, 'rb') as f:
                return f.read()
        except Exception as e:
            print(f"Cache read error: {e}")
            return None

    def cache_photo(self, image_path, data):
        """Save photo to local cache"""
        try:
            # Ensure cache directory exists
            os.makedirs(PHOTO_CACHE_DIR, exist_ok=True)
            
            cache_path = self.get_cache_path(image_path)
            with open(cache_path, 'wb') as f:
                f.write(data)
            print(f"Cached: {os.path.basename(image_path)}")
        except Exception as e:
            print(f"Cache write error: {e}")

    def send_json_response(self, data):
        """Helper to send JSON response"""
        response = json.dumps(data).encode('utf-8')
        self.send_response(200)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Access-Control-Allow-Origin', '*')
        self.end_headers()
        self.wfile.write(response)

    def proxy_synology_request(self):
        """Proxy requests to Synology Photos API"""
        try:
            # Parse the request path and query parameters
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)

            base_url = params.get('baseUrl', [''])[0]
            passphrase = params.get('passphrase', [''])[0]

            if not base_url or not passphrase:
                self.send_error(400, "Missing baseUrl or passphrase")
                return

            if '/api/synology/photos' in self.path:
                # List photos from shared album
                api_url = f"{base_url}/webapi/entry.cgi"
                query_params = urllib.parse.urlencode({
                    'api': 'SYNO.Foto.Browse.Item',
                    'version': '1',
                    'method': 'list',
                    'passphrase': passphrase,
                    'additional': '["thumbnail","resolution","orientation","gps"]',
                    'offset': '0',
                    'limit': '500'
                })
                full_url = f"{api_url}?{query_params}"

                req = urllib.request.Request(full_url)
                with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
                    data = response.read()

                    self.send_response(200)
                    self.send_header('Content-Type', 'application/json')
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.end_headers()
                    self.wfile.write(data)

            elif '/api/synology/thumbnail' in self.path:
                # Get thumbnail/image
                photo_id = params.get('id', [''])[0]
                size = params.get('size', ['xl'])[0]

                if not photo_id:
                    self.send_error(400, "Missing photo id")
                    return

                # Synology thumbnail sizes: sm, m, xl
                api_url = f"{base_url}/webapi/entry.cgi"
                query_params = urllib.parse.urlencode({
                    'api': 'SYNO.Foto.Thumbnail',
                    'version': '2',
                    'method': 'get',
                    'id': photo_id,
                    'cache_key': photo_id,
                    'size': size,
                    'passphrase': passphrase
                })
                full_url = f"{api_url}?{query_params}"

                req = urllib.request.Request(full_url)
                with urllib.request.urlopen(req, context=ssl_context, timeout=30) as response:
                    data = response.read()
                    content_type = response.headers.get('Content-Type', 'image/jpeg')

                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Access-Control-Allow-Origin', '*')
                    self.send_header('Cache-Control', 'public, max-age=86400')
                    self.end_headers()
                    self.wfile.write(data)

            else:
                self.send_error(404, "Synology endpoint not found")

        except urllib.error.HTTPError as e:
            self.send_error(e.code, str(e.reason))
        except Exception as e:
            print(f"Synology proxy error: {e}")
            self.send_error(500, str(e))

    def do_OPTIONS(self):
        self.send_response(200)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def handle_habits_request(self):
        """Handle all habits API requests"""
        try:
            parsed = urllib.parse.urlparse(self.path)
            path_parts = parsed.path.split('/')
            params = urllib.parse.parse_qs(parsed.query)
            
            # GET /api/habits - List all habits with today's status
            if self.command == 'GET' and parsed.path == '/api/habits':
                habits = get_habits()
                today = datetime.now().strftime('%Y-%m-%d')
                completions_today = get_completions(start_date=today, end_date=today)
                completed_ids = {c['habit_id'] for c in completions_today}
                
                # Add completion status and stats to each habit
                for habit in habits:
                    habit['completed_today'] = habit['id'] in completed_ids
                    stats = get_habit_stats(habit['id'], days=30)
                    habit['stats'] = stats
                    
                    # Parse schedule_data if it's JSON
                    if habit['schedule_data']:
                        try:
                            habit['schedule_data'] = json.loads(habit['schedule_data'])
                        except:
                            pass
                
                self.send_json_response({'habits': habits})
                return
            
            # GET /api/habits/stats - Get stats for all habits
            if self.command == 'GET' and parsed.path == '/api/habits/stats':
                habits = get_habits()
                stats = {}
                for habit in habits:
                    stats[habit['id']] = get_habit_stats(habit['id'], days=30)
                self.send_json_response({'stats': stats})
                return
            
            # GET /api/habits/completions - Get completion history
            if self.command == 'GET' and parsed.path == '/api/habits/completions':
                habit_id = params.get('habit_id', [None])[0]
                start_date = params.get('start', [None])[0]
                end_date = params.get('end', [None])[0]
                completions = get_completions(
                    habit_id=int(habit_id) if habit_id else None,
                    start_date=start_date,
                    end_date=end_date
                )
                self.send_json_response({'completions': completions})
                return
            
            # POST /api/habits - Create new habit
            if self.command == 'POST' and parsed.path == '/api/habits':
                content_length = int(self.headers.get('Content-Length', 0))
                body = json.loads(self.rfile.read(content_length))
                
                habit_id = create_habit(
                    name=body['name'],
                    person=body.get('person', 'Everyone'),
                    schedule_type=body.get('schedule_type', 'daily'),
                    schedule_data=body.get('schedule_data'),
                    icon=body.get('icon', '✓'),
                    category=body.get('category', 'general')
                )
                self.send_json_response({'success': True, 'id': habit_id})
                return
            
            # POST /api/habits/{id}/complete - Mark habit complete
            if self.command == 'POST' and '/complete' in parsed.path:
                habit_id = int(path_parts[3])
                content_length = int(self.headers.get('Content-Length', 0))
                body = {}
                if content_length > 0:
                    body = json.loads(self.rfile.read(content_length))
                
                date = body.get('date', datetime.now().strftime('%Y-%m-%d'))
                notes = body.get('notes')
                success = complete_habit(habit_id, date, notes)
                self.send_json_response({'success': success})
                return
            
            # POST /api/habits/{id}/uncomplete - Remove completion
            if self.command == 'POST' and '/uncomplete' in parsed.path:
                habit_id = int(path_parts[3])
                content_length = int(self.headers.get('Content-Length', 0))
                body = {}
                if content_length > 0:
                    body = json.loads(self.rfile.read(content_length))
                
                date = body.get('date', datetime.now().strftime('%Y-%m-%d'))
                uncomplete_habit(habit_id, date)
                self.send_json_response({'success': True})
                return
            
            # DELETE /api/habits/{id} - Delete habit
            if self.command == 'DELETE' and len(path_parts) >= 4:
                habit_id = int(path_parts[3])
                delete_habit(habit_id)
                self.send_json_response({'success': True})
                return
            
            self.send_error(404, "Habit endpoint not found")
            
        except Exception as e:
            print(f"Habits API error: {e}")
            import traceback
            traceback.print_exc()
            self.send_error(500, f'Habits API error: {e}')

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")


# ==================== HABIT TRACKER DATABASE ====================

HABITS_DB_PATH = os.path.join(os.path.dirname(__file__), 'habits.db')

def init_habits_db():
    """Initialize the habits tracking database"""
    conn = sqlite3.connect(HABITS_DB_PATH)
    c = conn.cursor()
    
    # Habits table
    c.execute('''
        CREATE TABLE IF NOT EXISTS habits (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            person TEXT DEFAULT 'Everyone',
            schedule_type TEXT NOT NULL,  -- 'daily', 'interval', 'weekly'
            schedule_data TEXT,           -- JSON: interval days or weekday list
            icon TEXT DEFAULT '✓',
            category TEXT DEFAULT 'general',
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            active INTEGER DEFAULT 1
        )
    ''')
    
    # Completions table
    c.execute('''
        CREATE TABLE IF NOT EXISTS completions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            habit_id INTEGER NOT NULL,
            completed_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            completed_date DATE NOT NULL,
            notes TEXT,
            FOREIGN KEY (habit_id) REFERENCES habits(id),
            UNIQUE(habit_id, completed_date)
        )
    ''')
    
    conn.commit()
    conn.close()
    print(f"Habits database initialized: {HABITS_DB_PATH}")

def get_habits():
    """Get all active habits"""
    conn = sqlite3.connect(HABITS_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute('SELECT * FROM habits WHERE active = 1 ORDER BY person, category, name')
    habits = [dict(row) for row in c.fetchall()]
    conn.close()
    return habits

def create_habit(name, person='Everyone', schedule_type='daily', schedule_data=None, icon='✓', category='general'):
    """Create a new habit"""
    conn = sqlite3.connect(HABITS_DB_PATH)
    c = conn.cursor()
    c.execute('''
        INSERT INTO habits (name, person, schedule_type, schedule_data, icon, category)
        VALUES (?, ?, ?, ?, ?, ?)
    ''', (name, person, schedule_type, json.dumps(schedule_data) if schedule_data else None, icon, category))
    habit_id = c.lastrowid
    conn.commit()
    conn.close()
    return habit_id

def delete_habit(habit_id):
    """Soft delete a habit"""
    conn = sqlite3.connect(HABITS_DB_PATH)
    c = conn.cursor()
    c.execute('UPDATE habits SET active = 0 WHERE id = ?', (habit_id,))
    conn.commit()
    conn.close()

def complete_habit(habit_id, date=None, notes=None):
    """Mark a habit as complete for a date"""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(HABITS_DB_PATH)
    c = conn.cursor()
    try:
        c.execute('''
            INSERT OR REPLACE INTO completions (habit_id, completed_date, notes)
            VALUES (?, ?, ?)
        ''', (habit_id, date, notes))
        conn.commit()
        success = True
    except Exception as e:
        print(f"Error completing habit: {e}")
        success = False
    conn.close()
    return success

def uncomplete_habit(habit_id, date=None):
    """Remove completion for a date"""
    if date is None:
        date = datetime.now().strftime('%Y-%m-%d')
    conn = sqlite3.connect(HABITS_DB_PATH)
    c = conn.cursor()
    c.execute('DELETE FROM completions WHERE habit_id = ? AND completed_date = ?', (habit_id, date))
    conn.commit()
    conn.close()

def get_completions(habit_id=None, start_date=None, end_date=None):
    """Get completions with optional filters"""
    conn = sqlite3.connect(HABITS_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    query = 'SELECT * FROM completions WHERE 1=1'
    params = []
    
    if habit_id:
        query += ' AND habit_id = ?'
        params.append(habit_id)
    if start_date:
        query += ' AND completed_date >= ?'
        params.append(start_date)
    if end_date:
        query += ' AND completed_date <= ?'
        params.append(end_date)
    
    query += ' ORDER BY completed_date DESC'
    c.execute(query, params)
    completions = [dict(row) for row in c.fetchall()]
    conn.close()
    return completions

def get_habit_stats(habit_id, days=30):
    """Get stats for a habit"""
    conn = sqlite3.connect(HABITS_DB_PATH)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    
    start_date = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    
    # Count completions
    c.execute('''
        SELECT COUNT(*) as count FROM completions 
        WHERE habit_id = ? AND completed_date >= ?
    ''', (habit_id, start_date))
    count = c.fetchone()['count']
    
    # Get streak
    c.execute('''
        SELECT completed_date FROM completions 
        WHERE habit_id = ? 
        ORDER BY completed_date DESC
    ''', (habit_id,))
    
    dates = [row['completed_date'] for row in c.fetchall()]
    streak = 0
    today = datetime.now().date()
    
    for i, date_str in enumerate(dates):
        expected = (today - timedelta(days=i)).strftime('%Y-%m-%d')
        if date_str == expected:
            streak += 1
        else:
            break
    
    conn.close()
    return {'count': count, 'streak': streak, 'days': days}

# Initialize habits database
init_habits_db()

# ==================== MAIN ====================

def main():
    global mqtt_client

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Start WebSocket server in background thread (always, for HA subscriptions)
    ws_thread = threading.Thread(target=run_websocket_server, daemon=True)
    ws_thread.start()
    print(f"WebSocket bridge running on ws://localhost:{WS_PORT}")

    # Start HA WebSocket subscription (for real-time updates)
    start_ha_websocket_thread()

    # Start MQTT client if enabled
    if MQTT_ENABLED:
        mqtt_client = SkylightMQTTClient()
        if mqtt_client.connect():
            print("MQTT integration enabled")
        else:
            print("MQTT connection failed, continuing without MQTT")
            mqtt_client = None
    else:
        print("MQTT integration disabled (set MQTT_ENABLED=True in config.py to enable)")

    # Start HTTP server (threaded to prevent blocking, allow reuse of address)
    class ThreadedTCPServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
        allow_reuse_address = True
        daemon_threads = True  # Don't wait for threads on shutdown
    
    with ThreadedTCPServer(("0.0.0.0", PORT), ProxyHandler) as httpd:
        print(f"Dashboard server running at http://0.0.0.0:{PORT}/index.html")
        print(f"Proxying API requests to {HA_URL}")
        print("Press Ctrl+C to stop")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            print("\nShutting down...")
            if mqtt_client:
                mqtt_client.disconnect()


if __name__ == "__main__":
    main()

