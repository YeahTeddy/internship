"""
用户服务层
处理用户注册、登录、鉴权等业务逻辑
"""

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.core.security import create_access_token, hash_password, verify_password
from app.entity.db_models import User


class UserService:
    """用户服务"""

    @staticmethod
    def register(db: Session, username: str, email: str, password: str) -> User:
        """
        用户注册

        Args:
            db: 数据库会话
            username: 用户名
            email: 邮箱
            password: 明文密码

        Returns:
            新创建的用户对象

        Raises:
            HTTPException: 用户名或邮箱已存在
        """
        # 检查用户名是否已存在
        existing_user = db.query(User).filter(User.username == username).first()
        if existing_user:
            raise HTTPException(status_code=400, detail="用户名已存在")

        # 检查邮箱是否已存在
        existing_email = db.query(User).filter(User.email == email).first()
        if existing_email:
            raise HTTPException(status_code=400, detail="邮箱已被注册")

        # 创建新用户
        new_user = User(
            username=username,
            email=email,
            hashed_password=hash_password(password),
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        return new_user

    @staticmethod
    def login(db: Session, username: str, password: str) -> User:
        """
        用户登录

        Args:
            db: 数据库会话
            username: 用户名
            password: 明文密码

        Returns:
            登录成功的用户对象

        Raises:
            HTTPException: 用户名或密码错误
        """
        user = db.query(User).filter(User.username == username).first()
        if not user:
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        if not verify_password(password, user.hashed_password):
            raise HTTPException(status_code=401, detail="用户名或密码错误")

        return user

    @staticmethod
    def create_access_token_for_user(user: User) -> str:
        """为用户生成 JWT Token"""
        return create_access_token(data={"sub": str(user.id)})

    @staticmethod
    def get_user_roles(db: Session, user: User) -> list[str]:
        """获取用户的角色标识列表"""
        return [ur.role.name for ur in user.user_roles]

    @staticmethod
    def get_user_by_id(db: Session, user_id: int) -> User:
        """根据 ID 获取用户"""
        user = db.query(User).filter(User.id == user_id).first()
        if not user:
            raise HTTPException(status_code=404, detail="用户不存在")
        return user

    @staticmethod
    def list_users(db: Session, page: int = 1, page_size: int = 20, keyword: str = None) -> dict:
        """分页查询用户列表"""
        from sqlalchemy import desc
        from app.entity.db_models import Role, UserRole

        query = db.query(User)
        if keyword:
            query = query.filter(
                User.username.contains(keyword) | User.email.contains(keyword)
            )

        total = query.count()
        users = query.order_by(desc(User.id)).offset((page - 1) * page_size).limit(page_size).all()

        items = []
        for u in users:
            roles = db.query(Role).join(UserRole, UserRole.role_id == Role.id).filter(UserRole.user_id == u.id).all()
            items.append({
                "id": u.id,
                "username": u.username,
                "email": u.email,
                "phone": u.phone,
                "is_active": u.is_active,
                "is_superuser": u.is_superuser,
                "roles": [{"id": r.id, "name": r.name, "display_name": r.display_name} for r in roles],
            })

        return {"items": items, "total": total}

    @staticmethod
    def list_roles(db: Session) -> list[dict]:
        """获取所有角色"""
        from app.entity.db_models import Role
        roles = db.query(Role).all()
        return [{"id": r.id, "name": r.name, "display_name": r.display_name} for r in roles]


# 全局单例
user_service = UserService()
