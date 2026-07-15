"""
历史记录服务层
"""

from datetime import datetime
from typing import Optional

from sqlalchemy import desc, func
from sqlalchemy.orm import joinedload

from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import DetectionResult, DetectionScene, DetectionTask

logger = get_logger(__name__)


class HistoryService:

    @staticmethod
    def list_tasks(user_id, page=1, page_size=10, task_type=None, status=None,
                   scene_id=None, start_date=None, end_date=None) -> dict:
        db = SessionLocal()
        try:
            query = db.query(DetectionTask).options(joinedload(DetectionTask.scene)).filter(DetectionTask.user_id == user_id)
            if task_type: query = query.filter(DetectionTask.task_type == task_type)
            if status: query = query.filter(DetectionTask.status == status)
            if scene_id: query = query.filter(DetectionTask.scene_id == scene_id)
            if start_date:
                try: query = query.filter(DetectionTask.created_at >= datetime.strptime(start_date, "%Y-%m-%d"))
                except ValueError: pass
            if end_date:
                try: query = query.filter(DetectionTask.created_at <= datetime.strptime(end_date, "%Y-%m-%d").replace(hour=23, minute=59, second=59))
                except ValueError: pass

            total = query.count()
            total_pages = (total + page_size - 1) // page_size
            tasks = query.order_by(desc(DetectionTask.created_at)).offset((page - 1) * page_size).limit(page_size).all()

            items = []
            for task in tasks:
                scene_name = task.scene.display_name if task.scene else None
                items.append({
                    "id": task.id, "task_type": task.task_type, "status": task.status,
                    "scene_id": task.scene_id, "scene_name": scene_name,
                    "total_images": task.total_images or 0, "total_objects": task.total_objects or 0,
                    "total_inference_time": round(task.total_inference_time or 0, 2),
                    "conf_threshold": task.conf_threshold, "error_message": task.error_message,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                })
            return {"total": total, "page": page, "page_size": page_size, "total_pages": total_pages, "items": items}
        finally:
            db.close()

    @staticmethod
    def get_task_detail(user_id: int, task_id: int) -> Optional[dict]:
        db = SessionLocal()
        try:
            task = db.query(DetectionTask).options(joinedload(DetectionTask.scene)).filter(
                DetectionTask.id == task_id, DetectionTask.user_id == user_id).first()
            if not task: return None

            results = db.query(DetectionResult).filter(DetectionResult.task_id == task_id).all()
            class_counts = {}
            for r in results:
                class_counts[r.class_name] = class_counts.get(r.class_name, 0) + 1

            result_items = [{
                "id": r.id, "class_name": r.class_name, "class_name_cn": r.class_name_cn,
                "class_id": r.class_id, "confidence": round(r.confidence, 4),
                "bbox": r.bbox, "image_path": r.image_path,
                "annotated_image_url": r.annotated_image_url,
                "inference_time": round(r.inference_time, 2) if r.inference_time else None,
            } for r in results]

            return {
                "task": {
                    "id": task.id, "task_type": task.task_type, "status": task.status,
                    "scene_id": task.scene_id, "scene_name": task.scene.display_name if task.scene else None,
                    "total_images": task.total_images or 0, "total_objects": task.total_objects or 0,
                    "total_inference_time": round(task.total_inference_time or 0, 2),
                    "conf_threshold": task.conf_threshold, "iou_threshold": task.iou_threshold,
                    "error_message": task.error_message,
                    "created_at": task.created_at.isoformat() if task.created_at else None,
                    "completed_at": task.completed_at.isoformat() if task.completed_at else None,
                },
                "class_counts": class_counts, "results": result_items,
            }
        finally:
            db.close()

    @staticmethod
    def delete_task(user_id: int, task_id: int) -> bool:
        db = SessionLocal()
        try:
            task = db.query(DetectionTask).filter(DetectionTask.id == task_id, DetectionTask.user_id == user_id).first()
            if not task: return False
            db.delete(task)
            db.commit()
            logger.info("用户 %d 删除检测任务 #%d", user_id, task_id)
            return True
        finally:
            db.close()

    @staticmethod
    def get_summary(user_id: int) -> dict:
        db = SessionLocal()
        try:
            today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
            total = db.query(func.count(DetectionTask.id)).filter(DetectionTask.user_id == user_id).scalar()
            today_count = db.query(func.count(DetectionTask.id)).filter(
                DetectionTask.user_id == user_id, DetectionTask.created_at >= today_start).scalar()
            status_counts = {}
            for s in ["completed", "processing", "failed", "pending"]:
                count = db.query(func.count(DetectionTask.id)).filter(
                    DetectionTask.user_id == user_id, DetectionTask.status == s).scalar()
                status_counts[s] = count
            return {"total_tasks": total, "today_tasks": today_count, "status_counts": status_counts}
        finally:
            db.close()

    @staticmethod
    def list_scenes() -> list:
        db = SessionLocal()
        try:
            scenes = db.query(DetectionScene).filter(DetectionScene.is_active == True).all()
            return [{"id": s.id, "name": s.name, "display_name": s.display_name, "category": s.category} for s in scenes]
        finally:
            db.close()


history_service = HistoryService()
