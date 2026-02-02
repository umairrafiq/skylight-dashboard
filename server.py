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

        except Exception as e:
            print(f"MQTT: Error handling message - {e}")

    def _handle_command(self, payload):
        """Process command payload and forward to WebSocket clients"""
        global dashboard_state

        try:
            cmd = json.loads(payload)
            command = cmd.get('command', '')

            print(f"MQTT: Processing command: {command}")

            # Handle brightness command locally (requires system access)
            if command == 'brightness':
                value = cmd.get('value', 128)
                self._set_brightness(value)
                return

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

    def _set_brightness(self, value):
        """Set screen brightness using xrandr (Linux)"""
        try:
            # Map 0-255 to 0.1-1.0 (don't go below 10%)
            brightness = max(0.1, value / 255.0)

            # Get primary display
            result = subprocess.run(
                ['xrandr', '--query'],
                capture_output=True,
                text=True
            )

            for line in result.stdout.split('\n'):
                if ' connected' in line:
                    display = line.split()[0]
                    subprocess.run([
                        'xrandr', '--output', display,
                        '--brightness', str(round(brightness, 2))
                    ])
                    print(f"MQTT: Set brightness to {round(brightness * 100)}% on {display}")
                    break
        except Exception as e:
            print(f"MQTT: Failed to set brightness - {e}")

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
                    await websocket.send(json.dumps({'type': 'pong'}))

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

    print(f"WebSocket: Starting server on ws://localhost:{WS_PORT}")
    async with websockets.serve(
        websocket_handler,
        "localhost",  # Bind to localhost only for security
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
        if self.path.startswith('/api/local/'):
            self.handle_local_request()
        elif self.path.startswith('/api/synology/'):
            self.proxy_synology_request()
        elif self.path.startswith('/api/'):
            self.proxy_request('GET')
        else:
            super().do_GET()

    def do_POST(self):
        if self.path.startswith('/api/'):
            self.proxy_request('POST')
        else:
            self.send_error(405, "Method Not Allowed")

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
                self.end_headers()
                self.wfile.write(data)

        except urllib.error.HTTPError as e:
            self.send_error(e.code, str(e.reason))
        except Exception as e:
            self.send_error(500, str(e))

    def handle_local_request(self):
        """Handle local folder photo requests"""
        try:
            parsed = urllib.parse.urlparse(self.path)
            params = urllib.parse.parse_qs(parsed.query)
            folder_path = params.get('path', [''])[0]

            if '/api/local/photos' in self.path:
                # List photos in folder
                if not folder_path or not os.path.isdir(folder_path):
                    self.send_json_response({'success': False, 'error': 'Folder not found'})
                    return

                # Supported image extensions
                image_extensions = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp'}
                photos = []

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
                except PermissionError:
                    self.send_json_response({'success': False, 'error': 'Permission denied'})
                    return

                # Sort by modification time (newest first)
                photos.sort(key=lambda x: x['mtime'], reverse=True)

                self.send_json_response({'success': True, 'photos': photos})

            elif '/api/local/image' in self.path:
                # Serve image file
                image_path = params.get('path', [''])[0]

                if not image_path or not os.path.isfile(image_path):
                    self.send_error(404, "Image not found")
                    return

                # Validate path is under allowed directories (security)
                real_path = os.path.realpath(image_path)

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

                try:
                    with open(real_path, 'rb') as f:
                        data = f.read()

                    self.send_response(200)
                    self.send_header('Content-Type', content_type)
                    self.send_header('Content-Length', len(data))
                    self.send_header('Cache-Control', 'public, max-age=86400')
                    self.end_headers()
                    self.wfile.write(data)
                except Exception as e:
                    self.send_error(500, str(e))

            else:
                self.send_error(404, "Local endpoint not found")

        except Exception as e:
            print(f"Local request error: {e}")
            self.send_error(500, str(e))

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

    def log_message(self, format, *args):
        print(f"[{self.log_date_time_string()}] {args[0]}")


# ==================== MAIN ====================

def main():
    global mqtt_client

    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    # Start MQTT client if enabled
    if MQTT_ENABLED:
        mqtt_client = SkylightMQTTClient()
        if mqtt_client.connect():
            print("MQTT integration enabled")
        else:
            print("MQTT connection failed, continuing without MQTT")
            mqtt_client = None

        # Start WebSocket server in background thread
        ws_thread = threading.Thread(target=run_websocket_server, daemon=True)
        ws_thread.start()
        print(f"WebSocket bridge running on ws://localhost:{WS_PORT}")
    else:
        print("MQTT integration disabled (set MQTT_ENABLED=True in config.py to enable)")

    # Start HTTP server (allow reuse of address to avoid "Address already in use" after restart)
    socketserver.TCPServer.allow_reuse_address = True
    with socketserver.TCPServer(("", PORT), ProxyHandler) as httpd:
        print(f"Dashboard server running at http://localhost:{PORT}/index.html")
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
