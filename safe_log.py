"""敏感信息脱敏与响应摘要（转换自 Node.js 版 utils/safeLog.js）。

日志中不得出现明文 token、手机号等敏感数据：
- 敏感字段整体替换为 [REDACTED]
- 昵称类字段保留首尾字符，中间以星号占位
- 标识符类字段保留首尾片段
- 字符串中的 GitHub token / 手机号做正则脱敏
"""

import os
import re

SENSITIVE_KEYS = {
    "token",
    "vip_token",
    "viptoken",
    "cookie",
    "authorization",
    "pat",
    "gh_token",
    "userinfo",
    "password",
    "code",
    "mobile",
    "phone",
    "qrcode",
    "qrcode_img",
    "qrcode_txt",
    "qrimg",
    "key",
}

DISPLAY_NAME_KEYS = {"nickname", "username", "display_name", "displayname"}
IDENTIFIER_KEYS = {"userid", "user_id", "uid", "kguid", "kugouid", "t_userid"}

_GITHUB_TOKEN_PATTERN = re.compile(r"github_pat_[A-Za-z0-9_]+|gh[pousr]_[A-Za-z0-9]{20,}")
_PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d{9})(?!\d)")

_MAX_DEPTH = 4
_MAX_LIST_ITEMS = 20


def _normalize_key(key: object) -> str:
    return str(key).lower()


def _sanitize_string(value: str) -> str:
    """脱敏字符串中出现的 GitHub token 与手机号。"""

    def mask_phone(match: re.Match) -> str:
        phone = match.group()
        return f"{phone[:2]}*******{phone[-2:]}"

    value = _GITHUB_TOKEN_PATTERN.sub("[REDACTED]", value)
    return _PHONE_PATTERN.sub(mask_phone, value)


def mask_display_name(value: object) -> str:
    """脱敏昵称：保留前两个和最后一个字符，其余以星号占位。"""
    chars = list(str(value) if value is not None else "")
    if not chars:
        return ""
    if len(chars) == 1:
        return f"{chars[0]}********"
    if len(chars) == 2:
        return f"{chars[0]}********{chars[1]}"
    return f"{''.join(chars[:2])}********{chars[-1]}"


def mask_identifier(value: object) -> str:
    """脱敏标识符（如 userid）：保留首尾片段，中间以星号占位。"""
    chars = list(str(value) if value is not None else "")
    if not chars:
        return ""
    if len(chars) <= 2:
        return "*" * len(chars)
    if len(chars) <= 6:
        return f"{chars[0]}***{chars[-1]}"
    return f"{''.join(chars[:3])}***{''.join(chars[-2:])}"


def _redact_value(key: object, value: object) -> object:
    """按键名对值做脱敏：昵称 > 标识符 > 敏感字段 > 字符串正则脱敏。"""
    normalized_key = _normalize_key(key)

    if normalized_key in DISPLAY_NAME_KEYS:
        return mask_display_name(value)
    if normalized_key in IDENTIFIER_KEYS:
        return mask_identifier(value)
    if normalized_key in SENSITIVE_KEYS:
        return "[REDACTED]"
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def sanitize_for_log(value: object, depth: int = 0) -> object:
    """递归脱敏任意 JSON 结构，超过深度或列表长度上限时截断。"""
    if value is None:
        return value
    if not isinstance(value, (dict, list)):
        return _sanitize_string(value) if isinstance(value, str) else value
    if depth >= _MAX_DEPTH:
        return "[Object]"
    if isinstance(value, list):
        return [sanitize_for_log(item, depth + 1) for item in value[:_MAX_LIST_ITEMS]]

    return {
        key: sanitize_for_log(_redact_value(key, item), depth + 1)
        for key, item in value.items()
    }


def summarize_response(response: object) -> object:
    """提取响应中的关键字段作为摘要，避免日志输出完整敏感内容。"""
    safe = sanitize_for_log(response)
    if not isinstance(safe, dict):
        return safe

    summary = {
        key: safe[key]
        for key in ("status", "code", "error_code", "errcode", "error", "msg", "message", "httpStatus")
        if key in safe
    }

    data = safe.get("data")
    if isinstance(data, dict):
        summary["data"] = {
            key: data[key]
            for key in ("status", "code", "error_code", "errcode", "msg", "message", "nickname", "userid")
            if key in data
        }

    return summary if summary else safe


def should_print_sensitive_value() -> bool:
    """是否允许打印敏感信息（环境变量 ALLOW_PRINT_USERINFO 控制）。"""
    return os.environ.get("ALLOW_PRINT_USERINFO", "").lower() in ("是", "true", "1", "yes")
