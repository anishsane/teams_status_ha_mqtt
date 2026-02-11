# Teams status - home assistant via MQTT

Add MS Teams status as home assistant sensors and buttons.


MS Teams supports [third-party devices API](https://support.microsoft.com/en-us/office/connect-to-third-party-devices-in-microsoft-teams-aabca9f2-47bb-407f-9f9b-81a104a883d6).
When it is enabled, some aspects of MS Teams meetings can be observed and controlled by sending commands over the WebSocket.

## What it does
This script creates an MQTT device in Home Assistant via discovery messages. The device has:

1. Binary sensors for  
    1. Meeting in progress  
    2. Microphone unmuted  
    3. Video on  
    4. Meeting recording on  
    5. Unread messages  

2. mute/unmute switch
3. Buttons for
     1. Exit meeting
     2. Stop video (By default, this is created as a 'stop video' button. It can be changed to a switch by a script change.)
     3. Stop screen sharing

The binary sensors can be used for automation. (e.g., like [presencelight](https://github.com/isaacrlevin/presencelight))  
The switches and buttons can be used to interact with the team's meeting.

## Setup:

0. Initial setup:  
    1. Set up [MQTT integration](https://www.home-assistant.io/integrations/mqtt/) in Home Assistant.  
    2. [Enable third party api](https://support.microsoft.com/en-us/office/connect-to-third-party-devices-in-microsoft-teams-aabca9f2-47bb-407f-9f9b-81a104a883d6) in MS teams.
   
1. This script is an initial script and currently needs modifications in the code to set these parameters:

    MQTT_SERVER # Point to your MQTT server and port  
    MQTT_PORT  
    MQTT_USER # MQTT server's credentials  
    MQTT_PASSWORD
 
2. Install dependencies

    pip3 install -r requirements.txt

3. Running as a Windows startup script:
   
   Rename the script as `.pyw` and add it to the user startup. You can use the task scheduler/registry/startup folder, or any other method of your choice for this.  

4. Running as a service in WSL2:
   
   WSL2 typically runs under a separate network within the Windows machine. Hence, the teams websocket is not directly accessible from WSL2.  
   You can force a 'mirrored' network by setting `networkingMode=mirrored` in %USERPROFILE%\\.wslconfig  
   After this, you can simply run the Python script as a regular systemd service.


## Acknowledgements
1. https://github.com/AntoineGS/teams-status-rs/ (Rust)  
   I based most of the logic on this code. However, I wanted to extend some functionality, and I was unfamiliar with Rust.
2. https://github.com/MrRoundRobin/TeamsLocalApi/blob/main/src/ClientMessage.cs (C#)  

## Disclaimer
This script was implemented to suit my requirements. It may or may not be useful as-is for your requirements. Feel free to modify it to suit your requirements.
