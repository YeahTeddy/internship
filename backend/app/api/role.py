"""
角色管理 API 路由

接口列表：
  - GET    /api/role/list          角色列表
  - POST   /api/role               创建角色
  - PUT    /api/role/{role_id}     编辑角色
  - DELETE /api/role/{role_id}     删除角色
  - POST   /api/role/{role_id}/permissions  分配权限
  - DELETE /api/role/{role_id}/permissions    移除权限
  - GET    /api/role/{role_id}/permissions    角色权限列表
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException

from app.api.auth import get_current_user
from app.core.logger import get_logger
from app.database.session import SessionLocal
from app.entity.db_models import Permission, Role, RolePermission
from pydantic import BaseModel

logger = get_logger(__name__)
router = APIRouter(prefix="/api/role", tags=["角色管理"])


class PermissionIdsRequest(BaseModel):
    permission_ids: list[int] = []


@router.get("/list", summary="角色列表")
async def list_roles(_current_user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        roles = db.query(Role).all()
        return {"roles": [
            {
                "id": r.id,
                "name": r.name,
                "display_name": r.display_name,
                "description": r.description,
                "is_system": r.is_system,
            }
            for r in roles
        ]}
    finally:
        db.close()


@router.post("", summary="创建角色")
async def create_role(
    name: str,
    display_name: str,
    description: str = None,
    current_user=Depends(get_current_user),
):
    db = SessionLocal()
    try:
        existing = db.query(Role).filter(Role.name == name).first()
        if existing:
            raise HTTPException(status_code=400, detail="角色名已存在")

        role = Role(name=name, display_name=display_name, description=description, is_system=False)
        db.add(role)
        db.commit()
        db.refresh(role)
        logger.info("用户 %s 创建角色: %s", current_user.username, name)
        return {"id": role.id, "name": role.name, "display_name": role.display_name}
    finally:
        db.close()


@router.put("/{role_id}", summary="编辑角色")
async def update_role(
    role_id: int,
    display_name: str = None,
    description: str = None,
    current_user=Depends(get_current_user),
):
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")
        if role.is_system:
            raise HTTPException(status_code=400, detail="系统角色不可修改")

        if display_name: role.display_name = display_name
        if description is not None: role.description = description
        db.commit()
        return {"message": "角色已更新"}
    finally:
        db.close()


@router.delete("/{role_id}", summary="删除角色")
async def delete_role(role_id: int, current_user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")
        if role.is_system:
            raise HTTPException(status_code=400, detail="系统角色不可删除")
        db.delete(role)
        db.commit()
        return {"message": f"角色 {role.name} 已删除"}
    finally:
        db.close()


@router.get("/{role_id}/permissions", summary="角色权限列表")
async def get_role_permissions(role_id: int, _current_user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")

        perms = db.query(Permission).join(
            RolePermission, RolePermission.permission_id == Permission.id
        ).filter(RolePermission.role_id == role_id).all()

        return {"role": role.name, "permissions": [{"id": p.id, "code": p.code, "name": p.name, "module": p.module} for p in perms]}
    finally:
        db.close()


@router.post("/{role_id}/permissions", summary="分配权限")
async def assign_permissions(
    role_id: int,
    body: PermissionIdsRequest,
    current_user=Depends(get_current_user),
):
    db = SessionLocal()
    try:
        role = db.query(Role).filter(Role.id == role_id).first()
        if not role:
            raise HTTPException(status_code=404, detail="角色不存在")

        db.query(RolePermission).filter(RolePermission.role_id == role_id).delete()
        for pid in body.permission_ids:
            db.add(RolePermission(role_id=role_id, permission_id=pid))
        db.commit()
        return {"message": f"已为角色 {role.name} 分配 {len(body.permission_ids)} 个权限"}
    finally:
        db.close()


@router.delete("/{role_id}/permissions", summary="移除权限")
async def remove_permission(
    role_id: int,
    permission_id: int,
    current_user=Depends(get_current_user),
):
    db = SessionLocal()
    try:
        db.query(RolePermission).filter(
            RolePermission.role_id == role_id,
            RolePermission.permission_id == permission_id,
        ).delete()
        db.commit()
        return {"message": "权限已移除"}
    finally:
        db.close()
