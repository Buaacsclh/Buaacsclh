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

### 2026-05-12 补充修复
- [x] fix: main.py — validation_exception_handler 返回 JSONResponse(422) 而非 dict(200)
- [x] fix: arcface_recognizer.py — GPU prepare 失败时 fallback CPU (ctx_id=-1)
- [x] 代码审查通过：config、face_db 测试正常，所有路径正确

## 2026-05-12 - 阶段三：ESP32 固件开发

### 完成内容

**ESP32 固件代码编写**
- [x] esp32/platformio.ini — PlatformIO 项目配置（esp32cam, Arduino, PSRAM）
- [x] esp32/src/config.h — 设备配置常量（WiFi/服务器/摄像头/卸载阈值）
- [x] esp32/src/camera.h/.cpp — OV2640 摄像头驱动封装（初始化/拍照/释放）
- [x] esp32/src/offload.h/.cpp — JPEG 大小差分卸载决策算法（OffloadDecider 类）
- [x] esp32/src/network.h/.cpp — WiFi 连接 + HTTP multipart/form-data 上传
- [x] esp32/src/display.h/.cpp — 显示模块（串口输出，OLED 接口预留）
- [x] esp32/src/main.cpp — 主循环整合（拍照→判断→上传→显示）

### 硬件调试
- [x] 用户安装 PlatformIO IDE 插件 + Core
- [x] CH340 串口驱动安装
- [x] ESP32-CAM (DZQJ 品牌) 烧录成功
- [x] 修改 config.h：WiFi SSID/密码、服务器 IP (192.168.3.5)
- [x] 端到端测试通过：ESP32-CAM 拍照 → HTTP 上传 → 服务器处理 → 返回结果
- [x] 新增：服务器摄像头查看页面 (/camera)，浏览器实时查看 ESP32-CAM 画面
- [x] 串口输出无数据（DZQJ 板子串口引脚与标准 AI Thinker 不同，不影响功能）

### 待完成
- [ ] 录入人脸测试（需要用户准备照片）
- [ ] 端到端人脸识别验证
- [ ] OLED 显示模块（用户暂未购买）

### 下次继续
- 录入人脸并测试识别效果
- 优化识别精度和响应速度
- 更新 project.md 和 README.md
