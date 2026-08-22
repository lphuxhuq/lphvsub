"""OCR worker — runs INSIDE the dedicated .venv-ocr virtualenv.

Standalone script: must not import anything from ``autodub`` (different env).
Loads RapidOCR (onnxruntime, CPU) and OCR-ed each image path listed in the
file given by ``--list``. Frames are pre-cropped to the subtitle region by
the caller (ffmpeg), so no region logic lives here.

CLI:
    python ocr_worker.py --list frames.txt
        [--langs ch]

frames.txt: one image path per line.

stdout protocol (one JSON per line, everything else goes to stderr):
    {"ready": true}
    {"frame": "path.jpg", "lines": [{"text": "...", "score": 0.97,
                                     "box": [[x,y], [x,y], [x,y], [x,y]]}]}
    {"done": true, "num_frames": 42}
  | {"error": "..."}          then exit code 1

Lines per frame are sorted top→bottom by box y — caller ghép multi-line.
"""
import argparse
import json
import sys


def _die(proto_out, msg: str) -> None:
    print(json.dumps({"error": msg}, ensure_ascii=False),
          file=proto_out, flush=True)
    sys.exit(1)


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

    proto_out = sys.stdout
    sys.stdout = sys.stderr

    parser = argparse.ArgumentParser()
    parser.add_argument("--list", required=True,
                        help="text file, one image path per line")
    args = parser.parse_args()

    try:
        from rapidocr_onnxruntime import RapidOCR
    except ImportError as e:
        _die(proto_out, f"missing package in .venv-ocr: {e}")

    try:
        ocr = RapidOCR()
    except Exception as e:
        _die(proto_out, f"failed to init RapidOCR: {type(e).__name__}: {e}")

    try:
        with open(args.list, encoding="utf-8") as f:
            paths = [line.strip() for line in f if line.strip()]
    except OSError as e:
        _die(proto_out, f"cannot read list: {e}")

    print(json.dumps({"ready": True}), file=proto_out, flush=True)

    n = 0
    for path in paths:
        try:
            result, _ = ocr(path)
        except Exception as e:
            print(f"ocr failed on {path} ({e}) — skipping frame",
                  file=sys.stderr, flush=True)
            continue
        lines = []
        for item in (result or []):
            box, text, score = item[0], str(item[1]), float(item[2])
            # Bỏ dòng rác: text rỗng sau strip hoặc score quá thấp.
            text = text.strip()
            if not text or score < 0.3:
                continue
            top_y = min(p[1] for p in box)
            lines.append({"text": text, "score": round(score, 3),
                          "box": box, "top_y": top_y})
        lines.sort(key=lambda l: l["top_y"])
        n += 1
        print(json.dumps({"frame": path, "lines": lines},
                         ensure_ascii=False), file=proto_out, flush=True)

    print(json.dumps({"done": True, "num_frames": n}),
          file=proto_out, flush=True)


if __name__ == "__main__":
    main()
