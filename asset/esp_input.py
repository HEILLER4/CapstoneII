# asset/esp_input.py
import requests
import time
import logging

ESP32_STATUS_ENDPOINT = "http://192.168.206.37:8080/esp32/data"  # Update to your ESP32 IP
BUTTON_ACTION_COOLDOWN = 3  # seconds

last_button_state = None
last_action_time = 0

def monitor_esp32_input(handle_button_command):
    global last_button_state, last_action_time

    while True:
        try:
            response = requests.get(ESP32_STATUS_ENDPOINT, timeout=2)
            if response.ok:
                data = response.json()
                buttons = data.get("buttons")
                now = time.time()

                if buttons and buttons != last_button_state and now - last_action_time > BUTTON_ACTION_COOLDOWN:
                    last_button_state = buttons
                    last_action_time = now
                    logging.info(f"[ESP32] Buttons changed to: {buttons}")
                    handle_button_command(buttons)
        except Exception as e:
            logging.warning(f"[ESP32] Polling failed: {e}")

        time.sleep(1)
