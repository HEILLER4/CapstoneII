from flask import Flask, request, jsonify
import threading
import logging
import json
import time
from collections import defaultdict

# Flask app setup
app = Flask(__name__)

# Globals (assume integrated with navigation system)
announce_level = 1
halt_announcements = False
emergency_triggered = False
SAVE_FILE = "saved_locations.json"

# Button press state
button_timestamps = defaultdict(list)
DOUBLE_CLICK_THRESHOLD = 0.4  # seconds
HOLD_THRESHOLD = 1.0          # seconds

# Placeholder for external functions

def speak(msg):
    print(f"[SPEAK] {msg}")
    # Integrate with pyttsx3 or ThreadSafeTTS if used elsewhere

def save_location():
    print("[ACTION] Save current location")
    speak("Saving current location")
    # Implement actual save logic here

def send_sms():
    print("[ACTION] Send emergency SMS")
    speak("Sending emergency SMS")
    # Implement actual SMS logic here

def start_routing():
    print("[ACTION] Start routing")
    speak("Starting navigation routing")
    # Implement actual routing logic here

def setup_emergency_contact():
    print("[ACTION] Setup emergency contact")
    speak("Setting up emergency contact")
    # Implement actual setup logic here

def process_esp32_payload(data):
    global announce_level, halt_announcements, emergency_triggered
    try:
        buttons = data.get("buttons", "0000")
        timestamp = time.time()

        for i, state in enumerate(buttons):
            if state == "1":
                button_timestamps[i].append(timestamp)
                # Trim old presses
                button_timestamps[i] = [t for t in button_timestamps[i] if timestamp - t < 2.0]

                press_times = button_timestamps[i]
                time_diff = press_times[-1] - press_times[0] if len(press_times) > 1 else 0
                hold_detected = len(press_times) >= 1 and (timestamp - press_times[-1]) > HOLD_THRESHOLD

                # Handle button functions
                if i == 0:
                    if hold_detected:
                        save_location()
                    elif len(press_times) >= 2 and time_diff < DOUBLE_CLICK_THRESHOLD:
                        speak("Rapid double click: toggling debug mode")
                    else:
                        announce_level += 1
                        speak(f"Announcement level increased to {announce_level}")

                elif i == 1:
                    if hold_detected:
                        start_routing()
                    else:
                        announce_level = max(1, announce_level - 1)
                        speak(f"Announcement level decreased to {announce_level}")

                elif i == 2:
                    halt_announcements = not halt_announcements
                    state = "halted" if halt_announcements else "resumed"
                    speak(f"Announcements {state}")

                elif i == 3:
                    if hold_detected:
                        setup_emergency_contact()
                    else:
                        emergency_triggered = True
                        speak("Emergency button pressed")
                        send_sms()

    except Exception as e:
        logging.error(f"Error processing ESP32 payload: {e}")

@app.route("/esp32/data", methods=["POST"])
def esp32_data():
    try:
        data = request.get_json(force=True)
        threading.Thread(target=process_esp32_payload, args=(data,), daemon=True).start()
        return jsonify({"status": "ok"})
    except Exception as e:
        logging.error(f"Error in /esp32/data endpoint: {e}")
        return jsonify({"status": "error", "error": str(e)}), 500

if __name__ == "__main__":
    logging.basicConfig(filename="server.log", level=logging.INFO, format="%(asctime)s - %(message)s")
    logging.info("Starting integrated ESP32 Flask server")
    app.run(host="0.0.0.0", port=8080)
