"""The hotkey helper (hotkey_helper.py): it reads the keyboards so TuxTalk
needn't be in the "input" group, and tells only the user at the screen about
hotkeys, never about typing.

Keyboards here are pipes that events are written into, so no real device or
privilege is needed; the grab and inject calls are recorded instead.
"""
import os
import socket
import time

import pytest

from tuxtalk import hotkey_helper as hh

F8, F9, ESC, P, A = 66, 67, 1, 25, 30
LCTRL, LALT, LSHIFT = 29, 56, 42


class FakeKeyboard(hh.Keyboard):
    """A keyboard made of a pipe. The kernel's view of which keys are down is
    kept too: an injected event comes back only if it changes that, as with a
    real evdev device."""

    def __init__(self, path="/dev/input/event-fake"):
        r, w = os.pipe()
        os.set_blocking(r, False)
        super().__init__(path, r, "Fake keyboard", set())
        self.w = w
        self.kernel = set()
        self.calls = []

    def _event(self, code, value):
        os.write(self.w, hh.EVENT.pack(0, 0, hh.EV_KEY, code, value))

    def press(self, code, value=1):
        """The user presses (1) or lets go of (0) a key."""
        if value == 1:
            self.kernel.add(code)
        elif value == 0:
            self.kernel.discard(code)
        self._event(code, value)

    def kernel_down(self):
        return set(self.kernel)

    def grab(self, on):
        self.calls.append(("grab", on))
        self.grabbed = on
        return True

    def inject(self, code, value):
        self.calls.append(("inject", code, value))
        if (value == 1) != (code in self.kernel):
            (self.kernel.add if value == 1 else self.kernel.discard)(code)
            self._event(code, value)
        return True


@pytest.fixture
def setup(tmp_path, monkeypatch):
    seat = tmp_path / "seat0"
    seat.write_text(f"ACTIVE=c1\nACTIVE_UID={os.getuid()}\n")
    (tmp_path / "input").mkdir()
    helper = hh.Helper(socket_dir=str(tmp_path), seat_file=str(seat),
                       input_dir=str(tmp_path / "input"))
    helper.listen()
    keyboard = FakeKeyboard()
    helper.keyboards[keyboard.path] = keyboard
    clients = []

    def connect():
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        sock.connect(helper.socket_path)
        sock.settimeout(0.05)
        clients.append(sock)
        spin()
        return sock

    def spin(times=4):
        for _ in range(times):
            helper.run_once(timeout=0.01)

    def say(sock, line):
        sock.sendall(line.encode() + b"\n")
        spin()

    def heard(sock):
        spin()
        data = b""
        while True:
            try:
                chunk = sock.recv(4096)
            except (socket.timeout, BlockingIOError):
                break
            if not chunk:
                break
            data += chunk
        return data.decode().splitlines()

    yield helper, keyboard, connect, say, heard, seat
    for sock in clients:
        sock.close()
    helper.listener.close()


def _ready(connect, say, heard, specs="66 67 1 CA:25"):
    sock = connect()
    say(sock, "HELLO 1")
    say(sock, f"WATCH {specs}")
    assert heard(sock) == [f"HELLO 1 {hh.VERSION}", "OK WATCH"]
    return sock


# --- what may be watched --------------------------------------------------------------

@pytest.mark.parametrize("spec", ["66", "88", "183", "194", "1", "119", "70", "CA:25", "CA:30",
                                  "CM:30", "AM:30", "CAS:30", "S:66", "C:66"])
def test_hotkeys_and_modifier_combos_can_be_watched(spec):
    hh.parse_spec(spec)


@pytest.mark.parametrize("spec", [
    "30",       # a letter on its own: that's typing
    "2",        # a number
    "28",       # Enter
    "14",       # Backspace
    "57",       # Space
    "S:30",     # Shift+letter is a capital letter
    "C:30",     # one modifier can be made to type (XKB level-3 options)
    "A:30",
    "M:20",
    "CS:30",    # Shift doesn't count as the second one
    "AS:30",
    "42",       # a modifier on its own
    "C:29",     # a modifier as the key
    "X:30",     # not a modifier letter
    "CC:30",    # a repeated one
    "0", "999", "nope", "C:",
])
def test_anything_that_reveals_typing_is_refused(spec):
    with pytest.raises(ValueError):
        hh.parse_spec(spec)


def test_say_hello_first_and_refusals_are_named(setup):
    _helper, _kb, connect, say, heard, _seat = setup
    sock = connect()
    say(sock, "WATCH 66")
    say(sock, "HELLO 2")
    say(sock, "HELLO 1")
    say(sock, "WATCH 66 30")
    assert heard(sock) == ["ERR say HELLO first", "ERR this helper speaks protocol 1",
                           f"HELLO 1 {hh.VERSION}",
                           "ERR key 30 is only reported with two of Ctrl, Alt and Super"]


# --- what is reported ---------------------------------------------------------------------

def test_a_watched_key_is_reported_down_and_up(setup):
    _helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard)
    kb.press(F8)
    kb.press(F8, 2)          # auto-repeat: never reported
    kb.press(F8, 0)
    assert heard(sock) == ["DOWN 66 -", "UP 66"]


def test_typing_is_never_reported(setup):
    _helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard)
    for code in (A, 31, 32, 28, 14, LSHIFT, A, LSHIFT):
        kb.press(code)
        kb.press(code, 0)
    assert heard(sock) == []


def test_modifiers_go_with_the_key_and_their_release_follows(setup):
    _helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard)
    kb.press(LSHIFT)
    kb.press(F8)
    kb.press(F8, 0)
    kb.press(LSHIFT, 0)
    assert heard(sock) == ["DOWN 66 42", "UP 66", "UP 42"]


def test_a_combo_needs_its_modifiers(setup):
    _helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard)
    kb.press(P)                # P alone: typing
    kb.press(P, 0)
    kb.press(LCTRL)
    kb.press(P)                # Ctrl+P: not the combo
    kb.press(P, 0)
    kb.press(LALT)
    kb.press(P)                # Ctrl+Alt+P
    kb.press(P, 0)
    kb.press(LALT, 0)
    kb.press(LCTRL, 0)
    assert heard(sock) == ["DOWN 25 29,56", "UP 25", "UP 56", "UP 29"]


def test_only_the_user_at_the_screen_hears(setup):
    _helper, kb, connect, say, heard, seat = setup
    sock = _ready(connect, say, heard)
    seat.write_text(f"ACTIVE_UID={os.getuid() + 1}\n")     # someone else's session in front
    kb.press(F8)
    kb.press(F8, 0)
    seat.write_text("ACTIVE=c1\n")                          # no active user at all
    kb.press(F9)
    kb.press(F9, 0)
    assert heard(sock) == []


def test_a_key_held_on_two_keyboards_comes_up_once_both_let_go(setup):
    helper, kb, connect, say, heard, _seat = setup
    other = FakeKeyboard("/dev/input/event-other")
    helper.keyboards[other.path] = other
    sock = _ready(connect, say, heard)
    kb.press(F8)
    assert heard(sock) == ["DOWN 66 -"]
    other.press(F8)
    assert heard(sock) == []           # already down: no second DOWN
    kb.press(F8, 0)
    assert heard(sock) == []           # still held on the other one
    other.press(F8, 0)
    assert heard(sock) == ["UP 66"]


def test_an_unplugged_keyboard_lets_its_keys_go(setup):
    helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard)
    kb.press(F8)
    assert heard(sock) == ["DOWN 66 -"]
    helper.drop_keyboard(kb)
    assert heard(sock) == ["UP 66"]


# --- hiding a held hotkey ---------------------------------------------------------------

def test_hide_tells_the_desktop_it_went_up_then_keeps_the_keyboards(setup):
    helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard)
    kb.press(F8)
    heard(sock)
    say(sock, "HIDE 66")
    assert heard(sock) == ["OK HIDE"]
    assert kb.calls == [("inject", F8, 0), ("grab", True), ("inject", F8, 1)]
    # Our own injected events don't count as the user's.
    assert helper.hide is not None and kb.down == {F8}
    kb.press(F8, 0)                     # the real release still reaches us
    say(sock, "UNHIDE")
    assert heard(sock) == ["UP 66", "OK UNHIDE"]
    assert kb.calls[-1] == ("grab", False) and helper.hide is None


def test_hide_is_refused_unless_the_hotkey_is_held(setup):
    helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard)
    say(sock, "HIDE 66")
    kb.press(A)                        # a held letter isn't the client's to hide
    say(sock, "HIDE 30")
    assert heard(sock) == ["ERR the hotkey isn't held", "ERR the hotkey isn't held"]
    assert helper.hide is None and kb.calls == []


def test_a_release_waiting_to_be_read_beats_the_hide(setup):
    """Let go of F8 just as the hide is asked for: the release counts, nothing
    is grabbed, and the client hears UP before the refusal."""
    helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard)
    kb.press(F8)
    heard(sock)
    kb.press(F8, 0)                    # not read yet
    sock.sendall(b"HIDE 66\n")
    helper.on_client_data(next(iter(helper.clients.values())))
    assert heard(sock) == ["UP 66", "ERR the hotkey isn't held"]
    assert ("grab", True) not in kb.calls


def test_the_keyboards_come_back_by_themselves_after_letting_go(setup, monkeypatch):
    helper, kb, connect, say, heard, _seat = setup
    monkeypatch.setattr(hh, "HIDE_RELEASE_GRACE_S", 0.05)
    sock = _ready(connect, say, heard)
    kb.press(F8)
    heard(sock)
    say(sock, "HIDE 66")
    kb.press(F8, 0)                    # and TuxTalk never says UNHIDE
    heard(sock)
    time.sleep(0.1)
    heard(sock)
    assert helper.hide is None and kb.calls[-1] == ("grab", False)


def test_the_keyboards_come_back_when_tuxtalk_goes_away(setup):
    helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard)
    kb.press(F8)
    heard(sock)
    say(sock, "HIDE 66")
    sock.close()
    heard(connect())
    assert helper.hide is None and kb.calls[-1] == ("grab", False)


def test_someone_else_cant_hide(setup):
    helper, kb, connect, say, heard, seat = setup
    sock = _ready(connect, say, heard)
    kb.press(F8)
    heard(sock)
    seat.write_text(f"ACTIVE_UID={os.getuid() + 1}\n")
    say(sock, "HIDE 66")
    assert heard(sock) == ["ERR only the user at the screen can do that"]


# --- limits ---------------------------------------------------------------------------------

def test_a_line_too_long_ends_the_connection(setup):
    helper, _kb, connect, say, _heard, _seat = setup
    sock = connect()
    sock.sendall(b"X" * (hh.MAX_LINE + 10))
    for _ in range(4):
        helper.run_once(timeout=0.01)
    assert helper.clients == {}


def test_too_many_connections_are_turned_away(setup):
    helper, _kb, connect, _say, _heard, _seat = setup
    for _ in range(hh.MAX_CLIENTS_PER_UID + 2):
        connect()
    assert len(helper.clients) == hh.MAX_CLIENTS_PER_UID


def test_the_active_user_is_read_from_logind(tmp_path):
    seat = tmp_path / "seat0"
    seat.write_text("# This is private data. Do not parse.\nACTIVE=c2\nACTIVE_UID=1000\nUIDS=1000\n")
    assert hh.read_active_uid(str(seat)) == 1000
    assert hh.read_active_uid(str(tmp_path / "missing")) is None


def test_the_helper_needs_nothing_but_the_standard_library():
    """It runs with the system's python3 in isolated mode, outside TuxTalk."""
    import ast
    tree = ast.parse(open(hh.__file__).read())
    imported = {alias.name.split(".")[0] for node in ast.walk(tree)
                if isinstance(node, ast.Import) for alias in node.names}
    imported |= {node.module.split(".")[0] for node in ast.walk(tree)
                 if isinstance(node, ast.ImportFrom) and node.module}
    assert imported <= {"errno", "fcntl", "os", "select", "signal", "socket", "struct", "sys", "time"}


# --- from the security review, 2026-10-15 -------------------------------------------------

RALT, LMETA = 100, 125


def test_a_virtual_keyboard_cant_lend_its_modifiers_to_the_real_one(setup):
    """A program makes a virtual keyboard and holds Ctrl+Alt there: keys typed
    on the real keyboard must not turn into reportable combos."""
    helper, kb, connect, say, heard, _seat = setup
    virtual = FakeKeyboard("/dev/input/event-virtual")
    helper.keyboards[virtual.path] = virtual
    sock = _ready(connect, say, heard, "CA:25 CA:30 CA:31")
    virtual.press(LCTRL)
    virtual.press(LALT)
    heard(sock)
    for code in (A, 31, P):
        kb.press(code)
        kb.press(code, 0)
    assert heard(sock) == []


def test_modifiers_down_before_the_keyboard_was_opened_dont_count(setup):
    helper, _kb, connect, say, heard, _seat = setup
    late = FakeKeyboard("/dev/input/event-late")
    late.down = {LCTRL, LALT}             # already held when it appeared
    helper.keyboards[late.path] = late
    sock = _ready(connect, say, heard, "CA:25")
    late.press(P)
    late.press(P, 0)
    assert heard(sock) == []
    late.press(LCTRL, 0)
    late.press(LALT, 0)
    late.press(LCTRL)
    late.press(LALT)
    late.press(P)
    assert heard(sock) == ["DOWN 25 29,56"]


def test_altgr_never_unlocks_a_key(setup):
    """Right Alt is AltGr on most layouts: Ctrl+AltGr+key can type @ or €."""
    _helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard, "CA:25 CA:16")
    kb.press(LCTRL)
    kb.press(RALT)
    kb.press(16)                         # Q: AltGr+Q is @ on a German layout
    kb.press(16, 0)
    assert heard(sock) == []


def test_no_combos_while_a_keyboard_is_held_and_hidden_modifiers_stop_counting(setup):
    helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard, "66 CA:25")
    kb.press(LCTRL)
    kb.press(LALT)
    kb.press(F8)                          # Ctrl+Alt+F8 held, then hidden
    heard(sock)
    say(sock, "HIDE 66 29 56")
    assert heard(sock) == ["OK HIDE"]
    kb.press(P)                           # the desktop doesn't see this
    kb.press(P, 0)
    kb.press(F8, 0)
    say(sock, "UNHIDE")
    heard(sock)
    kb.press(P)                           # Ctrl+Alt still physically held, but the
    kb.press(P, 0)                        # desktop was told they went up
    assert "DOWN 25" not in " ".join(heard(sock))


def test_modifiers_pressed_while_held_dont_count(setup):
    helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard, "66 CA:25")
    kb.press(F8)
    heard(sock)
    say(sock, "HIDE 66")
    kb.press(LCTRL)                       # pressed while we hold the keyboard
    kb.press(LALT)
    kb.press(F8, 0)
    say(sock, "UNHIDE")
    heard(sock)
    kb.press(P)
    assert heard(sock) == []


def test_one_hide_per_press(setup):
    helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard)
    kb.press(F8)
    heard(sock)
    say(sock, "HIDE 66")
    say(sock, "UNHIDE")
    say(sock, "HIDE 66")                  # same press, still held
    assert heard(sock) == ["OK HIDE", "OK UNHIDE", "ERR the hotkey isn't held"]
    kb.press(F8, 0)
    kb.press(F8)                          # a new press may
    heard(sock)
    say(sock, "HIDE 66")
    assert heard(sock) == ["OK HIDE"]


def test_the_keyboard_comes_back_when_someone_else_is_at_the_screen(setup):
    helper, kb, connect, say, heard, seat = setup
    sock = _ready(connect, say, heard)
    kb.press(F8)
    heard(sock)
    say(sock, "HIDE 66")
    seat.write_text(f"ACTIVE_UID={os.getuid() + 1}\n")
    heard(sock)
    assert helper.hide is None and kb.calls[-1] == ("grab", False)


def test_only_the_keyboard_the_hotkey_is_held_on_is_grabbed(setup):
    helper, kb, connect, say, heard, _seat = setup
    other = FakeKeyboard("/dev/input/event-other")
    helper.keyboards[other.path] = other
    sock = _ready(connect, say, heard)
    kb.press(F8)
    heard(sock)
    say(sock, "HIDE 66")
    assert ("grab", True) in kb.calls and other.calls == []


def test_someone_not_at_the_screen_cant_connect(setup):
    helper, _kb, connect, _say, _heard, seat = setup
    seat.write_text(f"ACTIVE_UID={os.getuid() + 1}\n")
    sock = connect()
    assert helper.clients == {}
    assert sock.recv(10) == b""           # closed


def test_a_connection_that_never_says_hello_is_dropped(setup, monkeypatch):
    helper, _kb, connect, _say, _heard, _seat = setup
    monkeypatch.setattr(hh, "HELLO_DEADLINE_S", 0.05)
    connect()
    assert len(helper.clients) == 1
    time.sleep(0.1)
    helper.run_once(timeout=0.01)
    assert helper.clients == {}


def test_a_full_house_makes_room_for_the_user_at_the_screen(setup, monkeypatch):
    helper, _kb, connect, say, heard, _seat = setup
    monkeypatch.setattr(hh, "MAX_CLIENTS", 2)
    first = _ready(connect, say, heard)
    _ready(connect, say, heard)
    next(c for c in helper.clients.values() if c.sock.fileno() >= 0).uid = os.getuid() + 1
    third = connect()
    say(third, "HELLO 1")
    assert heard(third) == [f"HELLO 1 {hh.VERSION}"]
    assert sorted(c.uid for c in helper.clients.values()) == [os.getuid()] * 2


def test_lost_events_are_made_up_from_the_kernel(setup):
    helper, kb, connect, say, heard, _seat = setup
    sock = _ready(connect, say, heard)
    kb.press(F8)
    assert heard(sock) == ["DOWN 66 -"]
    kb.kernel.discard(F8)                 # released while events were being lost
    os.write(kb.w, hh.EVENT.pack(0, 0, hh.EV_SYN, hh.SYN_DROPPED, 0)
             + hh.EVENT.pack(0, 0, hh.EV_KEY, F8, 1)        # stale, skipped
             + hh.EVENT.pack(0, 0, hh.EV_SYN, hh.SYN_REPORT, 0))
    assert heard(sock) == ["UP 66"]


def test_virtual_keyboards_cant_crowd_out_real_ones(setup, monkeypatch, tmp_path):
    helper, _kb, _connect, _say, _heard, _seat = setup
    folder = tmp_path / "input"
    for i in range(hh.MAX_VIRTUAL_KEYBOARDS + 4):
        (folder / f"event{i}").write_text("")

    def fake_open(path):
        keyboard = FakeKeyboard(path)
        keyboard.virtual = True
        return keyboard
    monkeypatch.setattr(hh.Keyboard, "open", staticmethod(fake_open))
    helper.scan()
    assert sum(1 for k in helper.keyboards.values() if k.virtual) == hh.MAX_VIRTUAL_KEYBOARDS


def test_other_seats_keyboards_are_not_read(tmp_path):
    data = tmp_path / "data"
    data.mkdir()
    rdev = os.makedev(13, 70)
    (data / "c13:70").write_text("E:ID_INPUT=1\nE:ID_SEAT=seat1\n")
    assert hh.udev_seat(rdev, str(data)) == "seat1"
    assert hh.udev_seat(os.makedev(13, 71), str(data)) == "seat0"
