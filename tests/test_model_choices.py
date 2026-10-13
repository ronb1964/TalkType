"""Model pickers offer exactly the models that can be downloaded.

MODEL_REPOS is the real source of truth: a model can only be offered if there is
a repository to download it from. OFFERED_MODELS fixes the display order and is
what every model picker must build from, so a separate hardcoded list can't
drift and hide a model.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

# First run has no full picker: its card offers three models chosen
# by recommend.py, and points to Preferences for the rest.
SCREENS_WITH_MODEL_PICKERS = [
    "src/tuxtalk/prefs.py",
]


def test_offered_models_matches_what_can_actually_be_downloaded():
    from tuxtalk.model_helper import MODEL_REPOS, OFFERED_MODELS

    assert set(OFFERED_MODELS) == set(MODEL_REPOS), (
        f"OFFERED_MODELS {sorted(OFFERED_MODELS)} does not match the models that "
        f"can be downloaded {sorted(MODEL_REPOS)}. Offering a model with no repo "
        f"gives the user a choice that fails at download time; omitting one hides "
        f"a model that works."
    )


def test_offered_models_has_no_duplicates():
    from tuxtalk.model_helper import OFFERED_MODELS

    assert len(OFFERED_MODELS) == len(set(OFFERED_MODELS)), (
        f"OFFERED_MODELS contains duplicates: {OFFERED_MODELS}"
    )


def test_every_model_picker_builds_from_the_shared_list():
    """No picker may keep its own hardcoded list, or the lists drift apart."""
    offenders = []
    for path in SCREENS_WITH_MODEL_PICKERS:
        if "OFFERED_MODELS" not in (ROOT / path).read_text():
            offenders.append(path)

    assert not offenders, (
        f"{offenders} build a model picker without using OFFERED_MODELS. Two "
        f"hardcoded lists drift — that is exactly how 'base' went missing from "
        f"the first-run setup screen."
    )
