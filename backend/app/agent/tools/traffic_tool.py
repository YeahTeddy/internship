"""交通统计工具 — 车流/车型/密度分析"""

from collections import Counter

from langchain_core.tools import tool

from app.core.logger import get_logger

logger = get_logger(__name__)

VEHICLE_CLASSES = {"car", "truck", "bus", "motorcycle", "motorbike", "bicycle", "van", "suv", "vehicle"}
LARGE_VEHICLE_CLASSES = {"truck", "bus", "van"}
VULNERABLE_CLASSES = {"person", "pedestrian", "motorcycle", "motorbike", "bicycle"}


def _norm(name):
    return str(name or "unknown").strip().lower()


def _density_level(count, scope):
    if scope == "video":
        if count >= 60: return "high"
        if count >= 25: return "medium"
        if count >= 1: return "low"
    else:
        if count >= 12: return "high"
        if count >= 5: return "medium"
        if count >= 1: return "low"
    return "none"


def analyze_detection_result(class_counts_dict):
    """分析单张/批量检测结果的交通统计"""
    class_counts = Counter()
    for name, count in class_counts_dict.items():
        class_counts[_norm(name)] = int(count)

    vehicle_count = sum(c for n, c in class_counts.items() if n in VEHICLE_CLASSES)
    pedestrian_count = class_counts.get("person", 0)
    vulnerable_count = sum(c for n, c in class_counts.items() if n in VULNERABLE_CLASSES)
    large_vehicle_count = sum(c for n, c in class_counts.items() if n in LARGE_VEHICLE_CLASSES)

    return {
        "class_counts": dict(class_counts),
        "vehicle_count": vehicle_count,
        "pedestrian_count": pedestrian_count,
        "vulnerable_road_user_count": vulnerable_count,
        "large_vehicle_count": large_vehicle_count,
        "large_vehicle_ratio": round(large_vehicle_count / vehicle_count, 4) if vehicle_count else 0,
        "density_level": _density_level(vehicle_count, "image"),
        "density_score": _density_level(vehicle_count, "image"),
    }


def analyze_video_frames(frames):
    """分析视频帧的交通统计（含 track_id 去重）"""
    sampled_class_counts = Counter()
    unique_class_counts = Counter()
    track_classes = {}
    unique_vehicle_tracks = set()

    for frame in frames or []:
        for item in frame.get("detections", []):
            class_name = _norm(item.get("class_name"))
            sampled_class_counts[class_name] += 1
            if class_name in VEHICLE_CLASSES:
                track_id = item.get("track_id")
                if track_id is not None:
                    unique_vehicle_tracks.add(track_id)
                    track_classes.setdefault(track_id, class_name)

    unique_class_counts.update(track_classes.values())
    vehicle_count = sum(c for n, c in sampled_class_counts.items() if n in VEHICLE_CLASSES)
    unique_vehicle_count = len(unique_vehicle_tracks) if unique_vehicle_tracks else None

    return {
        "sampled_class_counts": dict(sampled_class_counts),
        "unique_class_counts": dict(unique_class_counts),
        "vehicle_count": vehicle_count,
        "unique_vehicle_count": unique_vehicle_count,
        "density_level": _density_level(unique_vehicle_count or vehicle_count, "video"),
    }


@tool
def analyze_traffic_stats(class_counts_dict: dict, frames: list = None) -> str:
    """分析检测结果的交通统计数据（车辆数、行人、密度等级等）。

    Args:
        class_counts_dict: 类别计数 dict，如 {"car": 5, "person": 2}
        frames: 可选的视频帧列表（含 track_id）

    Returns:
        JSON 字符串，包含交通统计分析结果
    """
    try:
        if frames:
            result = analyze_video_frames({"detections": [{"class_name": n, "track_id": None} for n, c in class_counts_dict.items() for _ in range(c)]})
        else:
            result = analyze_detection_result(class_counts_dict)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"交通统计分析失败: {str(e)}"}, ensure_ascii=False)


TRAFFIC_TOOLS = [analyze_traffic_stats]
