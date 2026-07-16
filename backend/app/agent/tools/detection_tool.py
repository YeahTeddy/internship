"""检测工具集"""

import json

from langchain_core.tools import tool

from app.core.logger import get_logger
from app.services.detection_service import detection_service

logger = get_logger(__name__)


@tool
def detect_single_image(image_path: str, conf: float = 0.25, iou: float = 0.45) -> str:
    """检测单张图片中的目标物体。

    Args:
        image_path: 图片文件的服务器路径（绝对路径）
        conf: 置信度阈值，默认 0.25
        iou: NMS IoU 阈值，默认 0.45

    Returns:
        JSON 字符串，包含 total_objects, class_counts, detections, inference_time
    """
    try:
        from app.agent.tools.analysis_tool import current_user_id
        uid = current_user_id.get()
        result = detection_service.detect_single(image_path, conf=conf, iou=iou, user_id=uid, scene_id=1)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"检测失败: {str(e)}"}, ensure_ascii=False)


@tool
def detect_batch_images(image_paths: list[str], conf: float = 0.25) -> str:
    """批量检测多张图片中的目标物体。

    Args:
        image_paths: 图片文件路径列表
        conf: 置信度阈值，默认 0.25

    Returns:
        JSON 字符串，包含每张图片的检测结果汇总
    """
    try:
        from app.agent.tools.analysis_tool import current_user_id
        uid = current_user_id.get()
        result = detection_service.detect_batch(image_paths, conf=conf, user_id=uid, scene_id=1)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"批量检测失败: {str(e)}"}, ensure_ascii=False)


@tool
def detect_zip_images_file(zip_path: str, conf: float = 0.25) -> str:
    """解压 ZIP 文件并批量检测其中所有图片的目标物体。

    Args:
        zip_path: ZIP 文件的服务器路径
        conf: 置信度阈值，默认 0.25

    Returns:
        JSON 字符串，包含 ZIP 内所有图片的检测结果汇总
    """
    try:
        from app.agent.tools.analysis_tool import current_user_id
        uid = current_user_id.get()
        result = detection_service.detect_zip(zip_path, conf=conf, user_id=uid, scene_id=1)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"ZIP 检测失败: {str(e)}"}, ensure_ascii=False)


@tool
def detect_video_file(video_path: str, conf: float = 0.25, frame_sample_rate: int = 5) -> str:
    """检测视频文件中的目标物体。对视频进行帧采样后逐帧检测。

    Args:
        video_path: 视频文件路径（mp4/avi/mov 等）
        conf: 置信度阈值，默认 0.25
        frame_sample_rate: 帧采样间隔，默认 5

    Returns:
        JSON 字符串，包含视频检测结果
    """
    try:
        from app.agent.tools.analysis_tool import current_user_id
        uid = current_user_id.get()
        result = detection_service.detect_video(video_path, conf=conf, frame_sample_rate=frame_sample_rate, user_id=uid, scene_id=1)
        if "key_frames" in result:
            for frame in result["key_frames"]:
                frame.pop("annotated_image_base64", None)
        result.pop("annotated_video_url", None)
        return json.dumps(result, ensure_ascii=False)
    except Exception as e:
        return json.dumps({"error": f"视频检测失败: {str(e)}"}, ensure_ascii=False)


DETECTION_TOOLS = [detect_single_image, detect_batch_images, detect_zip_images_file, detect_video_file]
