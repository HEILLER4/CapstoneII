from flask import Flask, request
import threading
import time
from Main import speak, save_location, send_sms

app = Flask(__name__)

# State shared with main logic
state = {
    "announce_level": 1,
    "halt_announcements": False
}

@app.route("/increase", methods=["POST"])
def increase():
    state["announce_level"] += 1
    speak(f"Announcement detail increased to level {state['announce_level']}.")
    return "OK"

@app.route("/decrease", methods=["POST"])
def decrease():
    state["announce_level"] = max(1, state["announce_level"] - 1)
    speak(f"Announcement detail decreased to level {state['announce_level']}.")
    return "OK"

@app.route("/halt", methods=["POST"])
def halt():
    state["halt_announcements"] = not state["halt_announcements"]
    state_txt = "halted" if state["halt_announcements"] else "resumed"
    speak(f"Announcements {state_txt}.")
    return "OK"

@app.route("/save", methods=["POST"])
def save():
    speak("Save location command received.")
    threading.Thread(target=save_location).start()
    return "OK"

@app.route("/emergency", methods=["POST"])
def emergency():
    speak("Emergency command received.")
    threading.Thread(target=send_sms).start()
    return "OK"

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5001)
