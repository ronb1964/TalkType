"""Rule-type problems ("select works right after you dictate") open a small
window explaining them, once per run; then the short label alone (Ron,
2026-10-14: the label made little sense and the notification was gone
before it could be read)."""
import pytest

from tuxtalk import app, explain


@pytest.fixture
def problems(monkeypatch):
    seen = {"windows": [], "labels": [], "notices": []}

    def open_window(kind):
        explain._mark_shown(kind)
        seen["windows"].append(kind)
        return True
    monkeypatch.setattr(explain, "open_window", open_window)
    monkeypatch.setattr(app, "_beep", lambda *a: None)
    monkeypatch.setattr(app, "_notify", lambda title, msg: seen["notices"].append(msg))
    from tuxtalk import screen_message
    monkeypatch.setattr(screen_message, "show_over_active_window", seen["labels"].append)
    return seen


def test_the_first_time_a_window_explains_then_the_label_is_enough(problems):
    app._edit_problem("nothing_said", False)
    assert problems["windows"] == ["nothing_said"] and problems["notices"] == []
    app._edit_problem("nothing_said", False)
    assert problems["windows"] == ["nothing_said"]                 # not again this run
    assert problems["labels"] == ["Works only right after dictating"]
    assert problems["notices"] == []


def test_dont_explain_again_is_kept(problems):
    explain.never_again("nav_terminal")
    assert not explain.should_explain("nav_terminal")
    app._edit_problem("nav_terminal", False)
    assert problems["windows"] == [] and problems["labels"] and problems["notices"] == []


def test_a_real_error_keeps_the_notification(problems):
    app._edit_problem("shortcut_failed", False)
    assert problems["windows"] == [] and problems["notices"]


def test_if_the_window_cannot_open_the_notification_still_says_it(problems, monkeypatch):
    monkeypatch.setattr(explain, "open_window", lambda kind: False)
    app._edit_problem("terminal", False)
    assert problems["notices"]


def test_every_explanation_has_a_label_and_a_notice():
    for kind in explain.EXPLANATIONS:
        assert kind in app._EDIT_NOTICES and kind in app._EDIT_LABELS


def test_the_window_has_the_title_text_tickbox_and_got_it():
    pytest.importorskip("gi")
    dialog, check = explain.build_dialog("nothing_said")
    try:
        assert dialog.get_property("text") == "Select works right after you dictate"
        assert "right after you dictate" in dialog.get_property("secondary-text")
        assert check.get_label() == "Don't explain this again"
    finally:
        dialog.destroy()


def test_a_broken_file_means_explain_again(tmp_path, monkeypatch):
    p = tmp_path / "explained.json"
    p.write_text("{not json")
    monkeypatch.setattr(explain, "_never_path", lambda: str(p))
    assert explain.should_explain("nothing_said")


def test_each_run_explains_again_but_never_again_holds(problems):
    app._edit_problem("terminal", False)
    explain.never_again("cant_format")
    explain.start_run()                        # TuxTalk restarted
    assert explain.should_explain("terminal")
    assert not explain.should_explain("cant_format")


def test_show_tips_again_brings_everything_back(problems):
    app._edit_problem("terminal", False)       # shown in this run
    explain.never_again("cant_format")
    assert explain.anything_to_reset()
    explain.reset()                            # Preferences' button, service still running
    assert explain.should_explain("terminal") and explain.should_explain("cant_format")
    assert not explain.anything_to_reset()
