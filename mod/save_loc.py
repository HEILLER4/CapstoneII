# save_location_button.py

import RPi.GPIO as GPIO
import time
import json
from mod.GP_s import get_current_location_info
import pyttsx3

SAVE_BUTTON_PIN = 5
SAVE_FILE = "saved_locations.json"

GPIO.setmode(GPIO.BCM)
GPIO.setup(SAVE_BUTTON_PIN, GPIO.IN, pull_up_down=GPIO.PUD_UP)
engine = pyttsx3.init()

def speak(msg):
    print("[SPEAK]:", msg)
    engine.say(msg)
    engine.runAndWait()

def save_location():
    loc = get_current_location_info()
    if not loc:
        speak("Unable to fetch GPS location.")
        return

    location_data = {
        "coordinates": loc['coordinates'],
        "address": loc['address']['full_address'],
        "timestamp": time.time()
    }

    try:
        with open(SAVE_FILE, "r") as f:
            data = json.load(f)
    except FileNotFoundError:
        data = []

    data.append(location_data)

    with open(SAVE_FILE, "w") as f:
        json.dump(data, f, indent=4)

    speak("Location saved successfully.")

def monitor_button():
    speak("Location save monitor active.")
    while True:
        if GPIO.input(SAVE_BUTTON_PIN) == GPIO.LOW:
            save_location()
            time.sleep(1)  # debounce

if __name__ == "__main__":
    try:
        monitor_button()
    except KeyboardInterrupt:
        GPIO.cleanup()