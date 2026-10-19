"""Advanced → System check: one line while all is well, open when it isn't.

The graphics card, typing setup and GNOME extension had a section each,
read by new users as homework even when nothing needed doing.
"""
from types import SimpleNamespace

from tuxtalk.prefs import PreferencesWindow


class FakeFold:
    def __init__(self):
        self.label, self.expanded = "", False

    def set_label(self, text):
        self.label = text

    def set_use_markup(self, _on):
        pass

    def set_expanded(self, value):
        self.expanded = value


def _window():
    w = SimpleNamespace(system_check=FakeFold(), _system_problems=set())
    w.report = lambda part, ok: PreferencesWindow._report_system_check(w, part, ok)
    return w


def test_all_well_stays_closed_and_says_so():
    w = _window()
    w.report(None, True)
    w.report("typing", True)
    assert "everything is set up" in w.system_check.label
    assert not w.system_check.expanded


def test_a_problem_opens_the_fold_and_fixing_it_clears_the_warning():
    w = _window()
    w.report("typing", False)
    assert "needs your attention" in w.system_check.label and w.system_check.expanded
    w.system_check.expanded = False          # the user closes it
    w.report("typing", False)                # the same problem, checked again
    assert not w.system_check.expanded       # not forced open a second time
    w.report("typing", True)
    assert "everything is set up" in w.system_check.label


def test_two_problems_need_both_fixed():
    w = _window()
    w.report("typing", False)
    w.report("extension", False)
    w.report("typing", True)
    assert "needs your attention" in w.system_check.label
