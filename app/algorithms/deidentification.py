"""真实工单导入前的基础敏感信息扫描；不能替代人工脱敏复核。"""

import re

_PATTERNS = {
    "PHONE": re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)"),
    "EMAIL": re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}"),
    "CHINA_ID": re.compile(r"(?<!\d)\d{17}[\dXx](?!\d)"),
}


def find_sensitive_patterns(text: str) -> list[str]:
    """返回可机械识别的敏感模式类型，不返回原始匹配文本。"""
    value = text or ""
    return [name for name, pattern in _PATTERNS.items() if pattern.search(value)]


def redact_sensitive_patterns(text: str) -> tuple[str, list[str]]:
    """替换可机械识别的敏感内容，且不在返回值中保留原始匹配文本。"""
    value = text or ""
    found: list[str] = []
    for name, pattern in _PATTERNS.items():
        if pattern.search(value):
            found.append(name)
            value = pattern.sub(f"[{name}_REDACTED]", value)
    return value, found
