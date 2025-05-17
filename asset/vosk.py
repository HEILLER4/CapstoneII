import json
import wave
import pyaudio
from vosk import Model, KaldiRecognizer


class VoskRecognizer:
	def __init__(self, model_path="../models/vosk-model-tl-ph-generic-0.6", sample_rate=16000):
		"""
		Initialize Vosk recognizer with a model.

		Args:
			model_path (str): Path to Vosk model folder
			sample_rate (int): Audio sample rate (default: 16000)
		"""
		self.model = Model(model_path)
		self.sample_rate = sample_rate
		self.recognizer = KaldiRecognizer(self.model, sample_rate)
		self.recognizer.SetWords(True)  # Enable word-level timestamps

	def transcribe_file(self, audio_path):
		"""
		Transcribe a WAV audio file.

		Args:
			audio_path (str): Path to WAV file (must be 16kHz mono)

		Returns:
			str: Full transcription text
		"""
		wf = wave.open(audio_path, "rb")
		if wf.getframerate() != self.sample_rate:
			raise ValueError(f"Audio must be {self.sample_rate}Hz. Got {wf.getframerate()}Hz instead.")

		full_text = []
		while True:
			data = wf.readframes(4000)
			if len(data) == 0:
				break
			if self.recognizer.AcceptWaveform(data):
				result = json.loads(self.recognizer.Result())
				full_text.append(result.get("text", ""))

		final_result = json.loads(self.recognizer.FinalResult())
		full_text.append(final_result.get("text", ""))
		return " ".join(full_text)

	def live_transcribe(self, callback=None, stop_event=None):
		"""
		Live transcription from microphone.

		Args:
			callback (function): Function to call with each new text
			stop_event (threading.Event): Event to stop transcription
		"""
		mic = pyaudio.PyAudio()
		stream = mic.open(
			format=pyaudio.paInt16,
			channels=1,
			rate=self.sample_rate,
			input=True,
			frames_per_buffer=8192
		)

		print("Listening... (Press Ctrl+C to stop)")
		try:
			while not (stop_event and stop_event.is_set()):
				data = stream.read(4096, exception_on_overflow=False)
				if self.recognizer.AcceptWaveform(data):
					result = json.loads(self.recognizer.Result())
					text = result.get("text", "")
					if text and callback:
						callback(text)
		except KeyboardInterrupt:
			pass
		finally:
			stream.stop_stream()
			stream.close()
			mic.terminate()