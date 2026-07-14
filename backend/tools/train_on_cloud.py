"""
云端独立训练脚本

用途：在 AutoDL 等 GPU 云平台上独立运行 YOLOv11 训练
不依赖 FastAPI 后端，直接执行即可

使用方式：
    # 基本用法
    python tools/train_on_cloud.py

    # 自定义参数
    python tools/train_on_cloud.py --model yolov11s --epochs 100 --batch 16

    # 指定数据集路径
    python tools/train_on_cloud.py --data /root/autodl-tmp/datasets/rsod/yolo_dataset/data.yaml
"""

import argparse
import os
import sys
from datetime import datetime

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_DATA_YAML = os.path.join(
    PROJECT_ROOT, "datasets", "rsod", "yolo_dataset", "data.yaml"
)
DEFAULT_OUTPUT_DIR = os.path.join(PROJECT_ROOT, "runs", "cloud_train")


def main():
    parser = argparse.ArgumentParser(description="YOLOv11 云端独立训练脚本")
    parser.add_argument("--model", "-m", type=str, default="yolov11n",
                        choices=["yolov11n", "yolov11s", "yolov11m", "yolov11l", "yolov11x"])
    parser.add_argument("--epochs", "-e", type=int, default=100)
    parser.add_argument("--batch", "-b", type=int, default=16)
    parser.add_argument("--imgsz", type=int, default=640)
    parser.add_argument("--device", type=str, default="0")
    parser.add_argument("--optimizer", type=str, default="SGD")
    parser.add_argument("--lr0", type=float, default=0.01)
    parser.add_argument("--data", "-d", type=str, default=DEFAULT_DATA_YAML)
    parser.add_argument("--output", "-o", type=str, default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--name", type=str, default=None)

    args = parser.parse_args()

    if not os.path.exists(args.data):
        print(f"[错误] data.yaml 不存在：{args.data}")
        sys.exit(1)

    if args.name is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        args.name = f"{args.model}_{timestamp}"

    print("=" * 60)
    print(f"  YOLOv11 云端训练")
    print(f"  模型：{args.model}")
    print(f"  数据：{args.data}")
    print(f"  轮数：{args.epochs}")
    print(f"  Batch：{args.batch}")
    print(f"  设备：{args.device}")
    print(f"  优化器：{args.optimizer}")
    print(f"  学习率：{args.lr0}")
    print(f"  输出：{args.output}/{args.name}")
    print("=" * 60)

    from ultralytics import YOLO

    model = YOLO(f"{args.model}.pt")

    results = model.train(
        data=args.data,
        epochs=args.epochs,
        imgsz=args.imgsz,
        batch=args.batch,
        device=args.device,
        optimizer=args.optimizer,
        lr0=args.lr0,
        project=args.output,
        name=args.name,
        exist_ok=True,
        verbose=True,
        save=True,
        plots=True,
    )

    print("\n" + "=" * 60)
    print("  训练完成！")
    print(f"  输出目录：{os.path.join(args.output, args.name)}")
    print(f"  最优权重：{os.path.join(args.output, args.name, 'weights', 'best.pt')}")
    print(f"  训练日志：{os.path.join(args.output, args.name, 'results.csv')}")
    print("=" * 60)


if __name__ == "__main__":
    main()
