"""
NVIDIA Parakeet speech engine for TalkType.

Parakeet TDT 0.6B v3 is an alternative to Whisper for English and 24 other
European languages. On a plain CPU it is several times faster than Whisper and
more accurate than Whisper large-v3, which TalkType cannot offer CPU users at
all. It adds its own punctuation and capitalisation, and it detects the
language by itself.

It runs on onnxruntime, which the AppImage already ships because faster-whisper
depends on it, so supporting it costs only the small `onnx-asr` package. The
model itself (~670 MB) is downloaded at runtime like the Whisper models.

The model is published by NVIDIA under CC-BY-4.0, which requires attribution;
see PARAKEET_ATTRIBUTION, shown in the About dialog.

The rest of TalkType treats "parakeet-v3" as just another model name, so the
model pickers, config validation and download dialogs all work unchanged.
"""
import os

from .logger import setup_logger

logger = setup_logger(__name__)

# The name stored in config.toml and shown in the model pickers.
PARAKEET_MODEL = "parakeet-v3"

# Hugging Face repo with the ONNX export of the model (istupakov is the author
# of onnx-asr, and this is the export that library is built and tested against).
PARAKEET_REPO = "istupakov/parakeet-tdt-0.6b-v3-onnx"

# Only the int8 files. The repo also holds full-precision weights (a 2.4 GB
# encoder-model.onnx.data), which must NOT be downloaded: int8 is what we load,
# and it is the version measured to run fast on a CPU.
PARAKEET_FILES = (
    "config.json",
    "vocab.txt",
    "nemo128.onnx",                    # audio preprocessor
    "decoder_joint-model.int8.onnx",
    "encoder-model.int8.onnx",
)

# The model type name onnx-asr uses for this model.
_ONNX_ASR_MODEL = "nemo-parakeet-tdt-0.6b-v3"

PARAKEET_ATTRIBUTION = (
    "Parakeet TDT 0.6B v3 speech model by NVIDIA, licensed under CC-BY-4.0."
)


def is_parakeet(model_name) -> bool:
    """True if *model_name* selects the Parakeet engine rather than Whisper."""
    return model_name == PARAKEET_MODEL


def cached_model_dir():
    """Folder holding a complete Parakeet download, or None if anything is missing.

    Checks file presence only, so it is cheap enough for the GTK main thread.
    hf_hub_download(local_files_only=True) returns a file only once its
    download has fully finished, so a cancelled download reports None.
    """
    try:
        from huggingface_hub import hf_hub_download
        paths = [
            hf_hub_download(PARAKEET_REPO, name, local_files_only=True)
            for name in PARAKEET_FILES
        ]
    except Exception:
        return None
    # All files come from one repo snapshot, so they share a folder.
    return os.path.dirname(paths[0])


class ParakeetModel:
    """Loaded Parakeet model.

    Offers a `recognize` method in place of faster-whisper's `transcribe`,
    and the dictation code branches on is_parakeet(). The two engines return
    such different results that forcing them behind one interface would hide
    more than it saved.
    """

    def __init__(self, model_dir: str):
        import onnx_asr
        # CPU only. The onnxruntime we ship is the CPU build, and on CPU
        # Parakeet already transcribes a 10 s clip in well under a second.
        self._model = onnx_asr.load_model(
            _ONNX_ASR_MODEL,
            model_dir,
            quantization="int8",
            providers=["CPUExecutionProvider"],
        )

    def recognize(self, audio_f32) -> str:
        """Transcribe 16 kHz mono float32 audio and return the text."""
        return (self._model.recognize(audio_f32, sample_rate=16000) or "").strip()


def load_parakeet_model():
    """Load Parakeet from the local download.

    Raises FileNotFoundError if it has not been downloaded, so the caller can
    offer the download instead of failing mysteriously inside onnx-asr.
    """
    model_dir = cached_model_dir()
    if model_dir is None:
        raise FileNotFoundError("Parakeet model has not been downloaded")
    logger.info(f"Loading Parakeet from {model_dir}")
    return ParakeetModel(model_dir)
