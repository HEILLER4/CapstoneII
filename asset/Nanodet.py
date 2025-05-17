import cv2
import time
from typing import Union, Optional, List, Dict, Tuple, Callable, Set
import numpy as np

from asset.Headless import NanoDetDetector


class NanoDetVisualizer(NanoDetDetector):
	"""
	NanoDet object detector with visualization capabilities.
	Inherits from NanoDetDetector and adds visualization methods.
	"""

	def __init__(self, config_path: str, model_path: str, device: str = "cpu"):
		super().__init__(config_path, model_path, device)

	def visualize(self, img: np.ndarray, detections: List[Dict], score_threshold: float = 0.35) -> np.ndarray:
		result_img = img.copy()

		if not isinstance(detections, list):
			print(f"Invalid detections output: {detections}")
			return img

		for det in detections:
			if det['score'] < score_threshold:
				continue

			bbox = det['bbox']
			class_name = det['class_name']
			score = det['score']
			direction = det.get('direction', '')  # ROI direction

			# Label with direction info
			label = f"{class_name} ({direction}): {score:.2f}"

			# Draw bounding box
			cv2.rectangle(result_img,
						  (int(bbox[0]), int(bbox[1])),
						  (int(bbox[2]), int(bbox[3])),
						  (0, 255, 0), 2)

			# Draw label background
			(label_width, label_height), _ = cv2.getTextSize(
				label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

			cv2.rectangle(result_img,
						  (int(bbox[0]), int(bbox[1]) - label_height - 5),
						  (int(bbox[0]) + label_width, int(bbox[1])),
						  (0, 255, 0), -1)

			# Draw label text
			cv2.putText(result_img, label,
						(int(bbox[0]), int(bbox[1]) - 5),
						cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

		return result_img

	def detect_and_visualize(self, img: Union[str, np.ndarray], score_threshold: float = 0.35) -> Tuple[
		List[dict], np.ndarray]:
		"""
		Perform detection and visualization in one call.

		Args:
			img (Union[str, np.ndarray]): Either path to image or numpy array
			score_threshold (float): Minimum confidence score for detections

		Returns:
			Tuple[List[dict], np.ndarray]:
				- detections: List of detection dictionaries
				- visualized_img: Image with visualizations
		"""
		if isinstance(img, str):
			img = cv2.imread(img)
			if img is None:
				raise ValueError(f"Could not read image from {img}")

		detections = self.get_detections(img, score_threshold)

		# ROI-based left/right detection
		img_width = img.shape[1]
		for det in detections:
			bbox = det["bbox"]
			x_center = (bbox[0] + bbox[2]) / 2
			det["direction"] = "left" if x_center < img_width / 2 else "right"

		visualized_img = self.visualize(img, detections, score_threshold)
		return detections, visualized_img

	def process_camera(
		self,
		url: Union[int, str] = 0,
		window_name: str = "NanoDet",
		score_threshold: float = 0.35,
		exit_key: int = ord('q'),
		log_file: Optional[str] = "detections.log",
		on_detect: Optional[Callable[[Set[str]], None]] = None  # 👈 Callback
	) -> None:
		"""
		Process live camera feed with visualization and detection logging.
		Optionally send detected class names to a callback function.
		"""
		cap = cv2.VideoCapture(url)
		if not cap.isOpened():
			raise RuntimeError(f"Could not open camera {url}")

		log_fp = open(log_file, "w", encoding="utf-8")
		print(f"Logging detections to {log_file}...")
		print(f"Processing camera feed... Press '{chr(exit_key)}' to quit.")

		while True:
			start_time = time.time()
			ret, frame = cap.read()
			if not ret:
				print("Failed to capture frame")
				break



			try:
				detections, visualized_frame = self.detect_and_visualize(frame, score_threshold)
				detected_names = set(det['class_name'] for det in detections)

				if detections:
					print("Detected:", ", ".join(detected_names))
					timestamp = time.strftime("[%Y-%m-%d %H:%M:%S]")
					log_line = f"{timestamp} Detected: {', '.join(detected_names)}"
					print(log_line)
					log_fp.write(log_line + "\n")
					log_fp.flush()

					if on_detect:
						on_detect(detections) # 👈 Call your external handler

				for direction in ("left", "right"):
					names = {det["class_name"] for det in detections if det["direction"] == direction}
					if names:
						print(f"{direction.title()} ROI: {', '.join(names)}")
			except Exception as e:
				print(f"Error processing frame: {e}")
				break

			fps = 1 / (time.time() - start_time)
			cv2.putText(visualized_frame, f"FPS: {fps:.1f}",
						(10, 30), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 255, 0), 2)

			cv2.imshow(window_name, visualized_frame)

			if cv2.waitKey(1) == exit_key:
				break

		cap.release()
		cv2.destroyAllWindows()
		log_fp.close()



	def get_class_names(self) -> List[str]:
		return self.class_names
