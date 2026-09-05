"""A model whose download did not finish must not stay in config.toml.

Apply/OK save the config *before* downloading, because the downloader reads the
model name out of the merged config. That ordering is deliberate, but it left a
gap: cancel or fail the download and config.toml still names the new model,
while the running service is loaded with the old one. Model changes are
deliberately excluded from the live-settings reload, so nothing corrects it.

The second half is worse than the first. save_config() also resets
_config_at_open to what it just wrote, so the retry sees no change at all:
Preferences reports "your changes are already in effect" and skips the restart,
leaving the service on the old model indefinitely.

These tests drive on_apply/on_ok with a stub `self`, which reaches the real
ordering logic without constructing a GTK window. The failure path returns
before any dialog is built, so no display is needed.
"""

import pytest


@pytest.fixture
def prefs_cls():
    gi = pytest.importorskip("gi")
    gi.require_version("Gtk", "3.0")
    from talktype.prefs import PreferencesWindow

    return PreferencesWindow


class StubPrefs:
    """Only what the Apply/OK ordering touches.

    save_config() mirrors the real one's two side effects: the config is
    written, and the baseline is reset to what was written.
    """

    def __init__(self, on_disk_model="small", chosen_model="large-v3"):
        self._config_at_open = {"model": on_disk_model, "beeps": True}
        self.config = {"model": chosen_model, "beeps": True}
        self.saved_models = []
        self.download_result = (False, False)  # (success, was_downloaded)
        self.restart_calls = 0

    # --- real collaborators, stubbed ---

    def save_config(self):
        self.saved_models.append(self.config["model"])
        self._config_at_open = dict(self.config)
        return True

    def _changed_since_open(self):
        # The real implementation — this is the baseline behaviour the bug
        # corrupts, so it must not be stubbed out with something simpler.
        from talktype.prefs import PreferencesWindow

        return PreferencesWindow._changed_since_open(self)

    def _rollback_model(self, previous_model):
        # The code under test — delegate, never reimplement.
        from talktype.prefs import PreferencesWindow

        return PreferencesWindow._rollback_model(self, previous_model)

    def _download_selected_model(self):
        return self.download_result

    def _apply_or_restart(self, changed):
        self.restart_calls += 1
        return True

    # --- helpers the tests read ---

    @property
    def model_on_disk(self):
        """The last model save_config() actually persisted."""
        return self.saved_models[-1] if self.saved_models else None


def _changed_since_open(stub):
    from talktype.config import changed_keys

    return changed_keys(stub._config_at_open, stub.config)


class TestApply:
    def test_a_cancelled_download_leaves_the_previous_model_on_disk(self, prefs_cls):
        """Cancel the 3 GB download and config must still name the live model."""
        stub = StubPrefs(on_disk_model="small", chosen_model="large-v3")
        stub.download_result = (False, False)

        prefs_cls.on_apply(stub, None)

        assert stub.model_on_disk == "small"

    def test_a_cancelled_download_does_not_restart_the_service(self, prefs_cls):
        stub = StubPrefs()
        stub.download_result = (False, False)

        prefs_cls.on_apply(stub, None)

        assert stub.restart_calls == 0

    def test_after_a_cancelled_download_a_retry_still_sees_a_change(self, prefs_cls):
        """The 'already in effect' half of the bug.

        Once rolled back, re-picking the model must register as a change so the
        next Apply actually restarts the service onto it.
        """
        stub = StubPrefs(on_disk_model="small", chosen_model="large-v3")
        stub.download_result = (False, False)

        prefs_cls.on_apply(stub, None)

        # The user picks it again and this time the download works.
        stub.config["model"] = "large-v3"
        assert "model" in _changed_since_open(stub)


class TestOk:
    def test_a_cancelled_download_leaves_the_previous_model_on_disk(self, prefs_cls):
        stub = StubPrefs(on_disk_model="small", chosen_model="large-v3")
        stub.download_result = (False, False)

        prefs_cls.on_ok(stub, None)

        assert stub.model_on_disk == "small"


class TestRollbackIsNarrow:
    def test_an_unrelated_setting_survives_the_rollback(self, prefs_cls):
        """Only the model is undone — the user's other edits were saved fine."""
        stub = StubPrefs(on_disk_model="small", chosen_model="large-v3")
        stub.config["beeps"] = False
        stub.download_result = (False, False)

        prefs_cls.on_apply(stub, None)

        assert stub.config["beeps"] is False

    def test_no_second_write_when_the_model_did_not_change(self, prefs_cls):
        """A failed download of the already-selected model has nothing to undo."""
        stub = StubPrefs(on_disk_model="small", chosen_model="small")
        stub.download_result = (False, False)

        prefs_cls.on_apply(stub, None)

        assert stub.saved_models == ["small"]
