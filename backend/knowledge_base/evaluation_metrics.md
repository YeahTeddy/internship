# 模型评估指标详解

## 混淆矩阵

|            | 预测为正例 | 预测为负例 |
|------------|-----------|-----------|
| 实际为正例  | TP        | FN        |
| 实际为负例  | FP        | TN        |

## Precision（精确率）

Precision = TP / (TP + FP)。检测出的目标中有多少是正确的。

## Recall（召回率）

Recall = TP / (TP + FN)。所有真实目标中有多少被检测到。

## F1-Score

F1 = 2 × (Precision × Recall) / (Precision + Recall)

## 训练损失函数

1. Box Loss：预测框与真实框的位置偏差
2. Class Loss：目标类别的预测误差
3. DFL Loss：Distribution Focal Loss
