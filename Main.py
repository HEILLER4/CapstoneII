import threading
import time
import requests
import urllib.parse

from mod.GP_s import get_current_location_info
from mod.voiice import listen_for_command
from mod.detect import DetectionEngine
from mod.obs import ObstacleMonitor
from mod.monitor import CrowdMonitor

# Shared state
detection_engine = None
crowd_monitor = CrowdMonitor()
GRAPH_HOPPER_URL = "http://localhost:8989/route"  # Offline instance


def gps_and_voice():
    location = get_current_location_info()
    if location:
        coords = location['coordinates']
        address = location['address']['full_address']
        print("Current location:", address)
    else:
        print("Failed to acquire GPS location.")
        return

    destination = listen_for_command()
    print("Destination received:", destination)

    # Geocode destination using Nominatim
    geocode_url = f"https://nominatim.openstreetmap.org/search/{urllib.parse.quote(destination)}?format=json"
    try:
        response = requests.get(geocode_url, headers={'User-Agent': 'PythonApp'})
        data = response.json()
        if not data:
            raise ValueError("No geocode result")
        dest_lat = float(data[0]['lat'])
        dest_lon = float(data[0]['lon'])
    except Exception as e:
        print("Geocoding error:", e)
        return

    # Call local GraphHopper routing API
    detection_engine.routing_active = True
    detection_engine.speak("Setting up navigation route. Please wait.")
    gh_url = f"{GRAPH_HOPPER_URL}?point={coords[0]},{coords[1]}&point={dest_lat},{dest_lon}&vehicle=foot&locale=en&instructions=true"
    try:
        gh_response = requests.get(gh_url)
        gh_data = gh_response.json()
        if 'paths' in gh_data:
            for instr in gh_data['paths'][0]['instructions']:
                detection_engine.speak(instr['text'])
                time.sleep(1)
        else:
            raise ValueError("Invalid GraphHopper response")
    except Exception as e:
        print("GraphHopper error:", e)
        detection_engine.speak("Failed to get route from GraphHopper.")

    detection_engine.speak("Route ready. Proceeding with detection.")
    detection_engine.routing_active = False


def run_detection():
    detection_engine.run()


def monitor_inactivity():
    while True:
        crowd_monitor.check_inactivity()
        time.sleep(5)


def start_all():
    global detection_engine
    detection_engine = DetectionEngine("config/nanodet.yaml", "model/nanodet.pth")
    detection_engine.detector.on_detect = lambda dets: (
        detection_engine.on_detect(dets),
        crowd_monitor.update_detection_time(),
        crowd_monitor.crowd_analysis(dets)
    )

    threads = [
        threading.Thread(target=gps_and_voice),
        threading.Thread(target=run_detection),
        threading.Thread(target=monitor_inactivity),
    ]

    obstacle = ObstacleMonitor()
    obstacle.start()

    for t in threads:
        t.start()

    for t in threads:
        t.join()


if __name__ == "__main__":
    start_all()