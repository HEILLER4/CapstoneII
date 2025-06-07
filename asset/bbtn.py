import threading
from asset.distanc import get_distance  # Optional: used for testing
from mod.GP_s import get_current_location_info
from Main import (
    gps_and_voice, save_location, set_emergency_contact, speak,
    adaptive_threshold, halt_announcements
)

# Global variable to modify
def handle_button_command(buttons: str):
    global halt_announcements

    if buttons == "0001":
        speak("Routing initiated.")
        threading.Thread(target=gps_and_voice, daemon=True).start()

    elif buttons == "0010":
        speak("Saving current location.")
        threading.Thread(target=save_location, daemon=True).start()

    elif buttons == "0011":
        speak("Setting emergency contact.")
        threading.Thread(target=set_emergency_contact, daemon=True).start()

    elif buttons == "0100":
        adaptive_threshold.base_threshold = min(0.5, adaptive_threshold.base_threshold + 0.05)
        speak(f"Threshold increased to {adaptive_threshold.base_threshold:.2f}")

    elif buttons == "0101":
        adaptive_threshold.base_threshold = max(0.1, adaptive_threshold.base_threshold - 0.05)
        speak(f"Threshold decreased to {adaptive_threshold.base_threshold:.2f}")

    elif buttons == "0110":
        halt_announcements = not halt_announcements
        speak("Announcements halted." if halt_announcements else "Announcements resumed.")
