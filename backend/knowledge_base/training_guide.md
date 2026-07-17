# 模型训练指南

## 训练流程

1. 准备数据集：图片 + YOLO 格式标签 + data.yaml
2. 选择模型：yolo11n（轻量）/ yolo11s（平衡）/ yolo11m（精度高）
3. 训练：使用 GPU 加速，batch=16，imgsz=640
4. 评估：查看 mAP50、Precision、Recall
5. 导出：注册为 ModelVersion 供检测使用

## 超参数建议

| 参数 | 推荐值 | 说明 |
|------|--------|------|
| epochs | 50-100 | 观察 loss 收敛后停止 |
| batch_size | 16 | 8GB 显存安全值 |
| img_size | 640 | 标准尺寸，小目标可选 960 |
| lr0 | 0.01 | SGD 默认学习率 |
| optimizer | SGD | 比 Adam 更稳定 |

## 常见问题

- **loss 不下降**: 检查学习率是否合适，数据标签是否正确
- **过拟合**: 增加 epochs、加数据增强、减小模型规模
- **类别不平衡**: 对少数类进行过采样，或使用 focal loss
- **显存不足**: 减小 batch_size 或 img_size

## ByteTrack 跟踪

视频检测使用 ByteTrack 实现多目标跟踪：
- 每辆车分配唯一 track_id
- 同一辆车跨帧 ID 不变
- unique_vehicles 字段给出去重后的真实车辆数
