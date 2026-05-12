from dataclasses import dataclass

import numpy as np
from ultralytics import YOLO

from config import settings


@dataclass
class FaceDetection:
    """人脸检测结果。"""
    x1: int
    y1: int
    x2: int
    y2: int
    confidence: float


class YOLODetector:
    """基于 YOLOv8 的人脸检测器。"""

    def __init__(self) -> None:
        """加载 YOLO 人脸检测模型。"""
        self.model = YOLO(settings.yolo_model_path)
        self.confidence_threshold = settings.yolo_confidence_threshold

    def detect_faces(self, image: np.ndarray) -> list[FaceDetection]:
        """检测图片中的人脸。

        Args:
            image: BGR 格式的图片 (OpenCV 读取)

        Returns:
            人脸检测结果列表，按置信度降序排列
        """
        results = self.model(image, conf=self.confidence_threshold, verbose=False)

        detections: list[FaceDetection] = []
        for result in results:
            boxes = result.boxes
            if boxes is None:
                continue
            for box in boxes:
                x1, y1, x2, y2 = map(int, box.xyxy[0].tolist())
                conf = float(box.conf[0])
                detections.append(FaceDetection(
                    x1=x1, y1=y1, x2=x2, y2=y2, confidence=conf,
                ))

        detections.sort(key=lambda d: d.confidence, reverse=True)
        return detections


_detector: YOLODetector | None = None


def get_detector() -> YOLODetector:
    """获取全局 YOLO 检测器单例。"""
    global _detector
    if _detector is None:
        _detector = YOLODetector()
    return _detector
