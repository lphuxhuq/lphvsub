"""Metadata cleaning, scrubbing, and unique hash randomization.

Designed to prevent platform duplicate detection (YouTube, TikTok, Facebook Reels, Instagram)
by scrubbing original camera/software metadata and guaranteeing a unique MD5/SHA256 checksum
on every exported video file.
"""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import os
import struct
import uuid


def calculate_file_hash(file_path: str, algo: str = "md5", chunk_size: int = 65536) -> str:
    """Tính mã băm hex của tệp (md5, sha1, sha256)."""
    h = hashlib.new(algo)
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()


def randomize_file_hash(file_path: str, salt_length: int = 32) -> str:
    """Ghi thêm một khối atom padding 'free' chuẩn MP4 ISO để biến đổi MD5/SHA256.

    Khối 'free' là khối chuẩn theo đặc tả ISO/IEC 14496-12 (MP4/MOV Container)
    dành cho vùng đệm tự do. Tất cả trình phát và nền tảng (VLC, QuickTime,
    Chrome, YouTube, TikTok) đều bỏ qua khối này khi phát hình và tiếng,
    nhưng mã băm nhị phân (MD5/SHA256) của tệp đảm bảo là duy nhất 100%.

    Sau khi ghi, cập nhật thời gian sửa đổi (mtime) của tệp trên đĩa.
    Trả về mã MD5 mới của tệp.
    """
    if not os.path.isfile(file_path):
        raise FileNotFoundError(f"Không tìm thấy tệp để đổi mã băm: {file_path}")

    # Cấu trúc atom chuẩn MP4: 4 bytes length + 4 bytes type b'free' + payload
    box_length = 8 + max(4, salt_length)
    atom_header = struct.pack(">I4s", box_length, b"free")
    random_payload = os.urandom(max(4, salt_length))

    with open(file_path, "ab") as f:
        f.write(atom_header + random_payload)

    # Làm mới thời gian tạo và sửa tệp trên hệ thống tệp
    try:
        os.utime(file_path, None)
    except OSError:
        pass

    return calculate_file_hash(file_path, "md5")


def build_clean_metadata_args() -> list[str]:
    """Tạo danh sách tham số FFmpeg để làm sạch và ngẫu nhiên hóa metadata.

    - `-map_metadata -1`: Xóa sạch 100% metadata gốc của video đầu vào (thiết bị quay,
      tọa độ GPS, phần mềm dựng cũ, tác giả cũ).
    - `creation_time`: Thời gian hiện tại theo chuẩn UTC.
    - `title`, `comment`: Chuỗi định danh ngẫu nhiên (UUID nonce) làm mới định danh.
    - `handler_name`: Định danh luồng chuẩn hóa, không lộ tên công cụ.
    """
    now_utc = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    nonce = uuid.uuid4().hex[:12]
    comment_id = uuid.uuid4().hex[:16]

    return [
        "-map_metadata", "-1",
        "-metadata", f"creation_time={now_utc}",
        "-metadata", f"title=dub_{nonce}",
        "-metadata", f"comment=id_{comment_id}",
        "-metadata:s:v:0", "handler_name=VideoHandler",
        "-metadata:s:a:0", "handler_name=SoundHandler",
    ]
