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
privileges). It tells whoever asks only about TuxTalk-style hotkeys:

* F1-F24, Esc, Pause and Scroll Lock on their own, and
* other keys only while Ctrl, Alt or Super is held with them,

and only to the user sitting at the screen (logind's active user of seat0).
It never reports a letter, a number, Enter, Backspace or Shift+letter, so
even a hostile program that connects learns nothing about what is typed.

It can also hide a held hotkey from the desktop and keep the keyboards to
itself while it is held (what TuxTalk does so a held F8 doesn't auto-repeat
into the window being dictated into). That is allowed only while the hotkey
is physically held, and ends by itself within a second of letting go, or
when the program that asked for it goes away.

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
                               the keyboards until UNHIDE or they're let go
  UNHIDE                       give the keyboards back
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
VERSION = "1.0"

DEFAULT_SOCKET_DIR = "/run/tuxtalk-hotkeys"
SOCKET_NAME = "hotkeys.sock"
DEFAULT_SEAT_FILE = "/run/systemd/seats/seat0"
INPUT_DIR = "/dev/input"

# --- evdev numbers (linux/input.h, linux/input-event-codes.h) -------------------

EV_SYN, EV_KEY, EV_REL = 0, 1, 2
SYN_REPORT = 0
REL_X = 0
BTN_LEFT = 0x110
KEY_MAX = 0x2FF
KEY_ESC, KEY_SCROLLLOCK, KEY_PAUSE = 1, 70, 119

F_KEYS = frozenset(list(range(59, 69)) + [87, 88] + list(range(183, 195)))   # F1-F24
BARE_KEYS = F_KEYS | {KEY_ESC, KEY_PAUSE, KEY_SCROLLLOCK}

# The modifiers, by the letter the protocol uses for each pair.
MOD_GROUPS = {
    "C": frozenset({29, 97}),       # Ctrl, left and right
    "A": frozenset({56, 100}),      # Alt
    "S": frozenset({42, 54}),       # Shift
    "M": frozenset({125, 126}),     # Meta / Super
}
MODIFIERS = frozenset().union(*MOD_GROUPS.values())

# Letter keys tell a keyboard from a power button, a lid switch or a game
# controller; TuxTalk's own test (uinput_helper.is_keyboard_device) is the same.
LETTER_KEYS = frozenset(list(range(16, 26)) + list(range(30, 39)) + list(range(44, 51)))

# struct input_event: a timeval (two longs), then type, code and value.
EVENT = struct.Struct("llHHi")


def _ioc(direction, number, size):
    return (direction << 30) | (size << 16) | (ord("E") << 8) | number


EVIOCGRAB = _ioc(1, 0x90, 4)
KEY_BYTES = KEY_MAX // 8 + 1


def EVIOCGBIT(event_type, length):
    return _ioc(2, 0x20 + event_type, length)


def EVIOCGKEY(length):
    return _ioc(2, 0x18, length)


def EVIOCGNAME(length):
    return _ioc(2, 0x06, length)


# --- limits: nobody gets to make this helper do much work ----------------------------

MAX_CLIENTS = 8
MAX_CLIENTS_PER_UID = 4
MAX_LINE = 512
MAX_SPECS = 32
MAX_OUTBUF = 64 * 1024
RESCAN_S = 2.0
HIDE_RELEASE_GRACE_S = 1.0    # the keyboards come back this long after the hotkey is let go
HIDE_MAX_S = 15 * 60          # and never later than this
INJECTED_TTL_S = 2.0


def log(message):
    """One line to the journal. Never a key the user typed: only devices,
    connections and refusals."""
    print(f"tuxtalk-hotkeys: {message}", flush=True)


# --- what may be reported ------------------------------------------------------------

def parse_spec(spec):
    """("bare", code) or ("combo", code, frozenset of mod letters) for a WATCH
    spec, or raise ValueError saying why it is refused.

    The rule, in one sentence: a key that types something is reported only
    while Ctrl, Alt or Super is held with it."""
    mods, _, number = spec.rpartition(":")
    try:
        code = int(number)
    except ValueError:
        raise ValueError(f"not a key code: {spec!r}")
    if not 0 < code <= KEY_MAX or code in MODIFIERS:
        raise ValueError(f"not a key that can be watched: {spec!r}")
    if not mods:
        if code not in BARE_KEYS:
            raise ValueError(f"key {code} is only reported together with Ctrl, Alt or Super")
        return ("bare", code)
    letters = frozenset(mods.upper())
    if not letters or not letters <= set(MOD_GROUPS) or len(letters) != len(mods):
        raise ValueError(f"bad modifiers in {spec!r}")
    if code not in BARE_KEYS and not letters & {"C", "A", "M"}:
        raise ValueError(f"{spec!r} needs Ctrl, Alt or Super")
    return ("combo", code, letters)


def mods_satisfy(letters, held):
    """Whether every modifier named in *letters* is held (left or right)."""
    return all(MOD_GROUPS[letter] & held for letter in letters)


def bits(buffer):
    """The set bit numbers of an ioctl bit-array reply."""
    return {i * 8 + j for i, byte in enumerate(buffer) for j in range(8) if byte >> j & 1}


def read_active_uid(seat_file):
    """The uid of the user whose session is in front on seat0, or None.
    logind keeps it in a plain file; no answer means nobody gets events."""
    try:
        with open(seat_file) as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key == "ACTIVE_UID" and value.isdigit():
                    return int(value)
    except OSError:
        pass
    return None


# --- keyboards --------------------------------------------------------------------------

class Keyboard:
    """One open /dev/input/event* keyboard and the keys down on it."""

    def __init__(self, path, fd, name, down):
        self.path, self.fd, self.name, self.down = path, fd, name, set(down)
        self.grabbed = False

    @classmethod
    def open(cls, path):
        """The keyboard at *path*, or None if it isn't one (mouse, power button,
        game controller) or can't be opened."""
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
            if len(keys & LETTER_KEYS) < 3 or pointer:
                os.close(fd)
                return None
            name = bytearray(256)
            fcntl.ioctl(fd, EVIOCGNAME(len(name)), name, True)
            state = bytearray(KEY_BYTES)
            fcntl.ioctl(fd, EVIOCGKEY(len(state)), state, True)
            return cls(path, fd, name.split(b"\0", 1)[0].decode("utf-8", "replace"), bits(state))
        except OSError:
            os.close(fd)
            return None

    def kernel_down(self):
        """The keys the kernel says are down on this keyboard right now.
        Hiding goes by this, not by what has been read so far: a release
        still waiting to be read must not be mistaken for our own."""
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
        self.inbuf = b""
        self.outbuf = b""
        self.hello = False
        self.bare = set()          # codes reported on their own
        self.combos = {}           # code -> list of modifier-letter sets
        self.reported = set()      # keys reported DOWN, not yet UP
        self.mods_owed = set()     # modifiers held at a reported DOWN, not yet UP

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
        self.hide = None           # the HIDE in force: dict(client, codes, since, all_up_at)
        self.injected = []         # (keyboard path, code, value, expires) we sent ourselves
        self.next_scan = 0.0
        self.not_keyboards = {}    # path -> identity of a node that isn't a keyboard
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
        # Anyone may connect: what is said is limited by the rules above and
        # goes only to the user at the screen, checked per connection.
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
                continue                    # a mouse or a button, seen before
            keyboard = Keyboard.open(path)
            if keyboard is None:
                self.not_keyboards[path] = identity
            else:
                self.not_keyboards.pop(path, None)
                self.keyboards[path] = keyboard
                log(f"watching keyboard {keyboard.name!r} ({path})")

    def drop_keyboard(self, keyboard):
        log(f"keyboard gone: {keyboard.name!r} ({keyboard.path})")
        self.keyboards.pop(keyboard.path, None)
        keyboard.close()
        # Its keys can't come up any more: tell whoever was told they went down.
        for code in sorted(keyboard.down):
            if not self.held(code):
                self.deliver(code, 0)

    # -- state ------------------------------------------------------------------------

    def held(self, code):
        return any(code in k.down for k in self.keyboards.values())

    def mods_held(self):
        held = set()
        for k in self.keyboards.values():
            held |= k.down & MODIFIERS
        return held

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
            if self.held(code):
                keyboard.down.add(code)
                return                  # already down on another keyboard
            keyboard.down.add(code)
        elif value == 0:
            keyboard.down.discard(code)
        else:
            return                      # auto-repeat: never reported
        if value == 0 and self.held(code):
            return                      # still down on another keyboard
        self.deliver(code, value)

    def deliver(self, code, value):
        if value == 0:
            # A release goes to whoever was told about the press, at the
            # screen or not: it says nothing new.
            for client in list(self.clients.values()):
                if code in client.reported or code in client.mods_owed:
                    client.reported.discard(code)
                    client.mods_owed.discard(code)
                    self.send(client, f"UP {code}")
            return
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
        mods = self.mods_held()
        for client in interested:
            if client.uid != active:
                continue
            wanted = code in client.bare or any(
                mods_satisfy(letters, mods) for letters in client.combos.get(code, ()))
            if wanted:
                client.reported.add(code)
                client.mods_owed |= mods
                self.send(client, f"DOWN {code} {','.join(map(str, sorted(mods))) or '-'}")

    # -- hiding a held hotkey ---------------------------------------------------------

    def start_hide(self, client, codes):
        if client.uid != read_active_uid(self.seat_file):
            return "ERR only the user at the screen can do that"
        if self.hide is not None and self.hide["client"] is not client:
            return "ERR the keyboards are already held"
        # Read what's already waiting first, so a key let go a moment ago
        # counts as let go (its UP goes out before this answer).
        for keyboard in list(self.keyboards.values()):
            self.read_keyboard(keyboard)
        mine = client.reported | client.mods_owed
        codes = [c for c in codes if c in mine and self.held(c)]
        if not any(c in client.reported for c in codes):
            return "ERR the hotkey isn't held"
        if self.hide is not None:
            return "OK HIDE"            # already done for this client
        # The desktop has seen these keys go down. Tell it they went up, so
        # it doesn't auto-repeat them, then keep the keyboards. Then mark them
        # down again, which only we see, so the real release still reaches us.
        released = []
        for keyboard in self.keyboards.values():
            really_down = keyboard.kernel_down()
            for code in codes:
                if code in really_down and self.inject(keyboard, code, 0):
                    released.append((keyboard, code))
        for keyboard in self.keyboards.values():
            keyboard.grab(True)
        for keyboard, code in released:
            self.inject(keyboard, code, 1)
        self.hide = {"client": client, "codes": set(codes),
                     "since": time.monotonic(), "all_up_at": None}
        return "OK HIDE"

    def end_hide(self, why=None):
        if self.hide is None:
            return
        for keyboard in self.keyboards.values():
            if keyboard.grabbed:
                keyboard.grab(False)
        if why:
            log(f"gave the keyboards back: {why}")
        self.hide = None

    def check_hide(self):
        """The safety net: the keyboards are never kept once the hotkey is let go."""
        hide = self.hide
        if hide is None:
            return
        now = time.monotonic()
        if now - hide["since"] > HIDE_MAX_S:
            self.end_hide("held too long")
        elif any(self.held(c) for c in hide["codes"]):
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
        per_uid = sum(1 for c in self.clients.values() if c.uid == uid)
        if len(self.clients) >= MAX_CLIENTS or per_uid >= MAX_CLIENTS_PER_UID:
            sock.close()
            return
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
            if kind == EV_KEY:
                self.on_key(keyboard, code, value)

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
