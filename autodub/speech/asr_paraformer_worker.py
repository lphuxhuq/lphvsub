"""Paraformer ASR worker — runs INSIDE the dedicated .venv-asr virtualenv.

Standalone script: must not import anything from ``autodub`` (different env).
Chains silero-VAD chunking with the offline Paraformer-large zh model via
sherpa-onnx (ONNX Runtime, CPU — zero VRAM, no torch). Optionally restores
punctuation with the CT-Transformer model when present in
``<model-dir>/punct``.

CLI:
    python asr_paraformer_worker.py --audio in.wav --model-dir models/paraformer-zh
        [--num-threads 4] [--no-punct] [--vad-pad 0.3]

stdout protocol (one JSON per line, everything else goes to stderr):
    {"ready": true}
    {"seg": true, "text": "...", "start": 1.02, "end": 4.31}
    {"empty": true, "start": 5.0, "end": 6.4}   # VAD có tiếng, decode rỗng
    {"done": true, "num_segments": 42, "num_empty": 1}
  | {"error": "..."}          then exit code 1

Timestamp của "seg"/"empty" luôn là biên VAD GỐC — decoding dùng bản đệm
pad hai bên (--vad-pad) nhưng timeline không trượt.
"""
import argparse
import json
import os
import sys
import wave


def _die(proto_out, msg: str) -> None:
    print(json.dumps({"error": msg}, ensure_ascii=False),
          file=proto_out, flush=True)
    sys.exit(1)


def _read_wav(path: str):
    """16 kHz mono PCM16 WAV → float32 numpy array in [-1, 1]."""
    import numpy as np

    with wave.open(path, "rb") as f:
        if f.getsampwidth() != 2:
            raise ValueError(f"expected 16-bit PCM, got {f.getsampwidth()*8}-bit")
        rate = f.getframerate()
        channels = f.getnchannels()
        data = f.readframes(f.getnframes())
    samples = np.frombuffer(data, dtype=np.int16).astype(np.float32) / 32768.0
    if channels > 1:
        samples = samples.reshape(-1, channels).mean(axis=1)
    return samples, rate


def padded_range(seg_start: int, seg_end: int, prev_end: int,
                 next_start: int, n_samples: int,
                 pad_samples: int) -> tuple[int, int]:
    """Khoảng sample dùng để decode: VAD chunk ``[seg_start, seg_end)`` mở
    rộng hai bên ``pad_samples``, clamp vào ``[0, n_samples)`` và vào biên
    GỐC của hai chunk kề (``prev_end``/``next_start``).

    Nhờ clamp hai phía, speech của mỗi chunk chỉ được decode đúng một lần
    (lần của chính nó) — force-split 20s hay gap ngắn không lặp chữ, và
    không có audio nào bị bỏ qua.
    """
    s = max(0, seg_start - pad_samples, prev_end)
    e = min(n_samples, seg_end + pad_samples,
            max(next_start, s + 1))
    return s, e


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    # Keep the real stdout for the JSON protocol only; library prints → stderr.
    proto_out = sys.stdout
    sys.stdout = sys.stderr

    parser = argparse.ArgumentParser()
    parser.add_argument("--audio", required=True, help="16 kHz mono WAV")
    parser.add_argument("--model-dir", required=True,
                        help="dir with model.int8.onnx + tokens.txt + "
                             "silero_vad.onnx (+ punct/)")
    parser.add_argument("--num-threads", type=int, default=4)
    parser.add_argument("--no-punct", action="store_true")
    parser.add_argument("--vad-pad", type=float, default=0.3,
                        help="giây đệm hai bên mỗi VAD chunk trước khi decode")
    args = parser.parse_args()

    model_file = os.path.join(args.model_dir, "model.int8.onnx")
    tokens_file = os.path.join(args.model_dir, "tokens.txt")
    vad_file = os.path.join(args.model_dir, "silero_vad.onnx")
    for p in (model_file, tokens_file, vad_file):
        if not os.path.isfile(p):
            _die(proto_out, f"missing model file: {p}")

    try:
        import numpy as np  # noqa: F401 — fail early with a clear message
        import sherpa_onnx
    except ImportError as e:
        _die(proto_out, f"missing package in .venv-asr: {e}")

    try:
        recognizer = sherpa_onnx.OfflineRecognizer.from_paraformer(
            paraformer=model_file,
            tokens=tokens_file,
            num_threads=max(1, args.num_threads),
            sample_rate=16000,
            feature_dim=80,
            decoding_method="greedy_search",
        )
    except Exception as e:
        _die(proto_out, f"failed to load Paraformer: {type(e).__name__}: {e}")

    # Punctuation (CT-Transformer zh-en) — optional, warn-only on failure.
    punct = None
    punct_dir = os.path.join(args.model_dir, "punct")
    punct_model = os.path.join(punct_dir, "model.onnx")
    if not args.no_punct and os.path.isfile(punct_model):
        try:
            punct_cfg = sherpa_onnx.OfflinePunctuationConfig(
                model=sherpa_onnx.OfflinePunctuationModelConfig(
                    ct_transformer=punct_model,
                    num_threads=max(1, args.num_threads)))
            punct = sherpa_onnx.OfflinePunctuation(punct_cfg)
        except Exception as e:
            print(f"punctuation model failed to load ({e}) — continuing "
                  "without punctuation", file=sys.stderr, flush=True)

    try:
        samples, rate = _read_wav(args.audio)
    except Exception as e:
        _die(proto_out, f"cannot read audio: {type(e).__name__}: {e}")
    if rate != 16000:
        _die(proto_out, f"expected 16 kHz audio, got {rate} Hz")

    print(json.dumps({"ready": True}), file=proto_out, flush=True)

    # VAD chunking mirrors faster-whisper's vad_filter (500 ms min silence, 0.35 threshold).
    vad_cfg = sherpa_onnx.VadModelConfig()
    vad_cfg.silero_vad.model = vad_file
    vad_cfg.silero_vad.threshold = 0.35
    vad_cfg.silero_vad.min_silence_duration = 0.5
    vad_cfg.silero_vad.min_speech_duration = 0.1
    vad_cfg.silero_vad.max_speech_duration = 20.0
    vad_cfg.sample_rate = 16000
    vad = sherpa_onnx.VoiceActivityDetector(vad_cfg, buffer_size_in_seconds=120)

    window = 512  # samples per VAD feed (silero requirement at 16 kHz)
    pad_samples = max(0, int(round(args.vad_pad * rate)))
    n_segments = 0
    n_empty = 0

    # Pass 1: quét VAD hết file thu thập biên các chunk — cần biên chunk SAU
    # để clamp decode range (xem padded_range), nên decode dồn sang pass 2.
    chunks: list[tuple[int, int]] = []
    i = 0
    while i < len(samples):
        vad.accept_waveform(samples[i:i + window])
        i += window
        while not vad.empty():
            seg = vad.front
            chunks.append((seg.start, seg.start + len(seg.samples)))
            vad.pop()
    vad.flush()
    while not vad.empty():
        seg = vad.front
        chunks.append((seg.start, seg.start + len(seg.samples)))
        vad.pop()

    # Pass 2: decode từng chunk với padding clamp theo hai chunk kề.
    for idx, (orig_start, orig_end) in enumerate(chunks):
        prev_end = chunks[idx - 1][1] if idx > 0 else 0
        next_start = chunks[idx + 1][0] if idx + 1 < len(chunks) \
            else len(samples)
        s, e = padded_range(orig_start, orig_end, prev_end, next_start,
                            len(samples), pad_samples)
        stream = recognizer.create_stream()
        stream.accept_waveform(rate, samples[s:e])
        recognizer.decode_stream(stream)
        text = stream.result.text.strip()
        if not text:
            # VAD bắt được tiếng nhưng decode rỗng — báo ra ngoài thay vì
            # nuốt im lặng để phía trên (suspect detection) còn biết mà xử lý.
            n_empty += 1
            print(json.dumps({"empty": True,
                              "start": round(orig_start / rate, 3),
                              "end": round(orig_end / rate, 3)}),
                  file=proto_out, flush=True)
            continue
        if punct is not None:
            try:
                text = punct.add_punctuation(text)
            except Exception as e_punct:
                print(f"add_punctuation failed ({e_punct}) — keeping raw "
                      "text", file=sys.stderr, flush=True)
        n_segments += 1
        print(json.dumps({"seg": True, "text": text,
                          "start": round(orig_start / rate, 3),
                          "end": round(orig_end / rate, 3)},
                         ensure_ascii=False), file=proto_out, flush=True)

    print(json.dumps({"done": True, "num_segments": n_segments,
                      "num_empty": n_empty}),
          file=proto_out, flush=True)


if __name__ == "__main__":
    main()
