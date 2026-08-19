import os
import subprocess
import sys

def test_gemini_srt_cli_help():
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    res = subprocess.run(
        [sys.executable, "-m", "autodub.tools.gemini_srt_ui", "--help"],
        capture_output=True,
        text=True,
        encoding="utf-8",
        env=env,
    )
    assert res.returncode == 0
    assert "Gemini SRT" in res.stdout or "port" in res.stdout
