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
    "Num_of_Frame": ""
  }
]
```

### Parameter Explanation

- **object name**: Target celestial body name
- **RA**: Right Ascension (hours:minutes:seconds)
- **Dec**: Declination (degrees:minutes:seconds)
- **Mag**: Magnitude
- **Priority**: Priority level (None, First, Top or Higher)
- **Exp_By_Mag**: Whether to automatically calculate exposure time based on magnitude
- **Filter**: Filters to use, e.g., up, gp, rp, ip, zp (required when Exp_By_Mag is False)
- **Exp_Time**: Exposure time in seconds (required when Exp_By_Mag is False)
- **Num_of_Frame**: Number of exposures (required when Exp_By_Mag is False)

### JSON Examples

#### Example 1: Automatic Exposure Time Based on Magnitude

```json
{
    "object name": "SN 2024ggi",
    "RA": "11:18:22.087",
    "Dec": "-32:50:15.27",
    "Mag": 19.20,
    "Priority": "None",
    "Exp_By_Mag": "True",
    "Filter": "",
    "Exp_Time": "",
    "Num_of_Frame": ""
}
```

#### Example 2: Manual Exposure Settings with Multiple Filters

```json
{
    "object name": "SN 2024ggi",
    "RA": "11:18:22.087",
    "Dec": "-32:50:15.27",
    "Mag": 19.20,
    "Priority": "None",
    "Exp_By_Mag": "False",
    "Filter": "gp, rp",
    "Exp_Time": "300, 300",
    "Num_of_Frame": "12, 12"
}
```

#### Example 3: High Priority Target

```json
{
  "object name": "M31",
  "RA": "00:42:44.3",
  "Dec": "+41:16:09",
  "Mag": 3.4,
  "Priority": "Top",
  "Exp_By_Mag": "False",
  "Filter": "up, gp, rp, ip",
  "Exp_Time": "60, 30, 30, 30",
  "Num_of_Frame": "5, 5, 5, 5"
}
```

### Running the Observation Plan

Before running the Trigger.py, need to change the setting in the python file.

Set `IS_LOT` to `True` in Trigger.py, to generate the LOT script, set to `False` for SLT.

Set `send_to_control_room` to `True` in Trigger.py, and the system will ask for confirmation before sending the observation plan to the control room.

```bash
python Trigger.py
```

## Important Notes

- Triple-check the accuracy of the observation plan before using `send_to_control_room = True`
- Ensure the .env file is not included in version control
- Make sure the obs_img directory exists or that the program has permission to create it

## Module Description

- **Trigger.py**: Main program
- **Trigger_LOT_SLT.py**: Generate the telescope script (ACP) for Lulin One meter Telescope and SLT
- **obsplan.py**: Observation planning and astronomical calculation functions (By Phil Cigan on github https://github.com/pjcigan/obsplanning)

## Developers

Kinder team and National Central University Astronomy Institute GREAT Lab

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
