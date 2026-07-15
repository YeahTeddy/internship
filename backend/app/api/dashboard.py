"""
数据看板 API 路由 — 聚合统计查询接口
"""

from fastapi import APIRouter, Depends, Query

from app.api.auth import get_current_user
from app.core.logger import get_logger
from app.services.dashboard_service import dashboard_service

logger = get_logger(__name__)
router = APIRouter(prefix="/api/dashboard", tags=["数据看板"])


@router.get("/statistics", summary="汇总统计")
async def get_statistics(
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
    current_user=Depends(get_current_user),
):
    return dashboard_service.get_statistics(user_id=current_user.id, days=days)


@router.get("/trend", summary="每日检测趋势")
async def get_trend(
    days: int = Query(30, ge=1, le=365, description="统计最近 N 天"),
    current_user=Depends(get_current_user),
):
    return dashboard_service.get_trend(user_id=current_user.id, days=days)


@router.get("/class-dist", summary="类别分布统计")
async def get_class_distribution(
    days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_user),
):
    return dashboard_service.get_class_distribution(user_id=current_user.id, days=days)


@router.get("/scene-dist", summary="场景分布统计")
async def get_scene_distribution(
    days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_user),
):
    return dashboard_service.get_scene_distribution(user_id=current_user.id, days=days)


@router.get("/type-dist", summary="任务类型分布统计")
async def get_type_distribution(
    days: int = Query(30, ge=1, le=365),
    current_user=Depends(get_current_user),
):
    return dashboard_service.get_type_distribution(user_id=current_user.id, days=days)
