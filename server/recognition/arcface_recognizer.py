from dataclasses import dataclass

import cv2
import numpy as np
from insightface.app import FaceAnalysis

from config import settings


@dataclass
class FaceMatch:
    """人脸匹配结果。"""
    name: str
    confidence: float


class ArcFaceRecognizer:
    """基于 InsightFace/ArcFace 的人脸识别器。"""

    def __init__(self) -> None:
        """初始化 ArcFace 识别器。"""
        self.app = FaceAnalysis(
            name=settings.arcface_model_name,
            root=settings.model_dir,
            providers=["CUDAExecutionProvider", "CPUExecutionProvider"],
        )
        self.app.prepare(ctx_id=0, det_size=(640, 640))

    def extract_embedding(self, face_image: np.ndarray) -> np.ndarray | None:
        """从人脸图片中提取特征向量。

        Args:
            face_image: BGR 格式的人脸图片（已裁剪）

        Returns:
            512 维特征向量，如果未检测到人脸则返回 None
        """
        faces = self.app.get(face_image)
        if not faces:
            return None
        return faces[0].embedding

    def find_match(
        self,
        embedding: np.ndarray,
        db_embeddings: np.ndarray,
        db_names: list[str],
    ) -> FaceMatch:
        """在数据库中查找最匹配的人脸。

        Args:
            embedding: 待匹配的特征向量
            db_embeddings: 数据库中的所有特征向量 (N, 512)
            db_names: 数据库中的所有人名

        Returns:
            匹配结果，包含人名和余弦相似度
        """
        if len(db_names) == 0:
            return FaceMatch(name="未知", confidence=0.0)

        # 计算余弦相似度
        norms = np.linalg.norm(db_embeddings, axis=1) * np.linalg.norm(embedding)
        similarities = np.dot(db_embeddings, embedding) / norms

        best_idx = int(np.argmax(similarities))
        best_similarity = float(similarities[best_idx])

        if best_similarity >= settings.face_match_threshold:
            return FaceMatch(name=db_names[best_idx], confidence=best_similarity)
        return FaceMatch(name="未知", confidence=best_similarity)


_recognizer: ArcFaceRecognizer | None = None


def get_recognizer() -> ArcFaceRecognizer:
    """获取全局 ArcFace 识别器单例。"""
    global _recognizer
    if _recognizer is None:
        _recognizer = ArcFaceRecognizer()
    return _recognizer
