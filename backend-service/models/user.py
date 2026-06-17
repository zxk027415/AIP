"""
用户模型
"""
from pydantic import BaseModel, Field
from typing import Optional
from datetime import datetime


class UserBase(BaseModel):
    """用户基础模型"""
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    email: Optional[str] = Field(None, description="邮箱")


class UserCreate(UserBase):
    """用户创建模型"""
    password: str = Field(..., min_length=6, max_length=100, description="密码")


class UserLogin(BaseModel):
    """用户登录模型"""
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")


class UserResponse(UserBase):
    """用户响应模型"""
    id: int
    created_at: datetime
    
    class Config:
        from_attributes = True


class Token(BaseModel):
    """Token 响应模型"""
    access_token: str
    token_type: str
    username: str
    user_id: int


class TokenData(BaseModel):
    """Token 数据模型"""
    username: Optional[str] = None
    user_id: Optional[int] = None


class UserUpdate(BaseModel):
    """用户信息更新模型"""
    username: Optional[str] = Field(None, min_length=3, max_length=50, description="新用户名")
    email: Optional[str] = Field(None, description="新邮箱")
    current_password: Optional[str] = Field(None, description="当前密码（修改密码时必需）")
    new_password: Optional[str] = Field(None, min_length=6, max_length=100, description="新密码")
