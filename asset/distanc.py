
import RPi.GPIO as GPIO
import time

# Define TRIG and ECHO pins for each sensor
SENSORS = [
    {"TRIG": 20, "ECHO": 21},
    {"TRIG": 19, "ECHO": 26},
    {"TRIG": 16, "ECHO": 13}
]

GPIO.setmode(GPIO.BCM)

for sensor in SENSORS:
    GPIO.setup(sensor["TRIG"], GPIO.OUT)
    GPIO.setup(sensor["ECHO"], GPIO.IN)


def get_distance(TRIG, ECHO):
    GPIO.output(TRIG, False)
    time.sleep(0.05)

    GPIO.output(TRIG, True)
    time.sleep(0.00001)
    GPIO.output(TRIG, False)

    timeout_start = time.time()
    while GPIO.input(ECHO) == 0:
        pulse_start = time.time()
        if time.time() - timeout_start > 0.02:
            return -1

    timeout_start = time.time()
    while GPIO.input(ECHO) == 1:
        pulse_end = time.time()
        if time.time() - timeout_start > 0.02:
            return -1

    pulse_duration = pulse_end - pulse_start
    distance = pulse_duration * 17150
    return round(distance, 2)


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
