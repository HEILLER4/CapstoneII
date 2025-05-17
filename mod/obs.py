import serial
import time
import threading

class ObstacleMonitor:
    def __init__(self, port='/dev/ttyUSB0', baudrate=9600):
        self.ser = serial.Serial(port, baudrate, timeout=1)
        self.running = True

    def read_distance(self):
        try:
            self.ser.write(b'distance\n')
            line = self.ser.readline().decode().strip()
            if line:
                return float(line)
        except Exception as e:
            print(f"Serial error: {e}")
        return None

    def monitor(self):
        while self.running:
            dist = self.read_distance()
            if dist and dist <= 0.5:
                print("Obstacle very close! Triggering vibration/buzzer.")
            time.sleep(0.5)

    def start(self):
        threading.Thread(target=self.monitor, daemon=True).start()

if __name__ == '__main__':
    om = ObstacleMonitor()
    om.start()
    while True:
        time.sleep(1)
