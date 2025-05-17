import sys
import sounddevice as sd
import queue
import vosk
import json
import threading

q = queue.Queue()
model = vosk.Model("model")  # Ensure vosk model is in ./model


def callback(indata, frames, time, status):
    if status:
        print(status, file=sys.stderr)
    q.put(bytes(indata))


def listen_for_command():
    with sd.RawInputStream(samplerate=16000, blocksize=8000, dtype='int16',
                           channels=1, callback=callback):
        rec = vosk.KaldiRecognizer(model, 16000)
        print("Listening for destination...")
        while True:
            data = q.get()
            if rec.AcceptWaveform(data):
                result = json.loads(rec.Result())
                text = result.get("text", "")
                if text:
                    print("Heard:", text)
                    return text


if __name__ == "__main__":
    listen_for_command()
