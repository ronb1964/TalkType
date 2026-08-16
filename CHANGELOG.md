# Changelog

All notable changes to TalkType are documented here.

## [0.7.0] - 2026-08-15

This release is about getting TalkType onto your computer the normal way and
making the very first run work reliably — whichever Linux you use.

### Install it the way your distribution expects
- **New `.deb` package** for Debian, Ubuntu and Linux Mint: `sudo apt install ./talktype_*_amd64.deb`
- **New `.rpm` package** for Fedora, RHEL and openSUSE: `sudo dnf install ./talktype-*.x86_64.rpm`
- **The Arch (AUR) package now pulls in the library it needs** so it no longer fails to start on a clean install.
- Each package adds a `talktype` command and an Applications menu entry and brings its own copies of the helper tools — nothing to install by hand first.

### Less than half the size it was
- **The download dropped from 306 MB to 135 MB.** TalkType was shipping PyTorch, an enormous library it never actually used — transcription runs on faster-whisper, and GPU acceleration uses its own CUDA libraries. Removing it cut ~170 MB with no change to how anything works, on CPU or GPU.

### A first run that just works, then gets out of your way
- **TalkType now starts itself when you log in.** After setup it's simply there in your system tray, ready — no launching it by hand. You can turn this off in Preferences → General, and the final setup screen tells you so.
- **The restart reminder waits until the end.** Some permissions only take effect after a restart, but you're now reminded once at the very end of setup — with a **"Restart Now"** button — instead of being nudged to reboot in the middle, before setup is finished.
- **On GNOME, the panel icon now appears on its own** after you install the extension and restart. Previously the extension was installed but never actually switched on, so there was no icon and no clue why.
- **If setup can't finish cleanly, it tells you** and doesn't leave you stuck part-way through.

### Fixed
- **TalkType would not start at all on Fedora.** The tray was built against an old system library Fedora doesn't ship, so the app quit the moment it launched. It now uses the current, maintained library every supported distribution provides.
- **Hotkeys did nothing on Fedora, with no error to explain why.** First-run setup checked only whether TalkType could *type*. On Fedora that permission is granted automatically while permission to *read your keyboard* is not, so setup was skipped and no key could ever be detected — while the app looked healthy. Setup now checks both, and says so plainly if it can't read the keyboard instead of failing silently.
- **Setup told you to log out when that often isn't enough.** A background session can keep old permissions alive, so hotkeys would still do nothing. It now tells you to restart, everywhere it asks.
- **Setup could run all over again after a restart.** Rebooting from the last setup screen could leave onboarding un-finished, so the next launch started the whole wizard over. It now records that setup is done before restarting.
- **Scrolling the mouse wheel over the model dropdown changed your model** — and could land on a GPU-only model and pop an error you never asked for. The dropdown now ignores the wheel, and the model you pick is always the one you get.
- **About and "Check for Updates" windows ignored your dark theme**, showing up light while the rest of the app was dark. They now match.
- **The setup window was taller than some screens**, leaving its buttons unreachable. It now fits the screen and scrolls when it has to.
- **Preferences could not be scrolled with the mouse wheel** over dropdowns and sliders.
- **The splash icon was missing** on installed (non-AppImage) versions.
- **"Check for Updates" flashed its result and vanished** before it could be read. The result window now stays until dismissed.
- **Some installed files had the wrong permissions**, so TalkType could fail to start for anyone but the user who installed it.

## [0.6.2] - 2026-08-14

### The recording indicator can now look four different ways
- **Alongside the original glowing orb, there are three new styles that react to your voice as you speak**: a Waveform, Frequency bars, and a Radial burst. Choose one under Preferences → Audio.
- **One colour control governs every style.** Match your desktop's accent colour, or pick your own from a colour picker that opens the moment you choose "Custom colour". The classic cyan is the first preset swatch, and a "Reset to classic cyan" link puts the original colour back in one click.
- **A soft dark backing** (Off / Soft / Medium / Strong) keeps the waveform, bars and radial styles readable over any wallpaper. The orb has its own background and ignores this — the setting greys out while the orb is selected, so that's clear at a glance.
- **A sensitivity slider** tunes how strongly the indicator reacts to your voice.
- All of these apply instantly, with no need to restart dictation.

### Your dictation stays private in the log
- **TalkType no longer writes what you dictate to its log file.** Previously every transcription was saved to the log in plain text, quietly building up a record on disk of everything you had said. The log now records only that a transcription happened and how long it was — never the words themselves.
- If you are troubleshooting a dictation problem, full logging can be turned back on under Preferences → Advanced → Privacy. It asks you to confirm in a warning first, so switching it on is always a deliberate, informed choice.
- A **"Clear log now"** button wipes the existing log whenever you want.
- The Text Injection help text no longer claims the app can avoid typing into password fields — no Linux app can reliably detect them on Wayland, so the honest guidance is simply to avoid dictating into them.

### Settings apply without restarting the service
- **Changing settings in Preferences no longer restarts dictation.** Almost any change used to trigger a ten-second model reload; now only changing the model or device does. Everything else — the indicator, punctuation, timeouts and the rest — takes effect on your very next dictation.

### Fixed
- **The recording indicator ignored its position setting.** The dictation service was being started from two different places that did not agree on settings, so where the indicator appeared depended on which one launched it. It now launches from a single place and honours the position you chose.

## [0.6.1] - 2026-08-13

### Preferences styling
- **The Preferences window's stylesheet had never actually applied.** It was attached in a way that could not reach the widgets inside the window, so around 70 style rules covering buttons, tabs, text fields, switches, sliders and scrollbars did nothing at all — the window fell back to the plain system theme. Those styles now render.
- **Accent colours follow your desktop.** They were fixed to a blue that clashed with any system not using a blue accent. Highlights — the selected tab, section headings, focused text fields, switches and checkboxes — now use whatever accent colour your desktop is set to.

## [0.6.0] - 2026-08-13

The largest release so far: three months of reliability work across dictation,
settings, and text handling. Several features that were advertised but quietly
did nothing now actually work.

**GNOME users should update the extension too.** Its version number was stuck at
5 through five rewrites, so the app told everyone they were up to date and never
offered the update. This release fixes that, and the newer extension is required
for the Claude Desktop paste fix below to reach you.

### Every dropdown in the app was unusable on Wayland
- **Dropdowns closed the instant you released the mouse button** — so you could not pick a model on the first-run setup screen, or change the model, device, language or hotkeys in Preferences. Only click-and-drag selected anything, which is not how anyone expects a dropdown to work. TalkType forced itself onto XWayland for the whole app, and under XWayland a GTK dropdown never latches open on a plain click. XWayland is now used only by the part that needs it (the recording indicator, which cannot position itself without it), so the windows you actually click run natively on Wayland.
- **Dropdown lists opened on top of the row above them** instead of below the button, which read as a rendering glitch. They now drop down as an ordinary list.

### Recording indicator position, and other desktops
- **The recording indicator's position could not be changed on Wayland.** The position dropdown and both offset boxes were greyed out with a note saying positioning "requires the GNOME extension". That was never true — positioning has nothing to do with the extension, and it works on any desktop that has XWayland, including KDE Plasma. The controls are now enabled whenever positioning genuinely works, and the warning only appears when it genuinely cannot.
- **"Restart Info" stayed clickable on desktops that are not GNOME**, where it explained how to press Alt+F2 and restart GNOME Shell — advice for software that isn't running. It is now greyed out alongside Install and Uninstall.
- **TalkType no longer refuses to dictate on systems without XWayland.** The dictation service asks for XWayland so the indicator can position itself, but now falls back to native Wayland instead of failing to start, giving a centred indicator rather than no dictation at all.

### Model and preset choices
- **The first-run setup screen offered fewer models than Preferences.** "Base" was missing from setup entirely, so new users picked from four models and later found five, with nothing indicating one had been hidden. Both screens now build from one list, and the models are ordered by size in both.
- **"Battery Saver" could never show as the selected preset in the GNOME menu.** It and "Fastest" are both tiny/CPU, and the extension compared only the model and device, so the first match always won. The setting applied correctly; only the dot was wrong. The extension now distinguishes them the same way the tray does.

### Onboarding
- **Added an "Open Preferences" button to the final setup screen**, so the settings are one click away instead of only being described in text.

### Dictation reliability
- **Hotkey silently stopped working after a USB blip, wireless-receiver glitch, or resume from suspend** — keyboards were detected once at startup and never again, so a device that dropped and came back was gone for the life of the process. TalkType now rescans every 3 seconds while idle. It never rescans mid-recording, which would let the hotkey leak into the app you're typing into.
- **System-wide keyboard and mouse lockups during recording** — TalkType takes an exclusive grab on input devices while recording. Several error paths lost the handle needed to release them, leaving the keyboard dead everywhere until the app was killed. Every exit path now releases, including when the microphone is busy, unplugged, or was changed over USB.
- **A keyboard unplugged mid-sentence left recording stuck on**, which also disabled the auto-timeout and the stranded-grab safety net.
- **The hotkey test in Preferences detected nothing** and pegged a CPU core while open.
- **The hotkey test could permanently disable GNOME's Alt+F8 / Alt+F7** window resize and move shortcuts — as a saved setting that survived reboots, with nothing pointing back at TalkType as the cause.
- **The hotkey dropdown showed F8 while the saved hotkey was actually blank**, so clicking OK saved a blank hotkey. The one screen you'd use to fix dead dictation couldn't fix it.

### Your settings stay put
A whole class of "TalkType reset itself and dictation stopped working" faults:
- **A microphone with a quote mark in its name wiped every setting**, hotkey included. A blank hotkey means dictation is silently dead.
- **An unreadable config file (wrong permissions) was mistaken for a damaged one and overwritten** — turning a working setup into a fresh install with nothing to recover from. An unreadable file is no longer treated as a damaged one.
- **Repairing a damaged config destroyed the backup it had just recovered from.**
- **A single transient read error could cache defaults and write them over a perfectly good settings file** five seconds after launch.
- **Custom commands were deleted** on any Apply in Preferences if the commands file was damaged.
- **TalkType's three processes could truncate each other's settings file** when writing at the same time.
- **Tray changes made while Preferences was open** are no longer discarded on Apply/OK.

### Text corrections
- `report.pdf` no longer becomes "report. Pdf" — filenames are protected.
- "meet at 9 a.m. tomorrow" no longer becomes "9 AM Tomorrow".
- "8 a.m. Tuesday" is no longer split into two sentences before a proper noun.
- "use it, i.e. the new one" no longer becomes "I.e.".
- "2024 was a good year" no longer becomes "2024 Was a good year" — same for prices, and email addresses are no longer capitalized.
- "here is the plan:" no longer collects a stray full stop.
- Silence no longer produces a lone ".".
- **"Ensure period at end of sentences" now works when unchecked** — it previously did nothing at all.
- Any dictation ending in "subscribe" no longer loses the word.
- Decimals, prices and abbreviations ("3.5", "$19.99", "U.S.") stay intact.
- After "undo that", the next words keep their capitals — "NASA" no longer becomes "nASA".
- **"Undo that" could delete an extra sentence** — often the whole dictation — when the previous sentence ended inside a quote or bracket. Those backspaces land in your live document, so this one mattered.

### Voice commands
- **A backslash in a custom command's replacement crashed every dictation**, even when that command's trigger phrase wasn't spoken.
- **One custom command could rewrite another's output.** Replacements are now final.
- **"delete everything" / "clear all"** wipes the whole input field.
- **"delete last 3 words"** — counted undo, using digits or number words, for words, sentences and paragraphs.
- "em dash" works again; "return" and "tab" no longer false-trigger mid-sentence.

### Text injection
- **Injection reported success even when it failed.** The two worst outcomes of that: the wrong text landing in your document, and the undo buffer recording text that never arrived — so a later "undo that" backspaced over writing you'd typed yourself.
- **On an X11 login, paste could insert whatever you'd copied earlier** — a URL, a password, a whole document — while reporting success. It now falls back to typing.
- **A failure partway through a long dictation** no longer leaves a partial copy followed by a complete second copy.
- **Claude Desktop paste works again.** An Electron update started rejecting synthetic Ctrl+V; affected apps are now routed to a fast type path. Within it, "tab" no longer submits the chat mid-dictation.
- Pasting no longer waits on two unbounded 25-second timeouts between releasing the hotkey and the text appearing.

### Features that didn't actually work
- **Changing the model from the tray or GNOME menu did nothing.** The change was written to a file the app has never read, and was gone by the restart it told you was required.
- **Model downloads failed in full if any single file failed** — including `README.md`, which is never loaded. A flaky fetch of a text file discarded a finished multi-gigabyte download.
- **"Battery Saver" could never show as the active preset** — the dot always jumped back to "Fastest".
- **"Launch at login" wrote its autostart file the moment you ticked the box**, so Cancel left it behind and the checkbox disagreed with reality from then on. It now applies on save.
- **Closing the download window left downloads running** with no window, no progress, and no way to stop them.
- **A failed CUDA download deleted the CUDA you already had** — including failures that happened before anything was downloaded.
- The tray no longer freezes for a second on Restart Service, or when switching presets.

### Security and integrity
- **The update check installed an AppImage whose checksum was missing** from a release that did publish checksums.
- **The GNOME extension installed an unverifiable zip** the same way — and that extension is JavaScript running in your shell. A missing checksum file (true of every release through v0.5.16) is now distinguished from a failed lookup.

### Under the hood
- The release build now fails loudly instead of shipping an AppImage whose PyTorch crashes on every machine without an NVIDIA card.
- Test suite grew from 223 to 361 tests.
- Removed two dead, non-working build scripts; the release toolchain is now tracked in the repository.

## [0.5.16] - 2026-05-09

### Bug Fixes
- **Words vanishing from longer dictations** — Disabled Whisper's VAD pre-filter that was trimming speech onsets after natural sentence-ending pauses. Phrases like "Eight hours later, we were standing in a kitchen with collapsed ceilings" no longer disappear after pauses. See [faster-whisper#925](https://github.com/SYSTRAN/faster-whisper/issues/925).
- **"period of time" mangled into "period. Of time"** — Command words like *period*, *comma*, *return*, *dash*, *quote* no longer get corrupted when used as ordinary English nouns. Phrases like "period of time", "in return", "tax return", "dash of salt", "great quote", and "comma operator" now transcribe correctly.
- **Standalone "i" not capitalized mid-sentence** — Whisper transcribes the pronoun "I" as lowercase when it appears mid-sentence; TalkType now automatically capitalizes it (also catches "i'll", "i'm", "i've", "i'd").
- Fixed *literal return* restoring as 'newline' instead of 'return'.
- Fixed time normalization to handle hours without minutes (e.g., "11 PM").

### New Features
- **Voice Commands Dialog** — Press Ctrl+Alt+V (configurable) to see a quick reference of all voice commands. Supports combo hotkeys.
- **Quoted Replacement Support for Custom Commands** — Custom commands can now use quoted strings for literal replacement (bypasses normalization).
- Enabled GitHub Discussions on the project repository.

### Improvements
- Increased Whisper `beam_size` from 1 to 5 (faster-whisper's default) for noticeably better decoding accuracy on the trade of ~0.5s extra inference time.
- D-Bus service refactor (internal).
- Added 18 new test cases for normalization patterns.

## [0.5.15] - 2026-03-22

### New Features
- **Performance Presets** — Choose from Battery Saver, Light, Balanced, Quality, or Most Accurate via the tray menu or GNOME extension
- **Unified CUDA + Model Download** — When selecting a preset that needs both CUDA libraries and a new model, a single download window handles both with clear progress bars and explanatory text
- **Smart Model Selection** — Large-v3 model is no longer grayed out; clicking it explains what's needed (CUDA download for NVIDIA users, or "NVIDIA required" for AMD/Intel) and offers to set it up

### Improvements
- **Onboarding** — Streamlined Setup Complete page with constrained model picker width, shorter labels, and dynamic button text ("Download and Get Started!" vs "Get Started!" based on cache state)
- **Hotkey Test** — Redesigned to be phantom-proof: keys show yellow "Holding..." on press and green "✓ Working!" on release, eliminating false positives from synthetic key events
- **CUDA Crash Loop Prevention** — Performance presets now verify CUDA availability before saving device=cuda, preventing repeated crashes when CUDA libraries aren't installed
- **CPU Fallback** — If CUDA fails at runtime, TalkType automatically falls back to CPU and persists the change to config so it doesn't crash again on restart
- **Preferences Consistency** — Model and preset selection in Preferences now behaves identically to the tray menu (click-to-explain instead of grayed-out)

### Bug Fixes
- Fixed large-v3 model selection showing a blocking confirmation dialog instead of offering CUDA download
- Fixed CUDA download from tray icon using a thread-blocking function that froze the UI
- Fixed double confirmation dialog when downloading CUDA from the tray menu
- Fixed GTK auto-repeat flooding the hotkey test with hundreds of key events when holding a key
- Fixed phantom F8 key events from evdev service termination appearing as false "Working!" results

## [0.5.14] - 2026-03-21

### Improvements
- Bumped version for internal testing

## [0.5.13] - 2026-02-18

### New Features
- **Always-Active Dual Hotkeys** — F8 (hold-to-talk) and F9 (tap-to-toggle) are now both active simultaneously
- Added "Restart Service" menu item to tray and GNOME extension

### Bug Fixes
- Fixed welcome dialog hotkey test false-positive from GNOME's Alt+F8 window-resize keybinding
- Fixed crash after model download (Python 3.10 f-string compatibility)
- Fixed "Setup Complete" screen text alignment

### Performance
- Config file cached — only re-read when changed on disk
- Regex patterns in auto-punctuation engine precompiled at startup

## [0.5.12] - 2026-02-17

### Bug Fixes
- Fixed audio device compatibility for non-standard sample rates

## [0.5.11] - 2026-02-13

### Bug Fixes
- Improved dictation accuracy and hallucination filtering
- Fixed longer paragraphs losing middle sentences during dictation
