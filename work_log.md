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
- 最新提交：`c08e638` feat: ESP32 固件开发 + 摄像头查看页面
- 已提交待推送

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

## 2026-05-12 - 功能完善

### 完成内容

**人脸录入与识别功能**
- [x] 人脸录入：用户准备 7 张照片，运行 enroll_face.py 成功录入 linhao
- [x] 人脸识别测试：API 返回 `{"status":"ok","name":"linhao","confidence":0.87}`
- [x] 服务器启动测试：端到端识别流程正常

**多人脸识别支持**
- [x] 修改 arcface_recognizer.py — 添加 extract_all_embeddings 方法
- [x] 修改 routes.py — /api/recognize 接口支持返回多个人脸结果
- [x] 新的返回格式：`{"status":"ok","faces":[{"name":"linhao","confidence":0.87,"bbox":[...]}]}`

**监控界面重新设计**
- [x] 重新设计 /camera 页面布局（左右分栏详细版）
- [x] 左边：大画面显示 ESP32-CAM 实时视频
- [x] 右边：识别统计 + 识别结果列表（支持多人脸）
- [x] 显示 FPS、分辨率、时间等信息
- [x] 深色主题，类似监控界面

**网页端人脸录入功能**
- [x] 新增 /enroll 页面 — 人脸录入界面
- [x] 新增 POST /api/enroll 接口 — 批量上传照片录入人脸
- [x] 新增 GET /api/faces 接口 — 获取已录入的人脸列表
- [x] 支持拖拽上传、多张照片、实时预览
- [x] 两个页面之间添加导航链接

### 测试结果
- 多人脸识别 API：正常返回多个人脸结果
- 监控界面：实时更新，显示识别统计
- 人脸录入页面：上传照片、输入名字、提交成功
- 已录入人脸列表：正确显示 linhao

### 待完成
- [ ] GPU 加速（用户正在下载 CUDA Toolkit）
- [ ] 推送代码到 GitHub
- [ ] 更新 project.md 和 README.md

## 2026-05-13 - 事件驱动架构升级 + UI 重构

### 背景

根据 linhao 与 GPT 的讨论，项目定位从"实时视频监控系统"调整为"事件驱动边缘视觉卸载系统"。网页端设计需要匹配这一定位。

### 完成内容

**服务器端功能扩展**
- [x] 识别完成后自动画人脸框（绿色：识别成功，黄色：置信度较低）
- [x] 保存带框图片为 latest_result.jpg
- [x] 新增 /api/latest_result_image 接口返回带框图片
- [x] 新增 /api/stats 接口返回统计数据
- [x] 新增 /api/events 接口返回事件记录
- [x] 扩展 /api/recognize 返回处理耗时
- [x] 全局统计计数器（上传帧数、事件数）
- [x] 事件记录（最近 50 条）

**网页端 UI 重构 - 战术指挥中心风格**
- [x] 调用 frontend-design skill 设计新界面
- [x] /camera 页面重构为事件驱动识别看板
  - 顶部：系统标题 + 状态指示（ESP32-CAM/Server 在线）
  - 统计卡片：上传帧数、识别事件、处理耗时、最近置信度
  - 左侧：最近识别关键帧（四角标记、状态提示）
  - 右侧：本次识别结果（结构化展示）
  - 底部：事件记录表格
  - 状态文案："当前场景稳定，暂无新关键帧上传"
- [x] /enroll 页面重构为统一风格
  - 保持原有功能不变
  - 改成战术指挥中心风格（配色、字体、卡片样式）
- [x] 两个页面风格统一

**设计特点**
- 深色主题：深海军蓝/碳灰基底 + 青色主色调
- 字体：JetBrains Mono（数据/标签）+ Inter（正文）
- 特效：背景网格、扫描线、脉冲动画、发光边框
- 交互：卡片悬停效果、表格行高亮、页面加载动画

### 测试结果
- 服务器启动正常
- /camera 页面：新设计已应用，功能正常
- /enroll 页面：新设计已应用，功能正常
- 所有 API 接口正常工作

### 论文表述调整
- 项目定位：事件驱动边缘视觉卸载系统
- 网页端描述：事件驱动识别结果的可视化界面
- 不再说"实时视频监控"，改为"关键帧采样 + 事件触发"

### 待完成
- [ ] ESP32 端统计上报（可选）
- [ ] GPU 加速（用户正在下载 CUDA Toolkit）
- [ ] 推送代码到 GitHub
- [ ] 更新 project.md 和 README.md
