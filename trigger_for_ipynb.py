def trigger(json_config):    
    import os
    import json
    import dotenv
    from datetime import datetime, timedelta

    # Obsplan module for observation planning
    import obsplan as obs

    # Use non-interactive matplotlib backend
    import matplotlib
    matplotlib.use('Agg')

    # Slack modules for sending message and file uploads
    from slack_sdk import WebClient
    from slack_sdk.errors import SlackApiError

    # Trigger module for generating scripts and images
    import Trigger_LOT_SLT as tri

    # Load environment variables from .env file if needed
    dotenv.load_dotenv()

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
    
    # ========================= JSON Configuration ============================
    # Embed the JSON configuration directly into the notebook


    # Load configuration from the JSON string
    config_data = json.loads(json_config)

    # Extract settings from the configuration
    if "settings" in config_data:
        IS_LOT = config_data["settings"].get("IS_LOT")  # "False" or "True" as string
        send_to_control_room = config_data["settings"].get("send_to_control_room", False)
    else:
        IS_LOT = "False"
        send_to_control_room = False

    # Extract targets from the configuration
    if "targets" in config_data:
        data = config_data["targets"]
    else:
        data = config_data

    print("====== Setting ======")
    print(f"IS_LOT: {IS_LOT}")
    print(f"send_to_control_room: {send_to_control_room}")
    print("=====================")

    # Prompt user for confirmation (optional in notebook)
    check = input("Do you want to continue? (y/n): ")
    if check.lower() not in ["y", ""]:
        exit()

    # ========================= Set up directories and Slack ===================
    # Get current working directory and define observation image directory path
    path_now = os.getcwd()
    obs_img_dir = os.path.join(path_now, "obs_img")
    plot_path = os.path.join(obs_img_dir, "Trigger_observing_tracks.jpg")

    # Set up Slack client if message sending is enabled
    if send_to_control_room == "True":
        SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
        channel_id_control_room = os.getenv("SLACK_CHANNEL_ID_CONTROL_ROOM")
        if not SLACK_BOT_TOKEN or not channel_id_control_room:
            print("Please set the SLACK_BOT_TOKEN and SLACK_CHANNEL_ID_CONTROL_ROOM environment variables.")
            print("For example, create a .env file with these variables.")
            exit(1)
        else:
            client = WebClient(token=SLACK_BOT_TOKEN)

    # ========================= Helper Functions ================================
    def send_slack_message(message, file_path, channel_id):
        """
        Send a message and a file to a Slack channel.
        """
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

    # Create the observation image directory if it does not exist
    if not os.path.exists(obs_img_dir):
        os.makedirs(obs_img_dir)
        print(f"Created folder: {obs_img_dir}")

    # ========================= Main Execution ==================================
    # Prepare the Slack message header
    slack_message = (
        "您好，若天氣允許，以下是今日的觀測目標:\n"
        "If the weather permits, here are today's observation targets:\n"
    )
    script = "script:\n```\n"

    now = datetime.now()
    current_day = now.strftime("%Y-%m-%d")

    target_list = []
    # Loop through each target object specified in the configuration
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
        
        # Create an observation target using the obsplan module
        target = obs.create_ephem_target(object_name, ra, dec)
        target_list.append(target)
        
        # Generate the observing script based on the exposure settings
        if exp_by_mag == "True":
            script += tri.generate_script(object_name, ra, dec, Mag, Priority, IS_LOT, Repeat, auto_exp=True)
        else:
            script += tri.generate_script(object_name, ra, dec, Mag, Priority, IS_LOT, Repeat, 
                                            auto_exp=False, filter_input=filter_val, exp_time=exp_time, count=count)

    # Generate image for observing tracks
    img_path = tri.generate_img(current_day, target_list)
    final_message = slack_message + script + "```"

    print("=====================")
    print(final_message)
    print("=====================")

    # If send_to_control_room is enabled, ask for final confirmation and send Slack message
    if send_to_control_room == "True":
        check2 = input("Do you really want to send this trigger to control room?(y/n): ")
        if check2.lower() == "y":
            send_slack_message(final_message, img_path, channel_id_control_room)
            print("Sent message to control room")
        else:
            print("Did not send message to control room")
