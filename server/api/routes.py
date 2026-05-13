import os
import time
import threading
import cv2
import numpy as np
from fastapi import APIRouter, File, UploadFile, HTTPException
from fastapi.responses import HTMLResponse, StreamingResponse
from pydantic import BaseModel

from database.face_db import get_face_db
from detection.yolo_detector import get_detector
from recognition.arcface_recognizer import get_recognizer

router = APIRouter()

# 存储最新图片的目录
_latest_img_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), "runtime")
os.makedirs(_latest_img_dir, exist_ok=True)
_latest_img_path = os.path.join(_latest_img_dir, "latest.jpg")
_latest_result_img_path = os.path.join(_latest_img_dir, "latest_result.jpg")

# 最新识别结果（线程安全）
_latest_result_lock = threading.Lock()
_latest_result = {
    "status": "waiting",
    "faces": [],
    "timestamp": 0,
    "process_time_ms": 0,
}

# 事件记录（最近 50 条）
_event_log_lock = threading.Lock()
_event_log: list[dict] = []
MAX_EVENT_LOG = 50

# 全局统计
_stats_lock = threading.Lock()
_stats = {
    "uploaded_frames": 0,
    "event_count": 0,
}


class FaceResult(BaseModel):
    """单个人脸识别结果。"""
    name: str
    confidence: float
    bbox: list[int]  # [x1, y1, x2, y2]


class RecognizeResponse(BaseModel):
    """识别结果响应。"""
    status: str
    faces: list[FaceResult] = []
    process_time_ms: int = 0


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

    start_time = time.time()

    nparr = np.frombuffer(contents, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img is None:
        raise HTTPException(status_code=400, detail="无法解码图片")

    # 保存原始图片
    cv2.imwrite(_latest_img_path, img)

    # ArcFace 多人脸识别
    recognizer = get_recognizer()
    faces_data = recognizer.extract_all_embeddings(img)

    if not faces_data:
        result = RecognizeResponse(status="no_face", faces=[])
    else:
        # 数据库比对
        db = get_face_db()
        db_embeddings, db_names = db.load_all_embeddings()

        face_results = []
        for embedding, bbox in faces_data:
            match = recognizer.find_match(embedding, db_embeddings, db_names)
            face_results.append(FaceResult(
                name=match.name,
                confidence=match.confidence,
                bbox=list(bbox),
            ))

        result = RecognizeResponse(status="ok", faces=face_results)

    process_time_ms = int((time.time() - start_time) * 1000)

    # 画人脸框并保存带框图片
    result_img = img.copy()
    if result.status == "ok" and result.faces:
        for face in result.faces:
            x1, y1, x2, y2 = face.bbox
            # 绿色：识别成功，黄色：置信度较低
            color = (0, 255, 0) if face.confidence > 0.6 else (0, 165, 255)
            cv2.rectangle(result_img, (x1, y1), (x2, y2), color, 2)
            label = f"{face.name} {face.confidence:.2f}"
            cv2.putText(result_img, label, (x1, y1 - 10),
                       cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
    cv2.imwrite(_latest_result_img_path, result_img)

    # 更新最新识别结果
    timestamp = time.time()
    with _latest_result_lock:
        _latest_result.update({
            "status": result.status,
            "faces": [f.dict() for f in result.faces],
            "timestamp": timestamp,
            "process_time_ms": process_time_ms,
        })

    # 添加事件记录
    event = {
        "time": time.strftime("%H:%M:%S", time.localtime(timestamp)),
        "event_type": "场景变化",
        "result": result.faces[0].name if result.faces else "no_face",
        "confidence": result.faces[0].confidence if result.faces else 0,
        "face_count": len(result.faces),
        "process_time_ms": process_time_ms,
        "status": "成功" if result.status == "ok" else ("无人脸" if result.status == "no_face" else "错误"),
    }
    with _event_log_lock:
        _event_log.insert(0, event)
        if len(_event_log) > MAX_EVENT_LOG:
            _event_log.pop()

    # 更新统计
    with _stats_lock:
        _stats["uploaded_frames"] += 1
        _stats["event_count"] += 1

    return result


@router.get("/api/latest_image")
async def latest_image():
    """返回 ESP32-CAM 最新拍摄的原始图片。"""
    if not os.path.exists(_latest_img_path):
        raise HTTPException(status_code=404, detail="暂无图片")
    with open(_latest_img_path, "rb") as f:
        img_bytes = f.read()
    return StreamingResponse(
        iter([img_bytes]),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/api/latest_result_image")
async def latest_result_image():
    """返回带人脸框的识别结果图片。"""
    if not os.path.exists(_latest_result_img_path):
        # 如果没有结果图片，返回原始图片
        if not os.path.exists(_latest_img_path):
            raise HTTPException(status_code=404, detail="暂无图片")
        with open(_latest_img_path, "rb") as f:
            img_bytes = f.read()
        return StreamingResponse(
            iter([img_bytes]),
            media_type="image/jpeg",
            headers={"Cache-Control": "no-cache"},
        )
    with open(_latest_result_img_path, "rb") as f:
        img_bytes = f.read()
    return StreamingResponse(
        iter([img_bytes]),
        media_type="image/jpeg",
        headers={"Cache-Control": "no-cache"},
    )


@router.get("/api/latest_result")
async def latest_result():
    """返回最新识别结果。"""
    with _latest_result_lock:
        return dict(_latest_result)


@router.get("/api/stats")
async def get_stats():
    """返回系统运行统计。"""
    with _stats_lock:
        return dict(_stats)


@router.get("/api/events")
async def get_events():
    """返回事件记录列表。"""
    with _event_log_lock:
        return {"events": list(_event_log)}


@router.get("/camera", response_class=HTMLResponse)
async def camera_page():
    """事件驱动识别看板页面。"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>事件驱动边缘视觉识别系统</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0e14;
            --bg-secondary: #0f1419;
            --bg-card: #141921;
            --bg-card-hover: #1a2029;
            --border-primary: #1e2733;
            --border-accent: #00d4ff;
            --text-primary: #e8edf3;
            --text-secondary: #7a8ba3;
            --text-muted: #4a5568;
            --accent-cyan: #00d4ff;
            --accent-cyan-dim: rgba(0, 212, 255, 0.15);
            --accent-green: #00ff88;
            --accent-green-dim: rgba(0, 255, 136, 0.12);
            --accent-amber: #ffb800;
            --accent-amber-dim: rgba(255, 184, 0, 0.12);
            --accent-red: #ff3366;
            --accent-red-dim: rgba(255, 51, 102, 0.12);
            --glow-cyan: 0 0 20px rgba(0, 212, 255, 0.3);
            --glow-green: 0 0 15px rgba(0, 255, 136, 0.25);
            --font-mono: 'JetBrains Mono', monospace;
            --font-sans: 'Inter', -apple-system, sans-serif;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: var(--font-sans);
            min-height: 100vh;
            overflow-x: hidden;
        }

        /* 背景网格效果 */
        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background:
                linear-gradient(90deg, transparent 49.5%, rgba(0, 212, 255, 0.03) 49.5%, rgba(0, 212, 255, 0.03) 50.5%, transparent 50.5%),
                linear-gradient(0deg, transparent 49.5%, rgba(0, 212, 255, 0.03) 49.5%, rgba(0, 212, 255, 0.03) 50.5%, transparent 50.5%);
            background-size: 60px 60px;
            pointer-events: none;
            z-index: 0;
        }

        /* 顶部导航 */
        .header {
            position: relative;
            z-index: 10;
            background: linear-gradient(180deg, rgba(15, 20, 25, 0.98) 0%, rgba(15, 20, 25, 0.95) 100%);
            border-bottom: 1px solid var(--border-primary);
            padding: 0 32px;
            height: 64px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            backdrop-filter: blur(20px);
        }

        .header::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--accent-cyan), transparent);
            opacity: 0.5;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 20px;
        }

        .logo-icon {
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-green));
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            box-shadow: var(--glow-cyan);
        }

        .header h1 {
            font-family: var(--font-mono);
            font-size: 1rem;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: 1px;
        }

        .header-subtitle {
            font-size: 0.7rem;
            color: var(--text-muted);
            font-family: var(--font-mono);
            text-transform: uppercase;
            letter-spacing: 2px;
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 24px;
        }

        .nav-links {
            display: flex;
            gap: 8px;
        }

        .nav-links a {
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 500;
            padding: 8px 16px;
            border-radius: 6px;
            transition: all 0.2s ease;
            position: relative;
        }

        .nav-links a:hover {
            color: var(--accent-cyan);
            background: var(--accent-cyan-dim);
        }

        .nav-links a.active {
            color: var(--accent-cyan);
            background: var(--accent-cyan-dim);
        }

        .status-group {
            display: flex;
            align-items: center;
            gap: 16px;
            padding-left: 24px;
            border-left: 1px solid var(--border-primary);
        }

        .status-indicator {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.75rem;
            font-family: var(--font-mono);
            color: var(--text-secondary);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            position: relative;
        }

        .status-dot.online {
            background: var(--accent-green);
            box-shadow: 0 0 8px var(--accent-green);
        }

        .status-dot.online::after {
            content: '';
            position: absolute;
            top: -3px;
            left: -3px;
            right: -3px;
            bottom: -3px;
            border-radius: 50%;
            border: 1px solid var(--accent-green);
            animation: pulse-ring 2s ease-out infinite;
        }

        @keyframes pulse-ring {
            0% { transform: scale(1); opacity: 1; }
            100% { transform: scale(1.5); opacity: 0; }
        }

        .event-counter {
            font-family: var(--font-mono);
            font-size: 0.8rem;
            color: var(--accent-cyan);
            background: var(--accent-cyan-dim);
            padding: 6px 14px;
            border-radius: 20px;
            border: 1px solid rgba(0, 212, 255, 0.2);
        }

        /* 主容器 */
        .container {
            position: relative;
            z-index: 1;
            max-width: 1400px;
            margin: 0 auto;
            padding: 24px 32px;
        }

        /* 统计卡片 */
        .stats-bar {
            display: grid;
            grid-template-columns: repeat(4, 1fr);
            gap: 16px;
            margin-bottom: 24px;
        }

        .stat-card {
            background: var(--bg-card);
            border: 1px solid var(--border-primary);
            border-radius: 12px;
            padding: 20px 24px;
            position: relative;
            overflow: hidden;
            transition: all 0.3s ease;
        }

        .stat-card:hover {
            border-color: var(--accent-cyan);
            transform: translateY(-2px);
            box-shadow: 0 8px 32px rgba(0, 0, 0, 0.3);
        }

        .stat-card::before {
            content: '';
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            height: 3px;
            background: linear-gradient(90deg, var(--accent-cyan), transparent);
            opacity: 0;
            transition: opacity 0.3s ease;
        }

        .stat-card:hover::before {
            opacity: 1;
        }

        .stat-card:nth-child(1) { --card-accent: var(--accent-cyan); }
        .stat-card:nth-child(2) { --card-accent: var(--accent-green); }
        .stat-card:nth-child(3) { --card-accent: var(--accent-amber); }
        .stat-card:nth-child(4) { --card-accent: var(--accent-red); }

        .stat-card:nth-child(1)::before { background: linear-gradient(90deg, var(--accent-cyan), transparent); }
        .stat-card:nth-child(2)::before { background: linear-gradient(90deg, var(--accent-green), transparent); }
        .stat-card:nth-child(3)::before { background: linear-gradient(90deg, var(--accent-amber), transparent); }
        .stat-card:nth-child(4)::before { background: linear-gradient(90deg, var(--accent-red), transparent); }

        .stat-label {
            font-size: 0.7rem;
            font-weight: 500;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 12px;
            font-family: var(--font-mono);
        }

        .stat-value {
            font-family: var(--font-mono);
            font-size: 2rem;
            font-weight: 700;
            color: var(--text-primary);
            line-height: 1;
            letter-spacing: -1px;
        }

        .stat-card:nth-child(1) .stat-value { color: var(--accent-cyan); }
        .stat-card:nth-child(2) .stat-value { color: var(--accent-green); }
        .stat-card:nth-child(3) .stat-value { color: var(--accent-amber); }
        .stat-card:nth-child(4) .stat-value { color: var(--accent-red); }

        .stat-unit {
            font-size: 0.9rem;
            font-weight: 400;
            color: var(--text-secondary);
            margin-left: 4px;
        }

        /* 主内容区 */
        .main-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 24px;
            margin-bottom: 24px;
        }

        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-primary);
            border-radius: 12px;
            overflow: hidden;
            transition: all 0.3s ease;
        }

        .card:hover {
            border-color: rgba(0, 212, 255, 0.3);
        }

        .card-header {
            padding: 16px 24px;
            border-bottom: 1px solid var(--border-primary);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .card-title {
            font-family: var(--font-mono);
            font-size: 0.75rem;
            font-weight: 600;
            color: var(--text-secondary);
            text-transform: uppercase;
            letter-spacing: 2px;
        }

        .card-badge {
            font-size: 0.65rem;
            font-family: var(--font-mono);
            color: var(--accent-cyan);
            background: var(--accent-cyan-dim);
            padding: 4px 10px;
            border-radius: 4px;
            border: 1px solid rgba(0, 212, 255, 0.2);
        }

        .card-body {
            padding: 24px;
        }

        /* 关键帧区域 */
        .frame-container {
            position: relative;
            background: #000;
            border-radius: 8px;
            overflow: hidden;
            aspect-ratio: 4/3;
            display: flex;
            align-items: center;
            justify-content: center;
            border: 1px solid var(--border-primary);
        }

        .frame-container img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }

        .frame-overlay {
            position: absolute;
            top: 0;
            left: 0;
            right: 0;
            bottom: 0;
            pointer-events: none;
        }

        .frame-corner {
            position: absolute;
            width: 20px;
            height: 20px;
            border-color: var(--accent-cyan);
            border-style: solid;
            border-width: 0;
        }

        .frame-corner.tl { top: 12px; left: 12px; border-top-width: 2px; border-left-width: 2px; }
        .frame-corner.tr { top: 12px; right: 12px; border-top-width: 2px; border-right-width: 2px; }
        .frame-corner.bl { bottom: 12px; left: 12px; border-bottom-width: 2px; border-left-width: 2px; }
        .frame-corner.br { bottom: 12px; right: 12px; border-bottom-width: 2px; border-right-width: 2px; }

        .frame-status {
            position: absolute;
            bottom: 16px;
            left: 16px;
            background: rgba(10, 14, 20, 0.85);
            padding: 8px 14px;
            border-radius: 6px;
            font-family: var(--font-mono);
            font-size: 0.75rem;
            color: var(--text-secondary);
            backdrop-filter: blur(10px);
            border: 1px solid var(--border-primary);
        }

        .frame-time {
            position: absolute;
            top: 16px;
            right: 16px;
            background: rgba(10, 14, 20, 0.85);
            padding: 8px 14px;
            border-radius: 6px;
            font-family: var(--font-mono);
            font-size: 0.75rem;
            color: var(--accent-cyan);
            backdrop-filter: blur(10px);
            border: 1px solid rgba(0, 212, 255, 0.2);
        }

        .frame-meta {
            margin-top: 16px;
            display: flex;
            flex-direction: column;
            gap: 8px;
        }

        .frame-meta-item {
            font-size: 0.8rem;
            color: var(--text-secondary);
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .frame-meta-item .dot {
            width: 6px;
            height: 6px;
            border-radius: 50%;
            background: var(--text-muted);
        }

        .frame-meta-item.success .dot { background: var(--accent-green); }
        .frame-meta-item.warning .dot { background: var(--accent-amber); }

        /* 识别结果区域 */
        .result-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 12px;
        }

        .result-item {
            background: var(--bg-secondary);
            border: 1px solid var(--border-primary);
            border-radius: 8px;
            padding: 16px;
            transition: all 0.2s ease;
        }

        .result-item:hover {
            border-color: var(--border-accent);
            background: var(--bg-card-hover);
        }

        .result-label {
            font-size: 0.65rem;
            font-weight: 500;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            margin-bottom: 8px;
            font-family: var(--font-mono);
        }

        .result-value {
            font-family: var(--font-mono);
            font-size: 1.1rem;
            font-weight: 600;
            color: var(--text-primary);
        }

        .result-value.success { color: var(--accent-green); }
        .result-value.warning { color: var(--accent-amber); }
        .result-value.error { color: var(--accent-red); }

        .waiting-state {
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            padding: 40px 20px;
            text-align: center;
        }

        .waiting-icon {
            width: 48px;
            height: 48px;
            border: 2px solid var(--border-primary);
            border-top-color: var(--accent-cyan);
            border-radius: 50%;
            animation: spin 1s linear infinite;
            margin-bottom: 16px;
        }

        @keyframes spin {
            to { transform: rotate(360deg); }
        }

        .waiting-text {
            font-family: var(--font-mono);
            font-size: 0.85rem;
            color: var(--text-muted);
        }

        /* 事件记录表格 */
        .event-table-wrapper {
            overflow-x: auto;
        }

        .event-table {
            width: 100%;
            border-collapse: collapse;
            font-size: 0.85rem;
        }

        .event-table thead {
            position: sticky;
            top: 0;
            z-index: 1;
        }

        .event-table th {
            background: var(--bg-secondary);
            padding: 14px 16px;
            text-align: left;
            font-family: var(--font-mono);
            font-size: 0.7rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1px;
            border-bottom: 1px solid var(--border-primary);
        }

        .event-table td {
            padding: 14px 16px;
            border-bottom: 1px solid rgba(30, 39, 51, 0.5);
            font-family: var(--font-mono);
            font-size: 0.8rem;
            color: var(--text-secondary);
        }

        .event-table tbody tr {
            transition: all 0.15s ease;
        }

        .event-table tbody tr:hover {
            background: rgba(0, 212, 255, 0.04);
        }

        .event-table tbody tr:hover td {
            color: var(--text-primary);
        }

        .badge {
            display: inline-flex;
            align-items: center;
            gap: 6px;
            padding: 4px 10px;
            border-radius: 4px;
            font-size: 0.7rem;
            font-weight: 600;
            font-family: var(--font-mono);
        }

        .badge::before {
            content: '';
            width: 6px;
            height: 6px;
            border-radius: 50%;
        }

        .badge-success {
            background: var(--accent-green-dim);
            color: var(--accent-green);
            border: 1px solid rgba(0, 255, 136, 0.2);
        }
        .badge-success::before { background: var(--accent-green); }

        .badge-warning {
            background: var(--accent-amber-dim);
            color: var(--accent-amber);
            border: 1px solid rgba(255, 184, 0, 0.2);
        }
        .badge-warning::before { background: var(--accent-amber); }

        .badge-error {
            background: var(--accent-red-dim);
            color: var(--accent-red);
            border: 1px solid rgba(255, 51, 102, 0.2);
        }
        .badge-error::before { background: var(--accent-red); }

        .empty-state {
            text-align: center;
            padding: 48px 20px;
            color: var(--text-muted);
            font-family: var(--font-mono);
            font-size: 0.85rem;
        }

        /* 扫描线效果（可选，增加复古感） */
        .scanline {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: repeating-linear-gradient(
                0deg,
                transparent,
                transparent 2px,
                rgba(0, 212, 255, 0.01) 2px,
                rgba(0, 212, 255, 0.01) 4px
            );
            pointer-events: none;
            z-index: 999;
            opacity: 0.3;
        }

        /* 动画 */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }

        .stat-card, .card {
            animation: fadeIn 0.5s ease forwards;
        }

        .stat-card:nth-child(1) { animation-delay: 0.1s; }
        .stat-card:nth-child(2) { animation-delay: 0.15s; }
        .stat-card:nth-child(3) { animation-delay: 0.2s; }
        .stat-card:nth-child(4) { animation-delay: 0.25s; }

        .main-grid .card:nth-child(1) { animation-delay: 0.3s; }
        .main-grid .card:nth-child(2) { animation-delay: 0.35s; }
    </style>
</head>
<body>
    <!-- 扫描线效果 -->
    <div class="scanline"></div>

    <!-- 顶部导航 -->
    <div class="header">
        <div class="header-left">
            <div class="logo-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                    <circle cx="12" cy="12" r="3"></circle>
                </svg>
            </div>
            <div>
                <h1>事件驱动边缘视觉识别系统</h1>
                <div class="header-subtitle">Event-Driven Edge Vision Recognition</div>
            </div>
        </div>
        <div class="header-right">
            <nav class="nav-links">
                <a href="/camera" class="active">识别看板</a>
                <a href="/enroll">人脸录入</a>
            </nav>
            <div class="status-group">
                <div class="status-indicator">
                    <span class="status-dot online"></span>
                    <span>ESP32-CAM</span>
                </div>
                <div class="status-indicator">
                    <span class="status-dot online"></span>
                    <span>Server</span>
                </div>
                <div class="event-counter" id="event-count">EVENTS: 0</div>
            </div>
        </div>
    </div>

    <!-- 主容器 -->
    <div class="container">
        <!-- 统计卡片 -->
        <div class="stats-bar">
            <div class="stat-card">
                <div class="stat-label">上传帧数</div>
                <div class="stat-value" id="stat-uploaded">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">识别事件</div>
                <div class="stat-value" id="stat-events">0</div>
            </div>
            <div class="stat-card">
                <div class="stat-label">处理耗时</div>
                <div class="stat-value" id="stat-process-time">--<span class="stat-unit">ms</span></div>
            </div>
            <div class="stat-card">
                <div class="stat-label">最近置信度</div>
                <div class="stat-value" id="stat-last-confidence">--<span class="stat-unit">%</span></div>
            </div>
        </div>

        <!-- 主内容区 -->
        <div class="main-grid">
            <!-- 左侧：最近关键帧 -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">最近识别关键帧</span>
                    <span class="card-badge">LIVE FEED</span>
                </div>
                <div class="card-body">
                    <div class="frame-container">
                        <img id="result-frame" src="/api/latest_result_image" alt="最近关键帧">
                        <div class="frame-overlay">
                            <div class="frame-corner tl"></div>
                            <div class="frame-corner tr"></div>
                            <div class="frame-corner bl"></div>
                            <div class="frame-corner br"></div>
                        </div>
                        <div class="frame-status" id="frame-status">等待事件触发</div>
                        <div class="frame-time" id="frame-time">--:--:--</div>
                    </div>
                    <div class="frame-meta">
                        <div class="frame-meta-item" id="last-update">
                            <span class="dot"></span>
                            <span>上次更新：等待中...</span>
                        </div>
                        <div class="frame-meta-item" id="scene-status">
                            <span class="dot"></span>
                            <span>当前场景稳定，暂无新关键帧上传</span>
                        </div>
                    </div>
                </div>
            </div>

            <!-- 右侧：本次识别结果 -->
            <div class="card">
                <div class="card-header">
                    <span class="card-title">本次识别结果</span>
                    <span class="card-badge">ANALYSIS</span>
                </div>
                <div class="card-body">
                    <div id="result-content">
                        <div class="waiting-state">
                            <div class="waiting-icon"></div>
                            <div class="waiting-text">等待事件触发...</div>
                        </div>
                    </div>
                </div>
            </div>
        </div>

        <!-- 事件记录 -->
        <div class="card">
            <div class="card-header">
                <span class="card-title">事件记录</span>
                <span class="card-badge">HISTORY</span>
            </div>
            <div class="card-body" style="padding: 0;">
                <div class="event-table-wrapper">
                    <table class="event-table">
                        <thead>
                            <tr>
                                <th>时间</th>
                                <th>事件类型</th>
                                <th>识别结果</th>
                                <th>置信度</th>
                                <th>人脸数</th>
                                <th>处理耗时</th>
                                <th>状态</th>
                            </tr>
                        </thead>
                        <tbody id="event-list">
                            <tr>
                                <td colspan="7">
                                    <div class="empty-state">暂无事件记录</div>
                                </td>
                            </tr>
                        </tbody>
                    </table>
                </div>
            </div>
        </div>
    </div>

    <script>
        // 元素引用
        const resultFrame = document.getElementById('result-frame');
        const frameStatus = document.getElementById('frame-status');
        const frameTime = document.getElementById('frame-time');
        const lastUpdate = document.getElementById('last-update');
        const sceneStatus = document.getElementById('scene-status');
        const resultContent = document.getElementById('result-content');
        const eventList = document.getElementById('event-list');
        const eventCount = document.getElementById('event-count');
        const statUploaded = document.getElementById('stat-uploaded');
        const statEvents = document.getElementById('stat-events');
        const statProcessTime = document.getElementById('stat-process-time');
        const statLastConfidence = document.getElementById('stat-last-confidence');

        let lastTimestamp = 0;

        // 获取最新识别结果
        async function fetchResult() {
            try {
                const res = await fetch('/api/latest_result');
                const data = await res.json();

                if (data.timestamp && data.timestamp !== lastTimestamp) {
                    lastTimestamp = data.timestamp;
                    updateResultDisplay(data);
                    resultFrame.src = '/api/latest_result_image?t=' + Date.now();
                }
            } catch (e) {
                console.error('获取结果失败:', e);
            }
        }

        // 更新识别结果显示
        function updateResultDisplay(data) {
            const time = new Date(data.timestamp * 1000).toLocaleTimeString();
            const timeStr = new Date(data.timestamp * 1000).toLocaleString();

            frameTime.textContent = time;
            lastUpdate.innerHTML = `<span class="dot"></span><span>上次更新：${timeStr}</span>`;

            if (data.status === 'ok' && data.faces && data.faces.length > 0) {
                sceneStatus.innerHTML = '<span class="dot"></span><span>检测到场景变化，已上传关键帧并完成识别</span>';
                sceneStatus.className = 'frame-meta-item success';
                frameStatus.textContent = '识别成功';
                frameStatus.style.color = 'var(--accent-green)';
                frameStatus.style.borderColor = 'rgba(0, 255, 136, 0.3)';

                const face = data.faces[0];
                const confidence = (face.confidence * 100).toFixed(1);

                resultContent.innerHTML = `
                    <div class="result-grid">
                        <div class="result-item">
                            <div class="result-label">识别状态</div>
                            <div class="result-value success">识别成功</div>
                        </div>
                        <div class="result-item">
                            <div class="result-label">姓名</div>
                            <div class="result-value">${face.name}</div>
                        </div>
                        <div class="result-item">
                            <div class="result-label">置信度</div>
                            <div class="result-value">${confidence}%</div>
                        </div>
                        <div class="result-item">
                            <div class="result-label">人脸数量</div>
                            <div class="result-value">${data.faces.length}</div>
                        </div>
                        <div class="result-item">
                            <div class="result-label">触发原因</div>
                            <div class="result-value">场景变化</div>
                        </div>
                        <div class="result-item">
                            <div class="result-label">处理耗时</div>
                            <div class="result-value">${data.process_time_ms || '--'} ms</div>
                        </div>
                    </div>
                `;

                statProcessTime.innerHTML = `${data.process_time_ms || '--'}<span class="stat-unit">ms</span>`;
                statLastConfidence.innerHTML = `${confidence}<span class="stat-unit">%</span>`;
            } else if (data.status === 'no_face') {
                sceneStatus.innerHTML = '<span class="dot"></span><span>检测到场景变化，但未检测到人脸</span>';
                sceneStatus.className = 'frame-meta-item warning';
                frameStatus.textContent = '无人脸';
                frameStatus.style.color = 'var(--accent-amber)';
                frameStatus.style.borderColor = 'rgba(255, 184, 0, 0.3)';

                resultContent.innerHTML = `
                    <div class="result-grid">
                        <div class="result-item">
                            <div class="result-label">识别状态</div>
                            <div class="result-value warning">无人脸</div>
                        </div>
                        <div class="result-item">
                            <div class="result-label">触发原因</div>
                            <div class="result-value">场景变化</div>
                        </div>
                    </div>
                `;
            } else {
                sceneStatus.innerHTML = '<span class="dot"></span><span>识别失败</span>';
                sceneStatus.className = 'frame-meta-item';
                frameStatus.textContent = '错误';
                frameStatus.style.color = 'var(--accent-red)';
                frameStatus.style.borderColor = 'rgba(255, 51, 102, 0.3)';

                resultContent.innerHTML = `
                    <div class="result-grid">
                        <div class="result-item">
                            <div class="result-label">识别状态</div>
                            <div class="result-value error">错误</div>
                        </div>
                    </div>
                `;
            }
        }

        // 获取统计数据
        async function fetchStats() {
            try {
                const res = await fetch('/api/stats');
                const data = await res.json();
                statUploaded.textContent = data.uploaded_frames || 0;
                statEvents.textContent = data.event_count || 0;
                eventCount.textContent = 'EVENTS: ' + (data.event_count || 0);
            } catch (e) {
                console.error('获取统计失败:', e);
            }
        }

        // 获取事件记录
        async function fetchEvents() {
            try {
                const res = await fetch('/api/events');
                const data = await res.json();

                if (data.events && data.events.length > 0) {
                    let html = '';
                    data.events.forEach(event => {
                        const confidenceStr = event.confidence ? (event.confidence * 100).toFixed(1) + '%' : '-';
                        let badgeClass = 'badge-success';
                        let badgeText = '成功';
                        if (event.status === '无人脸') {
                            badgeClass = 'badge-warning';
                            badgeText = '无人脸';
                        } else if (event.status === '未知人员') {
                            badgeClass = 'badge-warning';
                            badgeText = '未知';
                        } else if (event.status === '错误') {
                            badgeClass = 'badge-error';
                            badgeText = '错误';
                        }

                        html += `
                            <tr>
                                <td>${event.time}</td>
                                <td>${event.event_type}</td>
                                <td>${event.result}</td>
                                <td>${confidenceStr}</td>
                                <td>${event.face_count}</td>
                                <td>${event.process_time_ms} ms</td>
                                <td><span class="badge ${badgeClass}">${badgeText}</span></td>
                            </tr>
                        `;
                    });
                    eventList.innerHTML = html;
                }
            } catch (e) {
                console.error('获取事件记录失败:', e);
            }
        }

        // 定时轮询
        setInterval(fetchResult, 2000);
        setInterval(fetchStats, 5000);
        setInterval(fetchEvents, 3000);

        // 初始加载
        fetchResult();
        fetchStats();
        fetchEvents();
    </script>
</body>
</html>
"""


class EnrollResponse(BaseModel):
    """人脸录入响应。"""
    status: str
    message: str
    name: str = ""
    count: int = 0


@router.post("/api/enroll", response_model=EnrollResponse)
async def enroll_face(
    name: str,
    images: list[UploadFile] = File(...),
) -> EnrollResponse:
    """批量录入人脸图片到数据库。

    Args:
        name: 人名
        images: 上传的人脸图片列表

    Returns:
        EnrollResponse: 录入结果
    """
    if not name.strip():
        raise HTTPException(status_code=400, detail="人名不能为空")

    if not images:
        raise HTTPException(status_code=400, detail="请上传至少一张图片")

    recognizer = get_recognizer()
    db = get_face_db()

    embeddings = []
    success_count = 0
    fail_count = 0

    for image in images:
        if not image.content_type or not image.content_type.startswith("image/"):
            fail_count += 1
            continue

        contents = await image.read()
        if len(contents) == 0:
            fail_count += 1
            continue

        nparr = np.frombuffer(contents, np.uint8)
        img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
        if img is None:
            fail_count += 1
            continue

        embedding = recognizer.extract_embedding(img)
        if embedding is None:
            fail_count += 1
            continue

        embeddings.append(embedding)
        success_count += 1

    if not embeddings:
        return EnrollResponse(
            status="error",
            message="没有成功提取到任何人脸特征",
            name=name,
            count=0,
        )

    # 计算平均特征向量
    mean_embedding = np.mean(embeddings, axis=0)
    norm = np.linalg.norm(mean_embedding)
    if norm > 0:
        mean_embedding = mean_embedding / norm

    # 保存到数据库
    try:
        db.add_face(name.strip(), mean_embedding)
    except Exception as e:
        return EnrollResponse(
            status="error",
            message=f"保存失败: {str(e)}",
            name=name,
            count=0,
        )

    return EnrollResponse(
        status="ok",
        message=f"录入成功: {success_count} 张, 失败: {fail_count} 张",
        name=name.strip(),
        count=success_count,
    )


@router.get("/enroll", response_class=HTMLResponse)
async def enroll_page():
    """人脸录入页面。"""
    return """<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>事件驱动边缘视觉识别系统 - 人脸录入</title>
    <link rel="preconnect" href="https://fonts.googleapis.com">
    <link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@300;400;500;600&display=swap" rel="stylesheet">
    <style>
        :root {
            --bg-primary: #0a0e14;
            --bg-secondary: #0f1419;
            --bg-card: #141921;
            --bg-card-hover: #1a2029;
            --border-primary: #1e2733;
            --border-accent: #00d4ff;
            --text-primary: #e8edf3;
            --text-secondary: #7a8ba3;
            --text-muted: #4a5568;
            --accent-cyan: #00d4ff;
            --accent-cyan-dim: rgba(0, 212, 255, 0.15);
            --accent-green: #00ff88;
            --accent-green-dim: rgba(0, 255, 136, 0.12);
            --accent-amber: #ffb800;
            --accent-amber-dim: rgba(255, 184, 0, 0.12);
            --accent-red: #ff3366;
            --accent-red-dim: rgba(255, 51, 102, 0.12);
            --glow-cyan: 0 0 20px rgba(0, 212, 255, 0.3);
            --glow-green: 0 0 15px rgba(0, 255, 136, 0.25);
            --font-mono: 'JetBrains Mono', monospace;
            --font-sans: 'Inter', -apple-system, sans-serif;
        }

        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            background: var(--bg-primary);
            color: var(--text-primary);
            font-family: var(--font-sans);
            min-height: 100vh;
            overflow-x: hidden;
        }

        /* 背景网格效果 */
        body::before {
            content: '';
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background:
                linear-gradient(90deg, transparent 49.5%, rgba(0, 212, 255, 0.03) 49.5%, rgba(0, 212, 255, 0.03) 50.5%, transparent 50.5%),
                linear-gradient(0deg, transparent 49.5%, rgba(0, 212, 255, 0.03) 49.5%, rgba(0, 212, 255, 0.03) 50.5%, transparent 50.5%);
            background-size: 60px 60px;
            pointer-events: none;
            z-index: 0;
        }

        /* 顶部导航 */
        .header {
            position: relative;
            z-index: 10;
            background: linear-gradient(180deg, rgba(15, 20, 25, 0.98) 0%, rgba(15, 20, 25, 0.95) 100%);
            border-bottom: 1px solid var(--border-primary);
            padding: 0 32px;
            height: 64px;
            display: flex;
            align-items: center;
            justify-content: space-between;
            backdrop-filter: blur(20px);
        }

        .header::after {
            content: '';
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 1px;
            background: linear-gradient(90deg, transparent, var(--accent-cyan), transparent);
            opacity: 0.5;
        }

        .header-left {
            display: flex;
            align-items: center;
            gap: 20px;
        }

        .logo-icon {
            width: 36px;
            height: 36px;
            background: linear-gradient(135deg, var(--accent-cyan), var(--accent-green));
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 18px;
            box-shadow: var(--glow-cyan);
        }

        .header h1 {
            font-family: var(--font-mono);
            font-size: 1rem;
            font-weight: 600;
            color: var(--text-primary);
            letter-spacing: 1px;
        }

        .header-subtitle {
            font-size: 0.7rem;
            color: var(--text-muted);
            font-family: var(--font-mono);
            text-transform: uppercase;
            letter-spacing: 2px;
        }

        .header-right {
            display: flex;
            align-items: center;
            gap: 24px;
        }

        .nav-links {
            display: flex;
            gap: 8px;
        }

        .nav-links a {
            color: var(--text-secondary);
            text-decoration: none;
            font-size: 0.85rem;
            font-weight: 500;
            padding: 8px 16px;
            border-radius: 6px;
            transition: all 0.2s ease;
            position: relative;
        }

        .nav-links a:hover {
            color: var(--accent-cyan);
            background: var(--accent-cyan-dim);
        }

        .nav-links a.active {
            color: var(--accent-cyan);
            background: var(--accent-cyan-dim);
        }

        .status-group {
            display: flex;
            align-items: center;
            gap: 16px;
            padding-left: 24px;
            border-left: 1px solid var(--border-primary);
        }

        .status-indicator {
            display: flex;
            align-items: center;
            gap: 8px;
            font-size: 0.75rem;
            font-family: var(--font-mono);
            color: var(--text-secondary);
        }

        .status-dot {
            width: 8px;
            height: 8px;
            border-radius: 50%;
            position: relative;
        }

        .status-dot.online {
            background: var(--accent-green);
            box-shadow: 0 0 8px var(--accent-green);
        }

        .status-dot.online::after {
            content: '';
            position: absolute;
            top: -3px;
            left: -3px;
            right: -3px;
            bottom: -3px;
            border-radius: 50%;
            border: 1px solid var(--accent-green);
            animation: pulse-ring 2s ease-out infinite;
        }

        @keyframes pulse-ring {
            0% { transform: scale(1); opacity: 1; }
            100% { transform: scale(1.5); opacity: 0; }
        }

        /* 主容器 */
        .container {
            position: relative;
            z-index: 1;
            max-width: 900px;
            margin: 0 auto;
            padding: 32px;
        }

        /* 卡片样式 */
        .card {
            background: var(--bg-card);
            border: 1px solid var(--border-primary);
            border-radius: 12px;
            overflow: hidden;
            margin-bottom: 24px;
            animation: fadeIn 0.5s ease forwards;
        }

        .card:nth-child(1) { animation-delay: 0.1s; }
        .card:nth-child(2) { animation-delay: 0.2s; }

        .card-header {
            padding: 20px 24px;
            border-bottom: 1px solid var(--border-primary);
            display: flex;
            align-items: center;
            justify-content: space-between;
        }

        .card-title {
            font-family: var(--font-mono);
            font-size: 0.85rem;
            font-weight: 600;
            color: var(--text-primary);
            display: flex;
            align-items: center;
            gap: 12px;
        }

        .card-title .icon {
            width: 32px;
            height: 32px;
            background: var(--accent-cyan-dim);
            border: 1px solid rgba(0, 212, 255, 0.2);
            border-radius: 8px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 16px;
        }

        .card-badge {
            font-size: 0.65rem;
            font-family: var(--font-mono);
            color: var(--accent-cyan);
            background: var(--accent-cyan-dim);
            padding: 4px 10px;
            border-radius: 4px;
            border: 1px solid rgba(0, 212, 255, 0.2);
        }

        .card-body {
            padding: 24px;
        }

        /* 表单样式 */
        .form-group {
            margin-bottom: 24px;
        }

        .form-label {
            display: block;
            font-family: var(--font-mono);
            font-size: 0.7rem;
            font-weight: 600;
            color: var(--text-muted);
            text-transform: uppercase;
            letter-spacing: 1.5px;
            margin-bottom: 10px;
        }

        .form-input {
            width: 100%;
            padding: 14px 18px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-primary);
            border-radius: 8px;
            color: var(--text-primary);
            font-family: var(--font-sans);
            font-size: 0.95rem;
            transition: all 0.2s ease;
            outline: none;
        }

        .form-input:focus {
            border-color: var(--accent-cyan);
            box-shadow: 0 0 0 3px var(--accent-cyan-dim);
        }

        .form-input::placeholder {
            color: var(--text-muted);
        }

        /* 上传区域 */
        .upload-zone {
            border: 2px dashed var(--border-primary);
            border-radius: 12px;
            padding: 48px 24px;
            text-align: center;
            cursor: pointer;
            transition: all 0.3s ease;
            background: var(--bg-secondary);
            position: relative;
            overflow: hidden;
        }

        .upload-zone:hover {
            border-color: var(--accent-cyan);
            background: rgba(0, 212, 255, 0.03);
        }

        .upload-zone.dragover {
            border-color: var(--accent-cyan);
            background: rgba(0, 212, 255, 0.08);
            transform: scale(1.01);
        }

        .upload-icon {
            width: 64px;
            height: 64px;
            margin: 0 auto 20px;
            background: var(--accent-cyan-dim);
            border: 1px solid rgba(0, 212, 255, 0.2);
            border-radius: 16px;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 28px;
            transition: all 0.3s ease;
        }

        .upload-zone:hover .upload-icon {
            transform: translateY(-4px);
            box-shadow: var(--glow-cyan);
        }

        .upload-title {
            font-family: var(--font-mono);
            font-size: 0.9rem;
            font-weight: 600;
            color: var(--text-primary);
            margin-bottom: 8px;
        }

        .upload-hint {
            font-size: 0.8rem;
            color: var(--text-muted);
        }

        .file-input {
            display: none;
        }

        /* 预览网格 */
        .preview-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(120px, 1fr));
            gap: 12px;
            margin-top: 20px;
        }

        .preview-item {
            position: relative;
            aspect-ratio: 1;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid var(--border-primary);
            transition: all 0.2s ease;
        }

        .preview-item:hover {
            border-color: var(--accent-cyan);
            transform: scale(1.05);
        }

        .preview-item img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }

        .preview-remove {
            position: absolute;
            top: 6px;
            right: 6px;
            background: rgba(255, 51, 102, 0.9);
            color: white;
            border: none;
            border-radius: 50%;
            width: 24px;
            height: 24px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 12px;
            opacity: 0;
            transition: opacity 0.2s ease;
        }

        .preview-item:hover .preview-remove {
            opacity: 1;
        }

        /* 提交按钮 */
        .btn {
            padding: 14px 28px;
            border: none;
            border-radius: 8px;
            font-family: var(--font-mono);
            font-size: 0.85rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.3s ease;
            text-transform: uppercase;
            letter-spacing: 1px;
            display: inline-flex;
            align-items: center;
            gap: 10px;
        }

        .btn-primary {
            background: linear-gradient(135deg, var(--accent-cyan), #0099cc);
            color: white;
            box-shadow: 0 4px 16px rgba(0, 212, 255, 0.3);
        }

        .btn-primary:hover {
            transform: translateY(-2px);
            box-shadow: 0 6px 24px rgba(0, 212, 255, 0.4);
        }

        .btn-primary:disabled {
            background: var(--bg-card-hover);
            color: var(--text-muted);
            box-shadow: none;
            cursor: not-allowed;
            transform: none;
        }

        /* 消息提示 */
        .message {
            padding: 16px 20px;
            border-radius: 8px;
            margin-top: 20px;
            font-family: var(--font-mono);
            font-size: 0.85rem;
            display: none;
            animation: fadeIn 0.3s ease;
        }

        .message.success {
            background: var(--accent-green-dim);
            border: 1px solid rgba(0, 255, 136, 0.3);
            color: var(--accent-green);
            display: block;
        }

        .message.error {
            background: var(--accent-red-dim);
            border: 1px solid rgba(255, 51, 102, 0.3);
            color: var(--accent-red);
            display: block;
        }

        /* 已录入人脸 */
        .face-tags {
            display: flex;
            flex-wrap: wrap;
            gap: 10px;
            margin-top: 8px;
        }

        .face-tag {
            display: inline-flex;
            align-items: center;
            gap: 8px;
            background: var(--bg-secondary);
            border: 1px solid var(--border-primary);
            border-radius: 20px;
            padding: 8px 16px;
            font-family: var(--font-mono);
            font-size: 0.8rem;
            color: var(--text-primary);
            transition: all 0.2s ease;
        }

        .face-tag:hover {
            border-color: var(--accent-cyan);
            background: var(--accent-cyan-dim);
        }

        .face-tag .tag-icon {
            width: 20px;
            height: 20px;
            background: var(--accent-cyan-dim);
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 10px;
        }

        .empty-state {
            text-align: center;
            padding: 32px;
            color: var(--text-muted);
            font-family: var(--font-mono);
            font-size: 0.85rem;
        }

        /* 扫描线效果 */
        .scanline {
            position: fixed;
            top: 0;
            left: 0;
            width: 100%;
            height: 100%;
            background: repeating-linear-gradient(
                0deg,
                transparent,
                transparent 2px,
                rgba(0, 212, 255, 0.01) 2px,
                rgba(0, 212, 255, 0.01) 4px
            );
            pointer-events: none;
            z-index: 999;
            opacity: 0.3;
        }

        /* 动画 */
        @keyframes fadeIn {
            from { opacity: 0; transform: translateY(10px); }
            to { opacity: 1; transform: translateY(0); }
        }
    </style>
</head>
<body>
    <!-- 扫描线效果 -->
    <div class="scanline"></div>

    <!-- 顶部导航 -->
    <div class="header">
        <div class="header-left">
            <div class="logo-icon">
                <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="white" stroke-width="2.5">
                    <path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path>
                    <circle cx="12" cy="12" r="3"></circle>
                </svg>
            </div>
            <div>
                <h1>事件驱动边缘视觉识别系统</h1>
                <div class="header-subtitle">Event-Driven Edge Vision Recognition</div>
            </div>
        </div>
        <div class="header-right">
            <nav class="nav-links">
                <a href="/camera">识别看板</a>
                <a href="/enroll" class="active">人脸录入</a>
            </nav>
            <div class="status-group">
                <div class="status-indicator">
                    <span class="status-dot online"></span>
                    <span>ESP32-CAM</span>
                </div>
                <div class="status-indicator">
                    <span class="status-dot online"></span>
                    <span>Server</span>
                </div>
            </div>
        </div>
    </div>

    <!-- 主容器 -->
    <div class="container">
        <!-- 录入卡片 -->
        <div class="card">
            <div class="card-header">
                <span class="card-title">
                    <span class="icon">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                            <circle cx="12" cy="7" r="4"></circle>
                        </svg>
                    </span>
                    录入新人脸
                </span>
                <span class="card-badge">NEW FACE</span>
            </div>
            <div class="card-body">
                <form id="enroll-form">
                    <div class="form-group">
                        <label class="form-label" for="name">人员姓名</label>
                        <input type="text" id="name" class="form-input" placeholder="请输入姓名，例如：张三" required>
                    </div>
                    <div class="form-group">
                        <label class="form-label">上传照片</label>
                        <div class="upload-zone" id="upload-zone">
                            <div class="upload-icon">
                                <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>
                                    <polyline points="17 8 12 3 7 8"></polyline>
                                    <line x1="12" y1="3" x2="12" y2="15"></line>
                                </svg>
                            </div>
                            <div class="upload-title">点击或拖拽上传照片</div>
                            <div class="upload-hint">支持 JPG、PNG 格式，建议 3-5 张不同角度的照片</div>
                            <input type="file" id="file-input" class="file-input" multiple accept="image/*">
                        </div>
                        <div class="preview-grid" id="preview-grid"></div>
                    </div>
                    <button type="submit" class="btn btn-primary" id="submit-btn" disabled>
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M12 5v14M5 12h14"></path>
                        </svg>
                        开始录入
                    </button>
                </form>
                <div class="message" id="message"></div>
            </div>
        </div>

        <!-- 已录入人脸 -->
        <div class="card">
            <div class="card-header">
                <span class="card-title">
                    <span class="icon">
                        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>
                            <circle cx="9" cy="7" r="4"></circle>
                            <path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>
                            <path d="M16 3.13a4 4 0 0 1 0 7.75"></path>
                        </svg>
                    </span>
                    已录入的人脸
                </span>
                <span class="card-badge">DATABASE</span>
            </div>
            <div class="card-body">
                <div class="face-tags" id="face-tags">
                    <span style="color: var(--text-muted);">加载中...</span>
                </div>
            </div>
        </div>
    </div>

    <script>
        const form = document.getElementById('enroll-form');
        const nameInput = document.getElementById('name');
        const uploadZone = document.getElementById('upload-zone');
        const fileInput = document.getElementById('file-input');
        const previewGrid = document.getElementById('preview-grid');
        const submitBtn = document.getElementById('submit-btn');
        const message = document.getElementById('message');
        const faceTags = document.getElementById('face-tags');

        let selectedFiles = [];

        // 点击上传区域
        uploadZone.addEventListener('click', () => {
            fileInput.click();
        });

        // 拖拽上传
        uploadZone.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadZone.classList.add('dragover');
        });

        uploadZone.addEventListener('dragleave', () => {
            uploadZone.classList.remove('dragover');
        });

        uploadZone.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadZone.classList.remove('dragover');
            handleFiles(e.dataTransfer.files);
        });

        // 文件选择
        fileInput.addEventListener('change', (e) => {
            handleFiles(e.target.files);
        });

        function handleFiles(files) {
            for (const file of files) {
                if (file.type.startsWith('image/')) {
                    selectedFiles.push(file);
                }
            }
            updatePreview();
            updateSubmitBtn();
        }

        function updatePreview() {
            previewGrid.innerHTML = '';
            selectedFiles.forEach((file, index) => {
                const reader = new FileReader();
                reader.onload = (e) => {
                    const div = document.createElement('div');
                    div.className = 'preview-item';
                    div.innerHTML = `
                        <img src="${e.target.result}" alt="预览">
                        <button class="preview-remove" onclick="removeFile(${index})">×</button>
                    `;
                    previewGrid.appendChild(div);
                };
                reader.readAsDataURL(file);
            });
        }

        function removeFile(index) {
            selectedFiles.splice(index, 1);
            updatePreview();
            updateSubmitBtn();
        }

        function updateSubmitBtn() {
            submitBtn.disabled = !nameInput.value.trim() || selectedFiles.length === 0;
        }

        nameInput.addEventListener('input', updateSubmitBtn);

        // 提交表单
        form.addEventListener('submit', async (e) => {
            e.preventDefault();

            const name = nameInput.value.trim();
            if (!name || selectedFiles.length === 0) {
                return;
            }

            submitBtn.disabled = true;
            submitBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" style="animation: spin 1s linear infinite;">
                    <path d="M21 12a9 9 0 1 1-6.219-8.56"></path>
                </svg>
                录入中...
            `;

            const formData = new FormData();
            formData.append('name', name);
            selectedFiles.forEach(file => {
                formData.append('images', file);
            });

            try {
                const res = await fetch('/api/enroll', {
                    method: 'POST',
                    body: formData,
                });
                const data = await res.json();

                if (data.status === 'ok') {
                    message.className = 'message success';
                    message.textContent = data.message;
                    nameInput.value = '';
                    selectedFiles = [];
                    updatePreview();
                    loadExistingFaces();
                } else {
                    message.className = 'message error';
                    message.textContent = data.message;
                }
            } catch (err) {
                message.className = 'message error';
                message.textContent = '上传失败: ' + err.message;
            }

            submitBtn.disabled = false;
            submitBtn.innerHTML = `
                <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                    <path d="M12 5v14M5 12h14"></path>
                </svg>
                开始录入
            `;
            updateSubmitBtn();
        });

        // 加载已录入的人脸
        async function loadExistingFaces() {
            try {
                const res = await fetch('/api/faces');
                const data = await res.json();
                if (data.faces && data.faces.length > 0) {
                    faceTags.innerHTML = data.faces.map(name =>
                        `<span class="face-tag">
                            <span class="tag-icon">
                                <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2">
                                    <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
                                    <circle cx="12" cy="7" r="4"></circle>
                                </svg>
                            </span>
                            ${name}
                        </span>`
                    ).join('');
                } else {
                    faceTags.innerHTML = '<span style="color: var(--text-muted); font-family: var(--font-mono); font-size: 0.85rem;">暂无人脸数据</span>';
                }
            } catch (err) {
                faceTags.innerHTML = '<span style="color: var(--accent-red); font-family: var(--font-mono); font-size: 0.85rem;">加载失败</span>';
            }
        }

        loadExistingFaces();

        // 添加旋转动画样式
        const style = document.createElement('style');
        style.textContent = `
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
        `;
        document.head.appendChild(style);
    </script>
</body>
</html>
"""


@router.get("/api/faces")
async def list_faces():
    """返回已录入的人脸列表。"""
    db = get_face_db()
    _, db_names = db.load_all_embeddings()
    unique_names = list(set(db_names))
    return {"faces": unique_names}
