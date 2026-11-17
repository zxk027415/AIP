# @AI_GENERATED: Kiro v1.0
"""
输入 Sanitize 工具 — 防止 SQL 注入、XSS、命令注入
"""
import re
import html
from typing import Optional


# 危险 SQL 关键词模式
_SQL_INJECTION_PATTERN = re.compile(
    r"(\b(SELECT|INSERT|UPDATE|DELETE|DROP|ALTER|CREATE|EXEC|UNION|"
    r"TRUNCATE|GRANT|REVOKE)\b\s)",
    re.IGNORECASE,
)

# 命令注入模式
_CMD_INJECTION_PATTERN = re.compile(
    r"[;&|`$]|\b(rm|del|format|shutdown|reboot|wget|curl)\b",
    re.IGNORECASE,
)

# XSS 标签模式
_XSS_PATTERN = re.compile(r"<\s*script|<\s*iframe|javascript\s*:|on\w+\s*=", re.IGNORECASE)

# 最大输入长度
MAX_DESCRIPTION_LENGTH = 2000
MAX_FIELD_LENGTH = 500
MAX_TAG_LENGTH = 50


def sanitize_text(text: Optional[str], max_length: int = MAX_FIELD_LENGTH) -> Optional[str]:
    """清理文本输入：转义 HTML、截断长度"""
    if text is None:
        return None
    text = text.strip()
    if not text:
        return text
    # HTML 实体转义（防 XSS）
    text = html.escape(text, quote=True)
    # 截断
    if len(text) > max_length:
        text = text[:max_length]
    return text


def sanitize_description(desc: str) -> str:
    """清理用户业务描述输入"""
    desc = desc.strip()
    if len(desc) > MAX_DESCRIPTION_LENGTH:
        desc = desc[:MAX_DESCRIPTION_LENGTH]
    # 移除潜在的脚本标签但保留正常文本
    desc = re.sub(r"<\s*script[^>]*>.*?</\s*script\s*>", "", desc, flags=re.IGNORECASE | re.DOTALL)
    desc = re.sub(r"<\s*iframe[^>]*>.*?</\s*iframe\s*>", "", desc, flags=re.IGNORECASE | re.DOTALL)
    return desc


def sanitize_id(value: str, max_length: int = 100) -> str:
    """清理 ID 类字段：只允许字母、数字、连字符、下划线"""
    value = value.strip()
    if len(value) > max_length:
        value = value[:max_length]
    # 只保留安全字符
    value = re.sub(r"[^a-zA-Z0-9\-_\u4e00-\u9fff]", "", value)
    return value


def check_sql_injection(text: str) -> bool:
    """检测是否包含 SQL 注入模式，返回 True 表示有风险"""
    return bool(_SQL_INJECTION_PATTERN.search(text))


def check_cmd_injection(text: str) -> bool:
    """检测是否包含命令注入模式，返回 True 表示有风险"""
    return bool(_CMD_INJECTION_PATTERN.search(text))


def check_xss(text: str) -> bool:
    """检测是否包含 XSS 模式，返回 True 表示有风险"""
    return bool(_XSS_PATTERN.search(text))


def validate_safe_input(text: str, field_name: str = "input") -> str:
    """综合安全校验，不安全时抛出 ValueError"""
    if check_sql_injection(text):
        raise ValueError(f"{field_name} 包含不安全的 SQL 关键词")
    if check_cmd_injection(text):
        raise ValueError(f"{field_name} 包含不安全的命令字符")
    if check_xss(text):
        raise ValueError(f"{field_name} 包含不安全的脚本内容")
    return text
# @AI_GENERATED: end
