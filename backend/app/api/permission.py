"""
权限管理 API 路由

接口列表：
  - GET /api/permission/list  所有权限列表
"""

from fastapi import APIRouter, Depends

from app.api.auth import get_current_user
from app.database.session import SessionLocal
from app.entity.db_models import Permission

router = APIRouter(prefix="/api/permission", tags=["权限管理"])


@router.get("/list", summary="权限列表")
async def list_permissions(_current_user=Depends(get_current_user)):
    db = SessionLocal()
    try:
        perms = db.query(Permission).all()
        return {"permissions": [
            {"id": p.id, "code": p.code, "name": p.name, "module": p.module, "description": p.description}
            for p in perms
        ]}
    finally:
        db.close()
