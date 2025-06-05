import subprocess
import time
import logging

logging.basicConfig(filename="supervisor.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

def run_with_restart(script_path):
    while True:
        try:
            logging.info("Starting supervised process...")
            process = subprocess.Popen(["python3", script_path])
            process.wait()
            logging.warning(f"Process exited with code {process.returncode}. Restarting in 5 seconds...")
            time.sleep(5)
        except Exception as e:
            logging.error(f"Supervisor error: {e}")
            time.sleep(5)

if __name__ == "__main__":
    run_with_restart("main.py")
