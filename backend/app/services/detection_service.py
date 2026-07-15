"""
目标检测服务 — 封装 YOLOv11 推理逻辑

职责：
  - 单图检测（detect_single）
  - 批量检测（detect_batch）
  - ZIP 解压 + 批量检测（detect_zip）
  - 结果持久化（MinIO 存储标注图 + PostgreSQL 存储检测结果）

架构：
  DetectionService 是无状态的纯服务，被 Agent Tool 和快捷按钮 API 共同调用。
  每次检测都会：
    1. 创建 DetectionTask 记录
    2. 运行 YOLO 推理
    3. 上传标注图到 MinIO
    4. 保存 DetectionResult 记录
"""

import base64
import os
import shutil
import subprocess
import tempfile
import zipfile
from datetime import datetime

import cv2
from sqlalchemy.orm import Session
from ultralytics import YOLO

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import (
    DetectionResult,
    DetectionScene,
    DetectionTask,
    ModelVersion,
)
from app.storage.minio_client import MinIOClient

logger = get_logger(__name__)


class DetectionService:
    """目标检测服务 — 封装 YOLOv11 推理全流程"""

    @staticmethod
    def _get_default_model_path() -> str:
        """
        获取默认模型权重路径

        查找顺序：
          1. models/ 目录下 is_default=True 的模型
          2. runs/train/ 目录下最新训练产出的 best.pt
          3. 回退到预训练模型 yolo11n.pt
        """
        db = SessionLocal()
        try:
            # 查找默认模型版本
            default_model = (
                db.query(ModelVersion).filter(ModelVersion.is_default == True).first()
            )
            if default_model and os.path.exists(default_model.model_path):
                return default_model.model_path

            # 回退：查找最新训练的 best.pt
            from app.entity.db_models import TrainingTask

            latest_task = (
                db.query(TrainingTask)
                .filter(TrainingTask.status == "completed")
                .order_by(TrainingTask.completed_at.desc())
                .first()
            )
            if latest_task:
                weights_path = os.path.join(
                    os.getcwd(),
                    settings.TRAIN_OUTPUT_DIR,
                    f"task_{latest_task.task_uuid}",
                    "weights",
                    "best.pt",
                )
                if os.path.exists(weights_path):
                    return weights_path
        finally:
            db.close()

        # 最终回退：预训练模型
        return "yolo11n.pt"

    @staticmethod
    def _get_model(scene_id: int = None) -> YOLO:
        """加载 YOLO 模型：优先使用场景关联的默认模型，否则使用全局默认模型"""
        model_path = None

        if scene_id:
            db = SessionLocal()
            try:
                default_model = (
                    db.query(ModelVersion)
                    .filter(
                        ModelVersion.scene_id == scene_id,
                        ModelVersion.is_default == True,
                    )
                    .first()
                )
                if default_model and os.path.exists(default_model.model_path):
                    model_path = default_model.model_path
            finally:
                db.close()

        if not model_path:
            model_path = DetectionService._get_default_model_path()

        logger.info("加载检测模型: %s", model_path)
        return YOLO(model_path)

    @staticmethod
    def _save_task_and_results(
        db: Session,
        user_id: int,
        scene_id: int,
        task_type: str,
        detections: list,
        annotated_image: bytes,
        original_filename: str,
        inference_time: float,
        conf: float,
        iou: float,
    ) -> dict:
        """保存检测任务和结果到数据库 + MinIO"""
        # 创建检测任务记录
        task = DetectionTask(
            user_id=user_id,
            scene_id=scene_id,
            task_type=task_type,
            status="completed",
            total_images=1,
            total_objects=len(detections),
            total_inference_time=inference_time,
            conf_threshold=conf,
            iou_threshold=iou,
            completed_at=datetime.now(),
        )
        db.add(task)
        db.flush()  # 获取 task.id

        # 上传标注图到 MinIO
        annotated_image_url = None
        try:
            minio_client = MinIOClient()
            object_name = f"detections/{task.id}/{original_filename}"
            annotated_image_url = minio_client.upload_bytes(
                object_name, annotated_image, "image/jpeg"
            )
        except Exception as e:
            logger.warning("MinIO 上传失败（不影响检测结果）: %s", str(e))

        # 保存每条检测结果
        for det in detections:
            result = DetectionResult(
                task_id=task.id,
                image_path=original_filename,
                annotated_image_url=annotated_image_url,
                class_name=det["class_name"],
                class_name_cn=det.get("class_name_cn"),
                class_id=det["class_id"],
                confidence=det["confidence"],
                bbox=det["bbox"],
                inference_time=inference_time,
            )
            db.add(result)

        db.commit()
        return {"task_id": task.id, "annotated_image_url": annotated_image_url}

    def detect_single(
        self,
        image_path: str,
        conf: float = 0.25,
        iou: float = 0.45,
        scene_id: int = None,
        user_id: int = None,
    ) -> dict:
        """
        单图检测

        Returns:
            {"total_objects", "class_counts", "detections", "annotated_image_base64", "inference_time", "task_id"}
        """
        db = SessionLocal()
        try:
            model = self._get_model(scene_id)

            results = model.predict(
                source=image_path,
                conf=conf,
                iou=iou,
                imgsz=640,
                device="cpu",
                save=False,
                verbose=False,
            )

            result = results[0]
            detections = []
            total_objects = 0

            if result.boxes is not None and len(result.boxes) > 0:
                for box in result.boxes:
                    cls_id = int(box.cls[0])
                    cls_name = model.names.get(cls_id, f"class_{cls_id}")
                    confidence = float(box.conf[0])
                    x1, y1, x2, y2 = box.xyxy[0].tolist()

                    detections.append({
                        "class_name": cls_name,
                        "class_id": cls_id,
                        "confidence": round(confidence, 4),
                        "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                    })
                    total_objects += 1

            # 生成标注图
            annotated_img = result.plot()
            _, buffer = cv2.imencode(".jpg", annotated_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
            annotated_base64 = base64.b64encode(buffer).decode("utf-8")

            # 统计各类别数量
            class_counts = {}
            for det in detections:
                name = det["class_name"]
                class_counts[name] = class_counts.get(name, 0) + 1

            # 持久化到数据库
            task_id = None
            annotated_image_url = None
            if user_id and scene_id:
                save_result = self._save_task_and_results(
                    db=db,
                    user_id=user_id,
                    scene_id=scene_id,
                    task_type="single",
                    detections=detections,
                    annotated_image=buffer.tobytes(),
                    original_filename=os.path.basename(image_path),
                    inference_time=float(result.speed.get("inference", 0)),
                    conf=conf,
                    iou=iou,
                )
                task_id = save_result["task_id"]
                annotated_image_url = save_result.get("annotated_image_url")

            logger.info(
                "单图检测完成: %s, 检测到 %d 个目标, 耗时 %.2fms",
                image_path, total_objects, float(result.speed.get("inference", 0)),
            )

            return {
                "total_objects": total_objects,
                "class_counts": class_counts,
                "detections": detections,
                "annotated_image_base64": annotated_base64,
                "annotated_image_url": annotated_image_url,
                "inference_time": round(float(result.speed.get("inference", 0)), 2),
                "task_id": task_id,
            }

        except Exception as e:
            logger.error("单图检测异常: %s", str(e), exc_info=True)
            return {"error": f"检测失败: {str(e)}"}
        finally:
            db.close()

    def detect_batch(
        self,
        image_paths: list[str],
        conf: float = 0.25,
        scene_id: int = None,
        user_id: int = None,
    ) -> dict:
        """批量检测多张图片"""
        db = SessionLocal()
        try:
            model = self._get_model(scene_id)

            if not scene_id:
                default_scene = db.query(DetectionScene).first()
                if default_scene:
                    scene_id = default_scene.id
                else:
                    return {"error": "数据库中没有可用的检测场景，请先创建检测场景"}

            task = DetectionTask(
                user_id=user_id or 0,
                scene_id=scene_id,
                task_type="batch",
                status="processing",
                total_images=len(image_paths),
                conf_threshold=conf,
            )
            db.add(task)
            db.flush()

            all_detections = []
            annotated_images = []
            total_objects = 0
            total_inference_time = 0
            class_counts = {}

            for i, image_path in enumerate(image_paths):
                results = model.predict(
                    source=image_path, conf=conf, iou=0.45,
                    imgsz=640, device="cpu", save=False, verbose=False,
                )
                result = results[0]
                inference_time = float(result.speed.get("inference", 0))
                total_inference_time += inference_time

                annotated_img = result.plot()
                _, buffer = cv2.imencode(".jpg", annotated_img, [cv2.IMWRITE_JPEG_QUALITY, 85])
                annotated_images.append({
                    "image_path": os.path.basename(image_path),
                    "annotated_image_base64": base64.b64encode(buffer).decode("utf-8"),
                })

                if result.boxes is not None and len(result.boxes) > 0:
                    for box in result.boxes:
                        cls_id = int(box.cls[0])
                        cls_name = model.names.get(cls_id, f"class_{cls_id}")
                        confidence = float(box.conf[0])
                        x1, y1, x2, y2 = box.xyxy[0].tolist()

                        det = {
                            "image_path": image_path,
                            "class_name": cls_name,
                            "class_id": cls_id,
                            "confidence": round(confidence, 4),
                            "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)],
                            "inference_time": inference_time,
                        }
                        all_detections.append(det)
                        total_objects += 1
                        class_counts[cls_name] = class_counts.get(cls_name, 0) + 1

                        db_result = DetectionResult(
                            task_id=task.id,
                            image_path=image_path,
                            class_name=cls_name,
                            class_id=cls_id,
                            confidence=round(confidence, 4),
                            bbox=det["bbox"],
                            inference_time=inference_time,
                        )
                        db.add(db_result)

            task.status = "completed"
            task.total_objects = total_objects
            task.total_inference_time = total_inference_time
            task.completed_at = datetime.now()
            db.commit()

            logger.info(
                "批量检测完成: %d 张图, 共 %d 个目标, 总耗时 %.2fms",
                len(image_paths), total_objects, total_inference_time,
            )

            return {
                "task_id": task.id,
                "total_images": len(image_paths),
                "total_objects": total_objects,
                "class_counts": class_counts,
                "total_inference_time": round(total_inference_time, 2),
                "detections": all_detections,
                "annotated_images": annotated_images,
            }

        except Exception as e:
            logger.error("批量检测异常: %s", str(e), exc_info=True)
            return {"error": f"批量检测失败: {str(e)}"}
        finally:
            db.close()

    def detect_zip(
        self,
        zip_path: str,
        conf: float = 0.25,
        scene_id: int = None,
        user_id: int = None,
    ) -> dict:
        """解压 ZIP 文件并批量检测其中所有图片"""
        temp_dir = None
        try:
            temp_dir = tempfile.mkdtemp(prefix="rsod_zip_")
            logger.info("解压 ZIP 文件: %s -> %s", zip_path, temp_dir)

            with zipfile.ZipFile(zip_path, "r") as zf:
                zf.extractall(temp_dir)

            image_files = []
            for root, dirs, files in os.walk(temp_dir):
                for fname in files:
                    ext = os.path.splitext(fname)[1].lower()
                    if ext in {".jpg", ".jpeg", ".png", ".bmp", ".webp"}:
                        image_files.append(os.path.join(root, fname))

            if not image_files:
                return {"error": "ZIP 文件中没有找到图片"}

            logger.info("ZIP 中包含 %d 张图片，开始批量检测", len(image_files))

            batch_result = self.detect_batch(
                image_paths=image_files, conf=conf,
                scene_id=scene_id, user_id=user_id,
            )

            batch_result["source"] = "zip"
            batch_result["zip_filename"] = os.path.basename(zip_path)
            batch_result["total_images_in_zip"] = len(image_files)

            return batch_result

        except zipfile.BadZipFile:
            return {"error": f"无效的 ZIP 文件: {zip_path}"}
        except Exception as e:
            logger.error("ZIP 检测异常: %s", str(e), exc_info=True)
            return {"error": f"ZIP 检测失败: {str(e)}"}
        finally:
            if temp_dir and os.path.exists(temp_dir):
                shutil.rmtree(temp_dir, ignore_errors=True)

    def detect_video(
        self,
        video_path: str,
        conf: float = 0.25,
        iou: float = 0.45,
        frame_sample_rate: int = 5,
        max_frames: int = 50,
        scene_id: int = None,
        user_id: int = None,
        task_id: int = None,
    ) -> dict:
        """
        视频检测 — 逐帧采样 + YOLO 推理

        Args:
            video_path: 视频文件路径
            conf: 置信度阈值
            iou: NMS IoU 阈值
            frame_sample_rate: 帧采样间隔（每 N 帧取 1 帧）
            max_frames: 最多处理的关键帧数量
            scene_id: 检测场景 ID
            user_id: 操作用户 ID
            task_id: 已创建的检测任务 ID

        Returns:
            视频检测结果字典
        """
        db = SessionLocal()
        try:
            model = self._get_model(scene_id)

            cap = cv2.VideoCapture(video_path)
            if not cap.isOpened():
                return {"error": f"无法打开视频文件: {video_path}"}

            total_frames = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
            fps = cap.get(cv2.CAP_PROP_FPS) or 30.0
            width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH))
            height = int(cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
            duration_seconds = total_frames / fps if fps > 0 else 0

            logger.info("视频信息: %dx%d, %.1ffps, %d 帧, %.1f 秒", width, height, fps, total_frames, duration_seconds)

            if not task_id:
                task = DetectionTask(
                    user_id=user_id or 0,
                    scene_id=scene_id or 1,
                    task_type="video",
                    status="processing",
                    total_images=0,
                    conf_threshold=conf,
                    iou_threshold=iou,
                )
                db.add(task)
                db.flush()
                task_id = task.id
            else:
                task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first()

            effective_interval = max(frame_sample_rate, total_frames // max_frames)
            sample_indices = list(range(0, total_frames, effective_interval))[:max_frames]
            sample_set = set(sample_indices)

            if task:
                task.total_images = len(sample_indices)
                db.commit()

            key_frames = []
            total_objects = 0
            total_inference_time = 0
            class_counts = {}
            last_detections = []
            last_frame = None

            # 创建标注视频输出
            output_tmp = tempfile.NamedTemporaryFile(suffix=".mp4", delete=False)
            output_video_path = output_tmp.name
            output_tmp.close()
            fourcc = cv2.VideoWriter_fourcc(*"mp4v")
            video_writer = cv2.VideoWriter(output_video_path, fourcc, fps, (width, height))

            frame_idx = 0
            while True:
                ret, frame = cap.read()
                if not ret:
                    break

                is_sampled = frame_idx in sample_set

                if is_sampled:
                    # 场景变化检测：决定是否重新推理
                    gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                    gray_small = cv2.resize(gray, (100, 100))
                    need_inference = False
                    if last_frame is None:
                        need_inference = True
                    else:
                        diff = cv2.absdiff(last_frame, gray_small)
                        if diff.mean() > 5:  # 降低阈值，交通视频帧间差异小
                            need_inference = True
                    last_frame = gray_small.copy()

                    if need_inference:
                        results = model.predict(source=frame, conf=conf, iou=iou, imgsz=640, device="cpu", save=False, verbose=False)
                        result = results[0]
                        frame_detections = []

                        if result.boxes is not None and len(result.boxes) > 0:
                            for box in result.boxes:
                                cls_id = int(box.cls[0])
                                cls_name = model.names.get(cls_id, f"class_{cls_id}")
                                confidence = float(box.conf[0])
                                x1, y1, x2, y2 = box.xyxy[0].tolist()
                                det = {"class_name": cls_name, "class_id": cls_id, "confidence": round(confidence, 4), "bbox": [round(x1, 1), round(y1, 1), round(x2, 1), round(y2, 1)]}
                                frame_detections.append(det)
                                total_objects += 1
                                class_counts[cls_name] = class_counts.get(cls_name, 0) + 1

                        last_detections = frame_detections
                        inference_time = float(result.speed.get("inference", 0))
                        total_inference_time += inference_time
                    else:
                        inference_time = 0

                    # 绘制标注（复用 last_detections）
                    annotated = frame.copy()
                    for det in last_detections:
                        x1, y1, x2, y2 = det["bbox"]
                        cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                        cv2.putText(annotated, f"{det['class_name']} {det['confidence']:.2f}", (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                    video_writer.write(annotated)

                    # 保留少量关键帧缩略图
                    annotated_base64 = None
                    if len(key_frames) < 6:
                        _, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 70])
                        annotated_base64 = base64.b64encode(buf).decode("utf-8")

                    key_frames.append({
                        "frame_index": frame_idx,
                        "timestamp": round(frame_idx / fps, 2),
                        "annotated_image_base64": annotated_base64,
                        "object_count": len(last_detections),
                        "detections": last_detections,
                        "inference_time": round(inference_time, 2),
                    })

                    if need_inference:
                        for det in last_detections:
                            db.add(DetectionResult(task_id=task_id, image_path=f"frame_{frame_idx}.jpg", class_name=det["class_name"], class_id=det["class_id"], confidence=det["confidence"], bbox=det["bbox"], inference_time=inference_time))

                    if task:
                        task.total_objects = total_objects
                        db.commit()
                else:
                    # 非采样帧：用上一帧的检测结果绘制标注框，保持连续
                    if last_detections:
                        annotated = frame.copy()
                        for det in last_detections:
                            x1, y1, x2, y2 = det["bbox"]
                            cv2.rectangle(annotated, (int(x1), int(y1)), (int(x2), int(y2)), (0, 255, 0), 2)
                            cv2.putText(annotated, f"{det['class_name']} {det['confidence']:.2f}", (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 255, 0), 2)
                        video_writer.write(annotated)
                    else:
                        video_writer.write(frame)

                frame_idx += 1

            cap.release()
            video_writer.release()

            # ffmpeg 转码为 H.264（浏览器兼容）
            h264_path = output_video_path.replace(".mp4", "_h264.mp4")
            try:
                subprocess.run([shutil.which("ffmpeg") or "ffmpeg", "-y", "-i", output_video_path, "-c:v", "libx264", "-preset", "fast", "-crf", "23", "-pix_fmt", "yuv420p", "-movflags", "+faststart", h264_path], capture_output=True, timeout=300, check=True)
                os.replace(h264_path, output_video_path)
                logger.info("视频已转码为 H.264 格式")
            except Exception as e:
                logger.warning("ffmpeg 转码失败，使用原始 mp4v: %s", str(e))
                try:
                    os.unlink(h264_path)
                except Exception:
                    pass

            # 上传标注视频到 MinIO
            annotated_video_url = None
            try:
                minio_client = MinIOClient()
                annotated_video_url = minio_client.upload_file(f"detections/{task_id}/annotated_video.mp4", output_video_path)
            except Exception as e:
                logger.warning("标注视频上传 MinIO 失败: %s", str(e))

            try:
                os.unlink(output_video_path)
            except Exception:
                pass

            if task:
                task.status = "completed"
                task.total_objects = total_objects
                task.total_inference_time = total_inference_time
                task.completed_at = datetime.now()
                db.commit()

            logger.info("视频检测完成: %d 帧处理, %d 关键帧, 共 %d 目标", frame_idx, len(key_frames), total_objects)

            return {
                "task_id": task_id,
                "total_frames": total_frames,
                "processed_frames": len(key_frames),
                "frame_sample_rate": frame_sample_rate,
                "fps": round(fps, 2),
                "duration_seconds": round(duration_seconds, 2),
                "video_resolution": {"width": width, "height": height},
                "total_objects": total_objects,
                "class_counts": class_counts,
                "key_frames": key_frames,
                "annotated_video_url": annotated_video_url,
                "total_inference_time": round(total_inference_time, 2),
            }

        except Exception as e:
            logger.error("视频检测异常: %s", str(e), exc_info=True)
            if task_id:
                task = db.query(DetectionTask).filter(DetectionTask.id == task_id).first()
                if task:
                    task.status = "failed"
                    task.error_message = str(e)
                    db.commit()
            return {"error": f"视频检测失败: {str(e)}"}
        finally:
            db.close()


def get_model(scene_id: int = None) -> YOLO:
    """模块级辅助函数：加载检测模型（供 WebSocket 等外部调用）"""
    return DetectionService._get_model(scene_id)


# 全局单例
detection_service = DetectionService()
