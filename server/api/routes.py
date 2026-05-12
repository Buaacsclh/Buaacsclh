import cv2
import numpy as np
from fastapi import APIRouter, File, UploadFile, HTTPException
from pydantic import BaseModel

from database.face_db import get_face_db
from detection.yolo_detector import get_detector
from recognition.arcface_recognizer import get_recognizer

router = APIRouter()


class RecognizeResponse(BaseModel):
    """识别结果响应。"""
    status: str
    name: str = ""
    confidence: float = 0.0


class HealthResponse(BaseModel):
    """健康检查响应。"""
    status: str
    version: str


@router.get("/health", response_model=HealthResponse)
async def health_check() -> HealthResponse:
    """健康检查端点。"""
    return HealthResponse(status="ok", version="1.0.0")


@router.post("/api/recognize", response_model=RecognizeResponse)
async def recognize(image: UploadFile = File(...)) -> RecognizeResponse:
    """接收 JPEG 图片，进行人脸检测和识别，返回识别结果。

    流程：图片解码 → YOLO 人脸检测 → ArcFace 特征提取 → 数据库比对

    Args:
        image: 上传的 JPEG 图片文件

    Returns:
        RecognizeResponse: 包含状态、人名和置信度的识别结果
    """
    if not image.content_type or not image.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="上传文件必须是图片格式")

    contents = await image.read()
    if len(contents) == 0:
        raise HTTPException(status_code=400, detail="上传文件为空")

    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="无法解码图片")

    # YOLO 人脸检测
    detector = get_detector()
    detections = detector.detect_faces(img)

    if not detections:
        return RecognizeResponse(status="no_face", name="", confidence=0.0)

    # 取置信度最高的人脸
    best = detections[0]
    face_img = img[best.y1:best.y2, best.x1:best.x2]

    if face_img.size == 0:
        return RecognizeResponse(status="no_face", name="", confidence=0.0)

    # ArcFace 特征提取
    recognizer = get_recognizer()
    embedding = recognizer.extract_embedding(face_img)

    if embedding is None:
        return RecognizeResponse(status="no_face", name="", confidence=0.0)

    # 数据库比对
    db = get_face_db()
    db_embeddings, db_names = db.load_all_embeddings()

    match = recognizer.find_match(embedding, db_embeddings, db_names)

    if match.name == "未知":
        return RecognizeResponse(status="no_face", name="未知", confidence=match.confidence)

    return RecognizeResponse(status="ok", name=match.name, confidence=match.confidence)
