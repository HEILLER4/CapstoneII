import cv2
from asset.Nanodet import NanoDetVisualizer
from asset.Headless import NanoDetDetector
import pyttsx3
import time

# Initialize NanoDet
visualizer = NanoDetVisualizer(
    "config/legacy_v0.x_configs/nanodet-m.yml",
    "model/nanodet_m.ckpt",
    "cpu"
)

# Initialize speech engine
engine = pyttsx3.init()
last_spoken_time = 0


def my_detection_handler(detections):
    """
    Custom handler that uses TTS to speak detected class names and their direction.
    """
    global last_spoken_time
    current_time = time.time()

    # Organize detections by (class_name, direction)
    objects_with_direction = [
        f"{det['class_name']} on the {det['direction']}"
        for det in detections
    ]

    if current_time - last_spoken_time >= 10 and objects_with_direction:
        message = "Detected: " + ", ".join(objects_with_direction)
        print("Speaking:", message)
        engine.say(message)
        engine.runAndWait()
        last_spoken_time = current_time
    else:
        print("Detected (speech suppressed):", objects_with_direction)


# ESP32-CAM stream + direction-aware TTS
visualizer.process_camera(
    url="http://192.168.4.2:81/stream",  # Your ESP32 stream
    log_file="detections.log",
    on_detect=my_detection_handler,
    score_threshold=0.35,
    window_name="NanoDet Direction View",
    exit_key=ord('q')
)
