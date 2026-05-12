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

# 最新识别结果（线程安全）
_latest_result_lock = threading.Lock()
_latest_result = {"status": "waiting", "name": "", "confidence": 0.0, "timestamp": 0}


class FaceResult(BaseModel):
    """单个人脸识别结果。"""
    name: str
    confidence: float
    bbox: list[int]  # [x1, y1, x2, y2]


class RecognizeResponse(BaseModel):
    """识别结果响应。"""
    status: str
    faces: list[FaceResult] = []


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

    # 保存最新图片
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

    # 更新最新识别结果
    with _latest_result_lock:
        _latest_result.update({
            "status": result.status,
            "faces": [f.dict() for f in result.faces],
            "timestamp": time.time(),
        })

    return result


@router.get("/api/latest_image")
async def latest_image():
    """返回 ESP32-CAM 最新拍摄的图片。"""
    if not os.path.exists(_latest_img_path):
        raise HTTPException(status_code=404, detail="暂无图片")
    with open(_latest_img_path, "rb") as f:
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


@router.get("/camera", response_class=HTMLResponse)
async def camera_page():
    """ESP32-CAM 实时画面查看页面。"""
    return """<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>智能眼镜人脸识别系统 - 监控界面</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #0d1117;
            color: #e6edf3;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            height: 100vh;
            overflow: hidden;
        }
        .header {
            background: #161b22;
            border-bottom: 1px solid #30363d;
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .header h1 {
            font-size: 1.2rem;
            color: #58a6ff;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .header .status {
            display: flex;
            align-items: center;
            gap: 15px;
            font-size: 0.85rem;
        }
        .status-dot {
            display: inline-block;
            width: 8px;
            height: 8px;
            border-radius: 50%;
            margin-right: 6px;
        }
        .status-dot.online { background: #3fb950; }
        .status-dot.offline { background: #f85149; }
        .nav-links {
            display: flex;
            gap: 20px;
        }
        .nav-links a {
            color: #8b949e;
            text-decoration: none;
            font-size: 0.9rem;
            transition: color 0.2s;
        }
        .nav-links a:hover {
            color: #58a6ff;
        }
        .main {
            display: flex;
            height: calc(100vh - 52px);
        }
        .video-panel {
            flex: 7;
            position: relative;
            background: #000;
            display: flex;
            align-items: center;
            justify-content: center;
            overflow: hidden;
        }
        .video-panel img {
            max-width: 100%;
            max-height: 100%;
            object-fit: contain;
        }
        .video-overlay {
            position: absolute;
            top: 15px;
            left: 15px;
            background: rgba(0, 0, 0, 0.7);
            padding: 8px 12px;
            border-radius: 6px;
            font-size: 0.8rem;
            color: #8b949e;
        }
        .side-panel {
            flex: 3;
            background: #161b22;
            border-left: 1px solid #30363d;
            display: flex;
            flex-direction: column;
            overflow: hidden;
        }
        .panel-section {
            border-bottom: 1px solid #30363d;
            padding: 16px;
        }
        .panel-title {
            font-size: 0.75rem;
            text-transform: uppercase;
            letter-spacing: 1px;
            color: #8b949e;
            margin-bottom: 12px;
        }
        .result-card {
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 8px;
            padding: 12px;
            margin-bottom: 10px;
            transition: all 0.2s;
        }
        .result-card:hover {
            border-color: #58a6ff;
        }
        .result-name {
            font-size: 1.1rem;
            font-weight: 600;
            color: #58a6ff;
            margin-bottom: 4px;
        }
        .result-confidence {
            font-size: 0.85rem;
            color: #3fb950;
        }
        .result-time {
            font-size: 0.75rem;
            color: #8b949e;
            margin-top: 4px;
        }
        .no-face {
            text-align: center;
            padding: 20px;
            color: #8b949e;
        }
        .waiting {
            text-align: center;
            padding: 20px;
            color: #8b949e;
        }
        .stats-grid {
            display: grid;
            grid-template-columns: 1fr 1fr;
            gap: 10px;
        }
        .stat-item {
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 6px;
            padding: 10px;
            text-align: center;
        }
        .stat-value {
            font-size: 1.5rem;
            font-weight: 600;
            color: #58a6ff;
        }
        .stat-label {
            font-size: 0.7rem;
            color: #8b949e;
            margin-top: 4px;
        }
        .face-list {
            flex: 1;
            overflow-y: auto;
            padding: 16px;
        }
        .face-count {
            background: #238636;
            color: #fff;
            padding: 2px 8px;
            border-radius: 10px;
            font-size: 0.75rem;
            font-weight: 600;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>
            <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm0 14.5a6.5 6.5 0 1 1 0-13 6.5 6.5 0 0 1 0 13zm-1-9.5a1 1 0 1 1 2 0v2a1 1 0 1 1-2 0V5zm1 5a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"/>
            </svg>
            智能眼镜人脸识别系统
        </h1>
        <div class="status">
            <div class="nav-links">
                <a href="/camera">监控界面</a>
                <a href="/enroll">人脸录入</a>
            </div>
            <span><span class="status-dot online"></span>服务器在线</span>
            <span id="fps">FPS: --</span>
        </div>
    </div>
    <div class="main">
        <div class="video-panel">
            <img id="stream" src="/api/latest_image" />
            <div class="video-overlay">
                <span id="resolution">分辨率: --</span> |
                <span id="timestamp">时间: --</span>
            </div>
        </div>
        <div class="side-panel">
            <div class="panel-section">
                <div class="panel-title">识别统计</div>
                <div class="stats-grid">
                    <div class="stat-item">
                        <div class="stat-value" id="total-count">0</div>
                        <div class="stat-label">总识别次数</div>
                    </div>
                    <div class="stat-item">
                        <div class="stat-value" id="face-count">0</div>
                        <div class="stat-label">检测到人脸</div>
                    </div>
                </div>
            </div>
            <div class="panel-section">
                <div class="panel-title">
                    识别结果
                    <span class="face-count" id="current-face-count">0</span>
                </div>
            </div>
            <div class="face-list" id="face-list">
                <div class="waiting">等待数据...</div>
            </div>
        </div>
    </div>
    <script>
        const streamImg = document.getElementById('stream');
        const faceList = document.getElementById('face-list');
        const totalCount = document.getElementById('total-count');
        const faceCount = document.getElementById('face-count');
        const currentFaceCount = document.getElementById('current-face-count');
        const fpsDisplay = document.getElementById('fps');
        const resolutionDisplay = document.getElementById('resolution');
        const timestampDisplay = document.getElementById('timestamp');

        let frameCount = 0;
        let lastTime = Date.now();
        let totalRecognitions = 0;
        let faceDetections = 0;

        // 刷新画面
        function refreshStream() {
            streamImg.src = '/api/latest_image?t=' + Date.now();
            frameCount++;

            const now = Date.now();
            if (now - lastTime >= 1000) {
                fpsDisplay.textContent = 'FPS: ' + frameCount;
                frameCount = 0;
                lastTime = now;
            }

            const date = new Date();
            timestampDisplay.textContent = '时间: ' + date.toLocaleTimeString();
        }
        setInterval(refreshStream, 500);

        // 获取图片分辨率
        streamImg.onload = function() {
            resolutionDisplay.textContent = '分辨率: ' + streamImg.naturalWidth + 'x' + streamImg.naturalHeight;
        };

        // 获取识别结果
        async function fetchResult() {
            try {
                const res = await fetch('/api/latest_result');
                const data = await res.json();
                updateDisplay(data);
            } catch (e) {
                console.error('获取结果失败:', e);
            }
        }

        function updateDisplay(data) {
            totalRecognitions++;
            totalCount.textContent = totalRecognitions;

            if (data.status === 'ok' && data.faces && data.faces.length > 0) {
                faceDetections++;
                faceCount.textContent = faceDetections;
                currentFaceCount.textContent = data.faces.length;

                let html = '';
                data.faces.forEach((face, index) => {
                    const confidence = (face.confidence * 100).toFixed(1);
                    const time = new Date(data.timestamp * 1000).toLocaleTimeString();
                    html += `
                        <div class="result-card">
                            <div class="result-name">${face.name}</div>
                            <div class="result-confidence">置信度: ${confidence}%</div>
                            <div class="result-time">${time}</div>
                        </div>
                    `;
                });
                faceList.innerHTML = html;
            } else {
                currentFaceCount.textContent = '0';
                faceList.innerHTML = '<div class="no-face">未检测到人脸</div>';
            }
        }

        setInterval(fetchResult, 500);
        fetchResult();
    </script>
</body>
</html>"""


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
<html>
<head>
    <meta charset="utf-8">
    <title>智能眼镜人脸识别系统 - 人脸录入</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body {
            background: #0d1117;
            color: #e6edf3;
            font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Helvetica, Arial, sans-serif;
            min-height: 100vh;
        }
        .header {
            background: #161b22;
            border-bottom: 1px solid #30363d;
            padding: 12px 24px;
            display: flex;
            align-items: center;
            justify-content: space-between;
        }
        .header h1 {
            font-size: 1.2rem;
            color: #58a6ff;
            display: flex;
            align-items: center;
            gap: 10px;
        }
        .nav-links {
            display: flex;
            gap: 20px;
        }
        .nav-links a {
            color: #8b949e;
            text-decoration: none;
            font-size: 0.9rem;
            transition: color 0.2s;
        }
        .nav-links a:hover {
            color: #58a6ff;
        }
        .container {
            max-width: 800px;
            margin: 40px auto;
            padding: 0 20px;
        }
        .card {
            background: #161b22;
            border: 1px solid #30363d;
            border-radius: 12px;
            padding: 30px;
            margin-bottom: 20px;
        }
        .card-title {
            font-size: 1.3rem;
            color: #58a6ff;
            margin-bottom: 20px;
        }
        .form-group {
            margin-bottom: 20px;
        }
        .form-group label {
            display: block;
            font-size: 0.9rem;
            color: #8b949e;
            margin-bottom: 8px;
        }
        .form-group input[type="text"] {
            width: 100%;
            padding: 12px 16px;
            background: #0d1117;
            border: 1px solid #30363d;
            border-radius: 8px;
            color: #e6edf3;
            font-size: 1rem;
            outline: none;
            transition: border-color 0.2s;
        }
        .form-group input[type="text"]:focus {
            border-color: #58a6ff;
        }
        .upload-area {
            border: 2px dashed #30363d;
            border-radius: 12px;
            padding: 40px;
            text-align: center;
            cursor: pointer;
            transition: all 0.2s;
        }
        .upload-area:hover {
            border-color: #58a6ff;
            background: rgba(88, 166, 255, 0.05);
        }
        .upload-area.dragover {
            border-color: #58a6ff;
            background: rgba(88, 166, 255, 0.1);
        }
        .upload-icon {
            font-size: 3rem;
            margin-bottom: 15px;
        }
        .upload-text {
            color: #8b949e;
            margin-bottom: 10px;
        }
        .upload-hint {
            font-size: 0.8rem;
            color: #6e7681;
        }
        .file-input {
            display: none;
        }
        .preview-grid {
            display: grid;
            grid-template-columns: repeat(auto-fill, minmax(100px, 1fr));
            gap: 10px;
            margin-top: 20px;
        }
        .preview-item {
            position: relative;
            aspect-ratio: 1;
            border-radius: 8px;
            overflow: hidden;
            border: 1px solid #30363d;
        }
        .preview-item img {
            width: 100%;
            height: 100%;
            object-fit: cover;
        }
        .preview-remove {
            position: absolute;
            top: 5px;
            right: 5px;
            background: rgba(248, 81, 73, 0.8);
            color: white;
            border: none;
            border-radius: 50%;
            width: 24px;
            height: 24px;
            cursor: pointer;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 14px;
        }
        .btn {
            padding: 12px 24px;
            border: none;
            border-radius: 8px;
            font-size: 1rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
        }
        .btn-primary {
            background: #238636;
            color: white;
        }
        .btn-primary:hover {
            background: #2ea043;
        }
        .btn-primary:disabled {
            background: #21262d;
            color: #484f58;
            cursor: not-allowed;
        }
        .message {
            padding: 12px 16px;
            border-radius: 8px;
            margin-top: 20px;
            display: none;
        }
        .message.success {
            background: rgba(63, 185, 80, 0.1);
            border: 1px solid #238636;
            color: #3fb950;
            display: block;
        }
        .message.error {
            background: rgba(248, 81, 73, 0.1);
            border: 1px solid #f85149;
            color: #f85149;
            display: block;
        }
        .existing-faces {
            margin-top: 30px;
        }
        .face-tag {
            display: inline-block;
            background: #21262d;
            border: 1px solid #30363d;
            border-radius: 20px;
            padding: 6px 14px;
            margin: 4px;
            font-size: 0.9rem;
            color: #e6edf3;
        }
    </style>
</head>
<body>
    <div class="header">
        <h1>
            <svg width="20" height="20" viewBox="0 0 16 16" fill="currentColor">
                <path d="M8 0a8 8 0 1 0 0 16A8 8 0 0 0 8 0zm0 14.5a6.5 6.5 0 1 1 0-13 6.5 6.5 0 0 1 0 13zm-1-9.5a1 1 0 1 1 2 0v2a1 1 0 1 1-2 0V5zm1 5a1 1 0 1 1 0-2 1 1 0 0 1 0 2z"/>
            </svg>
            智能眼镜人脸识别系统
        </h1>
        <div class="nav-links">
            <a href="/camera">监控界面</a>
            <a href="/enroll">人脸录入</a>
        </div>
    </div>
    <div class="container">
        <div class="card">
            <div class="card-title">录入新人脸</div>
            <form id="enroll-form">
                <div class="form-group">
                    <label for="name">人名</label>
                    <input type="text" id="name" name="name" placeholder="请输入人名，例如：张三" required>
                </div>
                <div class="form-group">
                    <label>上传照片</label>
                    <div class="upload-area" id="upload-area">
                        <div class="upload-icon">📷</div>
                        <div class="upload-text">点击或拖拽上传照片</div>
                        <div class="upload-hint">支持 JPG、PNG 格式，建议 3-5 张不同角度的照片</div>
                        <input type="file" id="file-input" class="file-input" multiple accept="image/*">
                    </div>
                    <div class="preview-grid" id="preview-grid"></div>
                </div>
                <button type="submit" class="btn btn-primary" id="submit-btn" disabled>
                    开始录入
                </button>
            </form>
            <div class="message" id="message"></div>
        </div>
        <div class="card existing-faces">
            <div class="card-title">已录入的人脸</div>
            <div id="face-tags">
                <span style="color: #8b949e;">加载中...</span>
            </div>
        </div>
    </div>
    <script>
        const form = document.getElementById('enroll-form');
        const nameInput = document.getElementById('name');
        const uploadArea = document.getElementById('upload-area');
        const fileInput = document.getElementById('file-input');
        const previewGrid = document.getElementById('preview-grid');
        const submitBtn = document.getElementById('submit-btn');
        const message = document.getElementById('message');
        const faceTags = document.getElementById('face-tags');

        let selectedFiles = [];

        // 点击上传区域
        uploadArea.addEventListener('click', () => {
            fileInput.click();
        });

        // 拖拽上传
        uploadArea.addEventListener('dragover', (e) => {
            e.preventDefault();
            uploadArea.classList.add('dragover');
        });

        uploadArea.addEventListener('dragleave', () => {
            uploadArea.classList.remove('dragover');
        });

        uploadArea.addEventListener('drop', (e) => {
            e.preventDefault();
            uploadArea.classList.remove('dragover');
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
            submitBtn.textContent = '录入中...';

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
            submitBtn.textContent = '开始录入';
            updateSubmitBtn();
        });

        // 加载已录入的人脸
        async function loadExistingFaces() {
            try {
                const res = await fetch('/api/faces');
                const data = await res.json();
                if (data.faces && data.faces.length > 0) {
                    faceTags.innerHTML = data.faces.map(name =>
                        `<span class="face-tag">${name}</span>`
                    ).join('');
                } else {
                    faceTags.innerHTML = '<span style="color: #8b949e;">暂无人脸数据</span>';
                }
            } catch (err) {
                faceTags.innerHTML = '<span style="color: #f85149;">加载失败</span>';
            }
        }

        loadExistingFaces();
    </script>
</body>
</html>"""


@router.get("/api/faces")
async def list_faces():
    """返回已录入的人脸列表。"""
    db = get_face_db()
    _, db_names = db.load_all_embeddings()
    unique_names = list(set(db_names))
    return {"faces": unique_names}
