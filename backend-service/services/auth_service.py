"""
认证服务
"""
from passlib.context import CryptContext
from jose import JWTError, jwt
from datetime import datetime, timedelta
from typing import Optional
from sqlalchemy.orm import Session
from models.user import UserCreate, UserLogin, Token, TokenData
from database import User

# 密码加密上下文
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# JWT 配置
SECRET_KEY = "your-secret-key-change-this-in-production"  # 生产环境中应该使用环境变量
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 30


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """验证密码"""
    return pwd_context.verify(plain_password, hashed_password)


def get_password_hash(password: str) -> str:
    """获取密码哈希"""
    return pwd_context.hash(password)


def create_access_token(data: dict, expires_delta: Optional[timedelta] = None) -> str:
    """创建访问令牌"""
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=15)
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt


def verify_token(token: str) -> Optional[TokenData]:
    """验证令牌"""
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        user_id: int = payload.get("user_id")
        if username is None or user_id is None:
            return None
        return TokenData(username=username, user_id=user_id)
    except JWTError:
        return None


def get_user_by_username(db: Session, username: str) -> Optional[User]:
    """根据用户名获取用户"""
    return db.query(User).filter(User.username == username).first()


def get_user_by_email(db: Session, email: str) -> Optional[User]:
    """根据邮箱获取用户"""
    return db.query(User).filter(User.email == email).first()


def authenticate_user(db: Session, username: str, password: str) -> Optional[User]:
    """认证用户"""
    user = get_user_by_username(db, username)
    if not user:
        return None
    if not verify_password(password, user.hashed_password):
        return None
    return user


def create_user(db: Session, user: UserCreate) -> User:
    """创建用户"""
    # 检查用户名是否已存在
    if get_user_by_username(db, user.username):
        raise ValueError("用户名已存在")
    
    # 检查邮箱是否已存在
    if user.email and get_user_by_email(db, user.email):
        raise ValueError("邮箱已被注册")
    
    # 创建新用户
    hashed_password = get_password_hash(user.password)
    db_user = User(
        username=user.username,
        email=user.email,
        hashed_password=hashed_password
    )
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user


def login_user(db: Session, user_login: UserLogin) -> Token:
    """用户登录"""
    user = authenticate_user(db, user_login.username, user_login.password)
    if not user:
        raise ValueError("用户名或密码错误")
    
    # 创建访问令牌
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": user.username, "user_id": user.id},
        expires_delta=access_token_expires
    )
    
    return Token(
        access_token=access_token,
        token_type="bearer",
        username=user.username,
        user_id=user.id
    )


def get_user_by_id(db: Session, user_id: int) -> Optional[User]:
    """根据用户ID获取用户"""
    return db.query(User).filter(User.id == user_id).first()


def update_user(db: Session, user_id: int, user_update: 'UserUpdate') -> User:
    """更新用户信息"""
    from models.user import UserUpdate
    
    user = get_user_by_id(db, user_id)
    if not user:
        raise ValueError("用户不存在")
    
    # 如果要修改密码，需要验证当前密码
    if user_update.new_password:
        if not user_update.current_password:
            raise ValueError("修改密码需要提供当前密码")
        if not verify_password(user_update.current_password, user.hashed_password):
            raise ValueError("当前密码错误")
        user.hashed_password = get_password_hash(user_update.new_password)
    
    # 更新用户名
    if user_update.username and user_update.username != user.username:
        # 检查新用户名是否已存在
        existing_user = get_user_by_username(db, user_update.username)
        if existing_user and existing_user.id != user_id:
            raise ValueError("用户名已被使用")
        user.username = user_update.username
    
    # 更新邮箱
    if user_update.email is not None and user_update.email != user.email:
        # 检查新邮箱是否已存在
        if user_update.email:  # 如果不是空字符串
            existing_user = get_user_by_email(db, user_update.email)
            if existing_user and existing_user.id != user_id:
                raise ValueError("邮箱已被使用")
        user.email = user_update.email if user_update.email else None
    
    db.commit()
    db.refresh(user)
    return user
