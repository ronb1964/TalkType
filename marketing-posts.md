# TalkType Marketing Posts

Ready-to-use posts for promoting TalkType. Copy/paste as needed.

---

## Post 1: r/linux (Main post - start here)

**Title:** `I built a voice dictation app for Wayland - TalkType (open source)`

**Body:**

Hey r/linux,

I've been working on a voice dictation app for Wayland called TalkType, and I think it's finally ready to share.

**The problem:** I wanted to dictate text on my Linux desktop, but most solutions are either X11-only, cloud-based, or require complicated setup. I wanted something that just works - press a key, talk, release, and the text appears.

**What TalkType does:**
- Press F8 (hold to talk) or F9 (toggle mode) to dictate
- Uses Whisper AI locally - no cloud, no subscription, your voice never leaves your machine
- Works on Wayland with ydotool for text injection
- Optional NVIDIA GPU acceleration (3-5x faster)
- Voice commands: "comma", "period", "new paragraph", "undo last word", etc.
- System tray with GNOME shell extension support

**Installation:**
- AppImage (all distros): https://github.com/ronb1964/TalkType/releases
- AUR: `yay -S talktype-appimage`

This is my first real software project, so I'd genuinely appreciate any feedback - bugs, feature requests, UI criticism, whatever. I use it daily for my own work and it's been solid for me, but I'm sure there are edge cases I haven't hit.

GitHub: https://github.com/ronb1964/TalkType

Screenshots in comments!

---

## Post 2: r/linuxapps (Shorter, casual)

**Title:** `TalkType - Voice dictation for Wayland (Whisper AI, open source)`

**Body:**

Built a voice dictation app because I couldn't find one that worked well on Wayland.

- Press F8 to talk, release to type
- Whisper AI runs locally (no cloud)
- GPU acceleration optional
- Voice commands for punctuation
- AppImage or AUR

First project, feedback welcome!

https://github.com/ronb1964/TalkType

---

## Post 3: r/wayland (Technical angle)

**Title:** `Voice dictation that actually works on Wayland - TalkType`

**Body:**

Finally got voice dictation working properly on Wayland. TalkType uses:

- **ydotool** for text injection (works on any Wayland compositor)
- **wl-clipboard** for clipboard paste fallback
- **Whisper AI** (faster-whisper) running locally

No X11 dependencies, no XWayland needed for the actual typing.

Features:
- Push-to-talk (F8) or toggle mode (F9)
- Smart punctuation and voice commands
- Optional CUDA acceleration
- GNOME shell extension for native integration

AppImage and AUR available: https://github.com/ronb1964/TalkType

Would love feedback from folks on different compositors - I've mainly tested on GNOME/Mutter.

---

## Post 4: r/gnome

**Title:** `TalkType - Voice dictation with native GNOME extension`

**Body:**

Made a voice dictation app that has a native GNOME shell extension for integration.

- Press F8 to dictate, text appears at cursor
- Whisper AI runs locally (private, no cloud)
- Extension shows in system tray with full menu
- GPU acceleration if you have NVIDIA

The extension is offered automatically on first run, or you can install it from Preferences.

AppImage: https://github.com/ronb1964/TalkType/releases
AUR: `yay -S talktype-appimage`

First project - feedback appreciated!

---

## Post 5: r/archlinux

**Title:** `TalkType - Voice dictation for Wayland (now on AUR)`

**Body:**

Just published my voice dictation app to AUR:

```
yay -S talktype-appimage
```

- Push-to-talk (F8) or toggle (F9) to dictate
- Whisper AI runs locally
- Optional CUDA for GPU acceleration
- GNOME extension included

Dependencies: fuse2, ydotool, wl-clipboard

GitHub: https://github.com/ronb1964/TalkType

First package on AUR, let me know if I messed anything up!

---

## Post 6: Hacker News (Show HN)

**Title:** `Show HN: TalkType – Open source voice dictation for Linux Wayland`

**URL:** `https://github.com/ronb1964/TalkType`

**Body (in first comment):**

I built TalkType because I wanted voice dictation on my Linux desktop that:
- Works on Wayland (not just X11)
- Runs locally (no cloud services)
- Doesn't require complex setup

It uses OpenAI's Whisper model via faster-whisper for transcription, ydotool for text injection, and has optional NVIDIA CUDA support for faster processing.

Press F8 to talk, release to type. Voice commands handle punctuation ("comma", "period", "new paragraph"). There's a system tray app and GNOME shell extension.

This is my first open source project. Feedback welcome.

---

## Posting Tips

### Best times to post:
- Tuesday, Wednesday, Thursday
- 9-11 AM Eastern Time

### Order of posting:
1. r/linux (day 1)
2. r/linuxapps (day 2)
3. r/wayland, r/gnome (day 3)
4. r/archlinux, r/fedora (day 4)
5. Hacker News (anytime, but weekday morning is best)

### Don't forget:
- Upload 2-3 screenshots with each Reddit post
- Respond to every comment
- Be genuine, not salesy
- Thank people for feedback even if critical
