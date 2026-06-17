"""
认证 API
"""
from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session
from models.user import UserCreate, UserLogin, Token, UserResponse, UserUpdate
from services.auth_service import create_user, login_user, get_user_by_id, update_user, verify_token
from database import get_db

router = APIRouter(prefix="/auth", tags=["认证"])
security = HTTPBearer()


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db)
) -> dict:
    """
    从JWT token获取当前用户
    
    用于保护需要认证的API端点
    """
    token = credentials.credentials
    
    token_data = verify_token(token)
    
    if token_data is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭证",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    return {"user_id": token_data.user_id, "username": token_data.username}


@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
async def register(user: UserCreate, db: Session = Depends(get_db)):
    """
    用户注册
    
    - **username**: 用户名（3-50字符）
    - **password**: 密码（至少6字符）
    - **email**: 邮箱（可选）
    """
    try:
        db_user = create_user(db, user)
        return UserResponse(
            id=db_user.id,
            username=db_user.username,
            email=db_user.email,
            created_at=db_user.created_at
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"注册失败: {str(e)}"
        )


@router.post("/login", response_model=Token)
async def login(user_login: UserLogin, db: Session = Depends(get_db)):
    """
    用户登录
    
    - **username**: 用户名
    - **password**: 密码
    
    返回访问令牌
    """
    try:
        token = login_user(db, user_login)
        return token
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(e),
            headers={"WWW-Authenticate": "Bearer"},
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"登录失败: {str(e)}"
        )


@router.get("/test")
async def test_auth():
    """测试认证 API"""
    return {"message": "认证 API 正常运行"}


@router.get("/user/{user_id}", response_model=UserResponse)
async def get_user(user_id: int, db: Session = Depends(get_db)):
    """
    获取用户信息
    
    - **user_id**: 用户ID
    """
    try:
        user = get_user_by_id(db, user_id)
        if not user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="用户不存在"
            )
        return UserResponse(
            id=user.id,
            username=user.username,
            email=user.email,
            created_at=user.created_at
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"获取用户信息失败: {str(e)}"
        )


@router.put("/user/{user_id}", response_model=UserResponse)
async def update_user_info(user_id: int, user_update: UserUpdate, db: Session = Depends(get_db)):
    """
    更新用户信息
    
    - **user_id**: 用户ID
    - **username**: 新用户名（可选）
    - **email**: 新邮箱（可选）
    - **current_password**: 当前密码（修改密码时必需）
    - **new_password**: 新密码（可选）
    """
    try:
        updated_user = update_user(db, user_id, user_update)
        return UserResponse(
            id=updated_user.id,
            username=updated_user.username,
            email=updated_user.email,
            created_at=updated_user.created_at
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"更新用户信息失败: {str(e)}"
        )
