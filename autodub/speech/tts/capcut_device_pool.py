"""Quản lý Device Pool đa thiết bị (fake nhiều device.json) cho CapCut TTS.

Hỗ trợ fake nhiều hồ sơ thiết bị phong phú (macOS, Windows, Android, iOS),
chia luồng độc lập và tự động xoay vòng định danh khi gặp giới hạn tốc độ.
"""
from __future__ import annotations

import hashlib
import json
import os
import random
import threading
import time
import uuid
from typing import Any, Dict, List, Optional, Tuple

from autodub.speech.tts.capcut_api.config import DEFAULT_DEVICE
from autodub.speech.tts.capcut_api.models import DeviceConfig
from autodub.utils import save_json_atomic, setup_logging

logger = setup_logging("autodub.tts.capcut_pool")

#: Danh sách các mẫu thiết bị Desktop thực tế (macOS & Windows) khớp chuẩn AID 359289
DEVICE_TEMPLATES = [
    {
        "device_platform": "mac",
        "device_type": "MacBookPro18,1",
        "device_brand": "MacBookPro18,1",
        "os_version": "15.7.4",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "3",
    },
    {
        "device_platform": "mac",
        "device_type": "MacBookPro16,1",
        "device_brand": "MacBookPro16,1",
        "os_version": "14.4.1",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "3",
    },
    {
        "device_platform": "mac",
        "device_type": "MacBookAir10,1",
        "device_brand": "MacBookAir10,1",
        "os_version": "15.2.0",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "3",
    },
    {
        "device_platform": "mac",
        "device_type": "Macmini9,1",
        "device_brand": "Macmini9,1",
        "os_version": "14.5.0",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "3",
    },
    {
        "device_platform": "mac",
        "device_type": "iMac21,1",
        "device_brand": "iMac21,1",
        "os_version": "15.1.0",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "3",
    },
    {
        "device_platform": "mac",
        "device_type": "MacPro7,1",
        "device_brand": "MacPro7,1",
        "os_version": "13.6.8",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "3",
    },
    {
        "device_platform": "mac",
        "device_type": "Mac14,2",
        "device_brand": "Mac14,2",
        "os_version": "14.7.0",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "3",
    },
    {
        "device_platform": "mac",
        "device_type": "Mac14,7",
        "device_brand": "Mac14,7",
        "os_version": "15.3.0",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "3",
    },
    {
        "device_platform": "mac",
        "device_type": "Mac15,3",
        "device_brand": "Mac15,3",
        "os_version": "15.3.1",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "3",
    },
    {
        "device_platform": "mac",
        "device_type": "Mac15,6",
        "device_brand": "Mac15,6",
        "os_version": "15.4.0",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "3",
    },
    {
        "device_platform": "windows",
        "device_type": "Desktop-x64",
        "device_brand": "CustomPC",
        "os_version": "10.0.22631",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "1",
    },
    {
        "device_platform": "windows",
        "device_type": "Dell-XPS-9520",
        "device_brand": "Dell",
        "os_version": "10.0.22621",
        "appvr": "8.7.0",
        "version_name": "8.7.0",
        "version_code": "8.7.0",
        "channel": "capcutpc_google",
        "pf": "1",
    },
]


def generate_fake_device(seed: Optional[str] = None, template_idx: Optional[int] = None) -> dict:
    """Tạo một hồ sơ thiết bị fake hoàn chỉnh và hợp lệ cho CapCut API."""
    if seed is None:
        seed = uuid.uuid4().hex + uuid.uuid4().hex
    digest = hashlib.sha256(seed.encode("utf-8")).hexdigest()

    def _id(chunk: str) -> str:
        return "7" + str(int(chunk, 16) % 10 ** 18).zfill(18)

    if template_idx is None:
        idx = int(digest[:4], 16) % len(DEVICE_TEMPLATES)
    else:
        idx = template_idx % len(DEVICE_TEMPLATES)
    template = DEVICE_TEMPLATES[idx]

    device = {
        **DEFAULT_DEVICE,
        **template,
        "device_id": _id(digest[:16]),
        "iid": _id(digest[16:32]),
        "tdid": _id(digest[32:48]),
        "region": "VN",
        "loc": "VN",
        "lan": "vi-VN",
    }
    return device


def pool_file_path() -> str:
    """Đường dẫn file lưu danh sách Device Pool trên đĩa."""
    return os.path.join(
        os.path.expanduser("~"), ".voxdub_cache", "capcut_devices_pool.json"
    )


class CapCutDevicePool:
    """Quản lý nhóm hồ sơ thiết bị (Device Pool) với cơ chế cân bằng tải và cooldown."""

    def __init__(self, size: int = 16):
        self.target_size = max(8, size)
        self._devices: List[dict] = []
        self._cooldowns: Dict[str, float] = {}  # device_id -> timestamp hết cooldown
        self._lock = threading.Lock()
        self._per_device_last_call: Dict[str, float] = {}
        self._load_or_generate_pool()

    def _load_or_generate_pool(self) -> None:
        path = pool_file_path()
        try:
            if os.path.exists(path):
                with open(path, "r", encoding="utf-8") as f:
                    saved = json.load(f)
                if isinstance(saved, list) and len(saved) >= 4:
                    self._devices = saved
                    return
        except Exception:
            pass

        # Tạo pool mới với sự kết hợp từ các template
        devices = []
        for i in range(self.target_size):
            dev = generate_fake_device(template_idx=i)
            devices.append(dev)
        self._devices = devices
        self._save_pool()

    def _save_pool(self) -> None:
        path = pool_file_path()
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            save_json_atomic(self._devices, path)
        except Exception:
            pass

    def get_device(self, worker_index: Optional[int] = None) -> dict:
        """Lấy một hồ sơ thiết bị hoạt động tốt từ pool."""
        now = time.monotonic()
        with self._lock:
            # Lọc ra danh sách device đang active (hết cooldown)
            available = [
                d for d in self._devices
                if self._cooldowns.get(d["device_id"], 0.0) <= now
            ]
            if not available:
                # Nếu tất cả đều bị cooldown, sinh ngay một device mới
                logger.info("Tất cả thiết bị trong pool đang cooldown — tự động cấp thiết bị mới...")
                new_dev = generate_fake_device()
                self._devices.append(new_dev)
                available = [new_dev]

            if worker_index is not None:
                return available[worker_index % len(available)]
            return random.choice(available)

    def report_block(self, blocked_device: dict, cooldown_seconds: float = 300.0) -> dict:
        """Báo cáo thiết bị bị chặn (shark block / ret -6) và nhận thiết bị thay thế mới."""
        did = blocked_device.get("device_id", "")
        with self._lock:
            self._cooldowns[did] = time.monotonic() + cooldown_seconds
            logger.warning(
                f"Thiết bị CapCut ({blocked_device.get('device_type')}, ...{did[-6:]}) "
                f"được đưa vào cooldown {cooldown_seconds}s. Đang cấp thiết bị thay thế..."
            )
            # Sinh một thiết bị mới bổ sung vào pool
            replacement = generate_fake_device()
            self._devices.append(replacement)
            self._save_pool()
            return replacement

    def report_success(self, device: dict) -> None:
        """Báo cáo thiết bị hoạt động bình thường."""
        did = device.get("device_id", "")
        with self._lock:
            self._cooldowns.pop(did, None)

    def throttle_device(self, device: dict, min_gap_s: float = 0.03) -> None:
        """Giữ nhịp riêng cho từng thiết bị, không chặn chéo sang thiết bị khác."""
        did = device.get("device_id", "default")
        with self._lock:
            last = self._per_device_last_call.get(did, 0.0)
            now = time.monotonic()
            wait = (last + min_gap_s) - now
            self._per_device_last_call[did] = max(now, last + min_gap_s)
        if wait > 0:
            time.sleep(wait)


_DEVICE_POOL: Optional[CapCutDevicePool] = None
_POOL_LOCK = threading.Lock()


def get_device_pool() -> CapCutDevicePool:
    """Lấy hoặc khởi tạo instance Device Pool dùng chung."""
    global _DEVICE_POOL
    with _POOL_LOCK:
        if _DEVICE_POOL is None:
            _DEVICE_POOL = CapCutDevicePool()
        return _DEVICE_POOL
