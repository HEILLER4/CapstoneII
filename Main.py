# Ultra-optimized for Raspberry Pi 4 power efficiency
import threading
import requests
import time
import logging
import json
import os
import requests
import difflib
import csv
import subprocess
import queue
from collections import deque
from socket import socket, AF_INET, SOCK_DGRAM
from cryptography.fernet import Fernet
import sys
import gc
import psutil
from contextlib import contextmanager

from pyrosm.geometry import haversine

from mod.GP_s import get_current_location_info
from mod.voiice import listen_filtered_command
from mod.obs import ObstacleMonitor
from mod.monitor import CrowdMonitor
from asset.distanc import get_distance, SENSORS
from mod.geoc import geocode_opencage
from asset.Headless import NanoDetDetector
from asset.Nanodet import NanoDetVisualizer

try:
    import pyttsx3
except ImportError:
    pyttsx3 = None
    logging.warning("pyttsx3 not installed. TTS will not function.")

# Optimized logging - reduce I/O overhead
log_file = open("system.log", "a", buffering=8192)
logging.basicConfig(
    level=logging.WARNING,
    format="%(asctime)s - %(levelname)s - %(message)s",
    handlers=[
        logging.StreamHandler(),
        logging.StreamHandler(log_file)
    ]
)

ESP32_STATUS_ENDPOINT = "http://192.168.206.213:8080/esp32/data"  # Update with Pi’s IP if different
last_button_state = None
button_action_cooldown = 3  # seconds
last_action_time = 0


ESP32_COMMAND_URL = "http://192.168.206.213/vibrate"  # Change to ESP32 IP
VIBRATION_THRESHOLD_CM = 50
VIBRATION_ACTIVE = False


# Configuration with power-saving defaults
GRAPH_HOPPER_URL = "http://localhost:8989/route"
ESP32_CAM_URL = "http://192.168.206.206:81/stream"
USE_ESP32_CAM = True
SERIAL_PORT = "/dev/serial0"
BAUD_RATE = 115200
SAVE_FILE = "saved_locations.json"
CSV_LOCATION_FILE = "offline_locations.csv"
EMERGENCY_FILE = "emergency_number.txt"

# Power management settings
POWER_SAVE_MODE = True
LOW_BATTERY_THRESHOLD = 20  # Percentage
CPU_USAGE_THRESHOLD = 80  # Percentage
SLEEP_INTERVALS = {
    'detection': 0.1,  # Reduced from potential higher values
    'distance': 3.0,  # Increased from 2.0
    'inactivity': 20.0,  # Increased from 5.0
    'voice_cooldown': 2.0  # Voice command spacing
}


class PowerManager:
    def __init__(self):
        self.low_power_mode = False
        self.last_activity = time.time()
        self.cpu_samples = deque(maxlen=10)

    def check_system_resources(self):
        """Monitor CPU and adjust performance accordingly"""
        cpu_percent = psutil.cpu_percent(interval=None)
        self.cpu_samples.append(cpu_percent)
        avg_cpu = sum(self.cpu_samples) / len(self.cpu_samples)

        # Enable low power mode if high CPU usage
        if avg_cpu > CPU_USAGE_THRESHOLD:
            self.low_power_mode = True
            return True
        elif avg_cpu < 40:  # Normal operation threshold
            self.low_power_mode = False
            return False
        return self.low_power_mode

    def get_sleep_interval(self, task):
        """Return adaptive sleep intervals based on system load"""
        base_interval = SLEEP_INTERVALS.get(task, 1.0)
        if self.low_power_mode:
            return base_interval * 2  # Double sleep time in low power mode
        return base_interval

    def force_gc(self):
        """Aggressive garbage collection to free memory"""
        gc.collect()


power_manager = PowerManager()


class AdaptiveThreshold:
    def __init__(self):
        self.base_threshold = 0.30  # Increased to reduce false positives
        self.confidence_history = deque(maxlen=30)  # Reduced memory usage
        self.class_thresholds = {
            'person': 0.20,
            'car': 0.25,
            'motorcycle': 0.25,
            'bicycle': 0.20
        }
        self.last_announcements = {}
        self.cooldown = 4.0  # Increased cooldown to save power

    def get_threshold(self, class_name):
        # Higher thresholds in low power mode
        base = self.class_thresholds.get(class_name, self.base_threshold)
        if power_manager.low_power_mode:
            return base * 1.3
        return base

    def should_announce(self, detection):
        class_name = detection.get('class_name', '')
        score = detection.get('score', 0)
        direction = detection.get('direction', '')

        if score < self.get_threshold(class_name):
            return False

        key = f"{class_name}_{direction}"
        now = time.time()
        cooldown = self.cooldown * (2 if power_manager.low_power_mode else 1)

        if key in self.last_announcements and now - self.last_announcements[key] < cooldown:
            return False

        self.last_announcements[key] = now
        return True

    def cleanup_old_announcements(self):
        """Remove old announcement records to save memory"""
        now = time.time()
        cutoff = now - (self.cooldown * 3)
        self.last_announcements = {
            k: v for k, v in self.last_announcements.items()
            if v > cutoff
        }


adaptive_threshold = AdaptiveThreshold()
crowd_monitor = CrowdMonitor()
announce_level = 1
halt_announcements = False
emergency_number = None



class RHVoiceTTS:
    def __init__(self, lang="tl", voice="angela"):
        self.lang = lang
        self.voice = voice

    def speak(self, text: str):
        try:
            subprocess.run(
                ["RHVoice-client", "-s", self.voice, "-p", "100", "-r", "0", "-v", "1"],
                input=text.encode("utf-8"),
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL
            )
        except Exception as e:
            logging.error(f"RHVoice TTS error: {e}")

# Replace pyttsx3 with RHVoice
tts = RHVoiceTTS()

def speak(msg):
    if not halt_announcements:
        tts.speak(msg)

def send_vibration_command(on: bool):
    """Send command to ESP32 to trigger or stop vibration motor."""
    global VIBRATION_ACTIVE

    if on == VIBRATION_ACTIVE:
        return  # Skip if no state change

    try:
        payload = "on" if on else "off"
        r = requests.post(ESP32_COMMAND_URL, data=payload, timeout=1.5)
        if r.ok:
            logging.info(f"[ESP32] Vibration {payload.upper()} sent")
            VIBRATION_ACTIVE = on
        else:
            logging.warning(f"[ESP32] Failed to trigger vibration: {r.status_code}")
    except Exception as e:
        logging.warning(f"[ESP32] Vibration error: {e}")


@contextmanager
def error_handler(operation_name):
    """Context manager for consistent error handling"""
    try:
        yield
    except Exception as e:
        logging.error(f"{operation_name} error: {e}")
        if POWER_SAVE_MODE:
            time.sleep(1)  # Brief pause on errors to prevent rapid retries


def voice_once_and_handle():
    speak("Listening...")
    text = listen_filtered_command(min_confidence=0.75)
    if text:
        handle_voice_command(text)


def continuous_voice_loop():
    while True:
        text = listen_filtered_command(min_confidence=0.75)
        if text:
            handle_voice_command(text)
        time.sleep(1)


def handle_voice_command(text):
    if "navigate" in text or "route" in text or "go to" in text:
        speak("Routing started.")
        threading.Thread(target=lambda: gps_and_voice_live(simulated_input=text), daemon=True).start()

    elif "save location" in text or "mark this place" in text:
        speak("Saving current location.")
        threading.Thread(target=save_location, daemon=True).start()

    elif "set emergency" in text or "emergency number" in text:
        speak("Setting emergency contact.")
        set_emergency_contact()

    elif "increase threshold" in text or "make it stricter" in text:
        adaptive_threshold.base_threshold = min(0.5, adaptive_threshold.base_threshold + 0.05)
        speak(f"Threshold increased to {adaptive_threshold.base_threshold:.2f}")

    elif "decrease threshold" in text or "make it loose" in text:
        adaptive_threshold.base_threshold = max(0.1, adaptive_threshold.base_threshold - 0.05)
        speak(f"Threshold decreased to {adaptive_threshold.base_threshold:.2f}")

    elif "stop announcements" in text or "be quiet" in text:
        global halt_announcements
        halt_announcements = True
        speak("Announcements halted.")

    elif "resume announcements" in text or "talk again" in text:
        halt_announcements = False
        speak("Announcements resumed.")

    else:
        speak("Command not recognized.")

def save_location():
    try:
        location = get_current_location_info()
        if not location:
            speak("Failed to get GPS location.")
            return

        if not os.path.exists(SAVE_FILE):
            with open(SAVE_FILE, 'w') as f:
                json.dump([], f)

        with open(SAVE_FILE, 'r+') as f:
            data = json.load(f)
            default_name = f"Location {len(data) + 1}"
            data.append({
                "name": default_name,
                "coordinates": location["coordinates"],
                "address": location["address"].get("full_address", "Unknown")
            })
            f.seek(0)
            json.dump(data, f, indent=4)

        speak(f"Location saved as {default_name}.")
    except Exception as e:
        logging.error(f"save_location error: {e}")
        speak("Failed to save location.")

def set_emergency_contact():
    global emergency_number
    try:
        file_path = "predefined_emergency.txt"
        if not os.path.exists(file_path):
            with open(file_path, "w") as f:
                f.write("911")  # Default fallback

        with open(file_path, "r") as f:
            emergency_number = f.read().strip()

        with open(EMERGENCY_FILE, "w") as f:
            f.write(emergency_number)

        speak(f"Ang emergency number ay naka set sa {emergency_number}.")
    except Exception as e:
        logging.error(f"set_emergency_contact error: {e}")
        speak("Bigo ang pag set ng emergency contact.")


def poll_esp32_buttons():
    global last_button_state, last_action_time
    while True:
        try:
            response = requests.get(ESP32_STATUS_ENDPOINT, timeout=2)
            if response.ok:
                data = response.json()
                buttons = data.get("buttons")
                now = time.time()

                if buttons != last_button_state and now - last_action_time > button_action_cooldown:
                    last_button_state = buttons
                    last_action_time = now
                    print(f"[DEBUG] Buttons: {buttons}, Last: {last_button_state}, : {now - last_action_time:.2f}")

                    print(f"[BUTTON] {buttons}")
                    threading.Thread(
                        target=lambda: handle_button_command(buttons),
                        daemon=True
                    ).start()

        except Exception as e:
            logging.warning(f"[ESP32] Polling failed: {e}")
        time.sleep(1)



def handle_button_command(buttons):
    if buttons == "0001":
        speak("Ang paggawa ng routa ay uumpisahan.")
        threading.Thread(target=voice_once_and_handle, daemon=True).start()
    elif buttons == "0010":
        speak("Sinasave ang kasulukuyang lokasyon.")
        threading.Thread(target=save_location, daemon=True).start()
    elif buttons == "0011":
        speak("Pakiset ang bagong emergency contact.")
        set_emergency_contact()
    elif buttons == "0100":
        adaptive_threshold.base_threshold = min(0.5, adaptive_threshold.base_threshold + 0.05)
        speak(f"Tinaasan ang score ng {adaptive_threshold.base_threshold:.2f}")
    elif buttons == "0101":
        adaptive_threshold.base_threshold = max(0.1, adaptive_threshold.base_threshold - 0.05)
        speak(f"Binabaan ang score ng {adaptive_threshold.base_threshold:.2f}")
    elif buttons == "0110":
        global halt_announcements
        halt_announcements = not halt_announcements
        speak("Tumigil na ang announcement." if halt_announcements else "Itutuloy na ang announcement.")


def load_api_key():
    with error_handler("API key loading"):
        if not os.path.exists("secret.key") or not os.path.exists("encrypted_api.key"):
            return None
        with open("secret.key", "rb") as kf:
            key = kf.read()
        with open("encrypted_api.key", "rb") as ef:
            encrypted = ef.read()
        return Fernet(key).decrypt(encrypted).decode()


def load_emergency_contact():
    global emergency_number
    with error_handler("Emergency contact loading"):
        if os.path.exists(EMERGENCY_FILE):
            with open(EMERGENCY_FILE) as f:
                emergency_number = f.read().strip()
                logging.info("Emergency contact loaded.")


def get_saved_location(name):
    with error_handler("Saved location retrieval"):
        if not os.path.exists(SAVE_FILE):
            return None
        with open(SAVE_FILE) as f:
            data = json.load(f)
        for loc in data:
            if loc['name'].lower() == name.lower():
                return tuple(loc['coordinates'])
    return None


def fuzzy_geocode_offline(name):
    with error_handler("Offline geocoding"):
        if not os.path.exists(CSV_LOCATION_FILE):
            return None
        with open(CSV_LOCATION_FILE, newline='') as f:
            reader = csv.DictReader(f)
            rows = list(reader)
            names = [row['name'].strip().lower() for row in rows]
        match = difflib.get_close_matches(name.lower(), names, n=1, cutoff=0.6)
        if match:
            for row in rows:
                if row['name'].strip().lower() == match[0]:
                    return float(row['latitude']), float(row['longitude'])
    return None


def announce_detections(dets):
    if halt_announcements or power_manager.low_power_mode:
        return

    # More aggressive filtering to reduce announcements
    speakable = [d for d in dets if adaptive_threshold.should_announce(d)]
    if not speakable:
        return

    # Group by direction to reduce speech
    left = set()
    right = set()
    for d in speakable:
        side = d.get("direction", "")
        name = d.get("class_name", "object")
        if side == "kaliwa":
            left.add(name)
        elif side == "kanan":
            right.add(name)

    # Limit announcements to most important
    if left and len(left) <= 2:
        speak(f"Kaliwa: {', '.join(list(left)[:2])}")
    if right and len(right) <= 2:
        speak(f"Kanan: {', '.join(list(right)[:2])}")


def gps_and_voice_live(simulated_input=None):
    try:
        # Step 1: Get destination from user (voice or simulated)
        location = get_current_location_info()
        if not location:
            speak("Ang GPS ay kasulukuyang di available.")
            return

        current_coords = location['coordinates']
        speak("Ang lokasyon ay nakita na.")

        dest = simulated_input or listen_filtered_command(min_confidence=0.75)
        if not dest:
            speak("Hindi klaro ang lokasyon.")
            return

        speak(f"Ang ruta ay  {dest[:20]}...")

        dest_coords = (
            get_saved_location(dest) or
            geocode_opencage(dest) or
            fuzzy_geocode_offline(dest)
        )
        if not dest_coords:
            speak("Ang destinasyon ay di nakita.")
            return

        # Step 2: Fetch route from GraphHopper
        url = f"{GRAPH_HOPPER_URL}?point={current_coords[0]},{current_coords[1]}&point={dest_coords[0]},{dest_coords[1]}&vehicle=foot&locale=en&instructions=true"
        r = requests.get(url, timeout=10)
        r.raise_for_status()
        path = r.json().get("paths", [{}])[0]
        instructions = path.get("instructions", [])

        # Step 3: Follow instructions in real time
        index = 0
        while index < len(instructions):
            time.sleep(3)
            current = get_current_location_info()
            if not current:
                speak("Inaantay ang GPS ...")
                continue

            lat1, lon1 = current['coordinates']
            instr = instructions[index]
            lat2, lon2 = instr['points']['coordinates'][0][1], instr['points']['coordinates'][0][0]

            dist = haversine(lat1, lon1, lat2, lon2)
            if dist < 10:
                speak(instr['text'][:50])
                index += 1
            else:
                print(f"[GPS] Approaching step {index + 1} - {int(dist)}m away")

    except Exception as e:
        logging.error(f"[GPS-NAV] {e}")
        speak("Ang pag ruta ay bigo.")
def send_vibration_command(on: bool):
    """Send command to ESP32 to trigger or stop vibration motor."""
    global VIBRATION_ACTIVE

    if on == VIBRATION_ACTIVE:
        return  # Skip if no state change

    try:
        payload = "on" if on else "off"
        r = requests.post(ESP32_COMMAND_URL, data=payload, timeout=1.5)
        if r.ok:
            logging.info(f"[ESP32] Vibration {payload.upper()} sent")
            VIBRATION_ACTIVE = on
        else:
            logging.warning(f"[ESP32] Failed to trigger vibration: {r.status_code}")
    except Exception as e:
        logging.warning(f"[ESP32] Vibration error: {e}")




def run_detection():
    with error_handler("Object detection"):
        try:
            detector = NanoDetVisualizer("config/legacy_v0.x_configs/nanodet-m.yml", "model/nanodet_m.ckpt")

            def detection_callback(dets):
                announce_detections(dets)
                crowd_monitor.update_detection_time()

                # Periodic memory cleanups
                if time.time() % 30 < 0.1:
                    adaptive_threshold.cleanup_old_announcements()
                    power_manager.force_gc()

            logging.info("Checking camera availability...")
            if not detector.is_camera_available(ESP32_CAM_URL if USE_ESP32_CAM else 0):
                logging.warning("Camera not available. Detection thread will exit cleanly.")
                return

            detector.process_camera(
                url=ESP32_CAM_URL if USE_ESP32_CAM else 0,
                on_detect=detection_callback
            )

        except RuntimeError as e:
            logging.error(f"Camera access failed: {e}. Skipping detection.")
        except Exception as e:
            logging.exception(f"Fatal error in detection thread: {e}")

def monitor_inactivity():
    while True:
        with error_handler("Inactivity monitoring"):
            crowd_monitor.check_inactivity()

            # Check system resources periodically
            power_manager.check_system_resources()

            sleep_time = power_manager.get_sleep_interval('inactivity')
            time.sleep(sleep_time)


def monitor_distance():
    sensor_count = len(SENSORS)

    while True:
        with error_handler("Distance monitoring"):
            too_close = False

            # Only use sensor 0 and 1
            for i in range(2):
                sensor = SENSORS[i]
                dist = get_distance(sensor["TRIG"], sensor["ECHO"])
                if dist != -1:
                    print(f"[Sensor {i}] Distance: {dist} cm")
                    if dist < VIBRATION_THRESHOLD_CM:
                        too_close = True

            send_vibration_command(on=too_close)
            time.sleep(power_manager.get_sleep_interval('distance'))

def system_monitor():
    """Monitor system health and adjust performance"""
    while True:
        try:
            # Force garbage collection periodically
            power_manager.force_gc()

            # Log system stats occasionally
            if time.time() % 60 < 1:  # Every minute
                cpu = psutil.cpu_percent()
                memory = psutil.virtual_memory().percent
                logging.info(f"System: CPU {cpu}%, RAM {memory}%, Low Power: {power_manager.low_power_mode}")

            time.sleep(30)  # Check every 30 seconds

        except Exception as e:
            logging.warning(f"System monitor error: {e}")
            time.sleep(60)



def start_all():
    load_emergency_contact()

    # Prioritized thread list - critical functions first
    voice_listener_thread = threading.Thread(target=continuous_voice_loop, daemon=True, name="VoiceListener")

    threads = [
        threading.Thread(target=run_detection, daemon=True, name="Detection"),
        threading.Thread(target=monitor_distance, daemon=True, name="Distance"),
        threading.Thread(target=monitor_inactivity, daemon=True, name="Inactivity"),
        threading.Thread(target=system_monitor, daemon=True, name="SystemMonitor"),
        threading.Thread(target=gps_and_voice_live, daemon=True, name="GPS"),
        voice_listener_thread  # ✅ Added correctly now
    ]

    esp32_thread = threading.Thread(
        target=poll_esp32_buttons, daemon=True, name="ESP32Poll"
    )
    esp32_thread.start()

    # Start threads with small delays to prevent resource contention
    for i, t in enumerate(threads):
        t.start()
        time.sleep(0.5)  # Stagger startup
        logging.info(f"Started {t.name} thread")

    try:
        # Keep main thread alive and handle graceful shutdown
        while True:
            time.sleep(10)
            # Check if critical threads are still alive
            for t in threads:
                if not t.is_alive():
                    logging.warning(f"Thread {t.name} died, restarting...")
                    # Could implement thread restart logic here

    except KeyboardInterrupt:
        logging.info("Shutdown requested")
        halt_announcements = True
        tts.shutdown()

    except Exception as e:
        logging.error(f"Main loop error: {e}")

    finally:
        logging.info("System shutdown complete")


if __name__ == "__main__":
    start_all()