"""Help and the README describe the app as it is in 0.14.2.

A read-through before 0.14.2 found them still describing the old first run
(an NVIDIA-only CUDA offer), calling Whisper Small the recommended model, a red
recording indicator (it's a cyan orb by default), Fix a Word under a
"Voice Commands" tab (it's "Commands"), tray items that no longer exist, a
"Fast & Accurate" preset, and setting names that were never real.
"""
import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent
HELP = (ROOT / "src" / "talktype" / "help_dialog.py").read_text()
README = (ROOT / "README.md").read_text()


def test_first_run_is_the_recommended_setup():
    assert "Offers to use your NVIDIA graphics card" not in HELP
    assert "Recommends a setup for your computer" in HELP
    assert "it asks which one you want" not in README


def test_parakeet_not_small_is_recommended():
    assert "General use (recommended)" not in HELP
    assert "| **small** | 244 MB | Balanced | Very Good | **Recommended** |" not in README
    assert 'Start with "small"' not in README


def test_no_red_indicator_or_dimmed_icon():
    assert "red microphone icon" not in HELP
    assert "Red recording indicator" not in HELP
    assert "dimmed = stopped" not in HELP
    assert "Preferences → Audio" in HELP


def test_fix_a_word_lives_on_the_commands_tab():
    assert "Preferences → Voice Commands" not in HELP
    assert "Preferences → Commands → Fix a Word" in HELP


def test_quote_lines_show_curly_quotes():
    assert 'Smart quotes (" " instead of " ")' not in HELP
    assert "open quotes</b> for \\u201c" in HELP or "open quotes</b> for “" in HELP
    assert "close quotes</b> for \\u201d" in HELP or "close quotes</b> for ”" in HELP


def test_no_menu_items_or_presets_that_do_not_exist():
    assert "Stop Service then Start Service" not in HELP
    assert "Fast &amp; Accurate" not in README and "Fast & Accurate" not in README
    assert "98 point 6" not in HELP          # a model's habit, not something TalkType does


def test_voice_commands_tab_mentions_english_and_self_corrections():
    assert "English words" in HELP
    assert "no wait" in HELP.split("Voice Commands Reference")[1]


def test_readme_config_example_uses_real_setting_names():
    from talktype.config import Settings
    block = README.split("```toml", 1)[1].split("```", 1)[0]
    for line in block.splitlines():
        key = line.split("=", 1)[0].strip()
        if key and not key.startswith("#"):
            assert hasattr(Settings, key), key
    assert 'model = "parakeet-v3"' in block
