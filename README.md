An astronomical observation task trigger tool for automatically generating observation scripts and sending them to the control room.

## Features

Kinder Trigger tool is designed specifically for astronomical observations that can:

- Read observation targets from a JSON configuration file
- Automatically generate observation scripts and commands
- Produce preview images of target celestial bodies
- Send observation plans to the control room via Slack
- Support both LOT (Lulin One-meter Telescope) and SLT (SLT Telescope) modes

## Installation

### Dependencies

Git clone

```bash
git clone https://github.com/AlexLee24/Kinder_Trigger.git
```

Install required packages using pip:

```bash
pip install -r requirements.txt
```

Or using conda:

```bash
conda install --file requirements.txt
```

Note: Some packages like `slack-sdk` and `python-dotenv` may need to be installed via pip even in a conda environment:

```bash
pip install slack-sdk python-dotenv timezonefinder
```

### Environment Variables

Create a .env file and set the following environment variables:

```
SLACK_BOT_TOKEN=your_slack_token
SLACK_CHANNEL_ID_CONTROL_ROOM=control_room_channel_id
```

## Usage

### Configuring Observation Targets

Create a Trigger.json file with the following format:

```json
{
  "settings": 
  {
    "IS_LOT": false,
    "send_to_control_room": false
  },

  "targets": 
  [
    {
      "object name": "",
      "RA": "",
      "Dec": "",
      "Mag": ,
      "Priority": "",
      "Exp_By_Mag": "",
      "Filter": "",
      "Exp_Time": "",
      "Num_of_Frame": "",
      "Repeat": 
    }
  ]
}
```

### Parameter Explanation

- **IS_LOT**: Set True to generate LOT script, set to False for SLT
- **send_to_control_room**: Set to True will send script to the control room


- **object name**: Target celestial body name
- **RA**: Right Ascension (hours:minutes:seconds)
- **Dec**: Declination (degrees:minutes:seconds)
- **Mag**: Magnitude
- **Priority**: Priority level (Urgent, High(_order), Filler)
- **Exp_By_Mag**: Whether to automatically calculate exposure time based on magnitude
- **Filter**: Filters to use, e.g., up, gp, rp, ip, zp (required when Exp_By_Mag is False)
- **Exp_Time**: Exposure time in seconds (required when Exp_By_Mag is False)
- **Num_of_Frame**: Number of exposures (required when Exp_By_Mag is False)
- **Repeat**: Repeat the plan (required when Exp_By_Mag is False) (Set "0" for no repeat, set "999" for unlimit repeat)

### Priority Detail

- **Urgent**: Immediate, time‑sensitive observations, execute right away. Must specify minimum elevation or start time.
- **High(_Order)**: Important scientific targets, preferred to observe same night. Must specify minimum elevation or start time. If multiple targets are all High, please indicate priority order; otherwise the assistant will schedule them automatically. For multiple high priority: High_1, High_2. For single high priority: High.
- **Normal**: Standard targets; observe based on conditions. Prefer observations at high elevation.
- **Filler**: Filler observations after other targets are completed. No strict conditions.

### JSON Examples

#### Example 1: Automatic Exposure Time Based on Magnitude

```json
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
```

#### Example 2: Manual Exposure Settings with Multiple Filters

```json
{
    "object name": "SN 2024ggi",
    "RA": "11:18:22.087",
    "Dec": "-32:50:15.27",
    "Mag": 19.20,
    "Priority": "Normal",
    "Exp_By_Mag": "False",
    "Filter": "gp, rp",
    "Exp_Time": "300, 300",
    "Num_of_Frame": "12, 12",
    "Repeat": 0
}
```

#### Example 3: High Priority Target

```json
{
  "object name": "M31",
  "RA": "00:42:44.3",
  "Dec": "+41:16:09",
  "Mag": 3.4,
  "Priority": "High_1",
  "Exp_By_Mag": "False",
  "Filter": "up, gp, rp, ip",
  "Exp_Time": "60, 30, 30, 30",
  "Num_of_Frame": "5, 5, 5, 5",
  "Repeat": 0
}
```

#### Example 4: High Priority Target with repeat 10 times

```json
{
  "object name": "M31",
  "RA": "00:42:44.3",
  "Dec": "+41:16:09",
  "Mag": 3.4,
  "Priority": "Urgent",
  "Exp_By_Mag": "False",
  "Filter": "up, gp, rp, ip",
  "Exp_Time": "60, 30, 30, 30",
  "Num_of_Frame": "5, 5, 5, 5",
  "Repeat": 10
}
```

### Env Example
Please ask Alex on slack to get the file or token
```env
SLACK_BOT_TOKEN= Bot Token
SLACK_CHANNEL_ID_CONTROL_ROOM= Channel ID
```

### Running the Observation Plan

```bash
python Trigger.py
```

After execution, you'll see a Message that can be directly copied and pasted into a Slack channel. Use command + shift + F to convert the format to markdown.

The Object visibility plot will be generated in the obs_img folder.

## Important Notes

- Triple-check the accuracy of the observation plan before using `send_to_control_room = True`
- Ensure the .env file is not included in version control
- Make sure the obs_img directory exists or that the program has permission to create it

## Module Description

- **Trigger.py**: Main program
- **Trigger_LOT_SLT.py**: Generate the telescope script (ACP) for Lulin One meter Telescope and SLT
- **obsplan.py**: Observation planning and astronomical calculation functions (By Phil Cigan on github https://github.com/pjcigan/obsplanning)

## Developers

Kinder team and National Central University Institute of Astronomy GREAT Lab

## License

This tool is develope by the Kinder Team, for more information [Kinder_Webpage](http://kinder.astro.ncu.edu.tw)
The observation planning tool is developed based on the original code [obsplanning](https://github.com/pjcigan/obsplanning) written by Phil Cigan.

## File Structure

```
Kinder_Trigger/
├── Trigger.py           # Main program
├── Trigger_LOT_SLT.py   # Generate the telescope script (ACP)
├── obsplan.py           # Observation planning module (By Phil Cigan on github https://github.com/pjcigan/obsplanning)
├── requirements.txt     # List of dependencies
├── .env                 # Environment variable configuration (Set the slack bot token and channel id)
├── Trigger.json         # Observation target configuration
└── obs_img/             # Directory for generated observation images
