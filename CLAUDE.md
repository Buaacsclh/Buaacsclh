# 工作规范 - 基于端边协同架构的智能眼镜人脸识别系统

## 称呼
每次对话都以 "linhao" 称呼用户。

## 核心原则
- 禁止 mock，禁止简化实现。所有代码必须真实可运行。
- 任何不清楚的点都要先问用户，讨论完成后才能设计和实现。
- 严格调用 karpathy-guidelines skill 的方法进行代码编写。

## 代码规范
- Python 函数必须有类型标注
- 核心函数必须有 docstring
- 配置项集中在 config.py 和 config.h
- API 返回结构统一为 JSON：`{"status": "ok|error", "data": {...}}`
- 模块化设计，每个文件职责单一
- 不要把所有代码写在一个文件里

## 工作日志
- 每次工作结束前必须写入工作日志（work_log.md），记录本次完成了什么、下次要做什么
- 防止跨对话遗忘进度

## Git 规范
- 每个功能模块完成后提交一次
- 提交信息格式：`feat: xxx` / `fix: xxx` / `docs: xxx`
- 用户确认后才上传到 Git

## 测试要求
- 必须包含基础测试或 benchmark 脚本
- API 端点测试
- 人脸识别准确率测试
- 端到端延迟 benchmark

## 文档要求
- 必须包含 README.md
- 必须包含 requirements.txt
- 项目设计文档在 project.md
- 代码要适合毕业设计演示和论文描述

## 项目文件
- `project.md` — 项目设计文档（架构、技术选型、流程）
- `README.md` — 项目说明（面向使用者）
