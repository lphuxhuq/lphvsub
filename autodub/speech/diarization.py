"""100% Offline Speaker Diarization via Acoustic Feature Clustering.

Extracts multi-feature acoustic embeddings (MFCCs, F0 pitch stats,
spectral centroid/rolloff, subband energy, RMS dynamics)
and performs unsupervised clustering (Agglomerative Clustering with Cosine Metric &
Silhouette Score auto-K estimation) to assign speaker_id (0, 1, ...) to ASR segments.

Operates completely offline without HuggingFace authentication tokens or PyTorch.
"""
from __future__ import annotations

import os
import wave
from dataclasses import dataclass, field
import numpy as np
from scipy import fft, signal
from sklearn.cluster import AgglomerativeClustering
from sklearn.metrics import silhouette_score
from sklearn.metrics.pairwise import cosine_distances

from autodub.utils import setup_logging

logger = setup_logging("autodub.diarization")

# --- Acoustic & Clustering Hyperparameters ---
FRAME_S: float = 0.025            # 25 ms analysis frame (400 samples @ 16kHz)
HOP_S: float = 0.010              # 10 ms frame shift (160 samples @ 16kHz)
N_FFT: int = 512                  # Real FFT point size
N_MELS: int = 26                  # Mel filterbank channels
N_MFCC: int = 13                  # MFCC coefficient count
FMIN_HZ: float = 60.0             # Minimum human pitch search
FMAX_HZ: float = 400.0            # Maximum human pitch search
ABS_ENERGY_FLOOR: float = 0.005   # Minimum RMS energy threshold for speech
DISTANCE_THRESHOLD: float = 0.30  # Max cosine distance for single-speaker classification
SILHOUETTE_THRESHOLD: float = 0.20 # Min silhouette score for multi-speaker split
MAX_SPEAKERS_DEFAULT: int = 4     # Default upper bound on auto-detected speakers
MIN_SPEECH_DURATION: float = 0.15 # Minimum segment duration to extract voiceprint


@dataclass
class DiarizationResult:
    """Structured result of speaker diarization."""
    speaker_ids: list[int]
    num_speakers: int
    confidence: float
    speaker_durations: dict[int, float] = field(default_factory=dict)


def _get_mel_filterbank(sr: int = 16000, n_fft: int = 512, n_mels: int = 26) -> np.ndarray:
    """Construct triangular Mel filterbank matrix (n_mels, n_fft // 2 + 1)."""
    m_min = 2595.0 * np.log10(1.0 + 0.0 / 700.0)
    m_max = 2595.0 * np.log10(1.0 + (sr / 2.0) / 700.0)
    m_pts = np.linspace(m_min, m_max, n_mels + 2)
    f_pts = 700.0 * (10.0 ** (m_pts / 2595.0) - 1.0)
    bins = np.floor((n_fft + 1) * f_pts / sr).astype(int)

    fb = np.zeros((n_mels, n_fft // 2 + 1), dtype=np.float32)
    for m in range(1, n_mels + 1):
        f_m_minus = bins[m - 1]
        f_m = bins[m]
        f_m_plus = bins[m + 1]
        if f_m > f_m_minus:
            fb[m - 1, f_m_minus:f_m] = (np.arange(f_m_minus, f_m) - f_m_minus) / (f_m - f_m_minus)
        if f_m_plus > f_m:
            fb[m - 1, f_m:f_m_plus] = (f_m_plus - np.arange(f_m, f_m_plus)) / (f_m_plus - f_m)
    return fb

_CACHED_MEL_FB = _get_mel_filterbank()


def _compute_deltas(feat: np.ndarray, n: int = 2) -> np.ndarray:
    """Compute temporal regression delta coefficients."""
    n_frames, n_feats = feat.shape
    if n_frames <= 1:
        return np.zeros_like(feat)
    deltas = np.zeros_like(feat)
    denom = 2 * sum(i ** 2 for i in range(1, n + 1))
    for t in range(n_frames):
        num = np.zeros(n_feats, dtype=np.float32)
        for i in range(1, n + 1):
            t_plus = min(t + i, n_frames - 1)
            t_minus = max(t - i, 0)
            num += i * (feat[t_plus] - feat[t_minus])
        deltas[t] = num / denom
    return deltas


def estimate_frame_f0(
    frame: np.ndarray,
    sr: int = 16000,
    fmin: float = FMIN_HZ,
    fmax: float = FMAX_HZ,
    threshold: float = 0.30,
) -> float:
    """Estimate fundamental frequency (F0 in Hz) of a single frame via Normalized Autocorrelation."""
    if len(frame) == 0:
        return 0.0
    x = frame - np.mean(frame)
    energy = np.sum(x ** 2)
    if energy < 1e-7:
        return 0.0

    min_lag = int(sr / fmax)
    max_lag = int(sr / fmin)
    if max_lag >= len(x):
        max_lag = len(x) - 1
    if min_lag >= max_lag:
        return 0.0

    corr = signal.correlate(x, x, mode="full")[len(x) - 1:]
    norm_corr = corr / energy

    search_region = norm_corr[min_lag:max_lag + 1]
    if len(search_region) == 0:
        return 0.0
    peak_idx = int(np.argmax(search_region))
    peak_val = search_region[peak_idx]

    if peak_val >= threshold:
        best_lag = min_lag + peak_idx
        return float(sr / best_lag)
    return 0.0


def extract_acoustic_embedding(audio_clip: np.ndarray, sr: int = 16000) -> np.ndarray:
    """Extract a 100-dimensional acoustic voiceprint embedding from a speech clip."""
    if len(audio_clip) == 0:
        return np.zeros(100, dtype=np.float32)

    frame_len = int(FRAME_S * sr)
    hop_len = int(HOP_S * sr)
    if len(audio_clip) < frame_len:
        audio_clip = np.pad(audio_clip, (0, frame_len - len(audio_clip)))

    # Frame slicing
    n_frames = 1 + (len(audio_clip) - frame_len) // hop_len
    frames = np.lib.stride_tricks.sliding_window_view(audio_clip[: (n_frames - 1) * hop_len + frame_len], frame_len)[::hop_len]
    
    # Windowing
    win = signal.windows.hann(frame_len, sym=False)
    w_frames = frames * win

    # FFT & Power spectrum
    spec = np.abs(fft.rfft(w_frames, n=N_FFT))
    power_spec = (spec ** 2) / N_FFT

    # Mel filterbank
    fb = _CACHED_MEL_FB if (sr == 16000 and N_FFT == 512) else _get_mel_filterbank(sr, N_FFT, N_MELS)
    mel_spec = np.dot(power_spec, fb.T)
    log_mel = np.log(np.maximum(mel_spec, 1e-6))

    # DCT to MFCC
    mfcc = fft.dct(log_mel, type=2, axis=1, norm="ortho")[:, :N_MFCC]
    delta_mfcc = _compute_deltas(mfcc)
    delta2_mfcc = _compute_deltas(delta_mfcc)

    # MFCC stats (13 * 6 = 78 dims)
    mfcc_all = np.hstack([mfcc, delta_mfcc, delta2_mfcc])
    mfcc_mean = np.mean(mfcc_all, axis=0)
    mfcc_std = np.std(mfcc_all, axis=0)
    mfcc_features = np.hstack([mfcc_mean, mfcc_std])  # 78 dims

    # F0 Pitch stats (4 dims)
    f0_list = [estimate_frame_f0(fr, sr=sr) for fr in frames]
    voiced_f0 = [f for f in f0_list if f > 0]
    if voiced_f0:
        f0_mean = float(np.mean(voiced_f0))
        f0_std = float(np.std(voiced_f0))
        f0_min = float(np.min(voiced_f0))
        f0_max = float(np.max(voiced_f0))
    else:
        f0_mean = f0_std = f0_min = f0_max = 0.0
    f0_features = np.array([f0_mean, f0_std, f0_min, f0_max], dtype=np.float32)

    # Spectral Centroid & Rolloff (4 dims)
    freqs = np.linspace(0, sr / 2, N_FFT // 2 + 1)
    tot_p = np.sum(power_spec, axis=1, keepdims=True) + 1e-9
    centroids = np.sum(power_spec * freqs, axis=1, keepdims=True) / tot_p
    cum_p = np.cumsum(power_spec, axis=1)
    rolloff_idx = np.argmax(cum_p >= 0.85 * tot_p, axis=1)
    rolloffs = freqs[rolloff_idx]
    spec_features = np.array([
        float(np.mean(centroids)), float(np.std(centroids)),
        float(np.mean(rolloffs)), float(np.std(rolloffs)),
    ], dtype=np.float32)

    # Subband Energy Ratios (6 dims)
    band1 = np.sum(power_spec[:, : N_FFT // 8], axis=1)
    band2 = np.sum(power_spec[:, N_FFT // 8 : N_FFT // 4], axis=1)
    band3 = np.sum(power_spec[:, N_FFT // 4 :], axis=1)
    tot_b = band1 + band2 + band3 + 1e-9
    r1, r2, r3 = band1 / tot_b, band2 / tot_b, band3 / tot_b
    subband_features = np.array([
        float(np.mean(r1)), float(np.std(r1)),
        float(np.mean(r2)), float(np.std(r2)),
        float(np.mean(r3)), float(np.std(r3)),
    ], dtype=np.float32)

    # RMS Dynamics (8 dims)
    rms = np.sqrt(np.mean(frames ** 2, axis=1) + 1e-9)
    rms_feats = np.array([
        float(np.mean(rms)), float(np.std(rms)),
        float(np.percentile(rms, 10)), float(np.percentile(rms, 25)),
        float(np.percentile(rms, 50)), float(np.percentile(rms, 75)),
        float(np.percentile(rms, 90)), float(np.max(rms) - np.min(rms)),
    ], dtype=np.float32)

    # Assemble 100 dims
    raw_emb = np.hstack([mfcc_features, f0_features, spec_features, subband_features, rms_feats]).astype(np.float32)
    norm = np.linalg.norm(raw_emb)
    return raw_emb / (norm + 1e-9)


def load_audio_mono16k(audio_path: str) -> tuple[np.ndarray, int]:
    """Read a WAV file as mono 16kHz float32 array in [-1.0, 1.0]."""
    with wave.open(audio_path, "rb") as wf:
        n_channels = wf.getnchannels()
        sampwidth = wf.getsampwidth()
        sr = wf.getframerate()
        n_frames = wf.getnframes()
        raw = wf.readframes(n_frames)

    if sampwidth == 2:
        data = np.frombuffer(raw, dtype=np.int16).astype(np.float32) / 32768.0
    elif sampwidth == 4:
        data = np.frombuffer(raw, dtype=np.int32).astype(np.float32) / 2147483648.0
    elif sampwidth == 1:
        data = (np.frombuffer(raw, dtype=np.uint8).astype(np.float32) - 128.0) / 128.0
    else:
        data = np.frombuffer(raw, dtype=np.float32)

    if n_channels > 1:
        data = data.reshape(-1, n_channels).mean(axis=1)

    if sr != 16000:
        # Resample to 16kHz
        num_target_samples = int(len(data) * 16000 / sr)
        data = signal.resample(data, num_target_samples)
        sr = 16000

    return data, sr


def estimate_num_speakers(
    emb_matrix: np.ndarray,
    min_speakers: int = 1,
    max_speakers: int = 4,
    distance_threshold: float = DISTANCE_THRESHOLD,
    silhouette_threshold: float = SILHOUETTE_THRESHOLD,
) -> tuple[int, float]:
    """Estimate optimal number of speakers using Silhouette analysis & distance clustering."""
    n_samples = len(emb_matrix)
    if n_samples <= 1:
        return 1, 1.0

    dist_mat = cosine_distances(emb_matrix)
    upper_tri = dist_mat[np.triu_indices(n_samples, k=1)]
    if len(upper_tri) == 0 or np.percentile(upper_tri, 90) < distance_threshold:
        return 1, 1.0

    max_k = min(max_speakers, n_samples - 1)
    if max_k < 2:
        return 1, 1.0

    best_k = 1
    best_score = -1.0

    for k in range(2, max_k + 1):
        clustering = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average")
        labels = clustering.fit_predict(emb_matrix)
        if len(set(labels)) < 2:
            continue
        try:
            score = float(silhouette_score(emb_matrix, labels, metric="cosine"))
            if score > best_score:
                best_score = score
                best_k = k
        except Exception:
            continue

    if best_k > 1 and best_score >= silhouette_threshold:
        return best_k, best_score
    return 1, max(0.0, best_score)


def cluster_speaker_embeddings(
    emb_matrix: np.ndarray,
    num_speakers: int = 1,
    segment_durations: list[float] | None = None,
) -> list[int]:
    """Cluster embeddings into speaker IDs sorted by speaking duration."""
    n = len(emb_matrix)
    if n == 0:
        return []
    if num_speakers <= 1 or n <= 1:
        return [0] * n

    k = min(num_speakers, n)
    clustering = AgglomerativeClustering(n_clusters=k, metric="cosine", linkage="average")
    raw_labels = clustering.fit_predict(emb_matrix)

    durations = segment_durations if segment_durations and len(segment_durations) == n else [1.0] * n
    cluster_durations: dict[int, float] = {}
    for lbl, dur in zip(raw_labels, durations):
        cluster_durations[lbl] = cluster_durations.get(lbl, 0.0) + dur

    sorted_clusters = sorted(cluster_durations.keys(), key=lambda c: (cluster_durations[c], -c), reverse=True)
    cluster_mapping = {orig_id: new_id for new_id, orig_id in enumerate(sorted_clusters)}
    return [cluster_mapping[lbl] for lbl in raw_labels]


def diarize_segments(
    audio_path: str,
    segments: list[dict],
    settings=None,
    num_speakers: int | None = None,
    max_speakers: int = MAX_SPEAKERS_DEFAULT,
    min_speech_duration: float = MIN_SPEECH_DURATION,
) -> list[dict]:
    """Assign speaker_id (0, 1, ...) to each segment."""
    out_segments = [dict(s) for s in segments]
    if not out_segments:
        return []

    if settings is not None and not getattr(settings, "diarization_enabled", True):
        for s in out_segments:
            s["speaker_id"] = 0
        return out_segments

    if settings is not None:
        if num_speakers is None:
            cfg_num = getattr(settings, "diarization_num_speakers", 0)
            if cfg_num > 0:
                num_speakers = cfg_num
        max_speakers = getattr(settings, "diarization_max_speakers", max_speakers)

    if len(out_segments) == 1 or num_speakers == 1:
        for s in out_segments:
            s["speaker_id"] = 0
        return out_segments

    try:
        audio_arr, sr = load_audio_mono16k(audio_path)
    except Exception as e:
        logger.warning(f"Diarization: cannot load audio ({e}) — fallback to single speaker (0)")
        for s in out_segments:
            s["speaker_id"] = 0
        return out_segments

    if len(audio_arr) == 0:
        for s in out_segments:
            s["speaker_id"] = 0
        return out_segments

    embeddings: list[np.ndarray | None] = []
    durations: list[float] = []

    for seg in out_segments:
        t0 = float(seg.get("speech_start", seg.get("start", 0.0)) or 0.0)
        t1 = float(seg.get("speech_end", seg.get("end", t0)) or t0)
        dur = max(0.0, t1 - t0)
        durations.append(dur)

        if dur < min_speech_duration:
            embeddings.append(None)
            continue

        s0 = max(0, min(len(audio_arr), int(t0 * sr)))
        s1 = max(0, min(len(audio_arr), int(t1 * sr)))
        if s1 <= s0 or (s1 - s0) < int(FRAME_S * sr):
            embeddings.append(None)
            continue

        clip = audio_arr[s0:s1]
        emb = extract_acoustic_embedding(clip, sr=sr)
        if np.all(emb == 0):
            embeddings.append(None)
        else:
            embeddings.append(emb)

    valid_indices = [i for i, e in enumerate(embeddings) if e is not None]
    if not valid_indices:
        for s in out_segments:
            s["speaker_id"] = 0
        return out_segments

    filled_embeddings: list[np.ndarray] = []
    for i, e in enumerate(embeddings):
        if e is not None:
            filled_embeddings.append(e)
        else:
            nearest_idx = min(valid_indices, key=lambda v_idx: abs(v_idx - i))
            filled_embeddings.append(embeddings[nearest_idx])

    emb_matrix = np.array(filled_embeddings, dtype=np.float32)

    if num_speakers is not None and num_speakers >= 1:
        k = min(num_speakers, len(out_segments))
    else:
        dist_thresh = getattr(settings, "diarization_threshold", DISTANCE_THRESHOLD) if settings else DISTANCE_THRESHOLD
        k, _ = estimate_num_speakers(
            emb_matrix,
            min_speakers=1,
            max_speakers=max_speakers,
            distance_threshold=dist_thresh,
            silhouette_threshold=SILHOUETTE_THRESHOLD,
        )

    labels = cluster_speaker_embeddings(emb_matrix, num_speakers=k, segment_durations=durations)
    for i, seg in enumerate(out_segments):
        seg["speaker_id"] = labels[i]

    return out_segments
