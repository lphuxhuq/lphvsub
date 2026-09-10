"""Đọc và ghi tệp cấu hình của ứng dụng.

Các hàm cơ bản (``read_env``, ``write_env``, ``env_bool``, ``bool_to_env``)
đã được chuyển sang ``autodub.env_io`` (core, không phụ thuộc GUI). Module
này re-export chúng cho backward-compat và thêm các tiện ích GUI-only.
"""
from __future__ import annotations

# Re-export core functions — existing GUI callers không cần đổi import.
from autodub.env_io import (  # noqa: F401
    ENV_PATH,
    bool_to_env,
    env_bool,
    read_env,
    write_env,
)


def env_to_multiline(value: str) -> str:
    """Đổi giá trị một dòng có ký tự xuống dòng thoát thành nhiều dòng thật."""
    return value.replace("\\n", "\n")


def multiline_to_env(value: str) -> str:
    """Gói đoạn văn nhiều dòng thành một dòng để lưu vào tệp cấu hình."""
    return value.strip().replace("\r\n", "\n").replace("\n", "\\n")


def api_keys_to_multiline(value: str) -> str:
    """Tách danh sách API Key (phân cách bởi dấu phẩy hoặc \\\\n) thành nhiều dòng để hiển thị.

    Mỗi key chiếm một dòng riêng, giúp người dùng dễ đọc và chỉnh sửa.
    """
    import re
    tokens = [t.strip() for t in re.split(r"[,;\n]+", value.replace("\\n", "\n")) if t.strip()]
    return "\n".join(tokens)


def multiline_to_api_keys(value: str) -> str:
    """Gộp danh sách API Key nhiều dòng thành một dòng dấu phẩy để lưu .env."""
    import re
    tokens = [t.strip() for t in re.split(r"[,;\n]+", value) if t.strip()]
    return ",".join(tokens)

