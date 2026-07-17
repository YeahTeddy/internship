# 数据集指南

## DAWN 数据集（恶劣天气车辆检测）

- 来源：DAWN (Dark Adverse Weather Natural)
- 规模：1027 张，4 类天气（雾/雨/雪/夜间）
- 标注：VOC XML 转 YOLO 格式，单类 car
- mAP50：87.6%（已训练验证）

## ACDC 数据集（恶劣天气多类检测）

- 来源：ACDC (Adverse Conditions Dataset with Correspondences)
- 规模：3206 张（有检测标注），8 类
- 天气：雾、雨、雪、夜间
- 类别：car, truck, bus, person, bicycle, motorcycle, train, rider
- 注意：mAP50 仅 33%，原因：目标太小（48.8% < 32px）、类别不平衡

## 数据集对比

| | DAWN | ACDC |
|---|------|------|
| 图片数 | 1027 | 3206 |
| 类别数 | 1 (car) | 8 |
| 标注质量 | 好（人工标注） | 一般（分割转检测） |
| 训练效果 | mAP 87.6% | mAP 33% |
| 推荐用途 | 车辆检测主力 | 多类检测探索 |

## 数据增强建议

- Mosaic: 1.0（标准）
- MixUp: 0.15（增加多样性）
- HSV 调整：适应不同光照
- 随机翻转/旋转：适应不同角度
