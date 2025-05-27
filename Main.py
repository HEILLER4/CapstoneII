import threading
import time
import pyttsx3
import requests
import urllib.parse
import os
import json
import RPi.GPIO as GPIO
import serial
import cv2
import numpy as np

from mod.GP_s import get_current_location_info
from mod.voiice import listen_for_command
from mod.obs import ObstacleMonitor
from mod.monitor import CrowdMonitor
from asset.distanc import get_distance, SENSORS
from mod.geoc import geocode_opencage
from asset.Headless import NanoDetDetector
from asset.Nanodet import NanoDetVisualizer

# Shared state
engine = pyttsx3.init()
detection_engine = None
crowd_monitor = CrowdMonitor()
GRAPH_HOPPER_URL = "http://localhost:8989/route"

# Camera config
ESP32_CAM_URL = "http://192.168.4.2/stream"
USE_ESP32_CAM = True

# GPIO setup
BUTTON_INCREASE = 17
BUTTON_DECREASE = 27
BUTTON_HALT = 22
BUTTON_SAVE = 23
BUTTON_EMERGENCY = 24

GPIO.setmode(GPIO.BCM)
GPIO.setup(BUTTON_INCREASE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BUTTON_DECREASE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BUTTON_HALT, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BUTTON_SAVE, GPIO.IN, pull_up_down=GPIO.PUD_UP)
GPIO.setup(BUTTON_EMERGENCY, GPIO.IN, pull_up_down=GPIO.PUD_UP)

announce_level = 1
halt_announcements = False
SERIAL_PORT = "/dev/ttyS0"
BAUD_RATE = 115200
emergency_number = None
SAVE_FILE = "saved_locations.json"


def speak(msg):
    print("[SPEAK]:", msg)
    engine.say(msg)
    engine.runAndWait()


def get_saved_location(name):
    if not os.path.exists(SAVE_FILE):
        return None
    with open(SAVE_FILE, 'r') as f:
        data = json.load(f)
        for loc in data:
            if loc["name"].lower() == name.lower():
                return tuple(loc["coordinates"])
    return None


def gps_and_voice():
    location = get_current_location_info()
    if location:
        coords = location['coordinates']
        address = location['address']['full_address']
        speak(f"Current location: {address}")
    else:
        speak("Failed to acquire GPS location.")
        return

    destination = listen_for_command()
    speak(f"Destination received: {destination}")

    dest_coords = get_saved_location(destination)
    if not dest_coords:
        speak("Searching address online. Please wait...")
        dest_coords = geocode_opencage(destination)
        if not dest_coords:
            speak("Destination not found. Please try a different address.")
            return
        else:
            speak("Location found and coordinates acquired.")

    dest_lat, dest_lon = dest_coords

    speak("Setting up navigation route. Please wait.")
    gh_url = f"{GRAPH_HOPPER_URL}?point={coords[0]},{coords[1]}&point={dest_lat},{dest_lon}&vehicle=foot&locale=en&instructions=true"
    try:
        gh_response = requests.get(gh_url)
        gh_data = gh_response.json()
        if 'paths' in gh_data:
            for instr in gh_data['paths'][0]['instructions']:
                speak(instr['text'])
                time.sleep(1)
        else:
            raise ValueError("Invalid GraphHopper response")
    except Exception as e:
        print("GraphHopper error:", e)
        speak("Failed to get route from GraphHopper.")

    speak("Route ready. Proceeding with detection.")


def run_detection():
    global detection_engine
    visualizer = NanoDetVisualizer("config/nanodet.yaml", "model/nanodet.pth")
    visualizer.on_detect = lambda dets: detection_engine.on_detect(dets) if detection_engine else None
    visualizer.process_camera(
        url=ESP32_CAM_URL if USE_ESP32_CAM else 0,
        on_detect=lambda dets: [
            crowd_monitor.update_detection_time(),
            crowd_monitor.crowd_analysis(dets)
        ]
    )

def monitor_inactivity():
    while True:
        crowd_monitor.check_inactivity()
        time.sleep(5)


def monitor_distance():
    while True:
        for i, sensor in enumerate(SENSORS):
            dist = get_distance(sensor["TRIG"], sensor["ECHO"])
            if dist != -1:
                print(f"[Ultrasonic Sensor {i + 1}] Distance: {dist} cm")
        time.sleep(1)


def save_location():
    location = get_current_location_info()
    if not location:
        speak("Failed to get current location.")
        return

    if not os.path.exists(SAVE_FILE):
        with open(SAVE_FILE, 'w') as f:
            json.dump([], f)

    with open(SAVE_FILE, 'r+') as f:
        data = json.load(f)
        default_name = f"Location {len(data) + 1}"
        speak("Please type a name for this location:")
        name = input("Location name: ") or default_name

        data.append({
            "name": name,
            "coordinates": location["coordinates"],
            "address": location["address"].get("full_address", "Unknown")
        })
        f.seek(0)
        json.dump(data, f, indent=4)

    speak(f"Location saved as {name}.")


def send_sms():
    if not emergency_number:
        speak("Emergency number not set.")
        return
    try:
        with serial.Serial(SERIAL_PORT, BAUD_RATE, timeout=2) as modem:
            def send_at(command, delay=1):
                modem.write((command + "\r").encode())
                time.sleep(delay)
                return modem.read_all().decode(errors="ignore")

            send_at("AT")
            send_at("AT+CMGF=1")
            send_at(f"AT+CMGS=\"{emergency_number}\"")
            modem.write(b"This is an emergency alert from your assistive device. Immediate attention needed.\x1A")
            time.sleep(3)
            speak("Emergency message sent.")
    except Exception as e:
        print("SMS error:", e)
        speak("Failed to send emergency message.")


def button_monitor():
    global announce_level, halt_announcements
    while True:
        if GPIO.input(BUTTON_INCREASE) == GPIO.LOW:
            announce_level += 1
            speak(f"Announcement detail increased to level {announce_level}.")
            time.sleep(1)
        if GPIO.input(BUTTON_DECREASE) == GPIO.LOW:
            announce_level = max(1, announce_level - 1)
            speak(f"Announcement detail decreased to level {announce_level}.")
            time.sleep(1)
        if GPIO.input(BUTTON_HALT) == GPIO.LOW:
            halt_announcements = not halt_announcements
            state = "halted" if halt_announcements else "resumed"
            speak(f"Announcements {state}.")
            time.sleep(1)
        if GPIO.input(BUTTON_SAVE) == GPIO.LOW:
            speak("Save location button pressed.")
            save_location()
            time.sleep(2)
        if GPIO.input(BUTTON_EMERGENCY) == GPIO.LOW:
            speak("Emergency button pressed.")
            send_sms()
            time.sleep(2)


def set_emergency_contact():
    global emergency_number
    speak("Please enter the emergency contact number.")
    emergency_number = input("Emergency contact number: ")
    speak(f"Emergency number {emergency_number} saved.")


def start_all():
    global detection_engine
    set_emergency_contact()

    detection_engine = NanoDetDetector("config/nanodet.yaml", "model/nanodet.pth")
    detection_engine.on_detect = lambda dets: None

    threads = [
        threading.Thread(target=gps_and_voice),
        threading.Thread(target=run_detection),
        threading.Thread(target=monitor_inactivity),
        threading.Thread(target=monitor_distance),
        threading.Thread(target=button_monitor),
    ]

    obstacle = ObstacleMonitor()
    obstacle.start()

    for t in threads:
        t.start()

    for t in threads:
        t.join()


if __name__ == "__main__":
    start_all()
