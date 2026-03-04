# Skylight Dashboard Documentation

A modern Home Assistant dashboard for managing calendars, tasks, weather, and prayer times.

## Overview

Skylight Dashboard is a single-page web application that integrates with Home Assistant to provide:

- Real-time weather display with forecasts
- Multi-calendar management (Personal, Work, Family, Kids)
- Todo/task lists for multiple users
- Islamic prayer times
- Event alerts with snooze functionality
- Automatic dark/light theme based on sunrise/sunset

---

## Features

### 1. Weather Display
**Location:** Header section (top-left)

- Current temperature and condition
- Weather icon based on condition
- Daily high/low temperatures
- Humidity and wind speed
- Sunrise/sunset times
- Weather forecast overlay on calendar days

**Home Assistant Entity:** `weather.forecast_home`

### 2. Prayer Times
**Location:** Header section (middle)

Displays five daily Islamic prayer times:
- Fajr
- Dhuhr
- Asr
- Maghrib
- Isha

**Home Assistant Entities:**
- `sensor.islamic_prayer_times_fajr_prayer`
- `sensor.islamic_prayer_times_dhuhr_prayer`
- `sensor.islamic_prayer_times_asr_prayer`
- `sensor.islamic_prayer_times_maghrib_prayer`
- `sensor.islamic_prayer_times_isha_prayer`

### 3. Clock
**Location:** Header section (top-right)

- Real-time clock with seconds
- Full date display

### 4. Calendar
**Location:** Main content area (Calendar tab)

**Views:**
| View | Description |
|------|-------------|
| Month | Full month grid with event badges and weather |
| Week | 7-day view with hourly time slots (6 AM - 8 PM) |
| Day | Single day with detailed hourly breakdown |

**Calendars:**
| Calendar | Entity ID | Color |
|----------|-----------|-------|
| Personal | `calendar.personal` | Indigo (#6366f1) |
| Work | `calendar.work` | Amber (#f59e0b) |
| Family | `calendar.family` | Emerald (#10b981) |
| Kids | `calendar.kids` | Pink (#ec4899) |

**Event Creation:**
- Click "Add Event" button or click on any time slot
- Specify title, calendar, date, and start/end times

### 5. Tasks/Todos
**Location:** Main content area (Tasks tab)

**Available Lists:**
- Shopping List (`todo.shopping_list`)
- Umair (`todo.umair`)
- Sanam (`todo.sanam`)
- Amairah (`todo.amairah`)
- Aileen (`todo.aileen`)
- Emaneh (`todo.emaneh`)

**Features:**
- Toggle task completion
- Delete tasks
- Add new tasks
- Progress bar showing completion percentage

### 6. Controls Tab
**Location:** Main content area (Controls tab)

Embeds `dashboard.html` for Home Assistant device controls.

### 7. Event Alerts
**Location:** Modal overlay

Alerts appear 5 minutes before:
- Calendar events
- Prayer times

**Alert Actions:**
- Snooze 5 minutes
- Snooze 15 minutes
- Dismiss

**Features:**
- Audio notification (3-note chime)
- Browser notification (if permitted)

---

## Navigation

### Sidebar Buttons
| Icon | Function |
|------|----------|
| Calendar | Switch to Calendar tab |
| Checklist | Switch to Tasks tab |
| Gear | Switch to Controls tab |
| Refresh | Reload all data |
| Sun/Moon | Toggle dark/light theme |

### Calendar Navigation
- **Left/Right arrows:** Navigate months/weeks/days
- **View buttons:** Switch between Month, Week, Day views
- **Click on day:** Jump to Day view for that date

---

## Theme System

### Automatic Theme
Theme automatically switches based on sun position:
- **Below horizon:** Dark mode
- **Above horizon:** Light mode

**Home Assistant Entity:** `sun.sun`

### Manual Override
Click the theme button (sun/moon icon) in sidebar to toggle.

### Color Variables
```css
/* Dark Mode */
--bg-primary: #0f172a
--bg-secondary: #1e293b
--bg-card: #334155
--text-primary: #ffffff
--text-secondary: #94a3b8

/* Light Mode */
--bg-primary: #f8fafc
--bg-secondary: #ffffff
--bg-card: #f1f5f9
--text-primary: #1e293b
--text-secondary: #475569
```

---

## API Integration

### Endpoints Used

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/states` | GET | Fetch all entity states |
| `/api/services/weather/get_forecasts` | POST | Get weather forecast |
| `/api/services/calendar/get_events` | POST | Fetch calendar events |
| `/api/services/calendar/create_event` | POST | Create new event |
| `/api/services/todo/get_items` | POST | Fetch todo items |
| `/api/services/todo/add_item` | POST | Add todo item |
| `/api/services/todo/update_item` | POST | Update todo status |
| `/api/services/todo/remove_item` | POST | Delete todo item |

---

## Data Refresh

| Trigger | What Updates |
|---------|--------------|
| Initial load | All data |
| Every 30 seconds | Event alert check |
| Every hour | All data |
| Page visibility | All data (when returning to tab) |
| Manual refresh | All data |

---

## File Structure

```
homeassistant/
├── index.html                  # Main dashboard
├── dashboard.html              # Device controls (embedded in Controls tab)
├── server.py                   # Proxy server (serves files + proxies HA API)
├── skylight-dashboard.sh       # Application launcher script
├── skylight-dashboard.svg      # Application icon
├── skylight-dashboard.desktop  # Desktop entry template
├── install.sh                  # Installer script
├── uninstall.sh                # Uninstaller script
├── connection.txt              # Home Assistant connection info
└── DOCUMENTATION.md            # This file
```

---

## Ubuntu Desktop Application

### Installation

Run the installer to set up the desktop application:

```bash
cd /home/umair/homeassistant
./install.sh
```

This will:
- Make the launcher script executable
- Install the application icon
- Create a desktop entry in `~/.local/share/applications/`

### Launching

After installation, you can launch the dashboard by:
1. **Application Menu:** Search for "Skylight Dashboard"
2. **Command Line:** Run `/home/umair/homeassistant/skylight-dashboard.sh`

### How It Works

1. The launcher starts the proxy server (`server.py`) on port 8765
2. Opens your default browser in fullscreen app mode (no address bar/tabs)
3. Browser connects to `http://localhost:8765/index.html`
4. The proxy server forwards `/api/*` requests to Home Assistant

### Browser Support

The launcher auto-detects and uses (in order of preference):
- Chromium Browser
- Google Chrome
- Firefox (kiosk mode)
- Epiphany Browser

### Controls

| Key | Action |
|-----|--------|
| `F11` | Toggle fullscreen |
| `Alt+F4` | Exit application |

### Uninstallation

```bash
/home/umair/homeassistant/uninstall.sh
```

### Server Configuration

The proxy server (`server.py`) uses configuration from `config.py`:

```bash
# Copy the example config
cp config.example.py config.py

# Edit with your values
nano config.py
```

```python
# config.py
HA_URL = "https://YOUR_HA_IP:8123"
HA_TOKEN = "YOUR_LONG_LIVED_ACCESS_TOKEN"
PORT = 8765
```

**Note:** `config.py` contains secrets and is excluded from git.

### Troubleshooting

**Port already in use:**
```bash
pkill -f "server.py"
# or
fuser -k 8765/tcp
```

**Check server logs:**
```bash
cat /tmp/skylight-dashboard.log
```

**Test server manually:**
```bash
cd /home/umair/homeassistant
python3 server.py
# Then open http://localhost:8765/index.html in browser
```

---

## Dependencies

### External
- **Tailwind CSS** (CDN): Utility-first CSS framework
- **Inter Font** (Google Fonts): UI typography

### Home Assistant Integrations Required
- Weather integration (forecast_home)
- Calendar integration
- Todo integration
- Sun integration
- Islamic Prayer Times integration

---

## Browser Requirements

- Modern browser with ES6+ support
- Web Audio API (for notification sounds)
- Notifications API (optional, for browser notifications)

---

## Key Functions Reference

| Function | Description |
|----------|-------------|
| `init()` | Initialize dashboard, load all data |
| `updateClock()` | Update time display |
| `loadWeather()` | Fetch weather and prayer data |
| `loadCalendarEvents()` | Fetch events from all calendars |
| `loadTodos()` | Fetch todo items for selected list |
| `renderCalendar()` | Render current calendar view |
| `renderMonthView()` | Render month grid |
| `renderWeekView()` | Render week grid |
| `renderDayView()` | Render day timeline |
| `checkUpcomingEvents()` | Check for events needing alerts |
| `showEventAlert()` | Display alert modal |
| `snoozeAlert(minutes)` | Snooze current alert |
| `dismissAlert()` | Dismiss current alert |
| `setTheme(dark)` | Apply dark/light theme |
| `refreshData()` | Reload all data sources |

---

## Configuration

### Alert Timing
```javascript
const ALERT_MINUTES_BEFORE = 5; // Alert 5 minutes before event
```

### Calendar Colors
```javascript
const CALENDAR_COLORS = {
    'calendar.personal': '#6366f1',
    'calendar.work': '#f59e0b',
    'calendar.family': '#10b981',
    'calendar.kids': '#ec4899'
};
```

### Weather Icons
Mapped conditions: `clear-night`, `cloudy`, `fog`, `hail`, `lightning`, `lightning-rainy`, `partlycloudy`, `pouring`, `rainy`, `snowy`, `snowy-rainy`, `sunny`, `windy`, `windy-variant`, `exceptional`
