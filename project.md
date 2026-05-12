# 项目设计文档 - 基于端边协同架构的智能眼镜人脸识别系统

## 项目概述

毕业设计项目。实现一套基于端边协同架构的智能眼镜人脸识别系统：
- **端侧**：ESP32-CAM 负责图像采集、JPEG 压缩、计算卸载决策、HTTP 上传、OLED 显示
- **边侧**：PC 服务器负责 YOLO 人脸检测、ArcFace 特征提取与身份识别

## 技术栈

### ESP32-CAM 端侧
- 硬件：ESP32-CAM AI Thinker + OV2640 + SSD1306 OLED
- 开发框架：PlatformIO + Arduino
- 语言：C/C++
- 通信：WiFi + HTTP Client

### PC 边缘服务器
- 框架：FastAPI (Python 3.10+)
- 人脸检测：YOLOv8 (ultralytics)
- 人脸识别：InsightFace (ArcFace)
- 数据库：SQLite + numpy 特征文件
- GPU：NVIDIA CUDA 加速

## 架构设计

```
ESP32-CAM                          PC Server
┌─────────────────┐   HTTP POST    ┌──────────────────────┐
│ OV2640 采集      │──────────────→│ /api/recognize       │
│ JPEG 压缩        │   JPEG 图片    │                      │
│ 卸载决策算法      │               │ YOLO 人脸检测         │
│ (JPEG大小差分)    │               │ ArcFace 特征提取      │
│                  │←──────────────│ SQLite 特征比对       │
│ JSON 解析        │   JSON 结果    │                      │
│ OLED 显示        │               └──────────────────────┘
└─────────────────┘
```

### 计算卸载决策算法（核心创新点）

采用 JPEG 文件大小差分法：
1. 连续拍摄两帧，分别压缩为 JPEG
2. 计算变化率：Δ = |size_curr - size_prev| / size_prev
3. 若 Δ > 阈值（默认 0.15），判定场景发生变化，上传当前帧
4. 否则跳过，节省带宽和能耗

优点：无需解码像素数据，计算成本极低，适合 ESP32 内存限制。

### 通信协议

ESP32 → PC：
- HTTP POST multipart/form-data
- 字段：image (JPEG 文件)
- 超时：5000ms

PC → ESP32：
- JSON 格式：`{"status": "ok|no_face|error", "name": "xxx", "confidence": 0.95}`

## 项目结构

```
clhbiyesheji/
├── CLAUDE.md                  # 工作规范
├── project.md                 # 项目设计文档（本文件）
├── README.md                  # 项目说明
├── .gitignore
│
├── esp32/                     # ESP32-CAM 固件
│   ├── platformio.ini         # PlatformIO 配置
│   ├── src/
│   │   ├── main.cpp           # 主程序入口
│   │   ├── camera.cpp/.h      # 摄像头驱动封装
│   │   ├── display.cpp/.h     # OLED 显示封装
│   │   ├── network.cpp/.h     # WiFi + HTTP 通信
│   │   ├── offload.cpp/.h     # 卸载决策算法
│   │   └── config.h           # 端侧配置常量
│   └── README.md
│
├── server/                    # PC 边缘服务器
│   ├── requirements.txt
│   ├── config.py              # 集中配置管理
│   ├── main.py                # FastAPI 入口
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py          # API 路由
│   ├── detection/
│   │   ├── __init__.py
│   │   └── yolo_detector.py   # YOLO 人脸检测
│   ├── recognition/
│   │   ├── __init__.py
│   │   └── arcface_recognizer.py  # ArcFace 识别
│   ├── database/
│   │   ├── __init__.py
│   │   └── face_db.py         # 人脸数据库管理
│   ├── scripts/
│   │   ├── enroll_face.py     # 人脸录入脚本
│   │   └── benchmark.py       # 性能测试脚本
│   └── tests/
│       ├── test_api.py
│       └── test_recognition.py
│
└── docs/                      # 文档
    └── architecture.md
```

## 开发流程（按顺序）

### 阶段一：基础框架搭建
1. 初始化 Git 仓库和 .gitignore
2. 创建项目目录结构
3. 编写 server/config.py 配置管理
4. 搭建 FastAPI 基础框架 + /api/recognize 接口
5. ESP32 PlatformIO 项目初始化 + WiFi 连接

### 阶段二：PC 端核心功能
6. 集成 YOLOv8 人脸检测
7. 集成 InsightFace/ArcFace 人脸识别
8. 实现人脸数据库（SQLite + 特征文件）
9. 完成 /api/recognize 接口（接收图片 → 检测 → 识别 → 返回结果）
10. 编写人脸录入脚本 enroll_face.py

### 阶段三：ESP32 端核心功能
11. 摄像头采集 + JPEG 压缩
12. 实现卸载决策算法（JPEG 大小差分）
13. HTTP 上传图片 + 解析 JSON 响应
14. OLED 显示识别结果

### 阶段四：联调与优化
15. 端到端联调
16. 性能测试与延迟优化
17. 错误处理与稳定性加固
18. 编写 benchmark 脚本
19. 编写 README

## 已知难点与应对

| 难点 | 风险 | 应对策略 |
|------|------|----------|
| ESP32 内存紧张 | 高 | 使用 PSRAM，单帧处理，及时释放 buffer |
| WiFi 不稳定 | 中 | 重连机制，超时处理，LED 状态指示 |
| 端到端延迟 | 中 | GPU 加速，异步处理，JPEG 质量可调 |
| 模型首次加载慢 | 低 | 预下载模型，启动时预热 |
| 人脸库管理 | 低 | 独立录入脚本，支持增删改查 |

## 关键配置项

### server/config.py
- SERVER_HOST / SERVER_PORT
- YOLO_MODEL_PATH / YOLO_CONFIDENCE_THRESHOLD
- ARCFACE_MODEL_NAME
- FACE_DB_PATH
- FACE_MATCH_THRESHOLD (默认 0.4 余弦相似度)

### esp32/src/config.h
- WIFI_SSID / WIFI_PASSWORD
- SERVER_URL / SERVER_PORT
- CAMERA_RESOLUTION / JPEG_QUALITY
- OFFLOAD_THRESHOLD (默认 0.15)
- OLED_I2C_ADDRESS

## 关键依赖版本

### Python (requirements.txt)
- fastapi>=0.100.0
- uvicorn>=0.23.0
- ultralytics>=8.0.0
- insightface>=0.7.0
- opencv-python>=4.8.0
- numpy>=1.24.0
- onnxruntime-gpu>=1.15.0 (CUDA) 或 onnxruntime (CPU)
- pydantic>=2.0.0

### ESP32 (platformio.ini)
- WiFiClientSecure (内置)
- HTTPClient (内置)
- bblanchon/ArduinoJson@^6
- adafruit/Adafruit SSD1306@^2
- adafruit/Adafruit GFX Library@^1
