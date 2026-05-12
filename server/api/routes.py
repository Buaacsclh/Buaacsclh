import cv2
import numpy as np
from fastapi import APIRouter, File, UploadFile, HTTPException
from pydantic import BaseModel

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

    # TODO: 接入 YOLO 检测和 ArcFace 识别
    raise HTTPException(status_code=501, detail="识别功能尚未实现")
