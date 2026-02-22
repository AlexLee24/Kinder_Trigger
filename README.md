An astronomical observation task trigger tool for automatically generating observation scripts and sending them to the control room.

Supports both **GUI App** (cross-platform) and **CLI** modes.

## Features

- Visual target builder with card-based UI
- Support both LOT (Lulin One-meter Telescope) and SLT modes
- RA / Dec input in **sexagesimal** (`hh:mm:ss`) or **decimal degrees** (auto-converted)
- Auto or manual exposure configuration per filter (ugriz)
- Automatically generate ACP observation scripts
- Object visibility plot preview
- Send observation plans to the control room via Slack
- Cross-platform: Windows, macOS, Linux, iOS, Android, Web

## Installation

### Clone

```bash
git clone https://github.com/AlexLee24/Kinder_Trigger.git
cd Kinder_Trigger
```

### Install Dependencies

```bash
pip install -r requirements.txt
```

> Some packages may need pip even in a conda environment:
> ```bash
> pip install slack-sdk python-dotenv timezonefinder flet
> ```

## Quick Start (GUI App)

```bash
python Trigger_App.py
```

The app has 4 pages accessible from the left sidebar:

| Page | Description |
|------|-------------|
| **Home** | Manage targets, switch telescope (SLT/LOT), set data path, import from legacy JSON |
| **Script** | Generate ACP script + visibility plot |
| **Send** | Preview and send script to Slack control room |
| **Settings** | Configure data path, Slack credentials |

### Adding Targets

1. Click **+** on the Home page
2. Fill in target name, RA, Dec, magnitude
3. Choose priority level
4. Toggle **Auto Exposure** on (by magnitude) or off (manual filter/exp/count)
5. Click **Save Target**

> **Coordinate formats**: RA/Dec accept both `hh:mm:ss.ss` / `±dd:mm:ss.ss` and decimal degrees.
> Decimal degrees are auto-converted to sexagesimal in the generated script.

> **Target names**: Spaces, underscores, and special characters are automatically stripped in the script output. Only letters, digits, and hyphens are kept.

### JSON Format (v2)

Targets are auto-saved to `main_set_SLT.json` or `main_set_LOT.json`:

```json
{
  "version": 2,
  "settings": { "telescope": "SLT" },
  "targets": [
    {
      "name": "SN2024ggi",
      "ra": "11:18:22.087",
      "dec": "-32:50:15.27",
      "mag": "19.2",
      "priority": "Normal",
      "auto_exposure": true,
      "observations": [],
      "repeat": 0,
      "note": ""
    }
  ]
}
```

Manual exposure example:

```json
{
  "name": "M31",
  "ra": "00:42:44.3",
  "dec": "+41:16:09",
  "mag": "3.4",
  "priority": "High",
  "auto_exposure": false,
  "observations": [
    { "filter": "gp", "exp_time": 300, "count": 5 },
    { "filter": "rp", "exp_time": 300, "count": 5 }
  ],
  "repeat": 0,
  "note": "Monitor nightly"
}
```

Legacy v1 JSON files are auto-converted on import.

### Priority Levels

| Priority | Description |
|----------|-------------|
| **Top** | Highest priority, override everything |
| **Urgent** | Immediate, time-sensitive. Must specify minimum elevation or start time |
| **Urgent_Observe_When_Possible** | Urgent but flexible timing |
| **High** | Important scientific targets, preferred same night |
| **Normal** | Standard targets; observe based on conditions |
| **None** | Filler observations after other targets are completed |

### Environment Variables (.env)

The app auto-creates a `.env` file on first launch. You can also edit it in **Settings**:

```env
DATA_PATH=/path/to/data          # Where JSON files are stored
SLACK_BOT_TOKEN=xoxb-...         # Slack bot token
SLACK_CHANNEL_ID_CONTROL_ROOM=C... # Slack channel ID
```

> Ask Alex on Slack to obtain the Slack token. The `.env` file is optional if you don't need auto-sending.

## CLI Mode (Legacy)

```bash
python Trigger.py
```

Uses the legacy `Trigger.json` format. See [legacy JSON examples](#legacy-json-format) below.

### Legacy JSON Format

```json
{
  "settings": {
    "IS_LOT": false,
    "send_to_control_room": false
  },
  "targets": [
    {
      "object name": "SN 2024ggi",
      "RA": "11:18:22.087",
      "Dec": "-32:50:15.27",
      "Mag": 19.20,
      "Priority": "Normal",
      "Exp_By_Mag": "True",
      "Filter": "",
      "Exp_Time": "",
      "Num_of_Frame": "",
      "Repeat": 0
    }
  ]
}
```

#### Legacy Parameter Reference

| Parameter | Description |
|-----------|-------------|
| `IS_LOT` | `true` for LOT, `false` for SLT |
| `send_to_control_room` | `true` to auto-send via Slack |
| `object name` | Target name |
| `RA` | Right Ascension (hh:mm:ss) |
| `Dec` | Declination (±dd:mm:ss) |
| `Mag` | Magnitude |
| `Priority` | Urgent, High, Normal, Filler |
| `Exp_By_Mag` | `"True"` for auto exposure, `"False"` for manual |
| `Filter` | Filters: up, gp, rp, ip, zp (when manual) |
| `Exp_Time` | Exposure time in seconds (when manual) |
| `Num_of_Frame` | Number of frames (when manual) |
| `Repeat` | 0 = no repeat, 999 = unlimited |

## Important Notes

- Triple-check the accuracy of the observation plan before sending to control room
- Ensure `.env` is not included in version control
- The `obs_img/` directory is auto-created for visibility plots
- Data files (JSON, script.txt, obs_img) are stored in `~/Documents/Kinder_Trigger/` by default

## Packaging as Desktop App

### Prerequisites

```bash
pip install pyinstaller
```

### macOS (.app)

```bash
./build_macos.sh
```

Or manually:

```bash
pyinstaller --name "Kinder Trigger" --windowed --onedir --icon assets/icon.png \
  --add-data "Trigger_LOT_SLT.py:." --add-data "obsplan.py:." --add-data "assets:assets" \
  --noconfirm Trigger_App.py
```

Output: `dist/Kinder Trigger.app`

### Windows (.exe)

Run `build_windows.bat` on a Windows machine with the same dependencies installed.

Or manually:

```bash
pyinstaller --name "Kinder Trigger" --windowed --onedir --icon assets/icon.png ^
  --add-data "Trigger_LOT_SLT.py;." --add-data "obsplan.py;." --add-data "assets;assets" ^
  --noconfirm Trigger_App.py
```

Output: `dist\Kinder Trigger\Kinder Trigger.exe`

> **Note**: On Windows, use `;` (semicolon) as the path separator in `--add-data` instead of `:` (colon).

## File Structure

```
Kinder_Trigger/
├── Trigger_App.py        # GUI App (Flet, cross-platform)
├── Trigger.py            # CLI mode (legacy)
├── Trigger_LOT_SLT.py    # ACP script generator
├── obsplan.py            # Observation planning (based on obsplanning by Phil Cigan)
├── pyproject.toml        # Build configuration
├── requirements.txt      # Dependencies
├── assets/               # App icons and logos
│   ├── icon.png
│   ├── Kinder_dark.png
│   └── Kinder_light.png
├── .env                  # Environment config (auto-generated in ~/.kinder_trigger/)
├── main_set_SLT.json     # SLT targets (v2, in DATA_PATH)
├── main_set_LOT.json     # LOT targets (v2, in DATA_PATH)
├── script.txt            # Generated ACP script (in DATA_PATH)
└── obs_img/              # Visibility plot output (in DATA_PATH)
```

## Module Description

| Module | Description |
|--------|-------------|
| `Trigger_App.py` | Cross-platform GUI app built with Flet |
| `Trigger.py` | CLI-based trigger (legacy) |
| `Trigger_LOT_SLT.py` | ACP script generation for LOT and SLT |
| `obsplan.py` | Astronomical calculation & plotting ([obsplanning](https://github.com/pjcigan/obsplanning) by Phil Cigan) |

## Developers

Kinder Team — National Central University, Institute of Astronomy, GREAT Lab

## License

Developed by the [Kinder Team](http://kinder.astro.ncu.edu.tw).
The observation planning module is based on [obsplanning](https://github.com/pjcigan/obsplanning) by Phil Cigan.
