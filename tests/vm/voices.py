"""The WAV the pretend microphone plays for each phrase in phrases.toml.

A person's recording wins (record_phrases.py writes them). Without one, a
computer voice reads the text: piper if its venv is set up (README), else
espeak-ng. Generated files are cached and remade when the text changes.
"""
import hashlib
import shutil
import subprocess
import tomllib
from pathlib import Path

from vmlib import TOOLS

PHRASES_FILE = Path(__file__).parent / "phrases.toml"
PHRASE_DIR = TOOLS / "phrases"
RECORDED_DIR = PHRASE_DIR / "recorded"
GENERATED_DIR = PHRASE_DIR / "generated"
PIPER = TOOLS / "tts/bin/piper"
PIPER_VOICES = {"en": TOOLS / "tts/voices/en_US-lessac-medium.onnx",
                "de": TOOLS / "tts/voices/de_DE-thorsten-medium.onnx"}
ESPEAK_VOICES = {"en": "en-us", "de": "de"}


def load_phrases():
    with open(PHRASES_FILE, "rb") as f:
        return tomllib.load(f)


def _speak(text, lang, raw_path):
    voice = PIPER_VOICES.get(lang)
    if PIPER.exists() and voice and voice.exists():
        subprocess.run([str(PIPER), "-m", str(voice), "-f", str(raw_path)], input=text,
                       text=True, check=True, capture_output=True)
        return "piper"
    subprocess.run(["espeak-ng", "-v", ESPEAK_VOICES.get(lang, lang), "-s", "155", "-w",
                    str(raw_path), text], check=True, capture_output=True)
    return "espeak-ng"


def wav_for(phrase_id):
    """(path, voice) for *phrase_id*: 16 kHz mono with a short silence either
    side, so the first word isn't clipped when the key goes down."""
    recorded = RECORDED_DIR / f"{phrase_id}.wav"
    if recorded.exists():
        return recorded, "recorded"
    phrase = load_phrases()[phrase_id]
    lang = phrase.get("lang", "en")
    text = phrase.get("tts", phrase["say"])
    stamp = hashlib.sha1(f"{lang}:{text}".encode()).hexdigest()[:10]
    GENERATED_DIR.mkdir(parents=True, exist_ok=True)
    for voice in ("piper", "espeak-ng"):
        cached = GENERATED_DIR / f"{phrase_id}-{voice}-{stamp}.wav"
        if cached.exists():
            return cached, voice
    raw = GENERATED_DIR / f"{phrase_id}.raw.wav"
    voice = _speak(text, lang, raw)
    final = GENERATED_DIR / f"{phrase_id}-{voice}-{stamp}.wav"
    subprocess.run(["sox", str(raw), "-r", "16000", "-c", "1", str(final), "pad", "0.3", "0.4"],
                   check=True, capture_output=True)
    raw.unlink()
    return final, voice


def duration(path):
    out = subprocess.run(["soxi", "-D", str(path)], check=True, capture_output=True, text=True)
    return float(out.stdout)


if __name__ == "__main__":
    # Make (or show) every phrase's audio: python3 voices.py
    if not shutil.which("sox"):
        raise SystemExit("sox is needed: sudo dnf install sox")
    for pid in load_phrases():
        path, voice = wav_for(pid)
        print(f"{pid:20} {voice:10} {duration(path):5.1f}s  {path}")
