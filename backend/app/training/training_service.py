"""
模型训练服务

职责：
  - 封装 YOLOv11 训练启动、监控、停止逻辑
  - 支持本地 CPU 训练和 GPU 训练
  - 训练在后台线程中执行，不阻塞 API 请求
  - 实时解析训练指标并写入数据库
  - 解析 Ultralytics 生成的 results.csv 获取训练日志

使用方式：
  from app.training.training_service import training_service

  # 启动训练
  task = training_service.start_training(
      db=db,
      user_id=current_user.id,
      scene_id=scene.id,
      config={"model_name": "yolov11n", "epochs": 50, "batch_size": 8}
  )

  # 查询训练状态
  status = training_service.get_training_status(db, task_id)

  # 获取训练指标
  metrics = training_service.get_training_metrics(db, task_id)
"""

import csv
import json
import os
import threading
import uuid
from datetime import datetime

from app.config.settings import settings
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import TrainingMetric, TrainingTask

logger = get_logger(__name__)

# ── 训练进程注册表 ────────────────────────────────────
# 存储正在运行的训练任务的 model 引用，用于中途停止训练
# key: task_uuid, value: YOLO model 实例
_running_tasks: dict = {}
_running_lock = threading.Lock()


class TrainingService:
    """模型训练服务 — 封装 YOLOv11 训练全流程"""

    @staticmethod
    def start_training(
        db,
        user_id: int,
        scene_id: int,
        config: dict,
    ) -> TrainingTask:
        """
        创建并启动训练任务

        流程：
          1. 在数据库中创建 TrainingTask 记录（状态 pending）
          2. 启动后台守护线程执行 _run_training()
          3. 立即返回任务对象（前端通过轮询获取进度）

        Args:
            db: SQLAlchemy 数据库会话
            user_id: 操作用户 ID
            scene_id: 关联的检测场景 ID
            config: 训练配置字典

        Returns:
            创建的 TrainingTask 数据库对象
        """
        # ── 生成唯一任务标识 ──
        task_uuid = str(uuid.uuid4())[:8]

        # ── 查找 data.yaml ──
        data_yaml = config.get("data_yaml")
        dataset_path = config.get("dataset_path", "")
        if not data_yaml and dataset_path:
            yaml_candidate = os.path.join(dataset_path, "data.yaml")
            if os.path.exists(yaml_candidate):
                data_yaml = yaml_candidate

        # ── 创建数据库记录 ──
        task = TrainingTask(
            user_id=user_id,
            scene_id=scene_id,
            task_uuid=task_uuid,
            status="pending",
            model_name=config.get("model_name", "yolov11n"),
            epochs=config.get("epochs", 50),
            img_size=config.get("img_size", 640),
            batch_size=config.get("batch_size", 8),
            device=config.get("device", "cpu"),
            optimizer=config.get("optimizer", "SGD"),
            lr0=config.get("lr0", 0.01),
            augment_config=config.get("augment_config"),
            dataset_path=dataset_path,
            data_yaml=data_yaml,
        )
        db.add(task)
        db.commit()
        db.refresh(task)

        # ── 启动后台训练线程 ──
        thread = threading.Thread(
            target=TrainingService._run_training,
            args=(task.id, task.task_uuid, config),
            daemon=True,
            name=f"train-{task_uuid}",
        )
        thread.start()

        logger.info(
            "训练任务已启动：task_id=%d, uuid=%s, model=%s, epochs=%d",
            task.id,
            task_uuid,
            task.model_name,
            task.epochs,
        )
        return task

    @staticmethod
    def _run_training(task_id: int, task_uuid: str, config: dict):
        """
        在后台线程中执行 YOLOv11 训练（内部方法）
        """
        db = SessionLocal()
        original_content = None
        data_yaml = None
        original_cwd = os.getcwd()

        try:
            task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
            if not task:
                logger.error("训练任务不存在：task_id=%d", task_id)
                return

            # ── 更新状态为 running ──
            task.status = "running"
            task.started_at = datetime.now()
            db.commit()

            # ── 导入 ultralytics ──
            from ultralytics import YOLO

            # ── 加载预训练模型 ──
            model_name = config.get("model_name", "yolov11n")
            # 构建绝对路径，确保后台线程能找到模型文件
            backend_dir = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
            model_path = os.path.join(backend_dir, f"{model_name}.pt")
            if not os.path.exists(model_path):
                model_path = model_name  # 如果本地没有，让 ultralytics 自动下载
            logger.info("加载预训练模型：%s", model_path)
            model = YOLO(model_path)

            # ── 注册到运行中任务表 ──
            with _running_lock:
                _running_tasks[task_uuid] = model

            # ── 确定 data.yaml 路径 ──
            data_yaml = config.get("data_yaml", "")
            if not data_yaml:
                dataset_path = config.get("dataset_path", "")
                data_yaml = os.path.join(dataset_path, "data.yaml")

            if not os.path.exists(data_yaml):
                raise FileNotFoundError(f"data.yaml 不存在：{data_yaml}")

            data_yaml_dir = os.path.dirname(data_yaml)

            # 临时修改 data.yaml 的 path 为绝对路径
            with open(data_yaml, "r", encoding="utf-8") as f:
                original_content = f.read()

            modified_content = original_content.replace(
                "path: .", f"path: {data_yaml_dir}"
            )
            with open(data_yaml, "w", encoding="utf-8") as f:
                f.write(modified_content)
            logger.info("临时修改 data.yaml path 为绝对路径：%s", data_yaml_dir)

            train_kwargs = {
                "data": data_yaml,
                "epochs": config.get("epochs", 50),
                "imgsz": config.get("img_size", 640),
                "batch": config.get("batch_size", 8),
                "device": config.get("device", "cpu"),
                "optimizer": config.get("optimizer", "SGD"),
                "lr0": config.get("lr0", 0.01),
                "project": os.path.join(original_cwd, settings.TRAIN_OUTPUT_DIR),
                "name": f"task_{task_uuid}",
                "exist_ok": True,
                "verbose": True,
                "save": True,
                "plots": False,
            }

            # ── 注册训练回调 ──
            # 注意：必须用 on_fit_epoch_end（验证完后触发），不能用 on_train_epoch_end
            # 因为 on_train_epoch_end 在验证之前触发，此时 trainer.metrics 是上一轮的旧值
            def on_fit_epoch_end(trainer):
                try:
                    epoch = trainer.epoch + 1
                    metrics = trainer.metrics or {}

                    # 训练 loss 从 trainer.tloss 获取（shape [3]: box, cls, dfl）
                    tloss = trainer.tloss
                    if tloss is not None and hasattr(tloss, "__len__") and len(tloss) >= 3:
                        box_loss = float(tloss[0])
                        cls_loss = float(tloss[1])
                        dfl_loss = float(tloss[2])
                    elif tloss is not None:
                        # 如果只有一个 loss 值，全部设为相同
                        box_loss = cls_loss = dfl_loss = float(tloss)
                    else:
                        box_loss = cls_loss = dfl_loss = 0.0

                    # 验证指标从 trainer.metrics 获取（on_fit_epoch_end 时已是当前轮最新值）
                    metric_record = TrainingMetric(
                        task_id=task_id,
                        epoch=epoch,
                        box_loss=box_loss,
                        cls_loss=cls_loss,
                        dfl_loss=dfl_loss,
                        precision=float(metrics.get("metrics/precision(B)", 0)),
                        recall=float(metrics.get("metrics/recall(B)", 0)),
                        map50=float(metrics.get("metrics/mAP50(B)", 0)),
                        map50_95=float(metrics.get("metrics/mAP50-95(B)", 0)),
                    )
                    db.add(metric_record)

                    total_epochs = config.get("epochs", 50)
                    task.current_epoch = epoch
                    task.progress = int((epoch / total_epochs) * 100)
                    db.commit()

                    logger.debug(
                        "训练进度：task=%s epoch=%d/%d box_loss=%.4f",
                        task_uuid,
                        epoch,
                        total_epochs,
                        metric_record.box_loss or 0,
                    )
                except Exception as e:
                    logger.warning("训练回调异常（不影响训练）：%s", str(e))
                    db.rollback()

            model.add_callback("on_fit_epoch_end", on_fit_epoch_end)

            # ── 开始训练 ──
            logger.info(
                "开始训练：data=%s, epochs=%d", data_yaml, train_kwargs["epochs"]
            )
            results = model.train(**train_kwargs)

            # ── 训练完成 ──
            task.status = "completed"
            task.progress = 100
            task.current_epoch = config.get("epochs", 50)
            task.completed_at = datetime.now()
            db.commit()

            # ── 从 results.csv 补充最终指标 ──
            project_path = os.path.join(original_cwd, settings.TRAIN_OUTPUT_DIR)
            TrainingService._parse_final_results(db, task_id, task_uuid, config, project_path)

            logger.info("训练完成：task_id=%d, uuid=%s", task_id, task_uuid)

        except FileNotFoundError as e:
            logger.error("训练文件缺失：task_id=%d, error=%s", task_id, str(e))
            if task:
                task.status = "failed"
                task.error_message = str(e)
                db.commit()

        except Exception as e:
            logger.error(
                "训练异常：task_id=%d, error=%s", task_id, str(e), exc_info=True
            )
            if task:
                task.status = "failed"
                task.error_message = str(e)[:2000]
                db.commit()

        finally:
            # 恢复 data.yaml 原始内容
            if original_content and data_yaml:
                try:
                    with open(data_yaml, "w", encoding="utf-8") as f:
                        f.write(original_content)
                    logger.info("恢复 data.yaml 原始内容")
                except Exception:
                    pass

            # 恢复工作目录
            try:
                os.chdir(original_cwd)
            except Exception:
                pass

            with _running_lock:
                _running_tasks.pop(task_uuid, None)
            db.close()

    @staticmethod
    def _parse_final_results(db, task_id: int, task_uuid: str, config: dict, project_path: str = None):
        """训练完成后从 results.csv 解析最终指标并补充到数据库"""
        if project_path is None:
            project_path = settings.TRAIN_OUTPUT_DIR

        results_csv = os.path.join(
            project_path,
            f"task_{task_uuid}",
            "results.csv",
        )

        if not os.path.exists(results_csv):
            logger.warning("results.csv 不存在：%s", results_csv)
            return

        try:
            existing_epochs = set()
            existing = (
                db.query(TrainingMetric).filter(TrainingMetric.task_id == task_id).all()
            )
            for m in existing:
                existing_epochs.add(m.epoch)

            with open(results_csv, "r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    row = {k.strip(): v.strip() for k, v in row.items()}
                    epoch = int(row.get("epoch", 0)) + 1

                    if epoch in existing_epochs:
                        continue

                    metric = TrainingMetric(
                        task_id=task_id,
                        epoch=epoch,
                        box_loss=_safe_float(row.get("train/box_loss", "")),
                        cls_loss=_safe_float(row.get("train/cls_loss", "")),
                        dfl_loss=_safe_float(row.get("train/dfl_loss", "")),
                        precision=_safe_float(row.get("metrics/precision(B)", "")),
                        recall=_safe_float(row.get("metrics/recall(B)", "")),
                        map50=_safe_float(row.get("metrics/mAP50(B)", "")),
                        map50_95=_safe_float(row.get("metrics/mAP50-95(B)", "")),
                        lr=_safe_float(row.get("lr/pg0", "")),
                    )
                    db.add(metric)

            db.commit()
            logger.info("results.csv 解析完成，指标已补充到数据库")

        except Exception as e:
            logger.warning("results.csv 解析异常（不影响训练结果）：%s", str(e))
            db.rollback()

    @staticmethod
    def get_training_status(db, task_id: int) -> dict:
        """获取训练任务状态"""
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return {"error": "训练任务不存在"}

        latest_metric = (
            db.query(TrainingMetric)
            .filter(TrainingMetric.task_id == task_id)
            .order_by(TrainingMetric.epoch.desc())
            .first()
        )

        with _running_lock:
            is_running = task.task_uuid in _running_tasks

        return {
            "task": {
                "id": task.id,
                "task_uuid": task.task_uuid,
                "status": task.status,
                "model_name": task.model_name,
                "epochs": task.epochs,
                "current_epoch": task.current_epoch,
                "progress": task.progress,
                "device": task.device,
                "batch_size": task.batch_size,
                "img_size": task.img_size,
                "started_at": str(task.started_at) if task.started_at else None,
                "completed_at": str(task.completed_at) if task.completed_at else None,
                "error_message": task.error_message,
            },
            "latest_metric": {
                "epoch": latest_metric.epoch,
                "box_loss": latest_metric.box_loss,
                "cls_loss": latest_metric.cls_loss,
                "dfl_loss": latest_metric.dfl_loss,
                "precision": latest_metric.precision,
                "recall": latest_metric.recall,
                "map50": latest_metric.map50,
                "map50_95": latest_metric.map50_95,
                "lr": latest_metric.lr,
            }
            if latest_metric
            else None,
            "is_running": is_running,
        }

    @staticmethod
    def get_training_metrics(db, task_id: int) -> list:
        """获取训练任务的所有 epoch 指标"""
        metrics = (
            db.query(TrainingMetric)
            .filter(TrainingMetric.task_id == task_id)
            .order_by(TrainingMetric.epoch.asc())
            .all()
        )

        return [
            {
                "epoch": m.epoch,
                "box_loss": m.box_loss,
                "cls_loss": m.cls_loss,
                "dfl_loss": m.dfl_loss,
                "precision": m.precision,
                "recall": m.recall,
                "map50": m.map50,
                "map50_95": m.map50_95,
                "lr": m.lr,
            }
            for m in metrics
        ]

    @staticmethod
    def stop_training(db, task_id: int) -> dict:
        """停止正在运行的训练任务"""
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return {"error": "训练任务不存在"}

        if task.status != "running":
            return {"error": f"任务当前状态为 {task.status}，无法停止"}

        with _running_lock:
            model = _running_tasks.get(task.task_uuid)
            if model:
                try:
                    # Ultralytics 中 trainer.stop 是布尔标志位（不是方法），
                    # 置 True 后训练循环在当前 epoch 结束时检测到并退出（最多延迟 1 个 epoch）
                    trainer = getattr(model, "trainer", None)
                    if trainer is not None:
                        trainer.stop = True
                except Exception as e:
                    logger.warning("停止训练异常：%s", str(e))

        task.status = "cancelled"
        task.completed_at = datetime.now()
        db.commit()

        logger.info("训练任务已停止：task_id=%d", task_id)
        return {"message": "训练任务已停止", "task_id": task_id}

    @staticmethod
    def get_task_list(db, user_id: int = None, limit: int = 20) -> list:
        """获取训练任务列表"""
        query = db.query(TrainingTask)
        if user_id:
            query = query.filter(TrainingTask.user_id == user_id)

        tasks = query.order_by(TrainingTask.created_at.desc()).limit(limit).all()

        return [
            {
                "id": t.id,
                "task_uuid": t.task_uuid,
                "status": t.status,
                "model_name": t.model_name,
                "epochs": t.epochs,
                "current_epoch": t.current_epoch,
                "progress": t.progress,
                "device": t.device,
                "created_at": str(t.created_at),
                "started_at": str(t.started_at) if t.started_at else None,
                "completed_at": str(t.completed_at) if t.completed_at else None,
            }
            for t in tasks
        ]

    @staticmethod
    def validate_model(
        db,
        task_id: int,
        split: str = "val",
        conf: float = 0.001,
        iou: float = 0.6,
    ) -> dict:
        """
        对已完成训练的模型执行验证集评估

        流程：
          1. 查找训练任务对应的 best.pt 路径
          2. 加载模型并运行 model.val()
          3. 解析评估结果
          4. 将评估指标写入 ModelVersion 表
          5. 返回结构化评估报告
        """
        from ultralytics import YOLO

        # ── 查找训练任务 ──
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return {"error": "训练任务不存在"}

        if task.status != "completed":
            return {"error": f"训练任务状态为 {task.status}，只有已完成的任务才能评估"}

        # ── 定位 best.pt ──
        original_cwd = os.getcwd()
        weights_path = os.path.join(
            original_cwd,
            settings.TRAIN_OUTPUT_DIR,
            f"task_{task.task_uuid}",
            "weights",
            "best.pt",
        )

        if not os.path.exists(weights_path):
            return {"error": f"模型权重不存在: {weights_path}"}

        # ── 定位 data.yaml ──
        data_yaml = task.data_yaml
        if not data_yaml or not os.path.exists(data_yaml):
            # 尝试在数据集目录下查找
            if task.dataset_path:
                data_yaml = os.path.join(task.dataset_path, "data.yaml")
            if not os.path.exists(data_yaml):
                return {"error": "data.yaml 不存在"}

        logger.info(
            "开始模型评估: task_id=%d, weights=%s, split=%s",
            task_id, weights_path, split,
        )

        try:
            # ── 加载模型并评估 ──
            model = YOLO(weights_path)
            results = model.val(
                data=data_yaml,
                split=split,
                conf=conf,
                iou=iou,
                imgsz=task.img_size,
                device="cpu",
                save_json=True,
                plots=True,
                project=os.path.join(
                    original_cwd, settings.TRAIN_OUTPUT_DIR
                ),
                name=f"task_{task.task_uuid}",
                exist_ok=True,
                verbose=False,
            )

            # ── 解析评估结果 ──
            overall = {
                "precision": float(results.box.mp),
                "recall": float(results.box.mr),
                "map50": float(results.box.map50),
                "map50_95": float(results.box.map),
            }

            per_class = {}
            if results.box.ap is not None and len(results.box.ap) > 0:
                for i, ap50 in enumerate(results.box.ap50):
                    class_name = model.names.get(i, f"class_{i}")
                    ap50_95 = results.box.ap[i] if i < len(results.box.ap) else 0.0
                    per_class[class_name] = {
                        "ap50": round(float(ap50), 4),
                        "ap50_95": round(float(ap50_95), 4),
                    }

            report = {
                "task_id": task_id,
                "task_uuid": task.task_uuid,
                "split": split,
                "overall": overall,
                "per_class": per_class,
            }

            # ── 更新或创建 ModelVersion 记录 ──
            from app.entity.db_models import ModelVersion, DetectionScene

            scene = (
                db.query(DetectionScene)
                .filter(DetectionScene.id == task.scene_id)
                .first()
            )

            # 查找已有版本或创建新版本
            model_version = (
                db.query(ModelVersion)
                .filter(ModelVersion.training_task_id == task_id)
                .first()
            )

            if not model_version:
                # 生成版本号
                existing_count = (
                    db.query(ModelVersion)
                    .filter(ModelVersion.scene_id == task.scene_id)
                    .count()
                )
                version = f"v{existing_count + 1}.0.0"

                model_version = ModelVersion(
                    scene_id=task.scene_id,
                    training_task_id=task_id,
                    version=version,
                    model_name=f"{task.model_name}_{scene.name}_{version}",
                    model_type=task.model_name,
                    model_path=weights_path,
                    map50=overall["map50"],
                    map50_95=overall["map50_95"],
                    precision=overall["precision"],
                    recall=overall["recall"],
                    per_class_ap=per_class,
                    file_size=os.path.getsize(weights_path),
                    description=f"训练任务 {task.task_uuid} 自动产出",
                )
                db.add(model_version)
            else:
                # 更新已有版本的评估指标
                model_version.map50 = overall["map50"]
                model_version.map50_95 = overall["map50_95"]
                model_version.precision = overall["precision"]
                model_version.recall = overall["recall"]
                model_version.per_class_ap = per_class

            db.commit()
            report["model_version_id"] = model_version.id
            report["model_version"] = model_version.version

            logger.info(
                "模型评估完成: task_id=%d, mAP50=%.4f, mAP50-95=%.4f",
                task_id, overall["map50"], overall["map50_95"],
            )

            return report

        except Exception as e:
            logger.error("模型评估异常: task_id=%d, error=%s", task_id, str(e), exc_info=True)
            return {"error": f"评估失败: {str(e)}"}

    @staticmethod
    def export_model(
        db,
        task_id: int,
        version: str = None,
        description: str = None,
        set_default: bool = False,
        upload_minio: bool = True,
    ) -> dict:
        """
        导出训练好的模型为正式版本

        流程：
          1. 复制 best.pt 到 models/ 目录
          2. 运行评估获取最终指标
          3. 保存评估报告 JSON
          4. 创建 ModelVersion 记录
          5. 可选上传到 MinIO
        """
        import shutil
        from app.entity.db_models import ModelVersion, DetectionScene

        # ── 查找训练任务 ──
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return {"error": "训练任务不存在"}

        if task.status != "completed":
            return {"error": f"训练任务状态为 {task.status}，只有已完成的任务才能导出"}

        # ── 定位 best.pt ──
        original_cwd = os.getcwd()
        weights_path = os.path.join(
            original_cwd,
            settings.TRAIN_OUTPUT_DIR,
            f"task_{task.task_uuid}",
            "weights",
            "best.pt",
        )

        if not os.path.exists(weights_path):
            return {"error": f"模型权重不存在: {weights_path}"}

        # ── 获取场景信息 ──
        scene = (
            db.query(DetectionScene)
            .filter(DetectionScene.id == task.scene_id)
            .first()
        )
        if not scene:
            return {"error": "关联场景不存在"}

        # ── 生成版本号 ──
        if not version:
            existing_count = (
                db.query(ModelVersion)
                .filter(ModelVersion.scene_id == task.scene_id)
                .count()
            )
            version = f"v{existing_count + 1}.0.0"

        # ── 创建导出目录 ──
        export_dir = os.path.join(
            original_cwd,
            "models",
            f"{scene.name}_{version}",
        )
        os.makedirs(export_dir, exist_ok=True)

        # ── 复制模型文件 ──
        exported_weight = os.path.join(export_dir, "best.pt")
        shutil.copy2(weights_path, exported_weight)
        logger.info("模型文件已复制: %s -> %s", weights_path, exported_weight)

        # ── 复制评估图表（如果存在）──
        task_output_dir = os.path.join(
            original_cwd,
            settings.TRAIN_OUTPUT_DIR,
            f"task_{task.task_uuid}",
        )
        eval_plots = [
            "confusion_matrix.png",
            "PR_curve.png",
            "F1_curve.png",
            "results.png",
        ]
        for plot_name in eval_plots:
            src = os.path.join(task_output_dir, plot_name)
            if os.path.exists(src):
                shutil.copy2(src, os.path.join(export_dir, plot_name))

        # ── 运行评估（获取最终指标）──
        eval_result = TrainingService.validate_model(db, task_id, split="val")
        overall = eval_result.get("overall", {})
        per_class = eval_result.get("per_class", {})

        # ── 保存评估报告 JSON ──
        report = {
            "version": version,
            "model_name": task.model_name,
            "scene": scene.name,
            "training_task": task.task_uuid,
            "evaluation": {
                "split": "val",
                "overall": overall,
                "per_class": per_class,
            },
            "training_config": {
                "epochs": task.epochs,
                "batch_size": task.batch_size,
                "img_size": task.img_size,
                "optimizer": task.optimizer,
                "lr0": task.lr0,
                "device": task.device,
            },
            "exported_at": datetime.now().isoformat(),
        }
        report_path = os.path.join(export_dir, "eval_report.json")
        with open(report_path, "w", encoding="utf-8") as f:
            json.dump(report, f, indent=2, ensure_ascii=False)

        # ── 上传到 MinIO ──
        minio_url = None
        if upload_minio:
            try:
                from app.storage.minio_client import MinIOClient
                minio_client = MinIOClient()
                object_name = f"models/{scene.name}/{version}/best.pt"
                minio_url = minio_client.upload_file(object_name, exported_weight)
                logger.info("模型已上传 MinIO: %s", minio_url)
            except Exception as e:
                logger.warning("MinIO 上传失败（不影响导出）: %s", str(e))

        # ── 创建/更新 ModelVersion 记录 ──
        model_version = (
            db.query(ModelVersion)
            .filter(ModelVersion.training_task_id == task_id)
            .first()
        )

        if model_version:
            # 更新已有记录
            model_version.version = version
            model_version.model_path = exported_weight
            model_version.minio_url = minio_url
            model_version.map50 = overall.get("map50")
            model_version.map50_95 = overall.get("map50_95")
            model_version.precision = overall.get("precision")
            model_version.recall = overall.get("recall")
            model_version.per_class_ap = per_class
            model_version.file_size = os.path.getsize(exported_weight)
            model_version.description = description or f"训练任务 {task.task_uuid} 导出"
        else:
            model_version = ModelVersion(
                scene_id=task.scene_id,
                training_task_id=task_id,
                version=version,
                model_name=f"{task.model_name}_{scene.name}_{version}",
                model_type=task.model_name,
                model_path=exported_weight,
                minio_url=minio_url,
                map50=overall.get("map50"),
                map50_95=overall.get("map50_95"),
                precision=overall.get("precision"),
                recall=overall.get("recall"),
                per_class_ap=per_class,
                file_size=os.path.getsize(exported_weight),
                description=description or f"训练任务 {task.task_uuid} 导出",
            )
            db.add(model_version)

        # ── 设置默认模型 ──
        if set_default:
            # 取消该场景其他版本的默认标记
            db.query(ModelVersion).filter(
                ModelVersion.scene_id == task.scene_id,
                ModelVersion.id != model_version.id,
            ).update({"is_default": False})
            model_version.is_default = True

        db.commit()
        db.refresh(model_version)

        logger.info(
            "模型导出完成: scene=%s, version=%s, mAP50=%.4f",
            scene.name, version, overall.get("map50", 0),
        )

        return {
            "model_version_id": model_version.id,
            "version": version,
            "model_name": model_version.model_name,
            "model_path": exported_weight,
            "export_dir": export_dir,
            "minio_url": minio_url,
            "file_size": model_version.file_size,
            "evaluation": {
                "map50": overall.get("map50"),
                "map50_95": overall.get("map50_95"),
                "precision": overall.get("precision"),
                "recall": overall.get("recall"),
                "per_class": per_class,
            },
            "is_default": model_version.is_default,
            "message": f"模型已导出为版本 {version}",
        }

    @staticmethod
    def get_model_download_path(db, task_id: int) -> dict:
        """
        获取训练任务的模型权重文件路径（用于下载）
        """
        task = db.query(TrainingTask).filter(TrainingTask.id == task_id).first()
        if not task:
            return {"error": "训练任务不存在"}

        original_cwd = os.getcwd()

        # 优先返回 best.pt
        best_path = os.path.join(
            original_cwd,
            settings.TRAIN_OUTPUT_DIR,
            f"task_{task.task_uuid}",
            "weights",
            "best.pt",
        )

        if os.path.exists(best_path):
            return {
                "file_path": best_path,
                "filename": f"best_{task.task_uuid}.pt",
                "file_size": os.path.getsize(best_path),
            }

        # 备选 last.pt
        last_path = os.path.join(
            original_cwd,
            settings.TRAIN_OUTPUT_DIR,
            f"task_{task.task_uuid}",
            "weights",
            "last.pt",
        )

        if os.path.exists(last_path):
            return {
                "file_path": last_path,
                "filename": f"last_{task.task_uuid}.pt",
                "file_size": os.path.getsize(last_path),
            }

        return {"error": "模型权重文件不存在"}


def _safe_float(value) -> float:
    """安全地将字符串转换为浮点数，失败时返回 None"""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


# 全局单例
training_service = TrainingService()
