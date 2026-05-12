# 工作日志

## 2026-05-12 - 阶段一 + 阶段二

### 完成内容

**阶段一：基础框架搭建**
- [x] Git 仓库初始化 + .gitignore
- [x] 项目目录结构（esp32/, server/, docs/, face_db/, models/）
- [x] server/config.py — pydantic BaseSettings 配置管理
- [x] server/main.py + api/routes.py — FastAPI 框架 + /health + /api/recognize
- [x] server/requirements.txt
- [x] 已提交：`c16d579`

**阶段二：PC 端核心功能**
- [x] server/detection/yolo_detector.py — YOLO 人脸检测封装（yolov8n-face.pt）
- [x] server/recognition/arcface_recognizer.py — ArcFace 识别封装（buffalo_l 模型）
- [x] server/database/face_db.py — SQLite + numpy 人脸数据库 CRUD
- [x] server/api/routes.py — 完整识别流程接入（检测→提取→比对→返回）
- [x] server/scripts/enroll_face.py — 命令行批量录入人脸脚本
- [x] models/yolov8n-face.pt — YOLO 人脸检测模型（linhao 手动下载）
- [x] 全部模块测试通过

### 测试结果
- YOLO 检测器：加载成功，黑图返回 0 检测
- ArcFace 识别器：加载成功，自动下载 buffalo_l 模型
- 人脸数据库：增删查全部正常
- /api/recognize：黑图返回 no_face，符合预期
- /health：返回 200

### Git 状态
- 远程仓库：https://github.com/Buaacsclh/Buaacsclh.git
- 最新提交：`4bf029e` feat: PC 端核心功能完成
- 已推送到 origin/master

### 下次继续
- 阶段三：ESP32 端核心功能
  - PlatformIO 项目初始化
  - 摄像头驱动（OV2640 + JPEG 压缩）
  - 卸载决策算法（JPEG 大小差分）
  - WiFi + HTTP 通信
  - OLED 显示（SSD1306）
  - 主循环整合
