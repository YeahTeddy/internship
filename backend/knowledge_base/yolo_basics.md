# YOLO 目标检测基础知识

## 什么是 YOLO

YOLO（You Only Look Once）是一种端到端的实时目标检测算法。与传统的两阶段检测方法不同，YOLO 将目标检测视为回归问题，在一次前向传播中同时预测边界框和类别概率。

## YOLOv11 的改进

YOLOv11 是 Ultralytics 发布的最新一代 YOLO 模型：
1. 改进的 C3k2 模块，增强多尺度特征融合
2. C2PSA 空间注意力机制，提升小目标检测能力
3. 支持 n/s/m/l/x 五种规模
4. 训练策略优化

## YOLO11n 模型

- 参数量：约 2.6M
- 推理速度：CPU 约 50ms/张，GPU 约 5ms/张
- 适用场景：边缘设备部署、实时检测

## 什么是置信度（Confidence）

- > 0.9：非常确信
- 0.5~0.9：较为确信
- < 0.5：不太确信，可能是误检

## 什么是 IoU（交并比）

IoU = 交集面积 / 并集面积。用于 NMS（非极大值抑制）去除重复检测框。

## 什么是 NMS（非极大值抑制）

去除对同一目标的重复检测：按置信度排序 → 保留最高 → 删除 IoU 大于阈值的框 → 重复。

## 什么是 mAP（mean Average Precision）

- Precision = TP / (TP + FP)
- Recall = TP / (TP + FN)
- mAP50：IoU=0.5 时的 mAP
- mAP50-95：IoU 从 0.5 到 0.95 的平均 mAP
