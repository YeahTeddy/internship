# 检测工作流程指南

## 从训练到部署的完整流程

```
数据准备 → 模型训练 → 评估 → 导出 → 部署检测
```

## 第一步：数据准备

- 数据集格式：YOLO 格式（images/ + labels/ + data.yaml）
- 标签格式：class_id x_center y_center width height（归一化）
- 划分比例：train 80% / val 10% / test 10%

## 第二步：模型训练

- 推荐：yolo11n（轻量快速）
- GPU 训练：device=0，约 30 秒/epoch
- CPU 训练：约 5-10 分钟/epoch
- 监控指标：box_loss、cls_loss、dfl_loss、mAP50

## 第三步：评估导出

- validate：在验证集上跑评估，输出 mAP/Precision/Recall
- export：复制 best.pt 到 models/ 目录，创建 ModelVersion
- 下载：提供 best.pt 文件下载

## 第四步：部署检测

- ModelVersion 注册后，检测页可选用对应模型
- 支持单图/批量/视频/摄像头 4 种检测模式
- ByteTrack 跟踪实现车辆计数和越线检测
