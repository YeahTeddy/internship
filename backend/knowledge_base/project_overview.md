# RSOD 目标检测智能体平台

## 平台简介

RSOD Agent Platform 是一个基于 YOLOv11 的目标检测智能体平台，支持恶劣天气条件下的车辆/目标检测。

## 技术栈

- **前端**: Vue 3 + Element Plus + ECharts + Pinia
- **后端**: FastAPI + SQLAlchemy + LangChain (Agent)
- **模型**: YOLOv11 (Ultralytics 8.3)
- **数据库**: PostgreSQL + pgvector (向量存储)
- **存储**: MinIO 对象存储
- **AI**: MiMo mimo-v2.5 (对话) + Doubao Embedding (向量化)

## 检测模式

- 单图检测、批量检测、ZIP 检测
- 视频检测（ByteTrack 跟踪）
- 摄像头实时检测（WebSocket）
- 对话驱动检测（LLM Agent 自动调用工具）

## 训练配置

- 数据集：DAWN（恶劣天气车辆检测，1027 图，1 类 car）
- 数据集：ACDC（恶劣天气，3206 图，8 类）
- 推荐模型：yolo11n（轻量快速）
- 推荐 epoch：50-100
- 推荐 batch：16（8GB 显存）
