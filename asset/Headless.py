import os
import time
from typing import List, Tuple, Union, Optional

import cv2
import torch
import numpy as np

from nanodet.data.batch_process import stack_batch_img
from nanodet.data.collate import naive_collate
from nanodet.data.transform import Pipeline
from nanodet.model.arch import build_model
from nanodet.util import Logger, cfg, load_config, load_model_weight
from nanodet.util.path import mkdir


class NanoDetDetector:
	"""
	Headless NanoDet object detector for integration with other applications.
	Returns raw detection results without visualization.
	"""

	def __init__(self, config_path: str, model_path: str, device: str = "cpu"):
		"""
		Initialize NanoDet object detector.

		Args:
			config_path (str): Path to model config file
			model_path (str): Path to model weights file
			device (str, optional): Device to run on ('cpu' or 'cuda'). Defaults to 'cpu'.
		"""
		self.device = device

		# Load configuration
		load_config(cfg, config_path)
		self.logger = Logger(-1, use_tensorboard=False)
		self.logger.log = lambda *args, **kwargs: None

		# Build and load model
		model = build_model(cfg.model)
		ckpt = torch.load(model_path, map_location=lambda storage, loc: storage)
		load_model_weight(model, ckpt, self.logger)

		# Handle RepVGG conversion if needed
		if cfg.model.arch.backbone.name == "RepVGG":
			deploy_config = cfg.model
			deploy_config.arch.backbone.update({"deploy": True})
			deploy_model = build_model(deploy_config)
			from nanodet.model.backbone.repvgg import repvgg_det_model_convert
			model = repvgg_det_model_convert(model, deploy_model)

		self.model = model.to(device).eval()
		self.pipeline = Pipeline(cfg.data.val.pipeline, cfg.data.val.keep_ratio)
		self.class_names = cfg.class_names

	def detect(self, img: Union[str, np.ndarray]) -> Tuple[dict, list]:
		"""
		Perform object detection on an input image.

		Args:
			img (Union[str, np.ndarray]): Either path to image or numpy array

		Returns:
			Tuple[dict, list]:
				- meta: Dictionary containing image metadata
				- results: List of detections (each detection contains bbox, score, class_id)
		"""
		img_info = {"id": 0}
		if isinstance(img, str):
			img_info["file_name"] = os.path.basename(img)
			img = cv2.imread(img)
			if img is None:
				raise ValueError(f"Could not read image from {img}")
		else:
			img_info["file_name"] = None

		height, width = img.shape[:2]
		img_info["height"] = height
		img_info["width"] = width
		meta = dict(img_info=img_info, raw_img=img, img=img)

		# Preprocess image
		meta = self.pipeline(None, meta, cfg.data.val.input_size)
		meta["img"] = torch.from_numpy(meta["img"].transpose(2, 0, 1)).to(self.device)
		meta = naive_collate([meta])
		meta["img"] = stack_batch_img(meta["img"], divisible=32)

		# Run inference
		with torch.no_grad():
			results = self.model.inference(meta)

		return meta, results

	def get_detections(self, img: Union[str, np.ndarray], score_threshold: float = 0.35) -> List[dict]:
		meta, results = self.detect(img)
		detections = []

		if not isinstance(results, dict) or 0 not in results:
			print(f"[WARNING] Invalid detection output structure: {results}")
			return []

		# results[0] is a dict where keys are class_ids and values are detections
		class_detections = results[0]

		for class_id, class_dets in class_detections.items():
			for det in class_dets:
				score = det[-1]
				if score < score_threshold:
					continue

				bbox = det[:4]
				detections.append({
					'bbox': bbox,
					'score': score,
					'class_name': self.class_names[class_id],
					'class_id': class_id
				})

		return detections

	def process_image(self, img: Union[str, np.ndarray], score_threshold: float = 0.35) -> List[dict]:
		"""
		Convenience method that combines detection and result formatting.

		Args:
			img (Union[str, np.ndarray]): Either path to image or numpy array
			score_threshold (float): Minimum confidence score for detections

		Returns:
			List[dict]: Formatted detection results
		"""
		return self.get_detections(img, score_threshold)

	def process_video_frame(self, frame: np.ndarray, score_threshold: float = 0.35) -> List[dict]:
		"""
		Process a single video frame.

		Args:
			frame (np.ndarray): Video frame as numpy array
			score_threshold (float): Minimum confidence score for detections

		Returns:
			List[dict]: Formatted detection results
		"""
		return self.get_detections(frame, score_threshold)

	def get_class_names(self) -> List[str]:
		return self.class_names
