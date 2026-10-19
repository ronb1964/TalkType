#!/usr/bin/env python3
"""Record the test phrases once in your own voice, so the VM tests stop
using a computer voice. Shows each phrase from phrases.toml, records from
your normal microphone while you read it, plays it back, and keeps it when
you say so. The recordings stay on this computer, outside the repo
(~/.local/share/talktype-vm-tools/phrases/recorded/).

  python3 tests/vm/record_phrases.py           every phrase not recorded yet
  python3 tests/vm/record_phrases.py numbers   just that one (again)

Turn TuxTalk's dictation off first, or F8 presses won't matter but the beeps
and a stray dictation might.
"""
import signal
import subprocess
import sys
import tempfile
from pathlib import Path

from voices import RECORDED_DIR, load_phrases


def record_one(phrase_id, text):
    print(f"\n[{phrase_id}]  Say:  {text}")
    while True:
        input("  Press Enter to start recording. ")
        with tempfile.TemporaryDirectory() as tmp:
            raw = Path(tmp) / "take.wav"
            recorder = subprocess.Popen(["pw-record", "--rate", "16000", "--channels", "1",
                                         str(raw)])
            input("  Recording: read the phrase, then press Enter. ")
            recorder.send_signal(signal.SIGINT)
            recorder.wait()
            subprocess.run(["pw-play", str(raw)], check=False)
            answer = input("  Keep it? [Y/n/q] ").strip().lower()
            if answer == "q":
                sys.exit(0)
            if answer in ("", "y", "yes"):
                RECORDED_DIR.mkdir(parents=True, exist_ok=True)
                # Trim the silence at either end, then pad it the way voices.py does.
                trim = ["silence", "1", "0.05", "0.5%", "reverse"]
                subprocess.run(["sox", str(raw), str(RECORDED_DIR / f"{phrase_id}.wav"),
                                *trim, *trim, "pad", "0.3", "0.4"], check=True)
                return


def main():
    phrases = load_phrases()
    wanted = sys.argv[1:] or [p for p in phrases if not (RECORDED_DIR / f"{p}.wav").exists()]
    unknown = [p for p in wanted if p not in phrases]
    if unknown:
        sys.exit(f"Not in phrases.toml: {', '.join(unknown)}")
    if not wanted:
        print("Every phrase is recorded. Name one to record it again.")
    for phrase_id in wanted:
        record_one(phrase_id, phrases[phrase_id]["say"])
    print("\nDone. The next VM run uses your recordings.")


if __name__ == "__main__":
    main()
