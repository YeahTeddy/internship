from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import settings
from app.api.auth import router as auth_router
from app.api.chat import router as chat_router
from app.api.dashboard import router as dashboard_router
from app.api.detection import router as detection_router
from app.api.history import router as history_router
from app.api.training import router as training_router
from app.api.user import router as user_router
from app.core.exceptions import register_exception_handlers
from app.middleware.rate_limiter import RateLimiterMiddleware
from app.middleware.request_logger import RequestLogMiddleware
from app.api.health import router as health_router


def init_minio():
    """初始化 MinIO 存储桶"""
    from app.storage.minio_client import MinIOClient
    try:
        minio_client = MinIOClient()
        print(f"MinIO 存储桶 '{minio_client.bucket_name}' 初始化完成")
    except Exception as e:
        print(f"MinIO 初始化失败: {e}")


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """应用生命周期管理"""
    # 启动时执行
    print("正在初始化服务...")
    init_minio()
    yield
    # 关闭时执行（如果需要）
    print("服务已关闭")


# 创建 FastAPI 实例
app = FastAPI(
    title="RSOD Agent Platform",
    version="0.1.0",
    description="基于 YOLOv11 的目标检测智能体平台 API",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

# ── 注册全局异常处理器 ─────────────────────────────────
register_exception_handlers(app)

# ── CORS 中间件配置 ──────────────────────────────────
# 允许前端跨域请求后端 API
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins_list,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 2. 请求日志中间件（在 CORS 之后执行）
app.add_middleware(RequestLogMiddleware)

# 3. 速率限制中间件
app.add_middleware(RateLimiterMiddleware)

# ── 注册路由 ─────────────────────────────────────────
app.include_router(auth_router)
app.include_router(health_router)
app.include_router(training_router)
app.include_router(chat_router)       # Day 8: 智能对话 SSE
app.include_router(detection_router)  # Day 8: 快捷检测
app.include_router(dashboard_router)  # Day 10: 数据看板
app.include_router(history_router)    # Day 10: 检测历史
app.include_router(user_router)       # Day 10: 用户管理


@app.get("/")
def root():
    return {
        "message": "欢迎使用 RSOD Agent Platform",
        "version": "0.1.0",
        "docs": "/docs",
        "redoc": "/redoc",
    }


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
