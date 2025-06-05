import os
import subprocess
import serial.tools.list_ports
import cv2
import shutil
import socket
import logging
import time

logging.basicConfig(filename="diagnostic.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def check_camera():
    cap = cv2.VideoCapture(0)
    if not cap.isOpened():
        logging.warning("Camera not detected")
        return False
    cap.release()
    return True

def check_serial_device(expected="/dev/ttyS0"):
    ports = [p.device for p in serial.tools.list_ports.comports()]
    if expected in ports:
        return True
    logging.warning(f"Expected serial device {expected} not found. Found: {ports}")
    return False

def check_disk_space(min_gb=1):
    total, used, free = shutil.disk_usage("/")
    free_gb = free / (1024 ** 3)
    if free_gb < min_gb:
        logging.warning(f"Low disk space: {free_gb:.2f} GB available")
        return False
    return True

def check_internet(host="8.8.8.8", port=53, timeout=3):
    try:
        socket.setdefaulttimeout(timeout)
        socket.socket(socket.AF_INET, socket.SOCK_STREAM).connect((host, port))
        return True
    except Exception as e:
        logging.warning(f"Network test failed: {e}")
        return False

def run_diagnostics():
    results = {
        "Camera": check_camera(),
        "Serial Modem": check_serial_device(),
        "Disk Space": check_disk_space(),
        "Internet": check_internet(),
    }

    for k, v in results.items():
        status = "✅" if v else "❌"
        logging.info(f"{k}: {status}")
        print(f"{k}: {status}")

if __name__ == "__main__":
    run_diagnostics()
