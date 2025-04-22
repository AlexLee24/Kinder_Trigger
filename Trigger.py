import json
# ========================= Setting =========================================
json_file = "Trigger.json"       # JSON file name

try:
    with open(json_file, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    
    if "settings" in json_data:
        IS_LOT = json_data["settings"].get("IS_LOT")  # True: LOT, False: SLT
        send_to_control_room = json_data["settings"].get("send_to_control_room", False)  # True: send to control room
        
    else:
        IS_LOT = "False" 
        send_to_control_room = False
    
    if "targets" in json_data:
        data = json_data["targets"]
    else:
        data = json_data
except Exception as e:
    print(f"Error: {e}")
    IS_LOT = False  
    send_to_control_room = False  
    data = []

print("====== Setting ======")
print(f"IS_LOT: {IS_LOT}")
print(f"send_to_control_room: {send_to_control_room}")
print("=====================")
check = input("Do you want to continue? (y/n): ")
if check.lower() not in ["y", ""]:
    exit()
# ===========================================================================
'''
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
'''










import os
import json
import dotenv
from datetime import datetime, timedelta

# Obsplan
import obsplan as obs
import matplotlib
matplotlib.use('Agg')

# Slack
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# Trigger
import Trigger_LOT_SLT as tri

dotenv.load_dotenv()
path_now = os.getcwd()
obs_img_dir = os.path.join(path_now, "obs_img")
plot_path = os.path.join(path_now, obs_img_dir, "Trigger_observing_tracks.jpg")
# ========================= Slack Setting (BOT) =============================
if send_to_control_room == "True":
    SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
    channel_id_control_room = os.getenv("SLACK_CHANNEL_ID_CONTROL_ROOM")
    if not SLACK_BOT_TOKEN or not channel_id_control_room:
        print("Please set the SLACK_BOT_TOKEN environment variable.")
        print("For example, create a .env file with the following content:")
        print("SLACK_BOT_TOKEN= your_token")
        print("SLACK_CHANNEL_ID_CONTROL_ROOM= channel_id")
        exit(1)
    else:
        client = WebClient(token=SLACK_BOT_TOKEN)
# ===========================================================================

# ========================= Function ========================================
def check_for_updates():
    import subprocess
    import sys
    try:
        print("Checking for updates...")
        # Fetch latest remote information
        subprocess.run(['git', 'fetch'], check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        # Check if local repository is behind remote
        result = subprocess.run(['git', 'rev-list', '--count', 'HEAD..origin/main'], 
                              check=False, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        
        commits_behind = result.stdout.decode('utf-8').strip()
        if commits_behind and int(commits_behind) > 0:
            print(f"\nUpdate available! Your local code is {commits_behind} commits behind the GitHub version.")
            print("It is recommended to use 'git pull' to update your code for the latest features and bug fixes.\n")
            
            update_now = input("Update now? (y/n): ")
            if update_now.lower() == 'y':
                print("Updating...")
                subprocess.run(['git', 'pull'], check=False)
                print("Update complete, please restart the program.")
                sys.exit(0)
        else:
            print("Your code is up to date.")
    except Exception as e:
        print(f"Cannot check for updates: {e}")
check_for_updates()
# read json file
def read_json(file):
    with open(file, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    
    if "targets" in json_data:
        return json_data["targets"]
    else:
        return json_data

# send slack message
def send_slack_message(message, file_path, channel_id):
    try:
        client.chat_postMessage(
            channel=channel_id, 
            text=message
        )
        client.files_upload_v2(
            channel=channel_id,
            file=file_path 
        )
    except SlackApiError as e:
        print(f"Send message to Slack failed: {e.response['error']}")

if not os.path.exists(obs_img_dir):
    os.makedirs(obs_img_dir)
    print(f"Create folder: {obs_img_dir}")
# ===========================================================================

# ========================= Main =============================================
slack_message = (
    "您好，若天氣允許，以下是今日的觀測目標:\n"
    "If the weather permits, here are today's observation targets:\n"
)
script = "script:\n```\n"
data = read_json(json_file)
now = datetime.now()
current_day = now.strftime("%Y-%m-%d")

target_list = []
for obj in data:
    object_name = obj["object name"]
    ra = obj["RA"]
    dec = obj["Dec"]
    Mag = obj["Mag"]
    Priority = obj["Priority"]
    exp_by_mag = obj["Exp_By_Mag"]
    filter_val = obj["Filter"]
    exp_time = obj["Exp_Time"]
    count = obj["Num_of_Frame"]
    Repeat = obj["Repeat"]
    
    # generate image
    object_name_show = f"{object_name}"
    target = obs.create_ephem_target(object_name_show, ra, dec)
    target_list.append(target)

    # generate script
    if exp_by_mag == "True":
        script += tri.generate_script(object_name, ra, dec, Mag, Priority, IS_LOT, Repeat, auto_exp=True)
    else:
        script += tri.generate_script(object_name, ra, dec, Mag, Priority, IS_LOT, Repeat, auto_exp=False, filter_input=filter_val, exp_time=exp_time, count=count)

img_path = tri.generate_img(current_day, target_list)
final_message = slack_message + script + "```"
print("=====================")
print(final_message)
print("=====================")

if send_to_control_room == "True":
    check2 = input("Do you really want to send this trigger to contro; room?(y/n): ")
    if check2 == "y":
        send_slack_message(final_message, img_path, channel_id_control_room)
        print("Send message to control room")
    else:
        print("Did not send message to control room")
        exit()
