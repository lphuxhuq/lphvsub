"""Engine CapCut: định tuyến, danh mục, và độc lập với VieNeu.

Hồi quy nguy hiểm nhất là giọng CapCut bị chặn oan trên máy chưa cài VieNeu —
đó chính là lý do tồn tại của engine này. Các bài ở đây khóa chặt điều đó.
Không bài nào gọi mạng.
"""
from __future__ import annotations

import json
import os

import pytest

from autodub.config import ConfigError, Settings
from autodub.languages import get_target
from autodub.speech.tts import capcut_catalog, capcut_vi, get_synthesizer
from autodub.speech.tts import voices


@pytest.fixture(autouse=True)
def isolated_device(tmp_path, monkeypatch):
    """Mọi bài dùng hồ sơ thiết bị trong tmp và không chờ van tiết lưu."""
    monkeypatch.setattr(
        capcut_catalog, "device_file",
        lambda: str(tmp_path / "device" / "capcut_device.json"))
    monkeypatch.setattr(capcut_vi, "_profile", None)
    monkeypatch.setattr(capcut_vi, "_rotations", 0)
    monkeypatch.setattr(capcut_vi, "_throttle", lambda: None)


@pytest.fixture
def settings(tmp_path):
    """Máy chưa cài VieNeu: thư mục model rỗng."""
    return Settings(vieneu_model_dir=str(tmp_path / "vieneu"))


def write_custom(settings, presets: dict) -> None:
    path = settings.vieneu_custom_voices_path()
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"presets": presets}, f, ensure_ascii=False)


# ------------------------------------------------------------- danh mục --- #

def test_catalog_has_every_vietnamese_voice_with_a_usable_id():
    entries = capcut_catalog.entries()
    assert len(entries) == 22
    for entry in entries:
        assert entry["name"] and " - " not in entry["name"]
        assert entry["voice_type"] and entry["resource_id"].isdigit()
        assert entry["gender"] in {"male", "female"}


def test_catalog_names_are_unique():
    """Tên là định danh giọng — trùng tên thì một giọng không bao giờ chọn được."""
    names = [e["name"] for e in capcut_catalog.entries()]
    assert len(names) == len(set(names))


def test_lookup_finds_by_name_and_rejects_strangers():
    entry = capcut_catalog.lookup("Nhỏ Ngọt Ngào")
    assert entry is not None and entry["voice_type"] == "BV421_vivn_streaming"
    assert capcut_catalog.lookup("Giọng Ma") is None


def test_default_capcut_voice_actually_exists():
    assert capcut_catalog.lookup(capcut_catalog.DEFAULT_CAPCUT_VOICE)


# ------------------------------------------------------------ device id --- #

@pytest.fixture
def device_home():
    return capcut_catalog.device_file()


def test_device_id_is_stable_for_the_same_machine(device_home):
    a, b = capcut_catalog.device_profile(), capcut_catalog.device_profile()
    assert a == b
    for key in ("device_id", "iid", "tdid"):
        assert len(a[key]) == 19 and a[key].isdigit()
    assert a["device_id"] != a["iid"] != a["tdid"]


def test_device_profile_is_saved_so_it_can_be_replaced(device_home):
    """Hồ sơ phải nằm trên đĩa — đó là điều kiện để đổi được khi bị chặn."""
    profile = capcut_catalog.device_profile()
    assert os.path.isfile(device_home)
    with open(device_home, encoding="utf-8") as f:
        assert json.load(f)["device_id"] == profile["device_id"]


def test_rotate_gives_a_brand_new_id_and_keeps_it(device_home):
    """Hồi quy chí mạng: bị chặn mà không đổi được ID thì máy chết vĩnh viễn."""
    before = capcut_catalog.device_profile()
    after = capcut_catalog.rotate_device()
    assert after["device_id"] != before["device_id"]
    assert len(after["device_id"]) == 19 and after["device_id"].isdigit()
    # Lần chạy sau phải dùng ID mới, không quay về ID đã bị chặn.
    assert capcut_catalog.device_profile()["device_id"] == after["device_id"]


def test_device_id_follows_the_fingerprint(device_home, monkeypatch):
    import autodub.device_id as device_id

    monkeypatch.setattr(device_id, "get_fingerprint", lambda: "a" * 64)
    first = capcut_catalog.device_profile()
    os.remove(device_home)
    monkeypatch.setattr(device_id, "get_fingerprint", lambda: "b" * 64)
    assert capcut_catalog.device_profile() != first


# ---------------------------------------------------------- định tuyến --- #

def test_capcut_voice_works_without_vieneu_installed(settings):
    """Ca kiểm thử quan trọng nhất: CapCut phải độc lập hoàn toàn với VieNeu."""
    assert settings.vieneu_configured() is False
    synth = get_synthesizer(get_target("vi"), settings, "Nhỏ Ngọt Ngào")
    assert type(synth).__name__ == "CapCutSynthesizer"
    assert synth.voice_name == "Nhỏ Ngọt Ngào"
    assert synth.recommended_threads == capcut_vi.RECOMMENDED_THREADS


def test_offline_voice_still_requires_vieneu(settings):
    write_custom(settings, {"Hoàng Nam": {"gender": "male",
                                          "source": "library"}})
    with pytest.raises(ConfigError):
        get_synthesizer(get_target("vi"), settings, "Hoàng Nam")


def test_unknown_name_on_a_bare_machine_lands_on_capcut(settings):
    """Không có giọng offline nào → resolve phải rơi về CapCut, không nổ."""
    synth = get_synthesizer(get_target("vi"), settings, "Không Hề Tồn Tại")
    assert type(synth).__name__ == "CapCutSynthesizer"
    assert voices.is_capcut_voice(synth.voice_name)


def test_constructing_with_a_non_capcut_name_is_rejected(settings):
    from autodub.speech.tts.capcut_vi import CapCutSynthesizer

    with pytest.raises(ValueError):
        CapCutSynthesizer(settings, voice_name="Hoàng Nam")


# ---------------------------------------------------------- tổng hợp ----- #

def test_sanitize_strips_cjk_and_caps_length():
    from autodub.speech.tts.capcut_vi import sanitize_capcut_text

    assert "你好" not in sanitize_capcut_text("Xin chào 你好 thế")
    long = "a" * 400
    assert len(sanitize_capcut_text(long)) <= 281


def test_invalid_text_skips_retries_and_writes_silence(settings, tmp_path, monkeypatch):
    from autodub.speech.tts.capcut_vi import CapCutSynthesizer

    synth = CapCutSynthesizer(settings, voice_name="Nhỏ Ngọt Ngào")
    calls = []

    def _fail(text):
        calls.append(text)
        raise RuntimeError(
            "TTS Task failed: {'data': {'tasks': [{'status': 'failed', "
            "'err_code': 40402002, 'err_msg': 'TTSInvalidText'}]}}"
        )

    monkeypatch.setattr(synth, "_fetch_mp3", _fail)
    out = str(tmp_path / "seg_invalid.wav")
    result = synth.synthesize("câu bị từ chối", out)
    assert result.rate_applied == "silence"
    assert os.path.isfile(out)
    assert len(calls) == 1


def test_blank_line_never_calls_the_network(settings, tmp_path, monkeypatch):
    """Dòng trống → clip im lặng; một dòng rỗng không được làm đổ cả video."""
    from autodub.speech.tts.capcut_vi import CapCutSynthesizer

    synth = CapCutSynthesizer(settings, voice_name="Nhỏ Ngọt Ngào")

    def _boom(text):
        raise AssertionError("không được gọi mạng cho dòng trống")

    monkeypatch.setattr(synth, "_fetch_mp3", _boom)
    out = str(tmp_path / "seg_00001.wav")
    result = synth.synthesize("  ,, ", out)
    assert result.rate_applied == "silence"
    assert os.path.isfile(out)


def test_network_failure_retries_then_raises_with_a_way_out(settings,
                                                            monkeypatch):
    """Hết lượt thử phải ném lỗi có hướng xử lý, không nuốt lỗi im lặng."""
    from autodub.speech.tts import capcut_vi
    from autodub.speech.tts.capcut_vi import CapCutSynthesizer

    synth = CapCutSynthesizer(settings, voice_name="Nhỏ Ngọt Ngào")
    calls = []

    def _fail(**kwargs):
        calls.append(kwargs)
        raise OSError("mạng hỏng")

    monkeypatch.setattr(synth._client, "generate_speech", _fail)
    monkeypatch.setattr(capcut_vi.time, "sleep", lambda s: None)
    with pytest.raises(RuntimeError) as excinfo:
        synth._fetch_mp3("xin chào")
    assert len(calls) == capcut_vi.RETRIES
    assert "offline" in str(excinfo.value).lower()


def test_a_transient_failure_is_survived(settings, monkeypatch):
    from autodub.speech.tts import capcut_vi
    from autodub.speech.tts.capcut_vi import CapCutSynthesizer

    synth = CapCutSynthesizer(settings, voice_name="Nhỏ Ngọt Ngào")
    attempts = []

    def _flaky(**kwargs):
        attempts.append(1)
        if len(attempts) == 1:
            raise OSError("mạng chập chờn")
        return {"speech_url": "https://example.invalid/a.mp3"}

    class _Resp:
        content = b"ID3fake"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(synth._client, "generate_speech", _flaky)
    monkeypatch.setattr(synth._client.session, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(capcut_vi.time, "sleep", lambda s: None)
    assert synth._fetch_mp3("xin chào") == b"ID3fake"
    assert len(attempts) == 2


# --------------------------------------------------------- bị chặn ------- #

_SHARK = ("No task returned from API: {'ret': '-6', "
          "'errmsg': 'shark block only', 'svr_time': 1786158435}")


def _blocking_client(synth, monkeypatch, ok_after=None, block_if=None):
    """Máy chủ chặn request. ``ok_after``: hết chặn từ lần gọi thứ N.

    ``block_if(device_id)`` cho phép mô tả kiểu chặn phụ thuộc định danh.
    """
    devices = []

    class _Resp:
        content = b"ID3fake"

        def raise_for_status(self):
            pass

    def _install(client):
        def _call(**kwargs):
            did = synth._device["device_id"]
            devices.append(did)
            if block_if is not None:
                blocked = block_if(did)
            else:
                blocked = ok_after is None or len(devices) < ok_after
            if blocked:
                raise RuntimeError(_SHARK)
            return {"speech_url": "https://example.invalid/a.mp3"}

        monkeypatch.setattr(client, "generate_speech", _call)
        monkeypatch.setattr(client.session, "get", lambda *a, **k: _Resp())

    _install(synth._client)
    # Đổi định danh sinh ra client mới — phải gắn giả lập vào cả client đó.
    original = capcut_vi.CapCutSynthesizer._reload_device

    def _reload(self, used):
        changed = original(self, used)
        if changed:
            _install(self._client)
        return changed

    monkeypatch.setattr(capcut_vi.CapCutSynthesizer, "_reload_device", _reload)
    return devices


def test_shark_block_switches_to_a_new_device_id(settings, monkeypatch):
    """Bị chặn thì phải đổi định danh máy, không gửi lại y hệt ID đã chết."""
    from autodub.speech.tts.capcut_vi import CapCutSynthesizer

    synth = CapCutSynthesizer(settings, voice_name="Nhỏ Ngọt Ngào")
    monkeypatch.setattr(capcut_vi.time, "sleep", lambda s: None)
    devices = _blocking_client(synth, monkeypatch, ok_after=2)
    assert synth._fetch_mp3("xin chào") == b"ID3fake"
    assert devices[0] != devices[1], "phải gửi lại bằng định danh khác"


def test_shark_block_gives_up_instead_of_rotating_forever(settings,
                                                          monkeypatch):
    """Chặn dai dẳng thì dừng sớm với lời khuyên, không đổi ID vô hạn."""
    from autodub.speech.tts.capcut_vi import CapCutSynthesizer

    synth = CapCutSynthesizer(settings, voice_name="Nhỏ Ngọt Ngào")
    monkeypatch.setattr(capcut_vi.time, "sleep", lambda s: None)
    devices = _blocking_client(synth, monkeypatch)
    with pytest.raises(RuntimeError) as excinfo:
        synth._fetch_mp3("xin chào")
    assert len(devices) == capcut_vi.MAX_ROTATIONS + 1
    assert len(set(devices)) == len(devices), "mỗi lần thử một định danh khác"
    assert "shark block" in str(excinfo.value).lower()


def test_a_successful_read_restores_the_rotation_budget(settings, monkeypatch):
    """Video dài bị chặn rải rác vẫn phải chạy hết, không cụt giữa chừng."""
    from autodub.speech.tts.capcut_vi import CapCutSynthesizer

    synth = CapCutSynthesizer(settings, voice_name="Nhỏ Ngọt Ngào")
    monkeypatch.setattr(capcut_vi.time, "sleep", lambda s: None)
    # Mỗi định danh chỉ đọc trôi đúng một câu rồi bị chặn — chặn rải rác.
    seen = set()

    def _block_if(device_id):
        if device_id in seen:
            return True
        seen.add(device_id)
        return False

    _blocking_client(synth, monkeypatch, block_if=_block_if)
    for _ in range(capcut_vi.MAX_ROTATIONS + 2):
        assert synth._fetch_mp3("xin chào") == b"ID3fake"


def test_threads_scale_safely_with_device_pool():
    """Device pool đa thiết bị cho phép chạy đa luồng an toàn."""
    assert capcut_vi.RECOMMENDED_THREADS >= 4
    assert capcut_vi.MIN_GAP_S > 0


def test_system_busy_retries_without_hard_cooldown(settings, monkeypatch):
    """Khi gặp ret=1014: system busy, hệ thống backoff thử lại thành công mà không phạt cooldown 300s."""
    from autodub.speech.tts.capcut_vi import CapCutSynthesizer

    synth = CapCutSynthesizer(settings, voice_name="Nhỏ Ngọt Ngào")
    attempts = []

    def _busy_then_ok(**kwargs):
        attempts.append(1)
        if len(attempts) < 3:
            raise RuntimeError("create_tts_task ret=1014: system busy")
        return {"speech_url": "https://example.invalid/ok.mp3"}

    class _Resp:
        content = b"ID3fake"

        def raise_for_status(self):
            pass

    monkeypatch.setattr(synth._client, "generate_speech", _busy_then_ok)
    monkeypatch.setattr(synth._client.session, "get", lambda *a, **k: _Resp())
    monkeypatch.setattr(capcut_vi.time, "sleep", lambda s: None)

    # Không được gọi report_block
    block_calls = []
    original_report_block = synth._pool.report_block
    monkeypatch.setattr(synth._pool, "report_block", lambda *a, **k: block_calls.append(1))

    assert synth._fetch_mp3("xin chào") == b"ID3fake"
    assert len(attempts) == 3
    assert len(block_calls) == 0, "Lỗi 1014 không được đưa thiết bị vào cooldown 300s!"


def test_device_pool_generates_diverse_devices():
    from autodub.speech.tts.capcut_device_pool import generate_fake_device, get_device_pool
    dev1 = generate_fake_device(template_idx=0)
    dev2 = generate_fake_device(template_idx=10)

    assert dev1["device_platform"] == "mac"
    assert dev2["device_platform"] == "windows"
    assert dev1["device_id"] != dev2["device_id"]
    assert len(dev1["device_id"]) == 19

    pool = get_device_pool()
    d_a = pool.get_device(0)
    d_b = pool.get_device(1)
    assert d_a and d_b


def test_device_pool_cooldown_and_auto_replacement():
    from autodub.speech.tts.capcut_device_pool import CapCutDevicePool
    pool = CapCutDevicePool(size=8)
    dev = pool.get_device(0)
    rep = pool.report_block(dev, cooldown_seconds=60.0)
    assert rep["device_id"] != dev["device_id"]


def test_extract_speech_url_from_nested_payload():
    from autodub.speech.tts.capcut_api.client import _extract_speech_url

    url = "https://example.invalid/voice.mp3"
    task = {
        "status": "success",
        "payload": json.dumps({"audio_subtitles": [{"speech_url": url}]}),
    }
    assert _extract_speech_url(task) == url
    assert _extract_speech_url({"speech_url": url}) == url
    assert _extract_speech_url({"payload": {"audios": [{"url": url}]}}) == url
    assert _extract_speech_url({"payload": "{}"}) == ""


def test_checked_json_raises_on_nonzero_ret():
    from autodub.speech.tts.capcut_api.client import _checked_json_response
    from autodub.speech.tts.capcut_api.exceptions import CapCutAPIError

    class _Resp:
        status_code = 200
        text = '{"ret":"-6"}'

        def json(self):
            return {"ret": "-6", "errmsg": "shark block only"}

    with pytest.raises(CapCutAPIError) as excinfo:
        _checked_json_response(_Resp(), "create_tts_task")
    assert "shark block" in str(excinfo.value).lower()
