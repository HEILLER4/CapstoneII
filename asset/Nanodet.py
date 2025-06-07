import os
import cv2
import time
from typing import Union, Optional, List, Dict, Tuple, Callable
import numpy as np
import logging
from asset.Headless import NanoDetDetector


class NanoDetVisualizer(NanoDetDetector):
    """
    NanoDet object detector with visualization capabilities.
    Inherits from NanoDetDetector and adds visualization methods.
    """

    def __init__(self, config_path: str, model_path: str, device: str = "cpu"):
        super().__init__(config_path, model_path, device)


    @staticmethod
    def is_camera_available(url, timeout=3) -> bool:
        cap = cv2.VideoCapture(url)
        start = time.time()
        while not cap.isOpened() and time.time() - start < timeout:
            time.sleep(0.2)
        available = cap.isOpened()
        cap.release()
        return available

    @staticmethod
    def is_display_available() -> bool:
        return "DISPLAY" in os.environ


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

            label = f"{class_name} ({direction}): {score:.2f}"

            cv2.rectangle(result_img,
                          (int(bbox[0]), int(bbox[1])),
                          (int(bbox[2]), int(bbox[3])),
                          (0, 255, 0), 2)

            (label_width, label_height), _ = cv2.getTextSize(
                label, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)

            cv2.rectangle(result_img,
                          (int(bbox[0]), int(bbox[1]) - label_height - 5),
                          (int(bbox[0]) + label_width, int(bbox[1])),
                          (0, 255, 0), -1)

            cv2.putText(result_img, label,
                        (int(bbox[0]), int(bbox[1]) - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 1)

        return result_img

    def detect_and_visualize(self, img: Union[str, np.ndarray], score_threshold: float = 0.35) -> Tuple[List[dict], np.ndarray]:
        if isinstance(img, str):
            img = cv2.imread(img)
            if img is None:
                raise ValueError(f"Could not read image from {img}")

        detections = self.get_detections(img, score_threshold)
        print("[DEBUG] Raw detections:", detections)

    # ROI-based left/right detection
        img_width = img.shape[1]
        for det in detections:
            bbox = det["bbox"]
            x_center = (bbox[0] + bbox[2]) / 2
            det["direction"] = "left" if x_center < img_width / 2 else "right"
            det['label'] = det.get("class_name", "object")

        visualized_img = self.visualize(img, detections, score_threshold)
        return detections, visualized_img

    def process_camera(
            self,
            url: Union[int, str] = 0,
            window_name: str = "NanoDet",
            score_threshold: float = 0.35,
            exit_key: int = ord('q'),
            log_file: Optional[str] = "detections.log",
            on_detect: Optional[Callable[[List[Dict]], None]] = None
    ) -> None:
        if not self.is_camera_available(url):
            logging.error(f"Camera {url} not available. Skipping detection.")
            return

        display_enabled = self.is_display_available()
        cap = cv2.VideoCapture(url)
        if not cap.isOpened():
            raise RuntimeError(f"Could not open camera {url}")

        log_fp = open(log_file, "w", encoding="utf-8") if log_file else None
        logging.info(f"Logging detections to {log_file}...")

        while True:
            ret, frame = cap.read()
            if not cap.read()[0]:
                logging.warning("Failed to capture frame, retrying...")
                cap.release()
                time.sleep(2)
                cap = cv2.VideoCapture(url)
                print(f"[{time.strftime('%H:%M:%S')}] [ERROR] Camera feed unavailable.")
                continue

            try:
                detections, visualized_frame = self.detect_and_visualize(frame, score_threshold)
                detected_names = set(det['class_name'] for det in detections)

                if detections:
                    log_line = f"{time.strftime('%Y-%m-%d %H:%M:%S')}: {', '.join(detected_names)}"
                    if log_fp:
                        log_fp.write(log_line + "\n")
                        log_fp.flush()
                    logging.info(log_line)
                    if on_detect:
                        on_detect(detections)

                if display_enabled:
                    cv2.imshow(window_name, visualized_frame)
                    if cv2.waitKey(1) & 0xFF == exit_key:
                        break

            except Exception as e:
                logging.error(f"Error during detection: {e}")
                if display_enabled:
                    pass

        cap.release()
        if log_fp:
            log_fp.close()
        if display_enabled:
            cv2.destroyAllWindows()