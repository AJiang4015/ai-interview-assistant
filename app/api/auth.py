from fastapi import APIRouter, HTTPException, Depends, Header

from app.api.schemas import RegisterRequest, LoginRequest, TokenResponse, UserResponse
from app.services.auth_service import AuthService
from app.utils.logger import get_logger

logger = get_logger(__name__)

router = APIRouter(prefix="/api/auth", tags=["auth"])


def _get_auth() -> AuthService:
    from app.main import auth_service
    if auth_service is None:
        raise HTTPException(status_code=503, detail="认证服务未初始化")
    return auth_service


async def get_current_user(
    authorization: str | None = Header(default=None),
) -> dict:
    """FastAPI dependency to get current user from JWT token."""
    if not authorization:
        raise HTTPException(status_code=401, detail="未登录")

    parts = authorization.split()
    if len(parts) == 2 and parts[0].lower() == "bearer":
        token = parts[1]
    elif len(parts) == 1:
        token = parts[0]
    else:
        raise HTTPException(status_code=401, detail="无效的Authorization头格式")

    auth = _get_auth()
    user = await auth.get_current_user(token)
    if not user:
        raise HTTPException(status_code=401, detail="token已过期或无效")

    return user


@router.post("/register", response_model=TokenResponse)
async def register(request: RegisterRequest):
    """Register a new user and return token."""
    auth = _get_auth()
    try:
        user = await auth.register(
            username=request.username,
            password=request.password,
            display_name=request.display_name,
        )
        token = auth.create_token(request.username)
        return TokenResponse(token=token, user=user)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.exception(f"Register failed: {e}")
        raise HTTPException(status_code=500, detail="注册失败")


@router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest):
    """Login and return JWT token."""
    auth = _get_auth()
    try:
        result = await auth.login(request.username, request.password)
        return TokenResponse(token=result["token"], user=result["user"])
    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        logger.exception(f"Login failed: {e}")
        raise HTTPException(status_code=500, detail="登录失败")


@router.get("/me", response_model=UserResponse)
async def get_me(current_user: dict = Depends(get_current_user)):
    """Get current user info."""
    return UserResponse(**current_user)


@router.post("/logout")
async def logout(current_user: dict = Depends(get_current_user)):
    """Logout (client-side, just return success)."""
    return {"message": "登出成功"}


@router.get("/users", response_model=list[UserResponse])
async def list_users(current_user: dict = Depends(get_current_user)):
    """List all users."""
    from app.main import user_store
    if user_store is None:
        raise HTTPException(status_code=503, detail="用户存储未初始化")
    users = await user_store.list_users()
    return [UserResponse(**u) for u in users]