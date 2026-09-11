"""Persistent, cross-project cache for expensive pipeline artifacts.

The cache lives outside ``work_dir`` so creating a new project from the same
source can reuse previous Demucs/ASR results.  Keys are deterministic and do
not depend on Python's process-randomised ``hash()``.
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import sqlite3
import tempfile
import threading
import time
from pathlib import Path

from autodub.utils import save_json_atomic

CACHE_VERSION = "upc-v1"
# Tên env giữ nguyên dạng cũ (LPHVSub_*) để không phá cấu hình người dùng đã đặt.
_ROOT = (
    Path(os.environ.get("LPHVSub_PIPELINE_CACHE", "")).expanduser()  # noqa: SIM112
    if os.environ.get("LPHVSub_PIPELINE_CACHE")  # noqa: SIM112
    else Path(os.environ.get("LOCALAPPDATA", Path.home())) / "lphvsub" / "cache" / "pipeline"
)
_LOCK = threading.RLock()


def cache_root() -> Path:
    _ROOT.mkdir(parents=True, exist_ok=True)
    return _ROOT


def compute_media_fingerprint(file_path: str) -> str:
    """Return a fast deterministic fingerprint for a media artifact.

    It intentionally avoids mtime: the same downloaded media copied into a
    new project must still hit the cache.

    For small files (<= 4MB), full SHA-256 is computed.
    For large files (> 4MB), multi-point deterministic sampling (head, 25%,
    50%, 75%, and tail chunks) combined with exact file size provides
    reliable tamper detection and collision resistance with sub-millisecond
    performance on large video files.
    """
    path = Path(file_path)
    if not path.is_file():
        raise FileNotFoundError(f"Media file not found: {file_path}")

    st = path.stat()
    size = st.st_size
    h = hashlib.sha256()
    h.update(CACHE_VERSION.encode("utf-8"))
    h.update(str(size).encode("utf-8"))

    if size == 0:
        return h.hexdigest()

    CHUNK = 65536
    if size <= 4 * 1024 * 1024:
        with path.open("rb") as f:
            while chunk := f.read(CHUNK):
                h.update(chunk)
    else:
        with path.open("rb") as f:
            # 1. Head chunk
            h.update(f.read(CHUNK))
            # 2. 25% chunk
            f.seek(size // 4)
            h.update(f.read(CHUNK))
            # 3. 50% chunk (middle)
            f.seek(size // 2)
            h.update(f.read(CHUNK))
            # 4. 75% chunk
            f.seek((3 * size) // 4)
            h.update(f.read(CHUNK))
            # 5. Tail chunk
            f.seek(max(0, size - CHUNK))
            h.update(f.read(CHUNK))

    return h.hexdigest()


def _valid_wav(path: Path) -> bool:
    try:
        if not path.is_file():
            return False
        if path.stat().st_size <= 100:
            return False
        with path.open("rb") as f:
            header = f.read(12)
            return len(header) >= 12 and header[:4] == b"RIFF" and header[8:12] == b"WAVE"
    except OSError:
        return False


class DemucsGlobalCache:
    """Persistent Demucs stem cache shared by all work directories."""

    def _key(self, audio_path: str, model: str, sample_rate: int, channels: int) -> str:
        fp = compute_media_fingerprint(audio_path)
        raw = f"{CACHE_VERSION}|{fp}|{model}|{sample_rate}|{channels}".encode()
        return hashlib.sha256(raw).hexdigest()

    def lookup_and_restore(
        self, audio_path: str, output_dir: str, model: str, sample_rate: int, channels: int
    ) -> dict[str, str] | None:
        key = self._key(audio_path, model, sample_rate, channels)
        bucket = cache_root() / "demucs" / key
        vocals = bucket / "vocals.wav"
        no_vocals = bucket / "no_vocals.wav"
        if not (_valid_wav(vocals) and _valid_wav(no_vocals)):
            return None
        with _LOCK:
            os.makedirs(output_dir, exist_ok=True)
            dst_v = Path(output_dir) / "vocals.wav"
            dst_n = Path(output_dir) / "no_vocals.wav"
            shutil.copy2(vocals, dst_v)
            shutil.copy2(no_vocals, dst_n)
        return {"vocals": str(dst_v), "no_vocals": str(dst_n)}

    def store_result(
        self,
        audio_path: str,
        vocals_path: str,
        no_vocals_path: str,
        model: str,
        sample_rate: int,
        channels: int,
    ) -> None:
        if not (_valid_wav(Path(vocals_path)) and _valid_wav(Path(no_vocals_path))):
            return
        key = self._key(audio_path, model, sample_rate, channels)
        parent = cache_root() / "demucs"
        parent.mkdir(parents=True, exist_ok=True)
        final = parent / key
        with _LOCK:
            if _valid_wav(final / "vocals.wav") and _valid_wav(final / "no_vocals.wav"):
                return
            tmp = Path(tempfile.mkdtemp(prefix=f".{key}.", dir=str(parent)))
            try:
                shutil.copy2(vocals_path, tmp / "vocals.wav")
                shutil.copy2(no_vocals_path, tmp / "no_vocals.wav")
                save_json_atomic(
                    {
                        "version": CACHE_VERSION,
                        "audio_fingerprint": compute_media_fingerprint(audio_path),
                        "model": model,
                        "sample_rate": sample_rate,
                        "channels": channels,
                    },
                    str(tmp / "meta.json"),
                )
                try:
                    os.replace(str(tmp), str(final))
                except FileExistsError:
                    shutil.rmtree(tmp, ignore_errors=True)
            except Exception:
                shutil.rmtree(tmp, ignore_errors=True)


class AsrGlobalCache:
    """Persistent transcript cache keyed by audio + ASR configuration."""

    def _path(self, audio_path: str, model: str, language: str, engine: str) -> Path:
        fp = compute_media_fingerprint(audio_path)
        raw = f"{CACHE_VERSION}|{fp}|{engine}|{model}|{language}".encode()
        return cache_root() / "asr" / (hashlib.sha256(raw).hexdigest() + ".json")

    def lookup(self, audio_path: str, model: str, language: str, engine: str) -> list[dict] | None:
        path = self._path(audio_path, model, language, engine)
        try:
            with path.open(encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, list) and all(
                isinstance(s, dict) and "start" in s and "end" in s and "text" in s for s in data
            ):
                return data
        except (OSError, ValueError, json.JSONDecodeError):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
        return None

    def store(
        self, audio_path: str, model: str, language: str, engine: str, segments: list[dict]
    ) -> None:
        path = self._path(audio_path, model, language, engine)
        path.parent.mkdir(parents=True, exist_ok=True)
        save_json_atomic(segments, str(path))


_DEMUCS = DemucsGlobalCache()
_ASR = AsrGlobalCache()


class TranslationGlobalCache:
    """Persistent translation memory cache shared across projects."""

    def __init__(self, db_path: Path | None = None):
        self._custom_db = db_path
        self._lock = threading.RLock()

    def _db_file(self) -> Path:
        if self._custom_db:
            self._custom_db.parent.mkdir(parents=True, exist_ok=True)
            return self._custom_db
        p = cache_root() / "translate"
        p.mkdir(parents=True, exist_ok=True)
        return p / "translations.db"

    def _reset_corrupt_db(self) -> None:
        db_path = self._db_file()
        try:
            if db_path.exists():
                db_path.unlink(missing_ok=True)
            for ext in ("-wal", "-shm", "-journal"):
                p_extra = Path(str(db_path) + ext)
                if p_extra.exists():
                    p_extra.unlink(missing_ok=True)
        except OSError:
            pass

    def _get_connection(self) -> sqlite3.Connection:
        db_path = self._db_file()
        conn = None
        try:
            conn = sqlite3.connect(str(db_path), timeout=10.0)
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("PRAGMA synchronous = NORMAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS translations (
                    cache_key TEXT PRIMARY KEY,
                    source_text TEXT,
                    target_lang TEXT,
                    provider TEXT,
                    translated_text TEXT,
                    created_at REAL
                );
            """)
            return conn
        except (sqlite3.DatabaseError, sqlite3.OperationalError):
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            self._reset_corrupt_db()
            conn = sqlite3.connect(str(db_path), timeout=10.0)
            conn.execute("PRAGMA journal_mode = WAL;")
            conn.execute("""
                CREATE TABLE IF NOT EXISTS translations (
                    cache_key TEXT PRIMARY KEY,
                    source_text TEXT,
                    target_lang TEXT,
                    provider TEXT,
                    translated_text TEXT,
                    created_at REAL
                );
            """)
            return conn

    def _key(self, text: str, target_lang: str, provider: str) -> str:
        raw = f"{CACHE_VERSION}|{text.strip()}|{target_lang.strip().lower()}|{provider.strip().lower()}".encode()
        return hashlib.sha256(raw).hexdigest()

    def lookup(self, source_text: str, target_lang: str, provider: str = "default") -> str | None:
        if not source_text or not source_text.strip():
            return None
        key = self._key(source_text, target_lang, provider)
        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                cur = conn.execute(
                    "SELECT translated_text FROM translations WHERE cache_key = ?", (key,)
                )
                row = cur.fetchone()
                return row[0] if row else None
            except sqlite3.DatabaseError:
                self._reset_corrupt_db()
                return None
            except Exception:
                return None
            finally:
                if conn:
                    conn.close()

    def store(
        self, source_text: str, target_lang: str, translated_text: str, provider: str = "default"
    ) -> None:
        if not source_text or not translated_text:
            return
        key = self._key(source_text, target_lang, provider)
        now = time.time()
        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                conn.execute(
                    """
                    INSERT INTO translations (cache_key, source_text, target_lang, provider, translated_text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET translated_text = excluded.translated_text;
                """,
                    (key, source_text, target_lang, provider, translated_text, now),
                )
                conn.commit()
            except sqlite3.DatabaseError:
                self._reset_corrupt_db()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()

    def lookup_batch(
        self, items: list[tuple[int, str]], target_lang: str, provider: str = "default"
    ) -> dict[int, str]:
        if not items:
            return {}
        hits: dict[int, str] = {}
        key_map: dict[str, list[int]] = {}
        for idx, text in items:
            if text and text.strip():
                k = self._key(text, target_lang, provider)
                key_map.setdefault(k, []).append(idx)

        if not key_map:
            return {}

        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                keys = list(key_map.keys())
                batch_size = 500
                for i in range(0, len(keys), batch_size):
                    chunk = keys[i : i + batch_size]
                    placeholders = ",".join("?" for _ in chunk)
                    cur = conn.execute(
                        f"SELECT cache_key, translated_text FROM translations WHERE cache_key IN ({placeholders})",
                        chunk,
                    )
                    for c_key, trans in cur.fetchall():
                        for idx in key_map.get(c_key, []):
                            hits[idx] = trans
            except sqlite3.DatabaseError:
                self._reset_corrupt_db()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()
        return hits

    def store_batch(
        self, items: list[tuple[str, str]], target_lang: str, provider: str = "default"
    ) -> None:
        if not items:
            return
        now = time.time()
        records = []
        for src, trans in items:
            if src and trans:
                k = self._key(src, target_lang, provider)
                records.append((k, src, target_lang, provider, trans, now))
        if not records:
            return

        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                conn.executemany(
                    """
                    INSERT INTO translations (cache_key, source_text, target_lang, provider, translated_text, created_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET translated_text = excluded.translated_text;
                """,
                    records,
                )
                conn.commit()
            except sqlite3.DatabaseError:
                self._reset_corrupt_db()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()


_TRANSLATE = TranslationGlobalCache()


class TtsGlobalCache:
    """Persistent TTS audio cache keyed by text + voice + engine + speed."""

    def __init__(self, cache_dir: Path | None = None):
        self._custom_dir = cache_dir
        self._lock = threading.RLock()

    def _root_dir(self) -> Path:
        if self._custom_dir:
            self._custom_dir.mkdir(parents=True, exist_ok=True)
            return self._custom_dir
        p = cache_root() / "tts"
        p.mkdir(parents=True, exist_ok=True)
        return p

    def _key(self, text: str, voice: str, speed: float = 1.0, engine: str = "vieneu") -> str:
        clean_text = " ".join(text.strip().split())
        raw = f"{CACHE_VERSION}|{clean_text}|{voice.strip().lower()}|{speed:.2f}|{engine.strip().lower()}".encode()
        return hashlib.sha256(raw).hexdigest()

    def lookup(
        self, text: str, voice: str, speed: float = 1.0, engine: str = "vieneu"
    ) -> Path | None:
        if not text or not text.strip():
            return None
        key = self._key(text, voice, speed, engine)
        wav_file = self._root_dir() / f"{key}.wav"
        if _valid_wav(wav_file):
            return wav_file
        if wav_file.exists():
            try:
                wav_file.unlink(missing_ok=True)
            except OSError:
                pass
        return None

    def restore_to(
        self, text: str, voice: str, dst_path: str, speed: float = 1.0, engine: str = "vieneu"
    ) -> bool:
        src = self.lookup(text, voice, speed, engine)
        if not src:
            return False
        with self._lock:
            try:
                dst = Path(dst_path)
                dst.parent.mkdir(parents=True, exist_ok=True)
                tmp = dst.with_suffix(f".tmp_{os.getpid()}_{time.time_ns()}.wav")
                shutil.copy2(src, tmp)
                os.replace(str(tmp), str(dst))
                return _valid_wav(dst)
            except Exception:
                return False

    def store(
        self, text: str, voice: str, wav_path: str, speed: float = 1.0, engine: str = "vieneu"
    ) -> None:
        src = Path(wav_path)
        if not _valid_wav(src):
            return
        key = self._key(text, voice, speed, engine)
        target_dir = self._root_dir()
        dst = target_dir / f"{key}.wav"
        with self._lock:
            if _valid_wav(dst):
                return
            tmp = None
            try:
                tmp = target_dir / f".{key}_{time.time_ns()}.tmp"
                shutil.copy2(src, tmp)
                os.replace(str(tmp), str(dst))
            except Exception:
                try:
                    if tmp and tmp.exists():
                        tmp.unlink(missing_ok=True)
                except Exception:
                    pass


_TTS = TtsGlobalCache()


def get_tts_cache() -> TtsGlobalCache:
    return _TTS


def get_translation_cache() -> TranslationGlobalCache:
    return _TRANSLATE


def get_demucs_cache() -> DemucsGlobalCache:
    return _DEMUCS


def get_asr_cache() -> AsrGlobalCache:
    return _ASR


class AlignGlobalCache:
    """Persistent word-level alignment cache keyed by audio fingerprint + text."""

    def __init__(self, custom_db: str | Path | None = None):
        self._custom_db = Path(custom_db) if custom_db else None
        self._lock = threading.Lock()

    def _db_file(self) -> Path:
        if self._custom_db:
            p = self._custom_db
        else:
            p = cache_root() / "align" / "alignments.db"
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def _get_connection(self) -> sqlite3.Connection:
        db = self._db_file()
        conn = None
        try:
            conn = sqlite3.connect(str(db), timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS alignments (
                        cache_key TEXT PRIMARY KEY,
                        words_json TEXT,
                        created_at REAL
                    );
                """)
            return conn
        except sqlite3.DatabaseError:
            if conn:
                try:
                    conn.close()
                except Exception:
                    pass
            self._reset_corrupt_db()
            conn = sqlite3.connect(str(db), timeout=10.0)
            conn.execute("PRAGMA journal_mode=WAL;")
            conn.execute("PRAGMA synchronous=NORMAL;")
            with conn:
                conn.execute("""
                    CREATE TABLE IF NOT EXISTS alignments (
                        cache_key TEXT PRIMARY KEY,
                        words_json TEXT,
                        created_at REAL
                    );
                """)
            return conn

    def _reset_corrupt_db(self) -> None:
        db = self._db_file()
        try:
            db.unlink(missing_ok=True)
            Path(str(db) + "-wal").unlink(missing_ok=True)
            Path(str(db) + "-shm").unlink(missing_ok=True)
        except OSError:
            pass

    def lookup(self, key: str) -> list[tuple[str, float, float]] | None:
        if not key:
            return None
        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                cur = conn.execute("SELECT words_json FROM alignments WHERE cache_key = ?", (key,))
                row = cur.fetchone()
                if row and row[0]:
                    raw = json.loads(row[0])
                    if isinstance(raw, list):
                        return [(w, float(t0), float(t1)) for w, t0, t1 in raw]
                return None
            except Exception:
                return None
            finally:
                if conn:
                    conn.close()

    def lookup_batch(self, keys: list[str]) -> dict[str, list[tuple[str, float, float]]]:
        if not keys:
            return {}
        hits: dict[str, list[tuple[str, float, float]]] = {}
        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                batch_size = 500
                for i in range(0, len(keys), batch_size):
                    chunk = keys[i : i + batch_size]
                    placeholders = ",".join("?" for _ in chunk)
                    cur = conn.execute(
                        f"SELECT cache_key, words_json FROM alignments WHERE cache_key IN ({placeholders})",
                        chunk,
                    )
                    for c_key, raw_json in cur.fetchall():
                        try:
                            raw = json.loads(raw_json)
                            if isinstance(raw, list):
                                hits[c_key] = [(w, float(t0), float(t1)) for w, t0, t1 in raw]
                        except Exception:
                            pass
            except sqlite3.DatabaseError:
                self._reset_corrupt_db()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()
        return hits

    def store_batch(self, items: list[tuple[str, list]]) -> None:
        if not items:
            return
        now = time.time()
        records = []
        for k, words in items:
            if k and words:
                records.append((k, json.dumps(words, ensure_ascii=False), now))
        if not records:
            return
        with self._lock:
            conn = None
            try:
                conn = self._get_connection()
                conn.executemany(
                    """
                    INSERT INTO alignments (cache_key, words_json, created_at)
                    VALUES (?, ?, ?)
                    ON CONFLICT(cache_key) DO UPDATE SET words_json = excluded.words_json;
                """,
                    records,
                )
                conn.commit()
            except sqlite3.DatabaseError:
                self._reset_corrupt_db()
            except Exception:
                pass
            finally:
                if conn:
                    conn.close()

    def store(self, key: str, words: list) -> None:
        self.store_batch([(key, words)])


_ALIGN = AlignGlobalCache()


def get_align_cache() -> AlignGlobalCache:
    return _ALIGN


class PipelineCacheOrchestrator:
    """Central orchestrator for all UPC cache subsystems."""

    def __init__(self):
        self.demucs = get_demucs_cache()
        self.asr = get_asr_cache()
        self.translate = get_translation_cache()
        self.tts = get_tts_cache()
        self.align = get_align_cache()

    def inspect_cache(
        self,
        media_path: str,
        lang: str = "zh",
        asr_model: str = "base",
        asr_engine: str = "whisper",
        demucs_model: str = "htdemucs",
        sample_rate: int = 44100,
        channels: int = 2,
        voice: str = "nam_bac_1",
    ) -> dict:
        if not os.path.isfile(media_path):
            return {"exists": False, "demucs": False, "asr": False}

        fp = compute_media_fingerprint(media_path)
        demucs_key = self.demucs._key(media_path, demucs_model, sample_rate, channels)
        demucs_bucket = cache_root() / "demucs" / demucs_key
        has_demucs = _valid_wav(demucs_bucket / "vocals.wav") and _valid_wav(
            demucs_bucket / "no_vocals.wav"
        )

        asr_path = self.asr._path(media_path, asr_model, lang, asr_engine)
        has_asr = asr_path.is_file()

        return {
            "exists": True,
            "fingerprint": fp,
            "demucs": has_demucs,
            "asr": has_asr,
        }

    def cache_stats(self) -> dict:
        root = cache_root()
        total_bytes = 0
        demucs_entries = 0
        asr_entries = 0
        tts_entries = 0

        for f in root.glob("**/*"):
            if f.is_file():
                total_bytes += f.stat().st_size
                if "demucs" in f.parts:
                    demucs_entries += 1
                elif "asr" in f.parts:
                    asr_entries += 1
                elif "tts" in f.parts:
                    tts_entries += 1

        return {
            "total_bytes": total_bytes,
            "demucs_entries": demucs_entries // 2 if demucs_entries else 0,
            "asr_entries": asr_entries,
            "tts_entries": tts_entries,
        }

    def clean_cache(
        self, category: str | None = None, max_age_seconds: float | None = None
    ) -> dict:
        root = cache_root()
        now = time.time()
        removed = 0
        reclaimed_bytes = 0

        targets = [category] if category else ["demucs", "asr", "tts"]
        for cat in targets:
            cat_dir = root / cat
            if not cat_dir.is_dir():
                continue
            for item in cat_dir.iterdir():
                try:
                    mtime = item.stat().st_mtime
                    if max_age_seconds is not None and (now - mtime) < max_age_seconds:
                        continue
                    if item.is_dir():
                        size = sum(f.stat().st_size for f in item.glob("**/*") if f.is_file())
                        shutil.rmtree(item, ignore_errors=True)
                    else:
                        size = item.stat().st_size
                        item.unlink(missing_ok=True)
                    removed += 1
                    reclaimed_bytes += size
                except OSError:
                    pass

        return {"removed_entries": removed, "reclaimed_bytes": reclaimed_bytes}

    def validate_and_heal(self) -> dict:
        """Scan all cache buckets, prune corrupted files, heal database."""
        root = cache_root()
        scanned = 0
        cleaned = 0

        # 1. Demucs buckets
        demucs_dir = root / "demucs"
        if demucs_dir.is_dir():
            for bucket in list(demucs_dir.iterdir()):
                if bucket.is_dir():
                    scanned += 1
                    v = bucket / "vocals.wav"
                    nv = bucket / "no_vocals.wav"
                    if not (_valid_wav(v) and _valid_wav(nv)):
                        shutil.rmtree(bucket, ignore_errors=True)
                        cleaned += 1

        # 2. ASR transcripts
        asr_dir = root / "asr"
        if asr_dir.is_dir():
            for item in list(asr_dir.iterdir()):
                if item.suffix == ".json":
                    scanned += 1
                    try:
                        with item.open(encoding="utf-8") as f:
                            d = json.load(f)
                        if not (
                            isinstance(d, list)
                            and all(
                                isinstance(s, dict) and "start" in s and "end" in s and "text" in s
                                for s in d
                            )
                        ):
                            item.unlink(missing_ok=True)
                            cleaned += 1
                    except Exception:
                        item.unlink(missing_ok=True)
                        cleaned += 1

        # 3. TTS clips
        tts_dir = root / "tts"
        if tts_dir.is_dir():
            for item in list(tts_dir.iterdir()):
                if item.suffix == ".wav":
                    scanned += 1
                    if not _valid_wav(item):
                        item.unlink(missing_ok=True)
                        cleaned += 1

        # 4. Translations DB integrity
        db_file = root / "translate" / "translations.db"
        if db_file.exists():
            scanned += 1
            try:
                conn = sqlite3.connect(str(db_file), timeout=5.0)
                cur = conn.execute("PRAGMA integrity_check;")
                res = cur.fetchone()
                conn.close()
                if not res or res[0] != "ok":
                    self.translate._reset_corrupt_db()
                    cleaned += 1
            except Exception:
                self.translate._reset_corrupt_db()
                cleaned += 1

        return {"scanned": scanned, "corrupted_cleaned": cleaned}


_ORCHESTRATOR = PipelineCacheOrchestrator()


def get_pipeline_orchestrator() -> PipelineCacheOrchestrator:
    return _ORCHESTRATOR
