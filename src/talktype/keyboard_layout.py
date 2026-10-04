"""
Type text correctly on any keyboard layout.

ydotool's `type` turns each character into the key it sits on in a US layout,
and the compositor then reads that key with the user's real layout. On a Swiss
German (QWERTZ) keyboard "my keyboard is lazy" arrived as "mz kezboard is
layz", punctuation moved, and umlauts couldn't be typed at all (GitHub issue
#8). So for any layout other than plain US this module works out the real
keys: it loads the active layout into libxkbcommon (the library compositors
use to turn key presses into characters) and finds, for each character, the
key plus Shift / AltGr that produces it. A character the layout has no key
for, like a capital Ä on a Swiss keyboard, is typed as its accent's dead key
followed by the letter. The keys go out through `ydotool key`, the same
uinput path as before, so no new permission is needed.

US layouts keep using `ydotool type` exactly as before. If some character
can't be typed on the active layout at all (an emoji, Latin text on a Russian
layout), the caller pastes that dictation instead, which works on any layout.

Finding the active layout depends on the desktop:
  KDE        org.kde.keyboard over D-Bus (the active one of the configured list)
  GNOME      gsettings org.gnome.desktop.input-sources (mru-sources first)
  Hyprland   `j/devices` on its socket (the main keyboard)
  Sway       GET_INPUTS on its socket; names are descriptions, mapped to codes
             with libxkbregistry
  X11        setxkbmap -query
  otherwise  the system default (xorg.conf.d / /etc/default/keyboard)
Anything that fails just means "unknown", and unknown means the old US path.
"""
import ctypes as C
import json
import os
import re
import subprocess
import unicodedata

from .logger import setup_logger

logger = setup_logger(__name__)

# --- libxkbcommon ------------------------------------------------------------------

_xkb = None


class _RuleNames(C.Structure):
    _fields_ = [(n, C.c_char_p) for n in ("rules", "model", "layout", "variant", "options")]


def _lib():
    """libxkbcommon with the signatures used here, loaded once."""
    global _xkb
    if _xkb is None:
        x = C.CDLL("libxkbcommon.so.0")
        P, U32 = C.c_void_p, C.c_uint32
        x.xkb_context_new.restype = P
        x.xkb_context_new.argtypes = [C.c_int]
        x.xkb_keymap_new_from_names.restype = P
        x.xkb_keymap_new_from_names.argtypes = [P, C.POINTER(_RuleNames), C.c_int]
        x.xkb_keymap_min_keycode.argtypes = [P]
        x.xkb_keymap_max_keycode.argtypes = [P]
        x.xkb_keymap_num_levels_for_key.argtypes = [P, U32, U32]
        x.xkb_keymap_key_get_syms_by_level.argtypes = [P, U32, U32, U32, C.POINTER(C.POINTER(U32))]
        x.xkb_keymap_key_get_mods_for_level.argtypes = [P, U32, U32, U32, C.POINTER(U32), C.c_size_t]
        x.xkb_keymap_key_get_mods_for_level.restype = C.c_size_t
        x.xkb_keymap_mod_get_index.argtypes = [P, C.c_char_p]
        x.xkb_keymap_mod_get_index.restype = U32
        x.xkb_utf32_to_keysym.argtypes = [U32]
        x.xkb_utf32_to_keysym.restype = U32
        _xkb = x
    return _xkb


_EVDEV_OFFSET = 8               # xkb keycode = evdev keycode + 8
_KEY_LEFTSHIFT = 42             # evdev
_KEY_RIGHTALT = 100             # evdev; AltGr on almost every layout
_ISO_LEVEL3_SHIFT = 0xfe03      # keysym AltGr produces
_INVALID_MOD = 0xffffffff

# Combining marks (what NFD splits an accented letter into) and the dead key
# that types each one on layouts without a key for the accented letter.
_DEAD_KEYS = {
    "̀": 0xfe50,  # grave
    "́": 0xfe51,  # acute
    "̂": 0xfe52,  # circumflex
    "̃": 0xfe53,  # tilde
    "̄": 0xfe54,  # macron
    "̆": 0xfe55,  # breve
    "̇": 0xfe56,  # dot above
    "̈": 0xfe57,  # diaeresis (umlaut)
    "̊": 0xfe58,  # ring
    "̋": 0xfe59,  # double acute
    "̌": 0xfe5a,  # caron
    "̧": 0xfe5b,  # cedilla
    "̨": 0xfe5c,  # ogonek
}


class KeyPlanner:
    """The keys that type text on one layout (layout + variant, e.g. "ch", "")."""

    def __init__(self, layout, variant=""):
        x = _lib()
        self.layout, self.variant = layout, variant or ""
        self.ctx = x.xkb_context_new(0)
        names = _RuleNames(b"evdev", b"pc105", layout.encode(), self.variant.encode(), None)
        self.keymap = x.xkb_keymap_new_from_names(self.ctx, C.byref(names), 0)
        if not self.keymap:
            raise ValueError(f"unknown keyboard layout {layout}({variant})")
        self._keys = {}         # keysym -> (evdev keycode, shift, altgr)
        self._altgr = None
        self._index()

    def _index(self):
        x = _lib()
        shift = x.xkb_keymap_mod_get_index(self.keymap, b"Shift")
        altgr = x.xkb_keymap_mod_get_index(self.keymap, b"Mod5")
        shift_bit = 1 << shift if shift != _INVALID_MOD else 0
        altgr_bit = 1 << altgr if altgr != _INVALID_MOD else 0
        allowed = shift_bit | altgr_bit
        altgr_keys = []
        for kc in range(x.xkb_keymap_min_keycode(self.keymap), x.xkb_keymap_max_keycode(self.keymap) + 1):
            for level in range(x.xkb_keymap_num_levels_for_key(self.keymap, kc, 0)):
                syms = C.POINTER(C.c_uint32)()
                if x.xkb_keymap_key_get_syms_by_level(self.keymap, kc, 0, level, C.byref(syms)) != 1:
                    continue
                sym = syms[0]
                masks = (C.c_uint32 * 8)()
                for i in range(x.xkb_keymap_key_get_mods_for_level(self.keymap, kc, 0, level, masks, 8)):
                    mask = masks[i]
                    if mask & ~allowed:
                        continue        # needs Caps Lock, Level5 or the like: skip
                    if sym == _ISO_LEVEL3_SHIFT and mask == 0:
                        altgr_keys.append(kc - _EVDEV_OFFSET)
                    entry = (kc - _EVDEV_OFFSET, bool(mask & shift_bit), bool(mask & altgr_bit))
                    cost = entry[1] + entry[2]
                    if sym not in self._keys or cost < self._keys[sym][1] + self._keys[sym][2]:
                        self._keys[sym] = entry
        # Right Alt if it is AltGr, as it is on real keyboards; layouts also map a
        # virtual key to it, which works in the keymap but not on every compositor.
        if altgr_keys:
            self._altgr = _KEY_RIGHTALT if _KEY_RIGHTALT in altgr_keys else altgr_keys[0]

    def _press(self, entry, tokens):
        keycode, shift, altgr = entry
        if altgr and self._altgr is None:
            return False
        held = ([_KEY_LEFTSHIFT] if shift else []) + ([self._altgr] if altgr else [])
        tokens += [f"{k}:1" for k in held]
        tokens += [f"{keycode}:1", f"{keycode}:0"]
        tokens += [f"{k}:0" for k in reversed(held)]
        return True

    def _keysym(self, char):
        return 0x20 if char == " " else _lib().xkb_utf32_to_keysym(ord(char))

    def plan(self, text):
        """ydotool `key` arguments ("keycode:pressed") that type *text*, or None
        if some character can't be typed on this layout."""
        tokens = []
        for char in text:
            entry = self._keys.get(self._keysym(char))
            if entry and self._press(entry, tokens):
                continue
            # Not on a key of its own: an accented letter as dead key + letter.
            parts = unicodedata.normalize("NFD", char)
            if len(parts) == 2 and parts[1] in _DEAD_KEYS:
                dead = self._keys.get(_DEAD_KEYS[parts[1]])
                base = self._keys.get(self._keysym(parts[0]))
                if dead and base and self._press(dead, tokens) and self._press(base, tokens):
                    continue
            return None
        return tokens


_planners = {}


def planner_for(layout_variant):
    """A cached KeyPlanner for (layout, variant); building one takes ~20 ms."""
    if layout_variant not in _planners:
        _planners[layout_variant] = KeyPlanner(*layout_variant)
    return _planners[layout_variant]


def needs_layout_typing(layout_variant, text) -> bool:
    """Whether text should be typed key by key for this layout: anything but
    plain US. Unknown layouts (None) keep the old path."""
    if not layout_variant:
        return False
    layout, variant = layout_variant
    return not (layout == "us" and not variant)


# --- the active layout ---------------------------------------------------------------

_XORG_KEYBOARD_CONF = "/etc/X11/xorg.conf.d/00-keyboard.conf"
_DEBIAN_KEYBOARD = "/etc/default/keyboard"


def _desktop():
    from .desktop_detect import get_desktop_environment
    return get_desktop_environment()


def _first(csv, index=0):
    items = [s.strip() for s in (csv or "").split(",")]
    return items[index] if 0 <= index < len(items) else (items[0] if items else "")


def _kde_layouts():
    """([(layout, variant)], active index) from KDE's keyboard daemon."""
    import dbus
    obj = dbus.SessionBus().get_object("org.kde.keyboard", "/Layouts")
    iface = dbus.Interface(obj, "org.kde.KeyboardLayouts")
    layouts = [(str(entry[0]), str(entry[1])) for entry in iface.getLayoutsList()]
    return layouts, int(iface.getLayout())


def _gsettings(key):
    return subprocess.run(["gsettings", "get", "org.gnome.desktop.input-sources", key],
                          capture_output=True, text=True, timeout=2).stdout


def _gnome_layout():
    for key in ("mru-sources", "sources"):
        found = re.findall(r"\('(\w+)',\s*'([^']*)'\)", _gsettings(key))
        if found:
            kind, name = found[0]
            if kind != "xkb":
                return None     # an input method (IBus); its layout isn't knowable here
            layout, _, variant = name.partition("+")
            return layout, variant
    return None


def _hyprland_devices():
    from .compositor_focus import _exchange, _recv_until_closed
    runtime = os.environ.get("XDG_RUNTIME_DIR") or f"/run/user/{os.getuid()}"
    path = os.path.join(runtime, "hypr", os.environ["HYPRLAND_INSTANCE_SIGNATURE"], ".socket.sock")
    return json.loads(_exchange(path, b"j/devices", _recv_until_closed))


def _hyprland_layout():
    keyboards = _hyprland_devices().get("keyboards") or []
    board = next((k for k in keyboards if k.get("main")), keyboards[0] if keyboards else None)
    if not board:
        return None
    index = int(board.get("active_layout_index") or 0)
    return _first(board.get("layout"), index), _first(board.get("variant"), index)


def _sway_inputs():
    import struct
    from .compositor_focus import _I3_MAGIC, _exchange, _i3_reply
    get_inputs = 100
    return _exchange(os.environ.get("SWAYSOCK") or os.environ["I3SOCK"],
                     _I3_MAGIC + struct.pack("<II", 0, get_inputs), _i3_reply)


def _layout_from_description(description):
    """(layout, variant) for a description like "German (Switzerland)", from
    libxkbregistry, which holds the names every layout picker shows."""
    reg = C.CDLL("libxkbregistry.so.0")
    P = C.c_void_p
    reg.rxkb_context_new.restype = P
    reg.rxkb_context_new.argtypes = [C.c_int]
    reg.rxkb_context_parse_default_ruleset.argtypes = [P]
    reg.rxkb_layout_first.restype = P
    reg.rxkb_layout_first.argtypes = [P]
    reg.rxkb_layout_next.restype = P
    reg.rxkb_layout_next.argtypes = [P]
    for fn in ("rxkb_layout_get_name", "rxkb_layout_get_variant", "rxkb_layout_get_description"):
        getattr(reg, fn).restype = C.c_char_p
        getattr(reg, fn).argtypes = [P]
    ctx = reg.rxkb_context_new(0)
    if not ctx or not reg.rxkb_context_parse_default_ruleset(ctx):
        return None
    layout = reg.rxkb_layout_first(ctx)
    while layout:
        if (reg.rxkb_layout_get_description(layout) or b"").decode() == description:
            return ((reg.rxkb_layout_get_name(layout) or b"").decode(),
                    (reg.rxkb_layout_get_variant(layout) or b"").decode())
        layout = reg.rxkb_layout_next(layout)
    return None


def _sway_layout():
    board = next((i for i in _sway_inputs() if i.get("type") == "keyboard"), None)
    if not board:
        return None
    names = board.get("xkb_layout_names") or []
    index = board.get("xkb_active_layout_index") or 0
    if not names:
        return None
    return _layout_from_description(names[index if index < len(names) else 0])


def _setxkbmap_query():
    return subprocess.run(["setxkbmap", "-query"], capture_output=True, text=True, timeout=2).stdout


def _x11_layout():
    fields = dict(re.findall(r"^(\w+):\s*(.*)$", _setxkbmap_query(), re.M))
    return (_first(fields.get("layout")), _first(fields.get("variant"))) if fields.get("layout") else None


def _system_layout():
    """The system-wide default layout, as set at install time."""
    try:
        with open(_XORG_KEYBOARD_CONF) as f:
            conf = f.read()
        layout = re.search(r'Option\s+"XkbLayout"\s+"([^"]+)"', conf)
        if layout:
            variant = re.search(r'Option\s+"XkbVariant"\s+"([^"]*)"', conf)
            return _first(layout.group(1)), _first(variant.group(1) if variant else "")
    except OSError:
        pass
    try:
        with open(_DEBIAN_KEYBOARD) as f:
            values = dict(re.findall(r'^(\w+)="?([^"\n]*)"?', f.read(), re.M))
        if values.get("XKBLAYOUT"):
            return _first(values["XKBLAYOUT"]), _first(values.get("XKBVARIANT", ""))
    except OSError:
        pass
    return None


def active_layout():
    """(layout, variant) of the keyboard layout in use, or None if unknown."""
    try:
        found = None
        if os.environ.get("HYPRLAND_INSTANCE_SIGNATURE"):
            found = _hyprland_layout()
        elif os.environ.get("SWAYSOCK") or os.environ.get("I3SOCK"):
            found = _sway_layout()
        else:
            desktop = _desktop()
            if desktop == "kde":
                layouts, index = _kde_layouts()
                found = layouts[index] if 0 <= index < len(layouts) else None
            elif desktop == "gnome":
                found = _gnome_layout()
            elif (os.environ.get("XDG_SESSION_TYPE") or "").lower() == "x11":
                found = _x11_layout()
        if found and found[0]:
            return found
    except Exception as e:
        logger.debug(f"Could not read the keyboard layout from the desktop: {e}")
    try:
        return _system_layout()
    except Exception:
        return None


def layout_key_events(text):
    """How to type *text* on the active layout:
      None              plain US or unknown: use `ydotool type` as always
      [] / ["30:1", ...] the ydotool `key` arguments that type it
    Raises UntypableText if the layout has no way to type some character."""
    layout = active_layout()
    if not needs_layout_typing(layout, text):
        return None
    tokens = planner_for(layout).plan(text)
    if tokens is None:
        raise UntypableText(layout)
    return tokens


class UntypableText(Exception):
    """Some character can't be typed on the active layout."""
