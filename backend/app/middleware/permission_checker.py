"""
权限校验中间件

使用方式：
    from app.middleware.permission_checker import require_permission

    @router.get("/training/tasks")
    async def list_tasks(current_user=Depends(require_permission("history:view"))):
        ...
"""

from fastapi import Depends, HTTPException

from app.api.auth import get_current_user
from app.database.session import SessionLocal


def require_permission(permission_code: str):
    """权限校验依赖注入 — 在 API 路由中使用"""

    async def checker(current_user=Depends(get_current_user)):
        # 超级管理员跳过权限检查
        if current_user.is_superuser:
            return current_user

        db = SessionLocal()
        try:
            from app.entity.db_models import Permission, RolePermission, UserRole

            has_perm = (
                db.query(Permission)
                .join(RolePermission, RolePermission.permission_id == Permission.id)
                .join(UserRole, UserRole.role_id == RolePermission.role_id)
                .filter(
                    UserRole.user_id == current_user.id,
                    Permission.code == permission_code,
                )
                .first()
            )

            if not has_perm:
                raise HTTPException(
                    status_code=403,
                    detail=f"无权执行此操作，需要权限: {permission_code}",
                )
            return current_user
        finally:
            db.close()

    return checker
