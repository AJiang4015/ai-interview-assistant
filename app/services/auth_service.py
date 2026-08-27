from datetime import datetime, timezone, timedelta
from typing import Optional

import jwt
from passlib.context import CryptContext

from app.config import settings
from app.storage.user_store import UserStore
from app.utils.logger import get_logger

logger = get_logger(__name__)

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")


class AuthService:
    def __init__(self, user_store: UserStore):
        self.user_store = user_store
        # JWT 签名密钥强制从配置读取（由 .env 提供），缺失时 Settings 解析即失败，杜绝硬编码默认值
        self.jwt_secret = settings.jwt_secret
        self.jwt_algorithm = "HS256"
        self.jwt_expire_hours = 24

    def hash_password(self, password: str) -> str:
        return pwd_context.hash(password)

    def verify_password(self, plain_password: str, hashed_password: str) -> bool:
        return pwd_context.verify(plain_password, hashed_password)

    def create_token(self, username: str) -> str:
        now = datetime.now(timezone.utc)
        payload = {
            "sub": username,
            "iat": now,
            "exp": now + timedelta(hours=self.jwt_expire_hours),
        }
        token = jwt.encode(payload, self.jwt_secret, algorithm=self.jwt_algorithm)
        return token

    def verify_token(self, token: str) -> Optional[str]:
        try:
            payload = jwt.decode(
                token, self.jwt_secret, algorithms=[self.jwt_algorithm]
            )
            username = payload.get("sub")
            if not username:
                return None
            return username
        except jwt.ExpiredSignatureError:
            logger.warning("Token expired")
            return None
        except jwt.InvalidTokenError as e:
            logger.warning(f"Invalid token: {e}")
            return None

    async def register(
        self, username: str, password: str, display_name: str | None = None
    ) -> dict:
        if len(username) < 3:
            raise ValueError("用户名至少3个字符")
        if len(password) < 6:
            raise ValueError("密码至少6个字符")

        if await self.user_store.user_exists(username):
            raise ValueError(f"用户名 '{username}' 已被占用")

        password_hash = self.hash_password(password)
        user = await self.user_store.create_user(username, password_hash, display_name)

        logger.info(f"User registered: {username}")
        return user

    async def login(self, username: str, password: str) -> dict:
        user = await self.user_store.get_user_with_password(username)

        if not user:
            raise ValueError("用户名或密码错误")

        if not self.verify_password(password, user["password_hash"]):
            raise ValueError("用户名或密码错误")

        token = self.create_token(username)
        user_data = {
            "username": user["username"],
            "display_name": user.get("display_name", user["username"]),
        }

        logger.info(f"User logged in: {username}")
        return {"token": token, "user": user_data}

    async def get_current_user(self, token: str) -> Optional[dict]:
        username = self.verify_token(token)
        if not username:
            return None

        user = await self.user_store.get_user(username)
        return user