"""Quản lý các bộ Checkpoint cấu hình (Logo, Watermark, Anti-Reup, Khung hình, Subtitle, Xóa sub).

Lưu trữ danh sách các cấu hình mẫu theo tên kênh / mục đích sử dụng để người dùng
chỉ cần cấu hình một lần và tái sử dụng bất cứ khi nào.
"""
from __future__ import annotations

import datetime
import json
import os
from typing import Any

from autodub.config import cache_dir
from autodub_gui.env_store import bool_to_env, write_env

CHECKPOINT_FILENAME = "checkpoints.json"
ACTIVE_CHECKPOINT_KEY = "_last_active_checkpoint"


def checkpoints_file_path() -> str:
    """Đường dẫn tệp lưu trữ danh sách checkpoint trong thư mục cache."""
    return os.path.join(cache_dir(), CHECKPOINT_FILENAME)


def load_checkpoints() -> dict[str, dict[str, Any]]:
    """Đọc toàn bộ các checkpoint đã lưu từ đĩa."""
    path = checkpoints_file_path()
    if not os.path.exists(path):
        return {}
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return {}


def save_checkpoint(name: str, data: dict[str, Any]) -> None:
    """Lưu hoặc cập nhật một checkpoint theo tên."""
    name = str(name).strip()
    if not name:
        return
    all_ckpts = load_checkpoints()
    payload = dict(data)
    payload["name"] = name
    payload["updated_at"] = datetime.datetime.now().isoformat()
    all_ckpts[name] = payload
    _write_checkpoints(all_ckpts)


def delete_checkpoint(name: str) -> bool:
    """Xóa một checkpoint theo tên. Trả về True nếu xóa thành công."""
    name = str(name).strip()
    all_ckpts = load_checkpoints()
    if name in all_ckpts:
        del all_ckpts[name]
        _write_checkpoints(all_ckpts)
        return True
    return False


def get_checkpoint(name: str) -> dict[str, Any] | None:
    """Lấy dữ liệu của một checkpoint theo tên."""
    name = str(name).strip()
    all_ckpts = load_checkpoints()
    return all_ckpts.get(name)


load_checkpoint = get_checkpoint


def get_checkpoint_names() -> list[str]:
    """Danh sách tên các checkpoint hiện có."""
    all_ckpts = load_checkpoints()
    names = [k for k in all_ckpts.keys() if k != ACTIVE_CHECKPOINT_KEY]
    # Sắp xếp để "Mặc định" lên đầu nếu có
    if "Mặc định" in names:
        names.remove("Mặc định")
        names.insert(0, "Mặc định")
    return names


def get_active_checkpoint_name() -> str:
    """Lấy tên checkpoint đang được chọn gần nhất."""
    all_ckpts = load_checkpoints()
    val = all_ckpts.get(ACTIVE_CHECKPOINT_KEY)
    if isinstance(val, str):
        return val
    names = get_checkpoint_names()
    return names[0] if names else ""


def set_active_checkpoint_name(name: str) -> None:
    """Ghi nhớ tên checkpoint vừa được kích hoạt gần nhất."""
    all_ckpts = load_checkpoints()
    all_ckpts[ACTIVE_CHECKPOINT_KEY] = str(name).strip()
    _write_checkpoints(all_ckpts)


def _write_checkpoints(data: dict[str, Any]) -> None:
    path = checkpoints_file_path()
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def bundle_checkpoint_data(
    values: dict[str, Any],
    subtitle_style: dict[str, Any] | None = None,
    blur_regions: list[dict[str, Any]] | None = None,
    mask_opts: dict[str, Any] | None = None,
    banner_opts: dict[str, Any] | None = None,
    reframe_opts: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Đóng gói toàn bộ các thông số từ giao diện thành một từ điển checkpoint chuẩn hóa."""
    vals = dict(values or {})
    mask = dict(mask_opts or {})
    banner = dict(banner_opts or {})
    reframe = dict(reframe_opts or {})

    return {
        "logo": {
            "logo_path": vals.get("logo_path", ""),
            "logo_position": vals.get("logo_position", "top_right"),
            "logo_scale": float(vals.get("logo_scale", 0.12)),
            "logo_opacity": float(vals.get("logo_opacity", 0.85)),
            "logo_motion": vals.get("logo_motion", "static"),
        },
        "watermark": {
            "watermark_text": vals.get("watermark_text", ""),
            "watermark_motion": vals.get("watermark_motion", "bounce"),
            "watermark_opacity": float(vals.get("watermark_opacity", 0.28)),
            "watermark_speed": int(vals.get("watermark_speed", 40)),
            "watermark_font_size": int(vals.get("watermark_font_size", 26)),
            "watermark_color": vals.get("watermark_color", "white"),
        },
        "anti_id": {
            "smart_flip": bool(vals.get("smart_flip", False)),
            "micro_zoom": bool(vals.get("micro_zoom", False)),
            "color_filter": vals.get("color_filter", "none"),
            "randomize_metadata": bool(vals.get("randomize_metadata", True)),
        },
        "reframe": {
            "aspect_preset": reframe.get("aspect_preset") or vals.get("aspect_preset", "original"),
            "reframe_mode": reframe.get("reframe_mode") or vals.get("reframe_mode", "blur"),
        },
        "banner": {
            "frame_banner_enabled": bool(banner.get("frame_banner_enabled", vals.get("frame_banner_enabled", False))),
            "frame_banner_color": banner.get("frame_banner_color", vals.get("frame_banner_color", "#000000")),
            "frame_header_text": banner.get("frame_header_text", vals.get("frame_header_text", "")),
            "frame_header_font_size": int(banner.get("frame_header_font_size", vals.get("frame_header_font_size", 32))),
            "frame_header_color": banner.get("frame_header_color", vals.get("frame_header_color", "#FFFFFF")),
            "frame_footer_text": banner.get("frame_footer_text", vals.get("frame_footer_text", "")),
            "frame_footer_font_size": int(banner.get("frame_footer_font_size", vals.get("frame_footer_font_size", 24))),
            "frame_footer_color": banner.get("frame_footer_color", vals.get("frame_footer_color", "#FFD54A")),
            "frame_banner_height_ratio": float(banner.get("frame_banner_height_ratio", vals.get("frame_banner_height_ratio", 0.16))),
        },
        "mask": {
            "mask_method": mask.get("mask_method") or vals.get("mask_method", "blur"),
            "inpaint_engine": mask.get("inpaint_engine") or vals.get("inpaint_engine", "lama_onnx"),
            "inpaint_device": mask.get("inpaint_device") or vals.get("inpaint_device", "auto"),
            "blur_regions": list(blur_regions if blur_regions is not None else vals.get("blur_regions", [])),
        },
        "subtitle": {
            "subtitle_mode": vals.get("subtitle_mode", "burn"),
            "subtitle_preset": vals.get("subtitle_preset", "custom"),
            "subtitle_style": dict(subtitle_style or vals.get("subtitle_style") or {}),
        },
        "voice": {
            "voice": vals.get("voice", ""),
            "voice_speed": float(vals.get("voice_speed", 1.0)),
            "bg_mode": vals.get("bg_mode", "demucs"),
            "bg_duck_db": float(vals.get("bg_duck_db", -12.0)),
        },
    }


def apply_checkpoint_to_env(checkpoint_data: dict[str, Any] | str, env_path: str | None = None) -> None:
    """Ghi trực tiếp các thiết lập trong checkpoint vào tệp .env để trở thành mặc định cho ứng dụng."""
    if isinstance(checkpoint_data, str):
        data = get_checkpoint(checkpoint_data)
        if not data:
            return
        checkpoint_data = data
    if not isinstance(checkpoint_data, dict):
        return

    updates: dict[str, str] = {}

    logo = checkpoint_data.get("logo", {})
    if "logo_path" in logo:
        updates["LOGO_PATH"] = str(logo["logo_path"])
    if "logo_position" in logo:
        updates["LOGO_POSITION"] = str(logo["logo_position"])
    if "logo_scale" in logo:
        updates["LOGO_SCALE"] = f"{float(logo['logo_scale']):.2f}"
    if "logo_opacity" in logo:
        updates["LOGO_OPACITY"] = f"{float(logo['logo_opacity']):.2f}"
    if "logo_motion" in logo:
        updates["LOGO_MOTION"] = str(logo["logo_motion"])

    wm = checkpoint_data.get("watermark", {})
    if "watermark_text" in wm:
        updates["WATERMARK_TEXT"] = str(wm["watermark_text"])
    if "watermark_motion" in wm:
        updates["WATERMARK_MOTION"] = str(wm["watermark_motion"])
    if "watermark_opacity" in wm:
        updates["WATERMARK_OPACITY"] = f"{float(wm['watermark_opacity']):.2f}"
    if "watermark_speed" in wm:
        updates["WATERMARK_SPEED"] = str(int(wm["watermark_speed"]))
    if "watermark_font_size" in wm:
        updates["WATERMARK_FONT_SIZE"] = str(int(wm["watermark_font_size"]))
    if "watermark_color" in wm:
        updates["WATERMARK_COLOR"] = str(wm["watermark_color"])

    anti = checkpoint_data.get("anti_id", {})
    if "smart_flip" in anti:
        updates["SMART_FLIP"] = bool_to_env(bool(anti["smart_flip"]))
    if "micro_zoom" in anti:
        updates["MICRO_ZOOM"] = bool_to_env(bool(anti["micro_zoom"]))
    if "color_filter" in anti:
        updates["COLOR_FILTER"] = str(anti["color_filter"])
    if "randomize_metadata" in anti:
        updates["RANDOMIZE_METADATA"] = bool_to_env(bool(anti["randomize_metadata"]))

    reframe = checkpoint_data.get("reframe", {})
    if "aspect_preset" in reframe:
        updates["VIDEO_ASPECT_PRESET"] = str(reframe["aspect_preset"])
    if "reframe_mode" in reframe:
        updates["VIDEO_REFRAME_MODE"] = str(reframe["reframe_mode"])

    banner = checkpoint_data.get("banner", {})
    if "frame_banner_enabled" in banner:
        updates["FRAME_BANNER_ENABLED"] = bool_to_env(bool(banner["frame_banner_enabled"]))
    if "frame_banner_color" in banner:
        updates["FRAME_BANNER_COLOR"] = str(banner["frame_banner_color"])
    if "frame_header_text" in banner:
        updates["FRAME_HEADER_TEXT"] = str(banner["frame_header_text"])
    if "frame_header_font_size" in banner:
        updates["FRAME_HEADER_FONT_SIZE"] = str(int(banner["frame_header_font_size"]))
    if "frame_header_color" in banner:
        updates["FRAME_HEADER_COLOR"] = str(banner["frame_header_color"])
    if "frame_footer_text" in banner:
        updates["FRAME_FOOTER_TEXT"] = str(banner["frame_footer_text"])
    if "frame_footer_font_size" in banner:
        updates["FRAME_FOOTER_FONT_SIZE"] = str(int(banner["frame_footer_font_size"]))
    if "frame_footer_color" in banner:
        updates["FRAME_FOOTER_COLOR"] = str(banner["frame_footer_color"])
    if "frame_banner_height_ratio" in banner:
        updates["FRAME_BANNER_HEIGHT_RATIO"] = f"{float(banner['frame_banner_height_ratio']):.2f}"

    mask = checkpoint_data.get("mask", {})
    if "mask_method" in mask:
        updates["MASK_METHOD"] = str(mask["mask_method"])
    if "inpaint_engine" in mask:
        updates["INPAINT_ENGINE"] = str(mask["inpaint_engine"])
    if "inpaint_device" in mask:
        updates["INPAINT_DEVICE"] = str(mask["inpaint_device"])
    if "blur_regions" in mask:
        regions = mask["blur_regions"]
        updates["BLUR_REGIONS"] = json.dumps(regions) if regions else ""

    sub = checkpoint_data.get("subtitle", {})
    if "subtitle_mode" in sub:
        updates["SUBTITLE_MODE"] = str(sub["subtitle_mode"])
    if "subtitle_preset" in sub:
        updates["SUBTITLE_PRESET"] = str(sub["subtitle_preset"])
    style = sub.get("subtitle_style", {})
    if style:
        if "font" in style:
            updates["SUBTITLE_FONT"] = str(style["font"])
        if "font_size" in style:
            updates["SUBTITLE_FONT_SIZE"] = str(style["font_size"])
        if "position" in style:
            updates["SUBTITLE_POSITION"] = str(style["position"])
        if "color" in style:
            updates["SUBTITLE_COLOR"] = str(style["color"])
        if "outline" in style:
            updates["SUBTITLE_OUTLINE"] = str(style["outline"])
        if "outline_color" in style:
            updates["SUBTITLE_OUTLINE_COLOR"] = str(style["outline_color"])
        if "shadow" in style:
            updates["SUBTITLE_SHADOW"] = str(style["shadow"])
        if "bold" in style:
            updates["SUBTITLE_BOLD"] = bool_to_env(bool(style["bold"]))
        if "box" in style:
            updates["SUBTITLE_BOX"] = str(style["box"])
        if "box_color" in style:
            updates["SUBTITLE_BOX_COLOR"] = str(style["box_color"])
        if "box_opacity" in style:
            updates["SUBTITLE_BOX_OPACITY"] = str(style["box_opacity"])
        if "display" in style:
            updates["SUBTITLE_DISPLAY"] = str(style["display"])
        if "words_per_cue" in style:
            updates["KARAOKE_WORDS_PER_CUE"] = str(style["words_per_cue"])
        if "effect" in style:
            updates["KARAOKE_EFFECT"] = str(style["effect"])
        if "highlight_color" in style:
            updates["KARAOKE_HIGHLIGHT_COLOR"] = str(style["highlight_color"])

    voice = checkpoint_data.get("voice", {})
    if "voice" in voice and voice["voice"]:
        updates["VIENEU_VOICE"] = str(voice["voice"])
    if "voice_speed" in voice:
        updates["VOICE_SPEED"] = f"{float(voice['voice_speed']):.2f}"
    if "bg_mode" in voice:
        updates["BG_MODE"] = str(voice["bg_mode"])
    if "bg_duck_db" in voice:
        updates["BG_DUCK_DB"] = f"{float(voice['bg_duck_db']):.1f}"

    if updates:
        try:
            if env_path:
                write_env(updates, path=env_path)
            else:
                from autodub_gui import env_store
                write_env(updates, path=env_store.ENV_PATH)
        except OSError:
            pass
