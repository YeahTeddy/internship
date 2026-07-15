"""
ACDC 数据集 COCO -> YOLO 格式转换脚本

将 ACDC 恶劣天气数据集（fog/rain/snow/night）的 COCO 检测标注
转换为 YOLO 格式，合并为一个"复杂天气"数据集。

输入：
  archive/rgb_anon/{fog,rain,snow,night}/{train,val,test}/{seq}/*.png
  archive/gt_detection_trainval/gt_detection/{weather}/instancesonly_{weather}_{split}_gt_detection.json

输出：
  backend/datasets/acdc/yolo_dataset/
    ├── images/{train,val}/
    ├── labels/{train,val}/
    └── data.yaml

使用：
  cd backend
  python tools/convert_acdc.py
"""

import json
import os
import shutil

# ── 路径配置 ──
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PROJECT_ROOT = os.path.dirname(BACKEND_DIR)
ARCHIVE_DIR = os.path.join(PROJECT_ROOT, "archive")
OUTPUT_DIR = os.path.join(BACKEND_DIR, "datasets", "acdc", "yolo_dataset")

# ACDC 8 类（COCO category_id -> YOLO class_id）
COCO_TO_YOLO = {
    24: 0,  # person
    25: 1,  # rider
    26: 2,  # car
    27: 3,  # truck
    28: 4,  # bus
    31: 5,  # train
    32: 6,  # motorcycle
    33: 7,  # bicycle
}
CLASS_NAMES = ["person", "rider", "car", "truck", "bus", "train", "motorcycle", "bicycle"]
CLASS_NAMES_CN = {
    "person": "行人", "rider": "骑车人", "car": "轿车", "truck": "卡车",
    "bus": "公交", "train": "火车", "motorcycle": "摩托", "bicycle": "自行车",
}

WEATHERS = ["fog", "rain", "snow", "night"]
SPLITS = ["train", "val"]  # test 集无公开标注


def convert_coco_to_yolo(coco_json_path, images_root, output_img_dir, output_lbl_dir):
    """
    转换单个 COCO JSON 文件到 YOLO 格式

    Args:
        coco_json_path: COCO 标注 JSON 路径
        images_root: 图片根目录（rgb_anon）
        output_img_dir: 输出图片目录
        output_lbl_dir: 输出标签目录
    """
    with open(coco_json_path, "r", encoding="utf-8") as f:
        data = json.load(f)

    # 建立 image_id -> annotations 映射
    img_anns = {}
    for ann in data.get("annotations", []):
        img_id = ann["image_id"]
        if img_id not in img_anns:
            img_anns[img_id] = []
        img_anns[img_id].append(ann)

    os.makedirs(output_img_dir, exist_ok=True)
    os.makedirs(output_lbl_dir, exist_ok=True)

    count = 0
    skipped = 0
    for img_info in data.get("images", []):
        img_id = img_info["id"]
        file_name = img_info["file_name"]  # 如 fog/train/GP010475/xxx.png
        img_w = img_info["width"]
        img_h = img_info["height"]

        # 源图片路径
        src_img = os.path.join(images_root, file_name)
        if not os.path.exists(src_img):
            skipped += 1
            continue

        # 目标文件名（加天气前缀避免重名）
        base_name = os.path.basename(file_name).replace("_rgb_anon", "")
        weather_prefix = file_name.split("/")[0]  # fog/rain/snow/night
        final_name = f"{weather_prefix}_{base_name}"
        dst_img = os.path.join(output_img_dir, final_name)
        dst_lbl = os.path.join(output_lbl_dir, final_name.replace(".png", ".txt"))

        # 跳过已存在的文件（避免重复处理）
        if os.path.exists(dst_img):
            continue

        # 复制图片
        shutil.copy2(src_img, dst_img)

        # 转换标注
        anns = img_anns.get(img_id, [])
        yolo_lines = []
        for ann in anns:
            cat_id = ann["category_id"]
            if cat_id not in COCO_TO_YOLO:
                continue
            yolo_cls = COCO_TO_YOLO[cat_id]

            # COCO bbox: [x, y, width, height]（绝对像素）
            # YOLO bbox: [x_center, y_center, width, height]（归一化）
            x, y, w, h = ann["bbox"]
            x_center = (x + w / 2) / img_w
            y_center = (y + h / 2) / img_h
            w_norm = w / img_w
            h_norm = h / img_h

            # 裁剪到 [0, 1]
            x_center = max(0, min(1, x_center))
            y_center = max(0, min(1, y_center))
            w_norm = max(0, min(1, w_norm))
            h_norm = max(0, min(1, h_norm))

            yolo_lines.append(f"{yolo_cls} {x_center:.6f} {y_center:.6f} {w_norm:.6f} {h_norm:.6f}")

        # 写标签文件（即使无标注也写空文件）
        with open(dst_lbl, "w", encoding="utf-8") as f:
            f.write("\n".join(yolo_lines))

        count += 1

    return count, skipped


def generate_data_yaml():
    """生成 data.yaml"""
    yaml_content = f"""path: {OUTPUT_DIR.replace(os.sep, '/')}
train: images/train
val: images/val
test: images/test

nc: {len(CLASS_NAMES)}

names:
"""
    for i, name in enumerate(CLASS_NAMES):
        yaml_content += f"  {i}: {name}\n"

    yaml_content += "\nnames_cn:\n"
    for i, name in enumerate(CLASS_NAMES):
        yaml_content += f"  {i}: {CLASS_NAMES_CN[name]}\n"

    yaml_path = os.path.join(OUTPUT_DIR, "data.yaml")
    with open(yaml_path, "w", encoding="utf-8") as f:
        f.write(yaml_content)
    print(f"  data.yaml 已生成: {yaml_path}")


def main():
    print("=" * 60)
    print("  ACDC COCO -> YOLO 格式转换")
    print("=" * 60)
    print(f"归档目录: {ARCHIVE_DIR}")
    print(f"输出目录: {OUTPUT_DIR}")
    print()

    images_root = os.path.join(ARCHIVE_DIR, "rgb_anon")
    gt_root = os.path.join(ARCHIVE_DIR, "gt_detection_trainval", "gt_detection")

    total_count = 0
    total_skipped = 0

    for split in SPLITS:
        split_img_dir = os.path.join(OUTPUT_DIR, "images", split)
        split_lbl_dir = os.path.join(OUTPUT_DIR, "labels", split)

        print(f"\n[{split}] 开始转换...")
        for weather in WEATHERS:
            coco_json = os.path.join(gt_root, weather, f"instancesonly_{weather}_{split}_gt_detection.json")
            if not os.path.exists(coco_json):
                print(f"  {weather}: 标注文件不存在，跳过")
                continue

            count, skipped = convert_coco_to_yolo(
                coco_json, images_root, split_img_dir, split_lbl_dir
            )
            print(f"  {weather}: {count} 张转换成功, {skipped} 张跳过")
            total_count += count
            total_skipped += skipped

    # 生成 data.yaml
    print("\n[配置] 生成 data.yaml...")
    generate_data_yaml()

    print("\n" + "=" * 60)
    print(f"完成：共转换 {total_count} 张图片，跳过 {total_skipped} 张")
    print(f"类别: {CLASS_NAMES}")
    print("=" * 60)


if __name__ == "__main__":
    main()
