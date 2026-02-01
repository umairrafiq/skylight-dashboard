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
- **Event Alerts** - Soothing chime with gradual volume increase
- **Text-to-Speech** - Announces events via Home Assistant Piper
- **Auto Theme** - Switches between dark/light based on sunrise/sunset

## Screenshots

| Calendar View | Todo Lists |
|---------------|------------|
| Month/Week/Day views with color-coded events | Vertical sections with quick-add |

## Requirements

- Home Assistant instance
- Python 3.x
- Modern web browser
- (Optional) Piper TTS add-on for voice announcements

## Installation

### 1. Clone the repository

```bash
git clone https://github.com/umairrafiq/skylight-dashboard.git
cd skylight-dashboard
```

### 2. Configure Home Assistant connection

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

### 3. Run the server

```bash
python3 server.py
```

### 4. Open the dashboard

Navigate to: `http://localhost:8765/index.html`

## Kiosk Mode (Optional)

For a wall-mounted display, use the included scripts:

```bash
# Install as a system service
sudo ./install.sh

# Or run manually in kiosk mode
./skylight-dashboard.sh start
```

## Project Structure

```
skylight-dashboard/
├── index.html          # Main dashboard (calendar, todos, weather)
├── dashboard.html      # Device controls panel
├── server.py           # Proxy server for Home Assistant API
├── config.example.py   # Configuration template
├── config.py           # Your local config (not committed)
├── skylight-dashboard.sh    # Kiosk mode launcher
├── install.sh          # System service installer
└── uninstall.sh        # System service uninstaller
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

## Home Assistant Entities

The dashboard automatically discovers:

- `calendar.*` - All calendar entities
- `todo.*` - All todo list entities
- `weather.forecast_home` - Weather data
- `sun.sun` - Sunrise/sunset times
- `sensor.islamic_prayer_times_*` - Prayer times

## License

MIT License - feel free to use and modify.

## Acknowledgments

Built for use with [Home Assistant](https://www.home-assistant.io/).
