import threading
import time
import pyttsx3
import requests
import urllib.parse
import os
import json
import csv
import difflib
import serial
import cv2
import numpy as np
import logging
import queue
from collections import defaultdict, deque
from cryptography.fernet import Fernet
from socket import socket, AF_INET, SOCK_DGRAM

from mod.GP_s import get_current_location_info
from mod.voiice import listen
from mod.obs import ObstacleMonitor
from mod.monitor import CrowdMonitor
from asset.distanc import get_distance, SENSORS
from mod.geoc import geocode_opencage
from asset.Headless import NanoDetDetector
from asset.Nanodet import NanoDetVisualizer
from asset.category_mapper import get_category

category = get_category("car")  # returns "vehicle"
category = get_category("bottle")  # returns "object"


logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.FileHandler("system.log"),
        logging.StreamHandler()
    ]
)


# Thread-safe TTS system
class ThreadSafeTTS:
    def __init__(self):
        self.tts_queue = queue.Queue()
        self.tts_thread = None
        self.running = False
        self.engine = None
        self.lock = threading.Lock()

    def start(self):
        """Start the TTS worker thread"""
        if not self.running:
            self.running = True
            self.tts_thread = threading.Thread(target=self._tts_worker, daemon=True)
            self.tts_thread.start()
            print("[TTS] Thread-safe TTS system started")

    def _tts_worker(self):
        """Worker thread that handles all TTS operations"""
        try:
            # Initialize TTS engine in this thread only
            self.engine = pyttsx3.init()
            print("[TTS] Engine initialized in worker thread")

            while self.running:
                try:
                    # Get message from queue with timeout
                    message = self.tts_queue.get(timeout=1.0)
                    if message is None:  # Shutdown signal
                        break

                    print(f"[SPEAK]: {message}")
                    logging.info(f"Speaking: {message}")

                    self.engine.say(message)
                    self.engine.runAndWait()

                    self.tts_queue.task_done()

                except queue.Empty:
                    continue
                except Exception as e:
                    logging.error(f"TTS worker error: {e}")

        except Exception as e:
            logging.error(f"TTS worker initialization error: {e}")
        finally:
            if self.engine:
                try:
                    self.engine.stop()
                except:
                    pass

    def speak(self, message):
        """Thread-safe speak method"""
        if self.running:
            try:
                self.tts_queue.put(message, timeout=1.0)
            except queue.Full:
                logging.warning("TTS queue full, dropping message")
        else:
            print(f"[TTS NOT READY]: {message}")

    def stop(self):
        """Stop the TTS system"""
        self.running = False
        if self.tts_queue:
            self.tts_queue.put(None)  # Shutdown signal
        if self.tts_thread and self.tts_thread.is_alive():
            self.tts_thread.join(timeout=2.0)


# Global thread-safe TTS instance
tts_system = ThreadSafeTTS()

# Global variables
EMERGENCY_FILE = "emergency_number.json"
crowd_monitor = CrowdMonitor()
announce_level = 1
halt_announcements = False
SERIAL_PORT = "/dev/serial0"
BAUD_RATE = 115200
emergency_number = None
SAVE_FILE = "saved_locations.json"
CSV_LOCATION_FILE = "offline_locations.csv"
ESP32_CAM_URL = "http://192.168.206.206:81/stream"
USE_ESP32_CAM = True
GRAPH_HOPPER_URL = "http://localhost:8989/route"


# Adaptive threshold configuration
class AdaptiveThreshold:
    def __init__(self):
        self.base_threshold = 0.20
        self.confidence_history = deque(maxlen=50)
        self.class_thresholds = {
            'person': 0.15,
            'car': 0.20,
            'truck': 0.20,
            'bus': 0.20,
            'motorcycle': 0.20,
            'bicycle': 0.15,
            'dog': 0.15,
            'cat': 0.15,
            'chair': 0.30,
            'bottle': 0.35,
            'cup': 0.35,
            'book': 0.40
        }
        self.last_announcements = {}
        self.announcement_cooldown = 3.0

    def get_threshold_for_class(self, class_name):
        return self.class_thresholds.get(class_name, self.base_threshold)

    def should_announce(self, detection):
        class_name = detection.get('class_name', '')
        score = detection.get('score', 0)
        direction = detection.get('direction', '')

        threshold = self.get_threshold_for_class(class_name)
        if score < threshold:
            return False

        key = f"{class_name}_{direction}"
        current_time = time.time()

        if key in self.last_announcements:
            time_since_last = current_time - self.last_announcements[key]
            if time_since_last < self.announcement_cooldown:
                return False

        self.last_announcements[key] = current_time
        return True

    def update_adaptive_threshold(self, detections):
        if not detections:
            return

        scores = [det['score'] for det in detections]
        self.confidence_history.extend(scores)

        if len(self.confidence_history) >= 20:
            avg_confidence = sum(self.confidence_history) / len(self.confidence_history)
            if avg_confidence > 0.8:
                self.base_threshold = min(0.35, self.base_threshold + 0.02)
            elif avg_confidence < 0.3:
                self.base_threshold = max(0.10, self.base_threshold - 0.02)


adaptive_threshold = AdaptiveThreshold()


def speak(msg):
    """Thread-safe speak function"""
    tts_system.speak(msg)


def announce_detections(dets):
    """Enhanced announcement system with adaptive thresholds and filtering"""
    if halt_announcements or not dets:
        return

    adaptive_threshold.update_adaptive_threshold(dets)

    filtered_detections = []
    for det in dets:
        if adaptive_threshold.should_announce(det):
            filtered_detections.append(det)

    if not filtered_detections:
        return

    left_objects = []
    right_objects = []

    for det in filtered_detections:
        class_name = det.get("class_name", "object")
        direction = det.get("direction", "")
        score = det.get("score", 0)

        if direction == "left":
            left_objects.append(class_name)
        elif direction == "right":
            right_objects.append(class_name)

        logging.info(f"[DETECTION] {class_name} {direction} (confidence: {score:.2f})")

    announcements = []

    if left_objects:
        if len(left_objects) == 1:
            announcements.append(f"{left_objects[0]} on the left")
        else:
            unique_objects = list(set(left_objects))
            if len(unique_objects) == 1:
                announcements.append(f"Multiple {unique_objects[0]}s on the left")
            else:
                announcements.append(f"Objects on the left: {', '.join(unique_objects[:3])}")

    if right_objects:
        if len(right_objects) == 1:
            announcements.append(f"{right_objects[0]} on the right")
        else:
            unique_objects = list(set(right_objects))
            if len(unique_objects) == 1:
                announcements.append(f"Multiple {unique_objects[0]}s on the right")
            else:
                announcements.append(f"Objects on the right: {', '.join(unique_objects[:3])}")

    for announcement in announcements:
        speak(announcement)
        if len(announcements) > 1:
            time.sleep(0.5)


def print_detection_stats():
    print(f"\n[STATS] Adaptive Threshold Status:")
    print(f"Base threshold: {adaptive_threshold.base_threshold:.2f}")
    print(f"Recent confidence history: {len(adaptive_threshold.confidence_history)} samples")
    if adaptive_threshold.confidence_history:
        avg_conf = sum(adaptive_threshold.confidence_history) / len(adaptive_threshold.confidence_history)
        print(f"Average recent confidence: {avg_conf:.2f}")
    print(f"Class-specific thresholds: {dict(list(adaptive_threshold.class_thresholds.items())[:5])}")
    print()


def load_api_key():
    try:
        with open("secret.key", "rb") as key_file:
            key = key_file.read()
        with open("encrypted_api.key", "rb") as encrypted_file:
            encrypted = encrypted_file.read()
        return Fernet(key).decrypt(encrypted).decode()
    except Exception as e:
        logging.error(f"Failed to load API key: {e}")
        return None


def get_saved_location(name):
    try:
        if not os.path.exists(SAVE_FILE):
            return None
        with open(SAVE_FILE, 'r') as f:
            data = json.load(f)
            for loc in data:
                if loc["name"].lower() == name.lower():
                    return tuple(loc["coordinates"])
    except Exception as e:
        logging.error(f"Error reading saved locations: {e}")
    return None


def fuzzy_geocode_offline(name, csv_file=CSV_LOCATION_FILE):
    try:
        if not os.path.exists(csv_file):
            logging.warning("Offline CSV not found")
            return None
        with open(csv_file, newline='', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            names = [row['name'].strip().lower() for row in rows]
        match = difflib.get_close_matches(name.lower(), names, n=1, cutoff=0.6)
        if match:
            for row in rows:
                if row['name'].strip().lower() == match[0]:
                    return float(row['latitude']), float(row['longitude'])
    except Exception as e:
        logging.error(f"Fuzzy geocode failed: {e}")
    return None


def gps_and_voice():
    try:
        location = get_current_location_info()
        if location:
            coords = location['coordinates']
            address = location['address']['full_address']
            speak(f"Current location: {address}")
        else:
            speak("Failed to acquire GPS location.")
            return

        destination = listen_filtered_command(min_confidence=0.75)
        speak(f"Destination received: {destination}")

        dest_coords = get_saved_location(destination)
        if not dest_coords:
            speak("Searching address online. Please wait...")
            dest_coords = geocode_opencage(destination)
            if not dest_coords:
                speak("Online geocoding failed. Trying offline location database...")
                dest_coords = fuzzy_geocode_offline(destination)
                if not dest_coords:
                    speak("Destination not found. Please try a different address.")
                    return
                else:
                    speak("Offline location found and coordinates acquired.")
            else:
                speak("Location found and coordinates acquired.")

        dest_lat, dest_lon = dest_coords
        speak("Setting up navigation route. Please wait.")
        gh_url = f"{GRAPH_HOPPER_URL}?point={coords[0]},{coords[1]}&point={dest_lat},{dest_lon}&vehicle=foot&locale=en&instructions=true"
        gh_response = requests.get(gh_url)
        gh_data = gh_response.json()
        if 'paths' in gh_data:
            for instr in gh_data['paths'][0]['instructions']:
                speak(instr['text'])
                time.sleep(1)
        else:
            raise ValueError("Invalid GraphHopper response")
        speak("Route ready. Proceeding with detection.")
    except Exception as e:
        logging.error(f"gps_and_voice error: {e}")
        speak("An error occurred while setting up navigation.")


def run_detection():
    try:
        print("[INFO] Starting adaptive detection system...")
        print_detection_stats()

        visualizer = NanoDetVisualizer("config/legacy_v0.x_configs/nanodet-m-0.5x.yml", "model/nanodet_m_0.5x.ckpt")

        def handle_detections(dets):
            if dets:
                announce_detections(dets)
                crowd_monitor.update_detection_time()
                crowd_monitor.crowd_analysis(dets)

                if hasattr(handle_detections, 'call_count'):
                    handle_detections.call_count += 1
                else:
                    handle_detections.call_count = 1

                if handle_detections.call_count % 50 == 0:
                    print_detection_stats()

        visualizer.process_camera(
            url=ESP32_CAM_URL if USE_ESP32_CAM else 0,
            on_detect=handle_detections,
            score_threshold=adaptive_threshold.base_threshold
        )

    except Exception as e:
        logging.error(f"run_detection error: {e}")


def monitor_inactivity():
    """Fixed monitor_inactivity with better error handling"""
    print("[INFO] Starting inactivity monitor...")

    while True:
        try:
            # Add a small delay before checking to avoid rapid loops
            time.sleep(5)

            # Safely call crowd_monitor.check_inactivity()
            if hasattr(crowd_monitor, 'check_inactivity'):
                crowd_monitor.check_inactivity()
            else:
                logging.warning("crowd_monitor.check_inactivity method not found")
                break  # Exit if method doesn't exist

        except Exception as e:
            logging.error(f"monitor_inactivity error: {e}")
            # Add longer delay on error to prevent spam
            time.sleep(10)

            # If we get too many errors, speak a warning (thread-safe)
            if hasattr(monitor_inactivity, 'error_count'):
                monitor_inactivity.error_count += 1
            else:
                monitor_inactivity.error_count = 1

            if monitor_inactivity.error_count > 5:
                speak("Inactivity monitor experiencing issues")
                monitor_inactivity.error_count = 0  # Reset counter


def monitor_distance():
    print("[INFO] Starting distance monitor...")

    while True:
        try:
            for i, sensor in enumerate(SENSORS):
                dist = get_distance(sensor["TRIG"], sensor["ECHO"])
                if dist != -1:
                    print(f"[Ultrasonic Sensor {i + 1}] Distance: {dist} cm")
            time.sleep(1)
        except Exception as e:
            logging.error(f"monitor_distance error: {e}")
            time.sleep(5)  # Longer delay on error


def save_location():
    try:
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
    except Exception as e:
        logging.error(f"save_location error: {e}")


def safe_send_sms(number, message, port=SERIAL_PORT, baudrate=BAUD_RATE):
    try:
        with serial.Serial(port, baudrate, timeout=2) as modem:
            def send_at(command, delay=1):
                modem.write((command + "\r").encode())
                time.sleep(delay)
                return modem.read_all().decode(errors="ignore")

            send_at("AT")
            send_at("AT+CMGF=1")
            send_at(f'AT+CMGS="{number}"')
            modem.write((message + "\x1A").encode())
            time.sleep(3)
            print("[SMS] Message sent successfully.")
            return True
    except (serial.SerialException, FileNotFoundError, Exception) as e:
        logging.error(f"safe_send_sms error: {e}")
        return False


def send_sms():
    if not emergency_number:
        speak("Emergency number not set.")
        return
    message = "This is an emergency alert from your assistive device. Immediate attention needed."
    if safe_send_sms(emergency_number, message):
        speak("Emergency message sent.")
    else:
        speak("SIMCOM module not detected or failed to send SMS.")


def load_emergency_number():
    global emergency_number
    if os.path.exists(EMERGENCY_FILE):
        with open(EMERGENCY_FILE, 'r') as f:
            emergency_number = json.load(f).get("number")
            if emergency_number:
                logging.info(f"Loaded emergency number: {emergency_number}")
                return
    emergency_number = None

def set_emergency_contact(force=False):
    global emergency_number
    if emergency_number and not force:
        return
    speak("Please enter the emergency contact number.")
    emergency_number = input("Emergency contact number: ")
    with open(EMERGENCY_FILE, 'w') as f:
        json.dump({"number": emergency_number}, f)
    speak(f"Emergency number {emergency_number} saved.")

# Modify announce_detections to use category
def announce_detections(dets):
    if halt_announcements or not dets:
        return

    adaptive_threshold.update_adaptive_threshold(dets)

    filtered_detections = [d for d in dets if adaptive_threshold.should_announce(d)]

    if not filtered_detections:
        return

    left_objects = []
    right_objects = []

    for det in filtered_detections:
        category = get_category(det.get("class_name", "object"))
        direction = det.get("direction", "")
        score = det.get("score", 0)
        if direction == "left":
            left_objects.append(category)
        elif direction == "right":
            right_objects.append(category)
        logging.info(f"[DETECTION] {category} {direction} (confidence: {score:.2f})")

    announcements = []
    if left_objects:
        unique = list(set(left_objects))
        if len(unique) == 1:
            announcements.append(f"Multiple {unique[0]}s on the left" if left_objects.count(unique[0]) > 1 else f"{unique[0]} on the left")
        else:
            announcements.append(f"Objects on the left: {', '.join(unique[:3])}")

    if right_objects:
        unique = list(set(right_objects))
        if len(unique) == 1:
            announcements.append(f"Multiple {unique[0]}s on the right" if right_objects.count(unique[0]) > 1 else f"{unique[0]} on the right")
        else:
            announcements.append(f"Objects on the right: {', '.join(unique[:3])}")

    for msg in announcements:
        speak(msg)
        if len(announcements) > 1:
            time.sleep(0.5)

import json

def udp_command_listener(host="0.0.0.0", port=4210):
    sock = socket(AF_INET, SOCK_DGRAM)
    sock.bind((host, port))
    print(f"[UDP] Listening on {host}:{port}")

    while True:
        try:
            data, addr = sock.recvfrom(1024)
            text = data.decode().strip()
            print(f"[UDP] From {addr} -> {text}")
            payload = json.loads(text)

            buttons = payload.get("buttons", "")
            if buttons == "1000":
                speak("Button 1 pressed")
            elif buttons == "0100":
                speak("Button 2 pressed")
            elif buttons == "0010":
                speak("Button 3 pressed")
            elif buttons == "0001":
                speak("Emergency button triggered")
                threading.Thread(target=send_sms, daemon=True).start()

            # Optional: Log or act on distance or pulse data
            distance = payload.get("distance")
            ir = payload.get("ir")
            red = payload.get("red")
            logging.info(f"Distance: {distance}cm, IR: {ir}, RED: {red}")

        except json.JSONDecodeError:
            logging.warning("Received malformed JSON")
        except Exception as e:
            logging.error(f"[UDP ERROR] {e}")



def start_all():
    # Start TTS system first
    tts_system.start()
    time.sleep(1)  # Give TTS time to initialize

    set_emergency_contact()

    # Create daemon threads to prevent hanging on exit
    threads = [
        threading.Thread(target=gps_and_voice, daemon=True),
        threading.Thread(target=run_detection, daemon=True),
        threading.Thread(target=monitor_inactivity, daemon=True),
        threading.Thread(target=monitor_distance, daemon=True),
        threading.Thread(target=udp_command_listener, daemon=True),
    ]

    try:
        obstacle = ObstacleMonitor()
        obstacle.start()

        for t in threads:
            t.start()
            time.sleep(0.5)  # Stagger thread starts

        # Keep main thread alive
        for t in threads:
            t.join()

    except KeyboardInterrupt:
        print("\n[INFO] Shutting down...")
    finally:
        tts_system.stop()


if __name__ == "__main__":
    start_all()