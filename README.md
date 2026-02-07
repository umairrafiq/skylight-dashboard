# Skylight Dashboard

A beautiful, wall-mounted dashboard for Home Assistant featuring calendars, todo lists, weather, prayer times, and more.

## Features

- **Calendar Views** - Month, week, and day views with event management
- **Dynamic Calendars** - Automatically fetches all calendars from Home Assistant
- **Calendar Toggles** - Hide/show individual calendars with one click
- **Todo Lists** - Vertical colored sections for each todo list
- **Quick Add** - Add tasks directly from the top of each list
- **Weather Display** - Current conditions, high/low, humidity
- **Sunrise/Sunset** - Daily sun times
- **Prayer Times** - Islamic prayer times with alerts
- **Quran Player** - Play surahs with Arabic text, translation display, and English audio
- **Screensaver Ayah** - Ayah of the Day overlay on screensaver with adaptive contrast
- **Event Alerts** - Soothing chime with gradual volume increase
- **Text-to-Speech** - Announces events via Home Assistant Piper
- **Auto Theme** - Switches between dark/light based on sunrise/sunset
- **Screensaver Slideshow** - Full-screen photo slideshow with Ken Burns effect
- **Photo Sources** - Local folders, SMB mounts, or Synology Photos
- **Hourly Chime** - Westminster-style chime with optional time announcement
- **MQTT Integration** - Two-way communication with Home Assistant
- **Camera Popups** - Show doorbell/security cameras with sound alerts
- **Wake on Motion** - Wake screen via Home Assistant automations
- **Notifications Center** - Unified notification panel in sidebar
- **Mail & Packages** - USPS, Amazon, FedEx, UPS tracking from Informed Delivery
- **HA Notifications** - Shows and dismisses Home Assistant persistent notifications
- **Screenshot Capture** - Take screenshots via Home Assistant (MQTT camera entity)
- **Scroll Preservation** - Week/day views maintain scroll position during auto-refresh
- **Smart Screensaver** - Background refreshes don't wake the screensaver
- **Smooth Transitions** - Preloaded images with seamless crossfade in screensaver

## Screenshots

| Calendar View | Todo Lists |
|---------------|------------|
| Month/Week/Day views with color-coded events | Vertical sections with quick-add |

## Requirements

- Home Assistant instance
- Python 3.x
- Modern web browser
- (Optional) Piper TTS add-on for voice announcements
- (Optional) MQTT broker for remote control (usually included with Home Assistant)

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/umairrafiq/skylight-dashboard.git
cd skylight-dashboard
```

### 2. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 3. Configure Home Assistant connection

```bash
cp config.example.py config.py
nano config.py
```

Update with your Home Assistant details:

```python
HA_URL = "https://YOUR_HA_IP:8123"
HA_TOKEN = "YOUR_LONG_LIVED_ACCESS_TOKEN"
PORT = 8765
```

To get a long-lived access token:
1. Go to your Home Assistant profile
2. Scroll to "Long-Lived Access Tokens"
3. Click "Create Token"

### 4. Run the server

```bash
python3 server.py
```

### 5. Open the dashboard

Navigate to: `http://localhost:8765/index.html`

## Installation as a Service (Recommended)

For a wall-mounted display or always-on dashboard:

```bash
# Install desktop app + systemd user service
./install.sh
```

This will:
- Install Python dependencies
- Create a desktop menu entry
- Create and enable a systemd user service (auto-starts on login)

Service commands:
```bash
systemctl --user status skylight-dashboard.service   # Check status
systemctl --user restart skylight-dashboard.service  # Restart
journalctl --user -u skylight-dashboard.service -f   # View logs
```

For kiosk mode (full-screen browser):
```bash
./skylight-dashboard.sh start
```

## Project Structure

```
skylight-dashboard/
├── index.html          # Main dashboard (calendar, todos, weather)
├── dashboard.html      # Device controls panel
├── server.py           # Proxy server with MQTT bridge
├── config.example.py   # Configuration template
├── config.py           # Your local config (not committed)
├── requirements.txt    # Python dependencies
├── skylight-dashboard.sh    # Kiosk mode launcher
├── install.sh          # Desktop app + systemd service installer
└── uninstall.sh        # Removes desktop app + systemd service
```

## Configuration

### TTS (Text-to-Speech)

The dashboard uses Home Assistant's Piper TTS for announcements. To enable:

1. Install the **Piper** add-on in Home Assistant
2. Install the **Wyoming** integration
3. Point Wyoming to the Piper add-on

If Piper isn't available, it falls back to the browser's Web Speech API.

### Alarm Volume

- Volume control appears in the alert modal
- Setting is saved and persists across sessions
- Alarm starts quiet and gradually increases over 30 seconds

### Screensaver

The screensaver activates after idle time and displays a photo slideshow:

- **Photo Sources**: Local folder, SMB/network mount, or Synology Photos
- **Ken Burns Effect**: Smooth pan and zoom animations
- **Crossfade Transitions**: Beautiful 1.5s transitions between photos
- **Header Overlay**: Weather, clock, and prayer times remain visible
- **Wake Events**: Wakes on mouse/touch activity or alarm notifications

To use with a Synology NAS SMB share:
```bash
# Mount the share
sudo mount -t cifs //your-nas/photos /mnt/synology -o username=user,password=pass

# Then set folder path in settings to: /mnt/synology
```

### Hourly Chime

- Westminster-style bell chime at the top of each hour
- Optional TTS announcement ("It's X o'clock")
- Configurable hours (default: 6 AM to 10 PM)
- Enable/disable in screensaver settings

### Quran Menu

Enable the Quran menu in settings to access Islamic content:

#### Features
- **Ayah of the Day** - Daily verse with Arabic text and English translation
- **Quick Play Surahs** - Al-Fatiha, Ya-Sin, Ar-Rahman, Al-Mulk, Al-Kahf, Al-Ikhlas
- **Ayat ul-Kursi** - Quick access to the Throne Verse (2:255)
- **Three Quls** - Play Al-Ikhlas, Al-Falaq, and An-Nas together
- **All Surahs** - Dropdown to select any of the 114 surahs

#### Now Playing Display
When a surah is playing, a "Now Playing" card appears showing:
- Current surah name and translation
- Arabic text of the current ayah (RTL, Arabic font)
- English translation
- Progress indicator (e.g., "Ayah 3/7")
- Playback controls (previous, play/pause, next, stop)
- Toggle for English translation audio

#### Translation Audio
- Plays English audio after each Arabic ayah (using Ibrahim Walk recitation)
- Falls back to browser TTS if audio unavailable
- Can be toggled on/off during playback

#### Screensaver Ayah Overlay
When enabled, the Ayah of the Day appears on the screensaver:
- Positioned at bottom center (between photo date and controls)
- Shows Arabic text, English translation, and surah reference
- **Adaptive contrast**: Automatically switches between light/dark text based on photo brightness
- Transparent background with blur effect

#### Required Home Assistant Sensors
```yaml
sensor.quran_daily_ayah          # Translation text + attributes
sensor.quran_daily_ayah_arabic   # Arabic text
sensor.quran_daily_ayah_audio    # Audio URL (optional)
```

### MQTT Integration

Enable MQTT for remote control from Home Assistant automations.

#### Configuration

Add to your `config.py`:

```python
MQTT_ENABLED = True
MQTT_BROKER = "YOUR_HA_IP"      # Usually same as HA_URL host
MQTT_PORT = 1883
MQTT_USERNAME = "mqtt_user"     # Leave empty if no auth
MQTT_PASSWORD = "mqtt_pass"
MQTT_DEVICE_ID = "skylight_living"   # Unique identifier
MQTT_DEVICE_NAME = "Living Room Dashboard"
WS_PORT = 8766
```

#### Auto-Discovery

When connected, these entities appear automatically in Home Assistant:

| Entity | Type | Description |
|--------|------|-------------|
| `switch.skylight_living_screen` | Switch | Wake/sleep control |
| `sensor.skylight_living_state` | Sensor | Online/offline status |
| `sensor.skylight_living_tab` | Sensor | Current tab |
| `number.skylight_living_volume` | Number | Volume (0-100%) |
| `binary_sensor.skylight_living_camera` | Binary Sensor | Camera overlay active |
| `camera.skylight_living_screenshot` | Camera | Latest dashboard screenshot |
| `button.skylight_living_take_screenshot` | Button | Capture new screenshot |

#### MQTT Commands

Publish to topic: `skylight/{device_id}/command`

| Command | Payload | Description |
|---------|---------|-------------|
| Wake screen | `{"command": "wake"}` | Exit screensaver |
| Start screensaver | `{"command": "screensaver", "enabled": true}` | Activate screensaver |
| TTS message | `{"command": "speak", "message": "Hello!", "alarm": true}` | Speak with optional alert sound |
| Show camera | `{"command": "show_camera", "entity_id": "camera.doorbell", "title": "Front Door", "duration": 30}` | Display camera feed |
| Hide camera | `{"command": "hide_camera"}` | Close camera overlay |
| Switch tab | `{"command": "navigate", "tab": "calendar"}` | Navigate to tab |
| Set volume | `{"command": "volume", "value": 80}` | Set volume (0-100) |
| Set brightness | `{"command": "brightness", "value": 200}` | Set screen brightness (0-255) |
| Reload | `{"command": "reload"}` | Refresh the dashboard |

You can also take screenshots by publishing to: `skylight/{device_id}/screenshot/take`

Or use the button entity: `button.skylight_{device_id}_take_screenshot`

#### Home Assistant Automation Examples

**Wake on Motion:**
```yaml
automation:
  - alias: "Wake Skylight on Motion"
    trigger:
      - platform: state
        entity_id: binary_sensor.living_room_motion
        to: "on"
    condition:
      - condition: state
        entity_id: switch.skylight_living_screen
        state: "off"
    action:
      - service: mqtt.publish
        data:
          topic: "skylight/skylight_living/command"
          payload: '{"command": "wake"}'
```

**Doorbell Camera Popup:**
```yaml
automation:
  - alias: "Show Doorbell on Dashboard"
    trigger:
      - platform: state
        entity_id: binary_sensor.doorbell_button
        to: "on"
    action:
      - service: mqtt.publish
        data:
          topic: "skylight/skylight_living/command"
          payload: '{"command": "show_camera", "entity_id": "camera.doorbell", "title": "Front Door", "duration": 30}'
```

**Voice Notification:**
```yaml
automation:
  - alias: "Announce Front Door Open"
    trigger:
      - platform: state
        entity_id: binary_sensor.front_door
        to: "on"
    action:
      - service: mqtt.publish
        data:
          topic: "skylight/skylight_living/command"
          payload: '{"command": "speak", "message": "Front door is open!", "alarm": true}'
```

### Screenshot Capture

Take screenshots of the dashboard remotely via Home Assistant or HTTP API.

#### How It Works
1. Screenshot request is sent via MQTT or HTTP
2. Browser captures the page using html2canvas
3. Image is published to MQTT camera topic
4. Screenshot is also available via HTTP API

#### Home Assistant Entities
- **Camera**: `camera.skylight_{device_id}_screenshot` - Shows the latest screenshot
- **Button**: `button.skylight_{device_id}_take_screenshot` - Triggers a new capture

#### HTTP API
```bash
# Get latest screenshot (PNG)
curl http://localhost:8765/api/screenshot -o screenshot.png

# Request new screenshot
curl http://localhost:8765/api/screenshot/take
```

#### Automation Example
```yaml
automation:
  - alias: "Daily Dashboard Screenshot"
    trigger:
      - platform: time
        at: "08:00:00"
    action:
      - service: button.press
        target:
          entity_id: button.skylight_living_take_screenshot
```

### Notifications Center

The sidebar includes a unified notifications panel that aggregates:

#### Mail & Packages
- USPS Mail, Packages, In Transit
- Amazon Packages
- FedEx Packages, In Transit
- UPS Packages, In Transit

Requires the **Mail and Packages** integration (HACS) with Informed Delivery configured.

#### Home Assistant Notifications
All persistent notifications from Home Assistant appear here and can be dismissed directly from the dashboard.

#### Usage
1. Click the 📬 icon in the left sidebar
2. View all notifications grouped by category
3. Hover over mail items and click **✕** to hide from the header overlay (stays in list)
4. Click **✕** on HA notifications to dismiss them completely
5. Hidden mail notifications reset daily at midnight

#### Supported Sensors
```yaml
# Mail and Packages integration (with or without _2 suffix)
sensor.mail_usps_mail
sensor.mail_usps_packages
sensor.mail_usps_delivering
sensor.mail_amazon_packages
sensor.mail_fedex_packages
sensor.mail_fedex_delivering
sensor.mail_ups_packages
sensor.mail_ups_delivering
```

## Home Assistant Entities

The dashboard automatically discovers:

- `calendar.*` - All calendar entities
- `todo.*` - All todo list entities
- `weather.forecast_home` - Weather data
- `sun.sun` - Sunrise/sunset times
- `sensor.islamic_prayer_times_*` - Prayer times
- `sensor.mail_*` - Mail and package notifications
- `persistent_notification.*` - HA persistent notifications

## Troubleshooting

### Dashboard doesn't launch in fullscreen/kiosk mode

**Problem:** When Chrome is already running, new windows ignore `--kiosk` or `--start-fullscreen` flags and open in the existing session as a regular window.

**Solution:** The launcher script uses a separate Chrome profile (`~/.config/skylight-chrome`) to ensure kiosk mode works independently of your main browser session.

If you're still having issues:
```bash
# Kill any existing dashboard instances
pkill -f "skylight-chrome"

# Relaunch
./skylight-dashboard.sh
```

### Fullscreen not working on Wayland

**Problem:** The `--start-fullscreen` flag doesn't work reliably on Wayland-based desktops (Ubuntu 22.04+, Fedora, etc.).

**Solution:** The script uses `--kiosk` mode instead, which works properly on both X11 and Wayland.

**To exit kiosk mode:** Press `Alt+F4` or `Ctrl+W`

### Server not starting

**Problem:** Dashboard shows connection error or blank page.

**Solution:**
```bash
# Check server status
systemctl --user status skylight-server

# View logs
journalctl --user -u skylight-server -f

# Restart server
systemctl --user restart skylight-server
```

### Screen goes to sleep while dashboard is open

**Problem:** The system screen saver activates even with the dashboard running.

**Solution:** The launcher script includes a background process that simulates user activity every 4 minutes. If this isn't working:
```bash
# Check if the watcher is running
pgrep -f "skylight-chrome"

# Disable screen blanking manually
gsettings set org.gnome.desktop.session idle-delay 0
```

### Photos not loading in screensaver

**Problem:** Screensaver shows "No photos available" or loading spinner.

**Solutions:**
1. **Local folder:** Ensure the path exists and contains images
2. **SMB mount:** Verify the network share is mounted:
   ```bash
   mount | grep photos
   ```
3. **Synology Photos:** Check the share link is correct and accessible

### MQTT not connecting

**Problem:** MQTT status shows disconnected in settings.

**Solution:**
1. Verify MQTT broker is running on Home Assistant
2. Check `config.py` has correct MQTT settings:
   ```python
   MQTT_ENABLED = True
   MQTT_BROKER = "YOUR_HA_IP"
   MQTT_PORT = 1883
   MQTT_USERNAME = "mqtt_user"
   MQTT_PASSWORD = "mqtt_pass"
   ```
3. Restart the server after config changes

### Calendar/Weather not updating

**Problem:** Data appears stale or shows errors.

**Solution:**
1. Check Home Assistant connection:
   ```bash
   curl -s -H "Authorization: Bearer YOUR_TOKEN" https://YOUR_HA:8123/api/
   ```
2. Verify `config.py` has correct HA_URL and HA_TOKEN
3. Check browser console for errors (F12 → Console)

## License

MIT License - feel free to use and modify.

## Acknowledgments

Built for use with [Home Assistant](https://www.home-assistant.io/).
