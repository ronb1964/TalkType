claude
DEV_NOTES.md
Project: TalkType (a.k.a. TalkType)

Press-and-hold (or toggle) dictation for Wayland. Uses Faster-Whisper for STT and ydotool to type into the focused window. Includes smart punctuation, quotes, ellipsis, capitalization, config file, CLI flags, optional tray, and a GTK Preferences UI.

Current features

Wayland typing via ydotool type -f - (preferred) with fallbacks:

wtype, then wl-copy (clipboard) if needed

Activation modes

hold: press & hold F8 (default); release to transcribe+type

toggle: tap a key (default F9) to start; tap again to stop

Audio

Captures mic using sounddevice at 16 kHz mono, 16-bit PCM

Optional beeps (start/stop/ready)

Optional desktop notifications for start/stop/result

Mic device selection by substring match of device name

Transcription

Faster-Whisper (ct2) models; default small, int8, CPU

Post-processing (normalize)

Voice tokens → punctuation & structure:

comma, period, exclamation point, question mark, colon, semicolon

open quote / close quote → “ ” (smart quotes)

dot dot dot → … (ellipsis)

new line → Shift+Enter (soft line break)

new paragraph → Two Shift+Enter keystrokes (paragraph break)

tab

Capitalization: start of text, after ellipsis, after newline

Punctuation inside closing quote: “Hello, world!”

Keeps tabs at line starts; strips spaces immediately after tabs

Collapses internal space runs; tightens spaces around punctuation

Auto-space: when a new utterance types into existing text, we prepend a single space unless the result would start on a new line or tab

Config

TOML: ~/.config/talktype/config.toml

Env overrides and CLI flags

Tray (AppIndicator)

Start / Stop / Restart service (direct process management, no systemd required)

Dynamic menu showing Start when stopped, Stop when running

Open Preferences (GTK) to edit config and restart the service

Launcher Integration

Single tray launcher manages both tray icon and dictation service

.desktop launchers available for Tray/Preferences

Repo layout
src/talktype/
  app.py           # main listener loop: hotkeys, audio record, STT, typing
  normalize.py     # text post-processing rules (tests cover behavior)
  config.py        # load config from TOML + env overrides
  tray.py          # AppIndicator tray menu (Start/Stop/Restart/Preferences)
  prefs.py         # GTK Preferences UI (edit config & restart service)
tests/
  test_normalize.py # unit tests for normalize_text()  (5 passing)
pyproject.toml     # Poetry config, console scripts
README.md


Console scripts (via Poetry):

dictate → talktype.app:main

dictate-tray → talktype.tray:main

dictate-prefs → talktype.prefs:main

Dependencies

Runtime (Python):

faster-whisper, sounddevice, evdev, numpy, pyperclip (fallback)

Optional tray/GUI/notify: pygobject

Tests/dev: pytest, black, ruff

System packages (Fedora/Nobara):

sudo dnf install -y portaudio-devel ffmpeg ydotool wl-clipboard wtype \
                    python3-gobject libappindicator-gtk3 libnotify


Nobara/GNOME Wayland needs the AppIndicator GNOME shell extension enabled for tray icons:

sudo dnf install -y gnome-shell-extension-appindicator
gnome-extensions enable appindicatorsupport@rgcjonas.gmail.com
# log out/in once


ydotoold daemon (user service) must be running:

mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/ydotoold.service <<'EOF'
[Unit]
Description=ydotool daemon (Wayland keystroke injector)
After=graphical-session.target
Wants=graphical-session.target

[Service]
Environment=XDG_RUNTIME_DIR=%t
ExecStartPre=/usr/bin/sleep 1
ExecStart=/usr/bin/ydotoold --socket-path=%t/.ydotool_socket
Restart=on-failure
RestartSec=1
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now ydotoold.service

Config file

~/.config/talktype/config.toml:

model = "small"         # tiny/base/small/medium/large-v3
device = "cpu"          # "cpu" or "cuda"
hotkey = "F8"           # hold-to-talk key
beeps = true
smart_quotes = true
mode = "hold"           # "hold" or "toggle"
toggle_hotkey = "F9"    # used when mode="toggle"
mic = ""                # substring of mic device name ("" = default)
notify = true           # desktop notifications on/off


Environment variable overrides (optional):

DICTATE_MODEL, DICTATE_DEVICE, DICTATE_HOTKEY, DICTATE_MODE, DICTATE_TOGGLE_HOTKEY,
DICTATE_MIC, DICTATE_BEEPS, DICTATE_SMART_QUOTES, DICTATE_NOTIFY


CLI flags (override config for one run):

poetry run dictate \
  --model base --device cpu \
  --mode toggle --toggle-hotkey F7 \
  --hotkey F8 --mic "USB" \
  --beeps on --smart-quotes on --notify on

Systemd service (user) for the app
mkdir -p ~/.config/systemd/user
cat > ~/.config/systemd/user/TalkType.service <<'EOF'
[Unit]
Description=Ron Dictation Listener (F8) - Faster-Whisper + ydotool
After=ydotoold.service graphical-session.target
Wants=ydotoold.service

[Service]
Type=simple
ExecStart=/bin/bash -lc 'cd ~/projects/TalkType && poetry run dictate'
Restart=on-failure
RestartSec=2
StandardOutput=journal
StandardError=journal

[Install]
WantedBy=default.target
EOF

systemctl --user daemon-reload
systemctl --user enable --now TalkType.service
journalctl --user -fu TalkType.service


Desktop launchers (already included in setup):

~/.local/share/applications/TalkType-start.desktop

~/.local/share/applications/TalkType-stop.desktop

~/.local/share/applications/TalkType-tray.desktop

~/.local/share/applications/TalkType-prefs.desktop

Autostart tray on login:

~/.config/autostart/TalkType-tray.desktop
Exec=sh -lc 'cd ~/projects/TalkType && poetry run dictate-tray'

Development (Cursor / Poetry)

Activate Poetry env (path will differ on your machine):

source /home/ron/.cache/pypoetry/virtualenvs/TalkType-*/bin/activate


Or in Cursor:

Install Python extension (Microsoft), Pylance

Set interpreter to the Poetry venv (…/bin/python)

Tasks:

Run app: poetry run dictate

Run tray: poetry run dictate-tray

Run tests: poetry run pytest -q

Tests

Run:

poetry run pytest -q


Behavior covered (all pass):

open quote hello comma world close quote exclamation point
→ “Hello, world!”

Ellipsis: dot dot dot sets capitalize_next

Newline + tab processing and spacing rules

Troubleshooting

Double characters (e.g., HHeelloo)
Likely two listeners running (old nohup/systemd + new service).
Fix:

systemctl --user stop voice-dictation.service
systemctl --user disable voice-dictation.service
systemctl --user mask voice-dictation.service
pkill -f 'speech_to_text.py|poetry run dictate|talktype.app' || true
systemctl --user restart TalkType.service


Nothing typed / “Could not type text”
Ensure ydotoold is active, socket exists, and user can access /dev/uinput.

systemctl --user status ydotoold.service
ls -l $XDG_RUNTIME_DIR/.ydotool_socket
groups  # ensure uinput permissions if needed


Tray not visible on GNOME Wayland
Make sure AppIndicator shell extension is installed & enabled; log out/in once.

CUDA/cuDNN warnings
If you don’t have cuDNN 9.x, set device to cpu (default) or install matching CUDA/cuDNN.

Roadmap

 Silence auto-stop (VAD) with configurable end-of-speech timeout

 Per-app profiles (Cursor vs Browser) with different hotkeys/models

 Language auto-detect / multilingual models

 Custom phrase mappings (user dictionary / commands → text)

 Microphone picker UI in Preferences (list devices, test meter)

 Notifications: richer summaries, error popups

 Packaging: PyPI wheel, RPM spec, Flatpak sandbox (portal typing?)

 Security: optionally require a modifier (e.g., Ctrl+F8) to prevent accidental capture

Credits

STT: Faster-Whisper (CTranslate2)

Typing: ydotool, wtype, wl-clipboard

UI: GTK (PyGObject), AppIndicator

Platform: Wayland (GNOME/Nobara/Fedora)

Quick commands (copy/paste)
# run listener in foreground (test)
poetry run dictate

# run tray
poetry run dictate-tray &

# open prefs GUI
poetry run dictate-prefs

# logs (service)
journalctl --user -fu TalkType.service


Maintainer notes: When adding features, please update this file so Cursor’s AI and future contributors have context without digging through chat history.

Commit this file
git add DEV_NOTES.md
git commit -m "Add DEV_NOTES with architecture, setup, and roadmap"
git push
