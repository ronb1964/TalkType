# TuxTalk Roadmap

Things I'd like to add or fix, roughly grouped. Nothing here has a date on it. What's already shipped is in the [CHANGELOG](CHANGELOG.md), so this list only holds what's still open.

`[ ]` not started, `[~]` partly done (the note says what's left).

## Dictation

- [ ] Importable packs of snippets, like a "Linux developer" pack that turns "why do tool" into ydotool and "dee bus" into D-Bus, so people don't have to build their list from scratch. Could grow into a library people send in by pull request.
- [ ] Per-app profiles, picked by the window you're typing into (cleanup on or off, paste mode, maybe a different model). Window class only. TuxTalk won't read the screen or take screenshots.
- [ ] Live text while you talk, using a streaming model. I'm not sold on it yet, so it's parked.
- [ ] Language quick switch in the tray menu. The setting exists, but only in Preferences.
- [ ] Ignore background noise that gets transcribed as a word or two (a confidence threshold).
- [ ] Some kind of signal when a dictation heard nothing at all. Hands-free mode already beeps and stops when you say nothing, but a normal hold-to-talk just types nothing.
- [ ] Spoken templates, like "compose email" putting in an email layout.

## Audio

- [ ] A choice of beep sounds, a volume control for them, or your own sound files.
- [ ] Warn when the room is too noisy to dictate well.
- [ ] Pick the best microphone automatically, and switch microphones from the tray.
- [~] Live audio level in the GNOME panel. The recording indicator and the Preferences mic test have one, the panel icon doesn't.

## Look and feel

- [ ] A custom symbolic icon for the tray and panel.
- [ ] Native Wayland positioning for the recording indicator (gtk-layer-shell). Today it uses XWayland to place itself.
- [~] Voice Commands reference (Ctrl+Alt+V) with a way to try a command and see what it types. The reference is done, the try-it part isn't.

## Safety and context

- [ ] Don't dictate into password fields. TuxTalk types into whatever has focus, password boxes included. The code to recognise a password field exists (`atspi_helper.py`) but nothing uses it yet.
- [ ] An option to need a modifier with the dictation key (Ctrl+F8, say) so it can't be set off by accident.
- [ ] A tray item to pause dictation for a while without stopping the service.
- [ ] Only listen on certain workspaces.

## GNOME extension

- [ ] Native toggle in GNOME's Quick Settings.
- [ ] Search from the Activities overview.
- [ ] Publish the extension on extensions.gnome.org. Right now TuxTalk installs it on first run.
- [~] Put the recording indicator where you're typing. With TuxTalk Labs' "indicator follows the window" it shows up near the bottom of that window. Following the text cursor itself would need help from each app, and most don't offer it.

## First run

- [ ] A typing test at the end of setup that checks text really lands in another window. There's a hotkey test, not a typing one.

## Packaging

- [~] Flatpak. The manifests are in `packaging/flatpak/` and were updated for the rename, but they haven't been built since, and nothing is published. The Flathub submission was closed, so it would be a `.flatpak` file on the Releases page or a self-hosted Flatpak repo.
- [ ] Snap.
- [ ] macOS or Windows. Big jobs, since the hotkeys, typing and tray are all Linux-specific today.

## Known limitations

These are accepted for now rather than bugs waiting on a fix.

- After "undo that", carrying on the sentence lowercases its first letter. That's right for ordinary words and wrong for names ("Ron" turns into "ron"). Whisper capitalises names and sentence starts the same way, so I can't tell the two apart. "I" and acronyms like NASA are handled.
