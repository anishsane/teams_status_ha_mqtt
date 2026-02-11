import websocket
import time
import rel
import sys
import platform
import json
import keyring
from getpass import getuser
import paho.mqtt.client as mqtt

SERVICE_NAME = "teams_status"
USER_NAME = getuser()

DEVICE = platform.node()

KEYRING_PASSWORD = "placeholder"
KEYRING_SERVICE_NAME = SERVICE_NAME
KEYRING_SERVICE_USER_NAME = USER_NAME

MQTT_SERVER = "mqtt.server"
MQTT_PORT = 1883
MQTT_USER = '<mqtt_username>'
MQTT_PASSWORD = '<mqtt_password>'
MQTT_CLIENT_ID = f"{SERVICE_NAME}-{USER_NAME}"

MQTT_DEVICE = {
    "identifiers":f"{SERVICE_NAME}-{DEVICE}",
    "manufacturer":"Anish Sane",
    "model":SERVICE_NAME,
    "name":f"{DEVICE} MS teams status",
    "sw_version":"1.0.0",
}

try:
    import sys
    if (sys.platform == "linux") and ('WSL' in open('/proc/version').read()):
        # MS windows can handle `keyring` via Windows credentials store.
        # Linux usually handles it via keyring manager like gnome-keyring-manager.
        # WSL cannot access these directly.
        # CryptFileKeyring is a low-trust keyring that stores the passwords on the filesystem.
        # You can choose any other keyring here if you want.
        from keyrings.cryptfile.cryptfile import CryptFileKeyring
        kr = CryptFileKeyring()
        kr.keyring_key = KEYRING_PASSWORD
        keyring.set_keyring(kr)
except:
    print("WSL detected, but keyring could not be accessed. Functionality may fail. Not exiting here, in case you have installed an alternate keyring mechanism.")

try:
    TEAMS_AUTH_TOKEN = keyring.get_password(KEYRING_SERVICE_NAME, KEYRING_SERVICE_USER_NAME)
    if not TEAMS_AUTH_TOKEN:
        print("TEAMS_AUTH_TOKEN was not obtained. If this connection is already approved in the past, then the keyring should return a valid token.")
except:
    TEAMS_AUTH_TOKEN = ''

ICONS = {
    "isinmeeting"       : ["mdi:phone-in-talk",    "mdi:phone-off"],
    "isunmuted"         : ["mdi:microphone",       "mdi:microphone-off"],
    "isvideoon"         : ["mdi:webcam",           "mdi:webcam-off"],
    "isrecordingon"     : ["mdi:record-rec",       "mdi:power-off"],
    "issharing"         : ["mdi:projector-screen", "mdi:projector-screen-off"],
    "hasunreadmessages" : ["mdi:message-alert",    "mdi:message-off"],
}
SENSOR_LABELS = {
    "isinmeeting"       : "Meeting in progress",
    "isunmuted"         : "Microphone unmuted",
    "isvideoon"         : "Video",
    "isrecordingon"     : "Recording",
    "issharing"         : "Screen sharing",
    "hasunreadmessages" : "Unread messages",
}
CONTROL_LABELS = {
    "isinmeeting"       : "Exit meeting",
    "issharing"         : "Stop screen sharing",
    "isvideoon"         : "Stop video",
}

class TeamsStatus():
    isinmeeting       = None
    isunmuted         = None
    isvideoon         = None
    isrecordingon     = None
    issharing         = None
    hasunreadmessages = None

    canToggleMute = False
    canToggleVideo = False
    canLeave = False
    canStopSharing = False

    subscribed_topics = []
    control_availibility = []

    @staticmethod
    def check_and_set(name, message, can_switch_off = True, can_switch_on = False, inverted_name = None):
        try:
            if inverted_name:
                new_val = not message.get(inverted_name, False)
            else:
                new_val = message.get(name, False)
            name = name.lower()
            old_val = TeamsStatus.__dict__[name]
            setattr(TeamsStatus, name, new_val)
            new_val = new_val and TeamsStatus.isinmeeting
            if new_val == old_val: return
            print(name, TeamsStatus.__dict__[name], new_val)

            control_availability = TeamsStatus.isinmeeting and can_switch_off

            if not can_switch_on:
                control_availability = control_availability and new_val

            TeamsStatus.send_mqtt_state(name, new_val, can_switch_off, can_switch_on, control_availability)

            #Hack to set the icon, since mqtt integration does not allow setting it via json attribute topic
            TeamsStatus.send_mqtt_config(name, new_val, can_switch_off, can_switch_on)

        except Exception as e:
            print(e)

    @staticmethod
    def disable_all_controls():
        for i in TeamsStatus.control_availibility:
            mqtt_client.publish(i, "offline", qos=2, retain=False)

    @staticmethod
    def send_mqtt_state(name, value, can_switch_off, can_switch_on, availability):
        switch_or_button = "switch" if can_switch_on else "button"
        mqtt_client.publish(f"homeassistant/binary_sensor/{DEVICE}-{SERVICE_NAME}", "online", qos=2, retain=False)
        mqtt_client.publish(f"homeassistant/binary_sensor/{DEVICE}-{SERVICE_NAME}/{name}/state", "ON" if value else "OFF", qos=2, retain=False)
        mqtt_client.publish(f"homeassistant/{switch_or_button}/{DEVICE}-{SERVICE_NAME}/{name}/state", "ON" if value else "OFF", qos=2, retain=False)
        mqtt_client.publish(f"homeassistant/{switch_or_button}/{DEVICE}-{SERVICE_NAME}/{name}/availability", "online" if availability else "offline", qos=2, retain=False)

    @staticmethod
    def mqtt_subscribe(topic):
        if topic not in TeamsStatus.subscribed_topics:
            TeamsStatus.subscribed_topics.append(topic)
            mqtt_client.subscribe(topic, 0)

    @staticmethod
    def mqtt_resubscribe():
        for topic in TeamsStatus.subscribed_topics:
            mqtt_client.unsubscribe(topic)
            mqtt_client.subscribe(topic, 0)

    @staticmethod
    def send_mqtt_config(name, state=False, can_switch_off=True, can_switch_on=False):
        unique_id = f"{DEVICE}-{SERVICE_NAME}-{name}"
        binary_sensor_config = {
            "icon": ICONS[name][0 if state else 1],
            "unique_id": f"{unique_id}-binary_sensor",
            "object_id": f"{unique_id}-binary_sensor",
            "default_entity_id": f"binary_sensor.{unique_id}",
            "availability_topic": f"homeassistant/binary_sensor/{DEVICE}-{SERVICE_NAME}",
            "device": MQTT_DEVICE,
            "name": SENSOR_LABELS[name],
            "state_topic": f"homeassistant/binary_sensor/{DEVICE}-{SERVICE_NAME}/{name}/state",
        }
        binary_sensor_topic = f"homeassistant/binary_sensor/{DEVICE}-{SERVICE_NAME}/{name}/config"
        mqtt_client.publish(binary_sensor_topic, json.dumps(binary_sensor_config), qos=2, retain=False)
        mqtt_client.publish(binary_sensor_config["state_topic"], state, qos=2, retain=False)

        switch_or_button = "switch" if can_switch_on else "button"
        switch_or_button_config = {
            "icon": ICONS[name][0 if state else 1],
            "unique_id": f"{unique_id}-{switch_or_button}",
            "object_id": f"{unique_id}-{switch_or_button}",
            "default_entity_id": f"{switch_or_button}.{unique_id}",
            "availability_topic": f"homeassistant/{switch_or_button}/{DEVICE}-{SERVICE_NAME}/{name}/availability",
            "device": MQTT_DEVICE,
            "name": CONTROL_LABELS[name] if (name in CONTROL_LABELS and not can_switch_on) else SENSOR_LABELS[name],
            "state_topic": f"homeassistant/{switch_or_button}/{DEVICE}-{SERVICE_NAME}/{name}/state",
            "command_topic": f"homeassistant/{switch_or_button}/{DEVICE}-{SERVICE_NAME}/{name}/cmnd",
            "optimistic": False,
        }
        if can_switch_off:
            switch_or_button_topic = f"homeassistant/{switch_or_button}/{DEVICE}-{SERVICE_NAME}/{name}/config"
            mqtt_client.publish(switch_or_button_topic, json.dumps(switch_or_button_config), qos=2, retain=False)

        if switch_or_button_config["availability_topic"] not in TeamsStatus.control_availibility:
            TeamsStatus.control_availibility.append(switch_or_button_config["availability_topic"])

        TeamsStatus.mqtt_subscribe(switch_or_button_config["command_topic"])

    @staticmethod
    def init_connection_button():
        unique_id = f"{DEVICE}-{SERVICE_NAME}-init-connection"
        button_config = {
            "icon": "mdi:button-pointer",
            "unique_id": unique_id,
            "object_id": unique_id,
            "default_entity_id": f"switch.{unique_id}",
            "device": MQTT_DEVICE,
            "name": "Init Connection",
            "command_topic": f"homeassistant/button/{DEVICE}-{SERVICE_NAME}/init-connection/cmnd",
            "optimistic": False,
        }
        button_topic = f"homeassistant/button/{DEVICE}-{SERVICE_NAME}/init-connection/config"
        mqtt_client.publish(button_topic, json.dumps(button_config), qos=2, retain=False)
        TeamsStatus.mqtt_subscribe(button_config["command_topic"])

        TeamsStatus.send_mqtt_config('isinmeeting')
        TeamsStatus.send_mqtt_config('isunmuted', can_switch_on=True)
        TeamsStatus.send_mqtt_config('isvideoon') # If you want to allow switching the video on, set can_switch_on=True here.
        TeamsStatus.send_mqtt_config('isrecordingon', can_switch_off=False)
        TeamsStatus.send_mqtt_config('issharing')
        TeamsStatus.send_mqtt_config('hasunreadmessages', can_switch_off=False)
        TeamsStatus.disable_all_controls()

    @staticmethod
    def on_teams_update(message):
        if not 'meetingUpdate' in message: return
        if 'meetingPermissions' in message['meetingUpdate']:
            TeamsStatus.canToggleMute  = message['meetingUpdate']['meetingPermissions'].get('canToggleMute', False)
            TeamsStatus.canToggleVideo = message['meetingUpdate']['meetingPermissions'].get('canToggleVideo', False)
            TeamsStatus.canLeave       = message['meetingUpdate']['meetingPermissions'].get('canLeave', True)
            TeamsStatus.canStopSharing = message['meetingUpdate']['meetingPermissions'].get('canStopSharing', False)

        meetingState = message['meetingUpdate'].get('meetingState', {})

        TeamsStatus.check_and_set('isInMeeting', meetingState, TeamsStatus.canLeave)
        TeamsStatus.check_and_set('isUnmuted', meetingState, TeamsStatus.canToggleMute, inverted_name="isMuted", can_switch_on = True)
        TeamsStatus.check_and_set('isVideoOn', meetingState, TeamsStatus.canToggleVideo)
        TeamsStatus.check_and_set('isRecordingOn', meetingState, False)
        TeamsStatus.check_and_set('isSharing', meetingState, TeamsStatus.canStopSharing)
        TeamsStatus.check_and_set('hasUnreadMessages', meetingState, False)

        if not TeamsStatus.isinmeeting:
            TeamsStatus.disable_all_controls()

# Some aspects of MS Teams meeting can be controlled by sending commands over the websocket.
#
# Available commands:
# query-state mute unmute toggle-mute hide-video show-video toggle-video unblur-background blur-background toggle-background-blur lower-hand raise-hand toggle-hand leave-call send-react toggle-ui stop-sharing
# Deprecated commands:
# stop-recording start-recording toggle-recording
#
# Some commands need additional parameters. See the sample usage section below.
# Commands list courtesy:
# https://github.com/MrRoundRobin/TeamsLocalApi/blob/main/src/ClientMessage.cs
#
# Sample command usage:
# ws.send('{"requestId":1,"apiVersion":"2.0.0","action":"mute"}')
# ws.send('{"requestId":2,"apiVersion":"2.0.0","action":"toggle-mute"}')
# ws.send('{"requestId":3,"apiVersion":"2.0.0","action":"toggle-ui","parameters":{"type":"chat"}}')
#
# Sample json string for meeting state update:
# {"meetingUpdate":{"meetingState":{"isMuted":true,"isVideoOn":false,"isHandRaised":false,"isInMeeting":true,"isRecordingOn":false,"isBackgroundBlurred":false,"isSharing":false,"hasUnreadMessages":false},"meetingPermissions":{"canToggleMute":true,"canToggleVideo":true,"canToggleHand":true,"canToggleBlur":false,"canLeave":true,"canReact":true,"canToggleShareTray":true,"canToggleChat":true,"canStopSharing":false,"canPair":false}}}

ws = None

def on_ws_close(_ws, close_status_code, close_msg):
    global ws
    print(f"Closed websocket connection {close_status_code}: {close_msg}")
    ws = None
    rel.abort()

def on_ws_open(ws):
    print("Opened websocket connection")

def on_ws_error(ws, error):
    print("on_ws_error:", error)

def on_ws_message(ws, message):
    global TEAMS_AUTH_TOKEN
    print(f"Message received:\n{message}\n\n")
    message = json.loads(message)
    if 'tokenRefresh' in message:
        TEAMS_AUTH_TOKEN = message['tokenRefresh']
        keyring.set_password(KEYRING_SERVICE_NAME, KEYRING_SERVICE_USER_NAME, TEAMS_AUTH_TOKEN)
    else:
        TeamsStatus.on_teams_update(message)

def ws_send_command(cmnd, params = None):
    if 'requestId' not in ws_send_command.__dict__:
        ws_send_command.requestId = 0
    ws_send_command.requestId = ws_send_command.requestId + 1
    if params:
        ws.send(f'{{"requestId":{ws_send_command.requestId},"apiVersion":"2.0.0","action":"{cmnd}","parameters":{json.dumps(params)}}}')
    else:
        ws.send(f'{{"requestId":{ws_send_command.requestId},"apiVersion":"2.0.0","action":"{cmnd}"}}')

def on_mqtt_message(client, userdata, message, tmp=None):
    ha, domain, device, entity, cmnd = message.topic.split('/')

    command_maps = {
        "init-connection": ["toggle-ui", {"type":"chat"}], # This was chosen as a least intrusive action that needs approval.
        "isinmeeting": "leave-call",
        "isunmuted/on": "unmute",
        "isunmuted/off": "mute",
        "isvideoon/on": "show-video",
        "isvideoon/off": "hide-video",
        "isvideoon": "hide-video",
        "issharing": "stop-sharing",
    }

    if domain == 'button':
        key = entity
    if domain == 'switch':
        key = f"{entity}/{message.payload.decode('ascii').lower()}"

    if key in command_maps:
        if isinstance(command_maps[key], str):
            ws_send_command(command_maps[key])
        else:
            ws_send_command(*command_maps[key])

    if key == "init-connection":
        time.sleep(1)
        ws_send_command("toggle-ui", {"type":"chat"})

def on_mqtt_connect(client, userdata, flags, rc):
    print("mqtt (re)connected. Resubscribing to the topics.")
    TeamsStatus.mqtt_resubscribe()

mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)
mqtt_client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
mqtt_client.connect(MQTT_SERVER, port=MQTT_PORT)
mqtt_client.on_message = on_mqtt_message
mqtt_client.on_connect = on_mqtt_connect
mqtt_client.loop_start()

TeamsStatus.init_connection_button()

def ws_run_till_interrupted():
    print("(re)init ws")
    global ws
    ws = websocket.WebSocketApp(f"ws://localhost:8124?token={TEAMS_AUTH_TOKEN}&protocol-version=2.0.0&manufacturer=Anish_Sane&device={DEVICE}&app=Anish_sane_teams_status&app-version=1.0",
        on_open=on_ws_open,
        on_message=on_ws_message,
        on_error=on_ws_error,
        on_close=on_ws_close)

    ws.run_forever(dispatcher=rel, reconnect=5)
    rel.signal(2, sys.exit)   # Keyboard Interrupt
    rel.signal(15, sys.exit)  # SIGTERM
    rel.dispatch()

while True:
    try:
        if ws is None:
            ws_run_till_interrupted()
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception as e:
        print(e)
        del ws
        ws = None
