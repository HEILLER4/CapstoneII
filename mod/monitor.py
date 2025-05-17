import time
import pyttsx3

class CrowdMonitor:
    def __init__(self):
        self.last_seen = time.time()
        self.engine = pyttsx3.init()

    def update_detection_time(self):
        self.last_seen = time.time()

    def check_inactivity(self):
        if time.time() - self.last_seen >= 30:
            self.engine.say("No objects detected. Would you like a comprehensive scan?")
            self.engine.runAndWait()
            self.last_seen = time.time()

    def crowd_analysis(self, detections):
        people = [d for d in detections if d['class_name'].lower() == 'person']
        if len(people) > 5:
            self.engine.say("You are entering a crowded area.")
            self.engine.runAndWait()

if __name__ == '__main__':
    cm = CrowdMonitor()
    while True:
        cm.check_inactivity()
        time.sleep(5)
