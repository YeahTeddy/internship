"""
用户与权限查询 API 路由
"""

from typing import Optional

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.api.auth import get_current_user
from app.core.logger import get_logger
from app.database.session import SessionLocal, get_db
from app.services.user_service import user_service

logger = get_logger(__name__)
router = APIRouter(prefix="/api/user", tags=["用户管理"])


@router.get("/list", summary="用户列表")
async def list_users(
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    keyword: Optional[str] = Query(None, description="用户名/邮箱关键词"),
    db: Session = Depends(get_db),
    _current_user=Depends(get_current_user),
):
    return user_service.list_users(db=db, page=page, page_size=page_size, keyword=keyword)


@router.get("/roles", summary="获取所有角色")
async def list_roles(db: Session = Depends(get_db), _current_user=Depends(get_current_user)):
    roles = user_service.list_roles(db)
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


@router.get("/{user_id}/roles", summary="用户角色列表")
async def get_user_roles(user_id: int, _current_user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        from app.entity.db_models import Role, UserRole
        roles = db.query(Role).join(UserRole, UserRole.role_id == Role.id).filter(UserRole.user_id == user_id).all()
        return {"user_id": user_id, "roles": [{"id": r.id, "name": r.name, "display_name": r.display_name} for r in roles]}
    finally:
        db.close()


from pydantic import BaseModel

class RoleIdsRequest(BaseModel):
    role_ids: list[int] = []

@router.post("/{user_id}/roles", summary="分配角色")
async def assign_role(user_id: int, body: RoleIdsRequest, _current_user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        from app.entity.db_models import UserRole
        db.query(UserRole).filter(UserRole.user_id == user_id).delete()
        for rid in body.role_ids:
            db.add(UserRole(user_id=user_id, role_id=rid))
        db.commit()
        return {"message": f"已为用户分配 {len(body.role_ids)} 个角色"}
    finally:
        db.close()


@router.delete("/{user_id}/roles", summary="移除用户角色")
async def remove_user_role(user_id: int, role_id: int, _current_user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        from app.entity.db_models import UserRole
        db.query(UserRole).filter(UserRole.user_id == user_id, UserRole.role_id == role_id).delete()
        db.commit()
        return {"message": "角色已移除"}
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
