"""First-run setup and Preferences must offer the same models.

They kept separate hardcoded lists and drifted: Preferences offered tiny, base,
small, medium and large-v3, while the first-run setup screen offered only four —
"base" was missing. A user choosing a starting model was shown a smaller menu
than the one they would see later, with no indication anything was hidden.

MODEL_REPOS is the real source of truth: a model can only be offered if there is
a repository to download it from. OFFERED_MODELS fixes the display order and is
what both screens must build from, so a model added to one appears in both.
"""

import pathlib

ROOT = pathlib.Path(__file__).resolve().parent.parent

SCREENS_WITH_MODEL_PICKERS = [
    "src/talktype/prefs.py",
    "src/talktype/welcome_dialog.py",
]


def test_offered_models_matches_what_can_actually_be_downloaded():
    from talktype.model_helper import MODEL_REPOS, OFFERED_MODELS

    assert set(OFFERED_MODELS) == set(MODEL_REPOS), (
        f"OFFERED_MODELS {sorted(OFFERED_MODELS)} does not match the models that "
        f"can be downloaded {sorted(MODEL_REPOS)}. Offering a model with no repo "
        f"gives the user a choice that fails at download time; omitting one hides "
        f"a model that works."
    )


def test_offered_models_has_no_duplicates():
    from talktype.model_helper import OFFERED_MODELS

    assert len(OFFERED_MODELS) == len(set(OFFERED_MODELS)), (
        f"OFFERED_MODELS contains duplicates: {OFFERED_MODELS}"
    )


def test_every_model_picker_builds_from_the_shared_list():
    """Neither screen may keep its own hardcoded list — that is how they drifted."""
    offenders = []
    for path in SCREENS_WITH_MODEL_PICKERS:
        if "OFFERED_MODELS" not in (ROOT / path).read_text():
            offenders.append(path)

    assert not offenders, (
        f"{offenders} build a model picker without using OFFERED_MODELS. Two "
        f"hardcoded lists drift — that is exactly how 'base' went missing from "
        f"the first-run setup screen."
    )
