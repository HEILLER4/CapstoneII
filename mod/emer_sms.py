# emergency_sms_button.py (SIMCom A7670E version)

import RPi.GPIO as GPIO
import time
import pyttsx3
import serial

EMERGENCY_BUTTON = 24
SERIAL_PORT = "/dev/ttyS0"  # Adjust if needed
BAUD_RATE = 115200

engine = pyttsx3.init()
emergency_number = None  # to be input via voice

GPIO.setmode(GPIO.BCM)
GPIO.setup(EMERGENCY_BUTTON, GPIO.IN, pull_up_down=GPIO.PUD_UP)


def speak(msg):
    print("[SPEAK]:", msg)
    engine.say(msg)
    engine.runAndWait()


def set_emergency_contact():
    global emergency_number
    speak("Please type the emergency contact number.")
    number = input("Enter emergency number: ")  # Replace with voice input if available
    emergency_number = number
    speak(f"Emergency number {number} saved.")


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
            send_at("AT+CMGF=1")  # Set SMS to text mode
            send_at(f"AT+CMGS=\"{emergency_number}\"")
            modem.write(b"This is an emergency alert from your assistive device. Immediate attention needed.\x1A")
            time.sleep(3)
            speak("Emergency message sent.")
    except Exception as e:
        print("SMS error:", e)
        speak("Failed to send emergency message.")


def monitor_button():
    while True:
        if GPIO.input(EMERGENCY_BUTTON) == GPIO.LOW:
            speak("Emergency button pressed.")
            send_sms()
            time.sleep(2)  # debounce


if __name__ == "__main__":
    try:
        speak("Emergency SMS system ready.")
        set_emergency_contact()
        monitor_button()
    except KeyboardInterrupt:
        GPIO.cleanup()
