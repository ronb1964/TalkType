# Third-party software in TuxTalk

TuxTalk itself is MIT-licensed (see [LICENSE](LICENSE)). The AppImage, .deb and
.rpm also contain other people's open-source software, and each keeps its own
license. All of their license texts are installed with TuxTalk:

- AppImage: `usr/share/licenses/` inside it
- .deb and .rpm: `/opt/talktype/usr/share/licenses/` (the folder kept its old name)
- AUR: inside the AppImage at `/opt/tuxtalk/TuxTalk.AppImage`

## Programs built from source

| Program | Version | License | Source code |
|---|---|---|---|
| ydotool | commit `708e96ff27e381a8c549418a9d34cdde12305317` | AGPL-3.0-or-later | https://github.com/ReimuNotMoe/ydotool |
| wl-clipboard | `v2.3.0` | GPL-3.0-or-later | https://github.com/bugaevc/wl-clipboard |

Both are built unmodified from the source at the version above, and TuxTalk
runs them as separate programs. ydotool types the dictated text; wl-clipboard
handles the clipboard for paste mode. The complete source for those exact
versions is at the addresses above, and backup copies are kept at
https://github.com/ronb1964/ydotool and https://github.com/ronb1964/wl-clipboard.
If it ever goes missing from all of those, open an issue at
https://github.com/ronb1964/TuxTalk/issues and I'll provide a copy, for at
least three years after the last TuxTalk release that includes it.

## Python and Python packages

- **Python 3.10** (PSF License), from Ubuntu 22.04.
- **Python packages** (faster-whisper, CTranslate2, onnxruntime, onnx-asr,
  NumPy, sounddevice, Hugging Face Hub, tokenizers, PyAV and the libraries they
  use): each package's license is in its own `*.dist-info` folder under
  `usr/lib/python3.10/site-packages/`. CTranslate2 (MIT) and tokenizers
  (Apache-2.0) don't include theirs, so they're added under
  `usr/share/licenses/`.
- **PyGObject, pycairo and dbus-python**, from Ubuntu 22.04.

## Libraries from Ubuntu 22.04

These are copied unmodified from Ubuntu 22.04: the tray icon libraries
(libayatana-appindicator3, libayatana-indicator3, libayatana-ido3,
libdbusmenu), GObject Introspection and its typelibs, libffi, PortAudio, the
JACK client library, Berkeley DB 5.3 and libpython. Mostly LGPL, MIT or
similar; each package's own copyright file is included.

The exact package versions are listed in
`usr/share/licenses/tuxtalk/bundled-ubuntu-packages.txt`. Their source is in
Ubuntu's archive: `apt-get source <package>` on Ubuntu 22.04, or
https://launchpad.net/ubuntu/jammy.
