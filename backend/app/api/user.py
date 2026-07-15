"""
用户与权限查询 API 路由
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query

from app.api.auth import get_current_user
from app.core.logger import get_logger
from app.services.user_service import user_service

logger = get_logger(__name__)
router = APIRouter(prefix="/api/user", tags=["用户管理"])


@router.get("/list", summary="用户列表")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="用户名/邮箱关键词"),
    _current_user=Depends(get_current_user),
):
    return user_service.list_users(page=page, page_size=page_size, keyword=keyword)


@router.get("/roles", summary="获取所有角色")
async def list_roles(_current_user=Depends(get_current_user)):
    roles = user_service.list_roles()
    return {"roles": roles}


@router.put("/profile", summary="更新个人信息")
async def update_profile(
    phone: Optional[str] = None,
    avatar: Optional[str] = None,
    email: Optional[str] = None,
    current_user=Depends(get_current_user),
):
    from app.database.session import SessionLocal
    db = SessionLocal()
    try:
        user = db.query(type(current_user)).filter(type(current_user).id == current_user.id).first()
        if phone is not None: user.phone = phone
        if avatar is not None: user.avatar = avatar
        if email is not None: user.email = email
        db.commit()
        return {"message": "个人信息已更新", "user": {"id": user.id, "username": user.username, "email": user.email, "phone": user.phone}}
    finally:
        db.close()


@router.put("/password", summary="修改密码")
async def change_password(
    old_password: str,
    new_password: str,
    current_user=Depends(get_current_user),
):
    from app.core.security import verify_password, hash_password
    from app.database.session import SessionLocal
    db = SessionLocal()
    try:
        user = db.query(type(current_user)).filter(type(current_user).id == current_user.id).first()
        if not verify_password(old_password, user.hashed_password):
            return {"error": "旧密码错误"}
        user.hashed_password = hash_password(new_password)
        db.commit()
        return {"message": "密码修改成功"}
    finally:
        db.close()
