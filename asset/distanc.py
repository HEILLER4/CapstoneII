
import RPi.GPIO as GPIO
import time

# Define TRIG and ECHO pins for two sensors
SENSORS = [
    {"TRIG": 23, "ECHO": 24},  # Sensor 1
    {"TRIG": 27, "ECHO": 22}   # Sensor 2
]

GPIO.setmode(GPIO.BCM)
GPIO.setwarnings(False)

# Set up GPIO pins
for sensor in SENSORS:
    GPIO.setup(sensor["TRIG"], GPIO.OUT)
    GPIO.setup(sensor["ECHO"], GPIO.IN)
    GPIO.output(sensor["TRIG"], False)

def get_distance(TRIG, ECHO, timeout=0.02):
    try:
        GPIO.output(TRIG, True)
        time.sleep(0.00001)
        GPIO.output(TRIG, False)

        pulse_start = None
        pulse_end = None
        start_wait = time.time()

        # Wait for echo to go HIGH (start pulse)
        while GPIO.input(ECHO) == 0:
            pulse_start = time.time()
            if pulse_start - start_wait > timeout:
                return -1

        start_wait = time.time()

        # Wait for echo to go LOW (end pulse)
        while GPIO.input(ECHO) == 1:
            pulse_end = time.time()
            if pulse_end - start_wait > timeout:
                return -1

        # Final check
        if pulse_start is None or pulse_end is None:
            return -1

        pulse_duration = pulse_end - pulse_start
        distance = pulse_duration * 17150
        return round(distance, 2)

    except Exception as e:
        logging.error(f"[Ultrasonic] Sensor error: {e}")
        return -1

if __name__ == "__main__":
    try:
        while True:
            for i, sensor in enumerate(SENSORS):
                dist = get_distance(sensor["TRIG"], sensor["ECHO"])
                if dist == -1:
                    print(f"Sensor {i+1}: Timeout or object too far")
                else:
                    print(f"Sensor {i+1}: {dist} cm")
            print("-------------------")
            time.sleep(1)

    except KeyboardInterrupt:
        GPIO.cleanup()
        print("GPIO cleaned up.")

