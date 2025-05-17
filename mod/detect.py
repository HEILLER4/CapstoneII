import time
import pyttsx3
from asset.Nanodet import NanoDetVisualizer

class DetectionEngine:
    def __init__(self, config_path, model_path):
        self.detector = NanoDetVisualizer(config_path, model_path)
        self.engine = pyttsx3.init()
        self.last_announcement = 0
        self.routing_active = False

    def speak(self, message):
        print("Speaking:", message)
        self.engine.say(message)
        self.engine.runAndWait()

    def on_detect(self, detections):
        if self.routing_active:
            return

        now = time.time()
        if now - self.last_announcement < 5:
            return

        for det in detections:
            name = det['class_name']
            direction = det.get('direction', 'center')
            if name.lower() == 'person':
                self.speak(f"Person detected on the {direction}, slow down.")
            else:
                self.speak(f"{name} on the {direction}, steer away.")
            break  # only one object per 5s
        self.last_announcement = now

    def run(self):
        self.detector.process_camera(on_detect=self.on_detect)

if __name__ == "__main__":
    engine = DetectionEngine("config/nanodet.yaml", "model/nanodet.pth")
    engine.run()
