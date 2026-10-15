"""TuxTalk's hotkey helper: reads the keyboards so nothing else has to.

Why this exists
---------------
TuxTalk starts dictating when you hold F8. On Wayland no ordinary program is
allowed to watch keys pressed in other windows, so TuxTalk read the keyboards
directly from /dev/input, which meant putting the user in the "input" group.
That group lets EVERY program the user runs read every key, passwords
included: a keylogger permission, given to everything.

This helper is the only thing that reads the keyboards. It runs as a system
service under a throwaway user that can do nothing else (see the unit in
secure_input.py: no network, no home folder, read-only system, no way to gain
privileges), and it only ever tells anyone about hotkeys.

The rule it keeps
-----------------
A key is reported only when the desktop itself sees it as a shortcut, never
as typing:

* F1-F24, Esc, Pause and Scroll Lock, which never type anything;
* any other key only while two of Ctrl, Alt and Super are held with it,
  having gone down while the desktop could see them, on a real keyboard
  (any of them, as the desktop counts them) or on the same virtual one.

"Two of" because any one modifier can be made to type characters: Right Alt
is AltGr on most layouts (it never counts here at all), and XKB options turn
Left Alt, Super or Right Ctrl into a third-level key too. "Seen by the
desktop" and "the same virtual one" because a program can make a virtual
keyboard: a Ctrl held there, or one the desktop didn't see go down, would
otherwise make every key typed on the real keyboard look like a shortcut.
Real keyboards (USB, built in) can't be made by a program, and the desktop
pools their modifiers, so their Ctrl and their letters may come from
different devices, as they do on some keyboards.

Everything goes only to the user at the screen (logind's active user on
seat0), and only keyboards of seat0 are read. Letters, numbers, Enter or
Shift+letter are never reported, so even a hostile program that connects
learns nothing about what is typed.

Hiding a held hotkey
--------------------
While TuxTalk records it hides the held hotkey from the desktop and keeps that
keyboard to itself, so a held F8 doesn't auto-repeat into the window being
dictated into. That's allowed once per press of a hotkey that is physically
held, grabs only the keyboard the press came from, and ends by itself within
a second of that key coming up there, when someone else's session comes to
the front, when the program that asked goes away, or after 15 minutes at
most. A press's release is reported from the keyboard it was pressed on, so
holding the same key on another keyboard can't keep a recording or a grab
going.

This file must stay self-contained: it is copied to a root-owned place
(/usr/local/libexec/tuxtalk/) and run with the system's own python3 in
isolated mode, outside TuxTalk. Standard library only, Python 3.8 or newer.

The protocol (one line each, over a Unix stream socket)
-------------------------------------------------------
client -> helper
  HELLO 1                      say hello; the helper answers HELLO 1 <version>
  WATCH <spec> [<spec>...]     the keys to report: a code ("66" = F8) or
                               MODS:code with MODS from C A S M
                               (Ctrl Alt Shift Meta/Super), "CA:25" = Ctrl+Alt+P
  HIDE <code> [<code>...]      hide these held keys from the desktop and keep
                               their keyboard until UNHIDE or they're let go
  UNHIDE                       give the keyboard back
helper -> client
  DOWN <code> <mods>           a watched key went down; mods = the modifier
                               codes held with it, comma-separated, or "-"
  UP <code>                    a key reported DOWN (or one of its modifiers)
                               was let go
  OK <what> / ERR <why>        answers to WATCH, HIDE and UNHIDE
Codes are Linux evdev key codes (linux/input-event-codes.h).
"""
import errno
import fcntl
import os
import select
import signal
import socket
import struct
import sys
import time

PROTOCOL = 1
VERSION = "1.2"

DEFAULT_SOCKET_DIR = "/run/tuxtalk-hotkeys"
SOCKET_NAME = "hotkeys.sock"
DEFAULT_SEAT_FILE = "/run/systemd/seats/seat0"
INPUT_DIR = "/dev/input"
UDEV_DATA_DIR = "/run/udev/data"
SYS_CHAR_DIR = "/sys/dev/char"

# --- evdev numbers (linux/input.h, linux/input-event-codes.h) -------------------

EV_SYN, EV_KEY, EV_REL = 0, 1, 2
SYN_REPORT, SYN_DROPPED = 0, 3
REL_X = 0
BTN_LEFT = 0x110
KEY_MAX = 0x2FF
KEY_ESC, KEY_SCROLLLOCK, KEY_PAUSE = 1, 70, 119
BUS_VIRTUAL = 0x06

F_KEYS = frozenset(list(range(59, 69)) + [87, 88] + list(range(183, 195)))   # F1-F24
BARE_KEYS = F_KEYS | {KEY_ESC, KEY_PAUSE, KEY_SCROLLLOCK}

KEY_RIGHTALT = 100
MODIFIERS = frozenset({29, 97, 42, 54, 56, KEY_RIGHTALT, 125, 126})
# The modifiers that can unlock a key, by the letter the protocol uses. Right
# Alt isn't among them: on most layouts it's AltGr, which types @, €, { and
# the like. Shift alone never unlocks anything (it types capitals).
UNLOCKERS = {
    "C": frozenset({29, 97}),       # Ctrl, left and right
    "A": frozenset({56}),           # Left Alt
    "S": frozenset({42, 54}),       # Shift
    "M": frozenset({125, 126}),     # Meta / Super
}
SHORTCUT_LETTERS = frozenset("CAM")

# Letter keys tell a keyboard from a power button, a lid switch or a game
# controller; TuxTalk's own test (uinput_helper.is_keyboard_device) is the same.
LETTER_KEYS = frozenset(list(range(16, 26)) + list(range(30, 39)) + list(range(44, 51)))

# struct input_event: a timeval (two longs), then type, code and value.
EVENT = struct.Struct("llHHi")


def _ioc(direction, number, size):
    return (direction << 30) | (size << 16) | (ord("E") << 8) | number


EVIOCGRAB = _ioc(1, 0x90, 4)
EVIOCGID = _ioc(2, 0x02, 8)
KEY_BYTES = KEY_MAX // 8 + 1


def EVIOCGBIT(event_type, length):
    return _ioc(2, 0x20 + event_type, length)


def EVIOCGKEY(length):
    return _ioc(2, 0x18, length)


def EVIOCGNAME(length):
    return _ioc(2, 0x06, length)


# --- limits: nobody gets to make this helper do much work ----------------------------

MAX_CLIENTS = 8
MAX_LINE = 512
MAX_SPECS = 32
MAX_OUTBUF = 64 * 1024
MAX_KEYBOARDS = 48
MAX_VIRTUAL_KEYBOARDS = 8      # made by programs; real keyboards always have room
HELLO_DEADLINE_S = 5.0
RESCAN_S = 2.0
HIDE_RELEASE_GRACE_S = 1.0    # the keyboard comes back this long after the hotkey is let go
HIDE_MAX_S = 15 * 60          # and never later than this
INJECTED_TTL_S = 2.0


def log(message):
    """One line to the journal. Never a key the user typed: only devices,
    connections and refusals."""
    print(f"tuxtalk-hotkeys: {message}", flush=True)


# --- what may be reported ------------------------------------------------------------

def parse_spec(spec):
    """("bare", code) or ("combo", code, frozenset of mod letters) for a WATCH
    spec, or raise ValueError saying why it is refused (see the rule at the top)."""
    mods, _, number = spec.rpartition(":")
    try:
        code = int(number)
    except ValueError:
        raise ValueError(f"not a key code: {spec!r}")
    if not 0 < code <= KEY_MAX or code in MODIFIERS:
        raise ValueError(f"not a key that can be watched: {spec!r}")
    letters = frozenset(mods.upper())
    if mods and (not letters <= set(UNLOCKERS) or len(letters) != len(mods)):
        raise ValueError(f"bad modifiers in {spec!r}")
    if code in BARE_KEYS:
        return ("bare", code)
    if len(letters & SHORTCUT_LETTERS) < 2:
        raise ValueError(f"key {code} is only reported with two of Ctrl, Alt and Super")
    return ("combo", code, letters)


def mods_satisfy(letters, held):
    """Whether every modifier named in *letters* is among *held*."""
    return all(UNLOCKERS[letter] & held for letter in letters)


def bits(buffer):
    """The set bit numbers of an ioctl bit-array reply."""
    return {i * 8 + j for i, byte in enumerate(buffer) for j in range(8) if byte >> j & 1}


def read_active_uid(seat_file):
    """The uid of the user whose session is in front on seat0, or None.
    logind keeps it in a plain file; no answer means nobody gets anything."""
    try:
        with open(seat_file) as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key == "ACTIVE_UID" and value.isdigit():
                    return int(value)
    except OSError:
        pass
    return None


def udev_seat(rdev, data_dir=UDEV_DATA_DIR):
    """The seat udev put this input device on; seat0 unless it says otherwise."""
    try:
        with open(os.path.join(data_dir, f"c{os.major(rdev)}:{os.minor(rdev)}")) as f:
            for line in f:
                if line.startswith("E:ID_SEAT="):
                    return line.strip().split("=", 1)[1] or "seat0"
    except OSError:
        pass
    return "seat0"


def device_group(rdev, sys_dir=SYS_CHAR_DIR):
    """Which keyboards' modifiers count together. Every real keyboard is in
    one group, as the desktop pools them; each virtual one (made through
    uinput, which a program can do) is in a group of its own. When it can't
    be told, a device counts as virtual: the safe side."""
    path = os.path.realpath(os.path.join(sys_dir, f"{os.major(rdev)}:{os.minor(rdev)}"))
    if path.startswith("/sys/devices/") and not path.startswith("/sys/devices/virtual/"):
        return "real"
    return f"virtual:{os.major(rdev)}:{os.minor(rdev)}"


# --- keyboards --------------------------------------------------------------------------

class Keyboard:
    """One open /dev/input/event* keyboard and the keys down on it."""

    def __init__(self, path, fd, name, down, virtual=False, group=None):
        self.path, self.fd, self.name, self.virtual = path, fd, name, virtual
        self.group = group or f"own:{path}"
        self.down = set(down)
        # The modifiers the desktop saw go down on this keyboard: only these
        # unlock a key. One already down when it was opened, pressed while we
        # held the keyboard, or hidden from the desktop by us, waits to be let go.
        self.trusted = set()
        self.grabbed = False
        self.dropping = False      # events were lost; skip to the next report, then re-read

    @classmethod
    def open(cls, path):
        """The keyboard at *path*, or None if it isn't one (mouse, power button,
        game controller), belongs to another seat, or can't be opened."""
        try:
            fd = os.open(path, os.O_RDWR | os.O_NONBLOCK | os.O_CLOEXEC)
        except OSError:
            return None
        try:
            keys = bytearray(KEY_BYTES)
            fcntl.ioctl(fd, EVIOCGBIT(EV_KEY, len(keys)), keys, True)
            keys = bits(keys)
            rel = bytearray(2)
            fcntl.ioctl(fd, EVIOCGBIT(EV_REL, len(rel)), rel, True)
            pointer = REL_X in bits(rel) and BTN_LEFT in keys
            if len(keys & LETTER_KEYS) < 3 or pointer or udev_seat(os.fstat(fd).st_rdev) != "seat0":
                os.close(fd)
                return None
            ident = bytearray(8)
            fcntl.ioctl(fd, EVIOCGID, ident, True)
            group = device_group(os.fstat(fd).st_rdev)
            virtual = struct.unpack("HHHH", ident)[0] == BUS_VIRTUAL or group != "real"
            name = bytearray(256)
            fcntl.ioctl(fd, EVIOCGNAME(len(name)), name, True)
            state = bytearray(KEY_BYTES)
            fcntl.ioctl(fd, EVIOCGKEY(len(state)), state, True)
            return cls(path, fd, name.split(b"\0", 1)[0].decode("utf-8", "replace"),
                       bits(state), virtual, group)
        except OSError:
            os.close(fd)
            return None

    def kernel_down(self):
        """The keys the kernel says are down on this keyboard right now."""
        state = bytearray(KEY_BYTES)
        try:
            fcntl.ioctl(self.fd, EVIOCGKEY(len(state)), state, True)
        except OSError:
            return set()
        return bits(state)

    def grab(self, on):
        """Keep this keyboard's events to ourselves (on) or give them back."""
        try:
            fcntl.ioctl(self.fd, EVIOCGRAB, 1 if on else 0)
            self.grabbed = on
            return True
        except OSError:
            return False

    def inject(self, code, value):
        """Send a key event into this keyboard, as if it came from it."""
        try:
            os.write(self.fd, EVENT.pack(0, 0, EV_KEY, code, value)
                     + EVENT.pack(0, 0, EV_SYN, SYN_REPORT, 0))
            return True
        except OSError:
            return False

    def close(self):
        try:
            os.close(self.fd)
        except OSError:
            pass


# --- clients -------------------------------------------------------------------------------

class Client:
    """One connection, normally the TuxTalk dictation service."""

    def __init__(self, sock, uid, pid):
        self.sock, self.uid, self.pid = sock, uid, pid
        self.connected_at = time.monotonic()
        self.inbuf = b""
        self.outbuf = b""
        self.hello = False
        self.bare = set()          # codes reported on their own
        self.combos = {}           # code -> list of modifier-letter sets
        self.origin = {}           # key reported DOWN, not yet UP -> the keyboard it came from
        self.mods_owed = {}        # modifier held at a reported DOWN, not yet UP -> its group
        self.hideable = set()      # reported keys whose press hasn't been hidden yet

    def send(self, line):
        self.outbuf += line.encode() + b"\n"
        if len(self.outbuf) > MAX_OUTBUF:
            raise ConnectionError("not reading its messages")
        self.flush()

    def flush(self):
        while self.outbuf:
            try:
                sent = self.sock.send(self.outbuf)
            except BlockingIOError:
                return
            self.outbuf = self.outbuf[sent:]


# --- the helper --------------------------------------------------------------------------

class Helper:
    def __init__(self, socket_dir=DEFAULT_SOCKET_DIR, seat_file=DEFAULT_SEAT_FILE,
                 input_dir=INPUT_DIR):
        self.socket_path = os.path.join(socket_dir, SOCKET_NAME)
        self.seat_file = seat_file
        self.input_dir = input_dir
        self.keyboards = {}        # path -> Keyboard
        self.clients = {}          # socket fd -> Client
        self.hide = None           # the HIDE in force (see start_hide)
        self.injected = []         # (keyboard path, code, value, expires) we sent ourselves
        self.next_scan = 0.0
        self.not_keyboards = {}    # path -> identity of a node not to open again
        self.listener = None
        self.running = True

    # -- setup ------------------------------------------------------------------------

    def listen(self):
        try:
            os.unlink(self.socket_path)
        except FileNotFoundError:
            pass
        sock = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM | socket.SOCK_CLOEXEC)
        sock.bind(self.socket_path)
        # Anyone may connect; only the user at the screen is kept (accept).
        os.chmod(self.socket_path, 0o666)
        sock.listen(MAX_CLIENTS)
        sock.setblocking(False)
        self.listener = sock

    def scan(self):
        """Open keyboards that have appeared. Not while hiding, so a keyboard
        plugged in mid-recording isn't left half-grabbed."""
        if self.hide is not None:
            return
        try:
            names = sorted(n for n in os.listdir(self.input_dir) if n.startswith("event"))
        except OSError:
            return
        for name in names:
            path = os.path.join(self.input_dir, name)
            if path in self.keyboards:
                continue
            try:
                st = os.stat(path)
                identity = (st.st_rdev, st.st_ino, st.st_ctime_ns)
            except OSError:
                continue
            if self.not_keyboards.get(path) == identity:
                continue                    # a mouse, a button, or one too many
            keyboard = Keyboard.open(path)
            if keyboard is None:
                self.not_keyboards[path] = identity
                continue
            virtual = sum(1 for k in self.keyboards.values() if k.virtual)
            if len(self.keyboards) >= MAX_KEYBOARDS or (
                    keyboard.virtual and virtual >= MAX_VIRTUAL_KEYBOARDS):
                keyboard.close()
                self.not_keyboards[path] = identity
                log(f"not watching {keyboard.name!r}: too many keyboards")
                continue
            self.not_keyboards.pop(path, None)
            self.keyboards[path] = keyboard
            log(f"watching keyboard {keyboard.name!r} ({path})")

    def drop_keyboard(self, keyboard):
        log(f"keyboard gone: {keyboard.name!r} ({keyboard.path})")
        self.keyboards.pop(keyboard.path, None)
        keyboard.close()
        # Its keys can't come up any more: tell whoever was told they went down.
        for code in sorted(keyboard.down):
            self.deliver_up(keyboard, code)
        if self.hide is not None and not any(
                k.path in self.keyboards for k in self.hide["keyboards"]):
            self.end_hide()

    def resync(self, keyboard):
        """After lost events, believe the kernel. A key found down now is
        down but untrusted; one found up is let go."""
        real = keyboard.kernel_down()
        for code in sorted(keyboard.down - real):
            keyboard.down.discard(code)
            keyboard.trusted.discard(code)
            self.deliver_up(keyboard, code)
        keyboard.down |= real

    # -- state ------------------------------------------------------------------------

    def held(self, code):
        return any(code in k.down for k in self.keyboards.values())

    def group_mods(self, group):
        """The trusted modifiers held on the keyboards of *group*."""
        mods = set()
        for k in self.keyboards.values():
            if k.group == group:
                mods |= k.down & k.trusted
        return mods

    def was_injected(self, path, code, value):
        now = time.monotonic()
        self.injected = [i for i in self.injected if i[3] > now]
        for i, (p, c, v, _) in enumerate(self.injected):
            if (p, c, v) == (path, code, value):
                del self.injected[i]
                return True
        return False

    def inject(self, keyboard, code, value):
        if keyboard.inject(code, value):
            self.injected.append((keyboard.path, code, value, time.monotonic() + INJECTED_TTL_S))
            return True
        return False

    # -- keys -------------------------------------------------------------------------

    def on_key(self, keyboard, code, value):
        if self.was_injected(keyboard.path, code, value):
            return
        if value == 1:
            elsewhere = self.held(code)
            keyboard.down.add(code)
            if code in MODIFIERS and not keyboard.grabbed:
                keyboard.trusted.add(code)
            if not elsewhere:
                self.deliver_down(keyboard, code)
        elif value == 0:
            keyboard.down.discard(code)
            keyboard.trusted.discard(code)
            self.deliver_up(keyboard, code)
        # value 2 is auto-repeat: never reported

    def deliver_up(self, keyboard, code):
        """*code* came up on *keyboard*. A release goes to whoever was told
        about the press from this keyboard, at the screen or not: it says
        nothing new. A modifier is let go once no keyboard of its group holds it."""
        for client in list(self.clients.values()):
            if client.origin.get(code) == keyboard.path:
                del client.origin[code]
                client.hideable.discard(code)
                self.send(client, f"UP {code}")
            elif client.mods_owed.get(code) == keyboard.group and \
                    code not in self.group_mods(keyboard.group) and \
                    not any(code in k.down for k in self.keyboards.values()
                            if k.group == keyboard.group):
                del client.mods_owed[code]
                self.send(client, f"UP {code}")

    def deliver_down(self, keyboard, code):
        if code in MODIFIERS:
            return
        # Most keys are wanted by nobody: drop them before anything else.
        interested = [c for c in self.clients.values()
                      if c.hello and (code in c.bare or code in c.combos)]
        if not interested:
            return
        active = read_active_uid(self.seat_file)
        if active is None:
            return
        # Modifiers count only from this keyboard's group (all real keyboards,
        # or this one virtual keyboard), and only those the desktop saw go
        # down (see Keyboard.trusted).
        mods = self.group_mods(keyboard.group)
        for client in interested:
            if client.uid != active:
                continue
            if code in client.bare:
                wanted = True
            else:
                # Not while a keyboard is held: the desktop doesn't see those keys.
                wanted = self.hide is None and any(
                    mods_satisfy(letters, mods) for letters in client.combos.get(code, ()))
            if wanted:
                client.origin[code] = keyboard.path
                client.hideable.add(code)
                for mod in mods:
                    client.mods_owed[mod] = keyboard.group
                self.send(client, f"DOWN {code} {','.join(map(str, sorted(mods))) or '-'}")

    # -- hiding a held hotkey ---------------------------------------------------------

    def start_hide(self, client, codes):
        if client.uid != read_active_uid(self.seat_file):
            return "ERR only the user at the screen can do that"
        if self.hide is not None:
            if self.hide["client"] is client:
                return "OK HIDE"            # already done for this client
            return "ERR the keyboards are already held"
        # Read what's already waiting first, so a key let go a moment ago
        # counts as let go (its UP goes out before this answer).
        for keyboard in list(self.keyboards.values()):
            self.read_keyboard(keyboard)
        # Once per press, and only on the keyboard the press came from: a
        # hotkey whose press was hidden before needs a new press.
        presses = {(client.origin[c], c) for c in codes
                   if c in client.hideable and c in client.origin
                   and client.origin[c] in self.keyboards
                   and c in self.keyboards[client.origin[c]].down}
        if not presses:
            return "ERR the hotkey isn't held"
        mods = [c for c in codes if c in client.mods_owed and c in MODIFIERS]
        # The desktop has seen these keys go down: tell it they went up, so it
        # doesn't auto-repeat them, then keep the keyboard, then mark them down
        # again, which only we see, so the real release still reaches us. By
        # the kernel's state, not what's been read, in case a release is on
        # its way. The press's own keyboard is kept; another keyboard of its
        # group only has its modifiers hidden the same way.
        held_on = []
        origins = {path for path, _ in presses}
        group = {self.keyboards[path].group for path in origins}
        for keyboard in list(self.keyboards.values()):
            if keyboard.path not in origins and keyboard.group not in group:
                continue
            really_down = keyboard.kernel_down()
            mine = [c for path, c in presses if path == keyboard.path]
            released = [c for c in mine + mods
                        if c in really_down and self.inject(keyboard, c, 0)]
            if keyboard.path in origins or released:
                keyboard.grab(True)
                held_on.append(keyboard)
            for code in released:
                self.inject(keyboard, code, 1)
            # The desktop now believes these are up.
            keyboard.trusted.difference_update(released)
        client.hideable.difference_update(c for _, c in presses)
        self.hide = {"client": client, "uid": client.uid, "presses": presses,
                     "keyboards": held_on, "since": time.monotonic(), "all_up_at": None}
        return "OK HIDE"

    def end_hide(self, why=None):
        if self.hide is None:
            return
        for keyboard in self.hide["keyboards"]:
            if keyboard.path in self.keyboards and keyboard.grabbed:
                keyboard.grab(False)
        if why:
            log(f"gave the keyboard back: {why}")
        self.hide = None

    def check_hide(self):
        """The safety net: a keyboard is never kept once the hotkey is let go."""
        hide = self.hide
        if hide is None:
            return
        now = time.monotonic()
        if now - hide["since"] > HIDE_MAX_S:
            self.end_hide("held too long")
        elif read_active_uid(self.seat_file) != hide["uid"]:
            self.end_hide("someone else is at the screen")
        elif any(path in self.keyboards and code in self.keyboards[path].down
                 for path, code in hide["presses"]):
            hide["all_up_at"] = None
        elif hide["all_up_at"] is None:
            hide["all_up_at"] = now
        elif now - hide["all_up_at"] > HIDE_RELEASE_GRACE_S:
            self.end_hide("the hotkey was let go")

    # -- talking ----------------------------------------------------------------------

    def accept(self):
        try:
            sock, _ = self.listener.accept()
        except OSError:
            return
        pid, uid, _gid = struct.unpack("3i", sock.getsockopt(
            socket.SOL_SOCKET, socket.SO_PEERCRED, struct.calcsize("3i")))
        active = read_active_uid(self.seat_file)
        if uid != active:
            sock.close()                    # only the user at the screen
            return
        if len(self.clients) >= MAX_CLIENTS:
            # Make room rather than turn the user at the screen away, so
            # nothing can hold every place and keep TuxTalk out: someone no
            # longer at the screen goes first, then a connection that never
            # said hello, then the oldest. Not the one holding a keyboard.
            keeper = self.hide["client"] if self.hide else None
            others = sorted((c for c in self.clients.values() if c is not keeper),
                            key=lambda c: (c.uid == active, c.hello, c.connected_at))
            if not others:
                sock.close()
                return
            self.drop_client(others[0])
        sock.setblocking(False)
        self.clients[sock.fileno()] = Client(sock, uid, pid)

    def drop_client(self, client):
        if self.hide is not None and self.hide["client"] is client:
            self.end_hide("TuxTalk went away")
        self.clients.pop(client.sock.fileno(), None)
        try:
            client.sock.close()
        except OSError:
            pass

    def send(self, client, line):
        try:
            client.send(line)
        except (ConnectionError, OSError):
            self.drop_client(client)

    def on_client_data(self, client):
        try:
            data = client.sock.recv(4096)
        except BlockingIOError:
            return
        except OSError:
            data = b""
        if not data:
            self.drop_client(client)
            return
        client.inbuf += data
        while b"\n" in client.inbuf:
            line, client.inbuf = client.inbuf.split(b"\n", 1)
            reply = self.handle(client, line.decode("ascii", "replace").strip())
            if reply:
                self.send(client, reply)
            if client.sock.fileno() not in self.clients:
                return
        if len(client.inbuf) > MAX_LINE:
            self.drop_client(client)

    def handle(self, client, line):
        words = line.split()
        if not words:
            return None
        command, args = words[0].upper(), words[1:]
        if command == "HELLO":
            if args[:1] != [str(PROTOCOL)]:
                return f"ERR this helper speaks protocol {PROTOCOL}"
            client.hello = True
            return f"HELLO {PROTOCOL} {VERSION}"
        if not client.hello:
            return "ERR say HELLO first"
        if command == "WATCH":
            if len(args) > MAX_SPECS:
                return "ERR too many keys"
            bare, combos, refused = set(), {}, []
            for spec in args:
                try:
                    parsed = parse_spec(spec)
                except ValueError as e:
                    refused.append(str(e))
                    continue
                if parsed[0] == "bare":
                    bare.add(parsed[1])
                else:
                    combos.setdefault(parsed[1], []).append(parsed[2])
            client.bare, client.combos = bare, combos
            return f"ERR {'; '.join(refused)}" if refused else "OK WATCH"
        if command == "HIDE":
            try:
                codes = [int(a) for a in args[:MAX_SPECS]]
            except ValueError:
                return "ERR not key codes"
            return self.start_hide(client, codes)
        if command == "UNHIDE":
            if self.hide is not None and self.hide["client"] is client:
                self.end_hide()
            return "OK UNHIDE"
        return "ERR unknown command"

    # -- the loop ---------------------------------------------------------------------

    def read_keyboard(self, keyboard):
        try:
            data = os.read(keyboard.fd, EVENT.size * 64)
        except BlockingIOError:
            return
        except OSError as e:
            if e.errno in (errno.ENODEV, errno.EIO, errno.EBADF):
                self.drop_keyboard(keyboard)
            return
        for offset in range(0, len(data) - EVENT.size + 1, EVENT.size):
            _s, _us, kind, code, value = EVENT.unpack_from(data, offset)
            if kind == EV_SYN and code == SYN_DROPPED:
                keyboard.dropping = True    # the kernel lost events
            elif keyboard.dropping:
                if kind == EV_SYN and code == SYN_REPORT:
                    keyboard.dropping = False
                    self.resync(keyboard)
            elif kind == EV_KEY:
                self.on_key(keyboard, code, value)

    def drop_silent_clients(self):
        """Connections that never said hello don't get to hold a place."""
        deadline = time.monotonic() - HELLO_DEADLINE_S
        for client in list(self.clients.values()):
            if not client.hello and client.connected_at < deadline:
                self.drop_client(client)

    def run_once(self, timeout=0.5):
        now = time.monotonic()
        if now >= self.next_scan:
            self.scan()
            self.next_scan = now + RESCAN_S
        readers = [self.listener] + [k.fd for k in self.keyboards.values()] \
            + [c.sock for c in self.clients.values()]
        writers = [c.sock for c in self.clients.values() if c.outbuf]
        try:
            ready, writable, _ = select.select(readers, writers, [], timeout)
        except InterruptedError:
            return
        by_fd = {k.fd: k for k in self.keyboards.values()}
        for item in ready:
            if item is self.listener:
                self.accept()
            elif isinstance(item, int):
                if item in by_fd and by_fd[item].path in self.keyboards:
                    self.read_keyboard(by_fd[item])
            else:
                client = self.clients.get(item.fileno()) if item.fileno() >= 0 else None
                if client is not None:
                    self.on_client_data(client)
        for sock in writable:
            client = self.clients.get(sock.fileno()) if sock.fileno() >= 0 else None
            if client is not None:
                try:
                    client.flush()
                except OSError:
                    self.drop_client(client)
        self.drop_silent_clients()
        self.check_hide()

    def run(self):
        self.listen()
        log(f"version {VERSION} listening on {self.socket_path}")
        try:
            while self.running:
                self.run_once()
        finally:
            self.end_hide()
            for keyboard in list(self.keyboards.values()):
                keyboard.close()
            try:
                os.unlink(self.socket_path)
            except OSError:
                pass


def main(argv=None):
    argv = sys.argv[1:] if argv is None else argv
    # --socket-dir is for testing only; the service uses the default.
    socket_dir = DEFAULT_SOCKET_DIR
    if len(argv) == 2 and argv[0] == "--socket-dir":
        socket_dir = argv[1]
    elif argv:
        print("usage: tuxtalk-hotkeys [--socket-dir DIR]", file=sys.stderr)
        return 2
    helper = Helper(socket_dir=socket_dir)

    def stop(*_args):
        helper.running = False

    signal.signal(signal.SIGTERM, stop)
    signal.signal(signal.SIGINT, stop)
    helper.run()
    return 0


if __name__ == "__main__":
    sys.exit(main())
