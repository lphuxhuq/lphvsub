"""Test sinh youtube_post.txt mẫu."""
import sys
import os

sys.path.insert(0, r"D:\Project\lphvsub-main")

from autodub.config import Settings
from autodub.content.generator import generate_social_metadata_direct, _write_post_file

# Load settings từ .env thật
settings = Settings.load()

print(f"[*] Gemini API Key: ...{settings.gemini_api_key[-20:] if settings.gemini_api_key else 'CHƯA CÓ'}")
print(f"[*] Gemini Model  : {settings.gemini_model}")

# Đọc script_vi.txt thật
script_vi_path = r"D:\Project\lphvsub-main\output\VN\20260817193154_vi\youtube\script_vi.txt"
with open(script_vi_path, encoding="utf-8") as f:
    script_vi = f.read().strip()

script_original = "花魁选择了一个只顾吃西瓜的男人，醉仙楼千两赌约"
video_title = "花魁选人 - 醉仙楼千两赌约"

print(f"\n[*] Đang gọi Gemini API để sinh nội dung đăng bài...\n")

meta = generate_social_metadata_direct(
    script_original=script_original,
    script_translated=script_vi,
    settings=settings,
    video_title=video_title,
)

if meta:
    print("[✓] Thành công! Nội dung nhận được:")
    import json
    print(json.dumps(meta, ensure_ascii=False, indent=2))

    out_path = r"D:\Project\lphvsub-main\output\VN\20260817193154_vi\youtube\youtube_post.txt"
    _write_post_file(out_path, meta)
    print(f"\n[✓] Đã ghi ra: {out_path}")
else:
    print("[✗] Không sinh được nội dung — kiểm tra API Key hoặc log bên trên.")
