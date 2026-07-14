"""
修复 fog_rain_vehicle 数据集标签（DAWN 数据集）

问题：
  fog_rain_vehicle/yolo_dataset/labels 里的标签是从 DAWN 的 YOLO_darknet 原样复制的，
  带着 0~8 多个类别 ID（DAWN 实际是 6 类：bicycle/bus/car/motorcycle/person/truck），
  但 data.yaml 声明 nc=1（只 car）。所有标签类 ID >= nc，被 Ultralytics 判 corrupt 丢弃，
  训练时报 "not enough values to unpack (expected 3, got 0)"。

修复（方案 A，单类车辆检测）：
  从 DAWN 的 PASCAL_VOC（类名正确）重新转换，把 6 个类全部映射为 0，
  生成全 0 类标签，匹配现有 nc=1 的 data.yaml。图片沿用已切好的 train/val/test。

使用：
  cd backend
  python tools/fix_dawn_labels.py
"""

import os
import xml.etree.ElementTree as ET

# backend/ 目录
BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
# DAWN 源数据（项目根目录下的 DAWN/）
DAWN_DIR = os.path.abspath(os.path.join(BACKEND_DIR, "..", "DAWN"))
# 要修复的目标数据集
TARGET_DIR = os.path.join(BACKEND_DIR, "datasets", "fog_rain_vehicle", "yolo_dataset")

# DAWN 6 类全部映射为 0（单类车辆检测）
DAWN_CLASSES = ["bicycle", "bus", "car", "motorcycle", "person", "truck"]
CLASS_MAPPING = {name: 0 for name in DAWN_CLASSES}

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".bmp"}


def build_xml_index(dawn_dir):
    """扫描 DAWN 所有 *_PASCAL_VOC 目录，建立 stem -> xml_path 索引"""
    index = {}
    for root, dirs, files in os.walk(dawn_dir):
        dirs[:] = [d for d in dirs if d != ".git"]  # 不进 .git
        if "PASCAL_VOC" not in root:
            continue
        for f in files:
            if f.lower().endswith(".xml"):
                stem = os.path.splitext(f)[0]
                index[stem] = os.path.join(root, f)
    return index


def voc_to_yolo_lines(xml_path, class_mapping):
    """解析单个 VOC XML -> YOLO 行列表（class_id x_c y_c w h），所有类映射为 0"""
    tree = ET.parse(xml_path)
    root = tree.getroot()

    size = root.find("size")
    if size is None:
        return []
    w_el, h_el = size.find("width"), size.find("height")
    if w_el is None or h_el is None or not w_el.text or not h_el.text:
        return []
    img_w, img_h = int(w_el.text), int(h_el.text)
    if img_w <= 0 or img_h <= 0:
        return []

    lines = []
    for obj in root.findall("object"):
        name_el = obj.find("name")
        if name_el is None or not name_el.text:
            continue
        cls_name = name_el.text.strip()
        if cls_name not in class_mapping:
            continue
        cls_id = class_mapping[cls_name]

        bbox = obj.find("bndbox")
        if bbox is None:
            continue
        coords = {}
        ok = True
        for tag in ("xmin", "ymin", "xmax", "ymax"):
            el = bbox.find(tag)
            if el is None or not el.text:
                ok = False
                break
            coords[tag] = float(el.text)
        if not ok:
            continue

        # 像素坐标裁剪到图像范围内
        xmin = max(0, min(coords["xmin"], img_w))
        ymin = max(0, min(coords["ymin"], img_h))
        xmax = max(0, min(coords["xmax"], img_w))
        ymax = max(0, min(coords["ymax"], img_h))
        if xmax <= xmin or ymax <= ymin:
            continue

        # VOC 像素 -> YOLO 归一化
        xc = (xmin + xmax) / 2.0 / img_w
        yc = (ymin + ymax) / 2.0 / img_h
        w = (xmax - xmin) / img_w
        h = (ymax - ymin) / img_h
        lines.append(f"{cls_id} {xc:.6f} {yc:.6f} {w:.6f} {h:.6f}")
    return lines


def main():
    print("=" * 60)
    print("  修复 fog_rain_vehicle (DAWN) 数据集标签")
    print("=" * 60)
    print(f"DAWN 源:   {DAWN_DIR}")
    print(f"目标目录: {TARGET_DIR}")

    print("\n[1] 建立 DAWN VOC XML 索引...")
    xml_index = build_xml_index(DAWN_DIR)
    print(f"  共索引 {len(xml_index)} 个 VOC XML")

    stats = {"total": 0, "labeled": 0, "no_xml": 0, "empty": 0}

    for split in ("train", "val", "test"):
        img_dir = os.path.join(TARGET_DIR, "images", split)
        lbl_dir = os.path.join(TARGET_DIR, "labels", split)
        if not os.path.isdir(img_dir):
            print(f"\n[{split}] 图片目录不存在，跳过: {img_dir}")
            continue
        os.makedirs(lbl_dir, exist_ok=True)

        # 清空旧标签（避免残留旧的多类标签）
        for old in os.listdir(lbl_dir):
            if old.endswith(".txt"):
                os.remove(os.path.join(lbl_dir, old))

        n_total, n_labeled = 0, 0
        for fname in os.listdir(img_dir):
            ext = os.path.splitext(fname)[1].lower()
            if ext not in IMAGE_EXTS:
                continue
            n_total += 1
            stem = os.path.splitext(fname)[0]
            xml_path = xml_index.get(stem)
            if not xml_path:
                stats["no_xml"] += 1
                open(os.path.join(lbl_dir, f"{stem}.txt"), "w").close()  # 空标签
                continue
            lines = voc_to_yolo_lines(xml_path, CLASS_MAPPING)
            with open(os.path.join(lbl_dir, f"{stem}.txt"), "w", encoding="utf-8") as f:
                f.write("\n".join(lines))
            if lines:
                n_labeled += 1
            else:
                stats["empty"] += 1
        print(f"\n[{split}] {n_total} 图，{n_labeled} 个有标注")
        stats["total"] += n_total
        stats["labeled"] += n_labeled

    # 删除旧缓存（Ultralytics 的 .cache，否则会用旧的扫描结果）
    print("\n[2] 删除旧 .cache...")
    removed = 0
    for root, _, files in os.walk(TARGET_DIR):
        for f in files:
            if f.endswith(".cache"):
                os.remove(os.path.join(root, f))
                removed += 1
    print(f"  删除 {removed} 个 .cache 文件")

    print("\n" + "=" * 60)
    print(f"完成：共 {stats['total']} 图，{stats['labeled']} 个有标注，"
          f"{stats['no_xml']} 个无 XML，{stats['empty']} 个无目标")
    print("=" * 60)


if __name__ == "__main__":
    main()
