# Changelog

All notable changes to TalkType are documented here.

## [Unreleased]

- TalkType's small message boxes, like "You're Up to Date!", had square
  corners on KDE while every other TalkType window had KDE's rounded frame.
  They get the desktop's own frame now, with rounded corners and a title bar,
  on KDE, GNOME and X11 desktops alike.
- The hotkey test on the welcome screen never saw your keyboards directly.
  It called a function the keyboard library doesn't have, which skipped every
  device. The test still worked through the window itself, so nobody noticed,
  but now it reads the keys the same way dictation does.
- The Stats graph said "most: 1 words". It says "1 word" now.

## [0.14.4] - 2026-10-10

Mostly things that came out of testing 0.14.3, plus a few older bugs that a
second review turned up.

- When a dictation can't be typed into the window, TalkType now tells you why
  and what fixes it. Usually it's the typing setup: after Fix Typing you have
  to restart the computer before typing works, and nothing said so. A Fedora
  user dictated for minutes with every word transcribed and none typed, and
  figured his laptop was too weak. If the typing helper has stopped, TalkType
  starts it again.
- The welcome screen said you could skip the typing setup and use Clipboard
  Paste instead. That was wrong, paste needs the same setup. It now says your
  dictations are still kept in Recent Dictations.
- Whisper models were loaded twice every time the dictation service started,
  once just to check the model was downloaded. Large-v3 starts a couple of
  seconds faster now and doesn't need the extra memory.
- Correcting yourself works better when you pause before "no wait". The
  speech model puts a period there and the AI read it as two sentences, so
  "Meet me at three. No wait, four o'clock." mostly came out unchanged. In
  testing it went from 4 out of 10 fixed to 8 out of 10. It's also stricter
  now, so it won't drop the "no wait" and keep the wrong time.
- "look at github.com" and the like turned into an email address. Fixed.
- A failed download of the AI model could be reported as finished.
- The Stats page fits without the Reset button half hidden under the edge,
  and so does Updates.
- Performance > Custom opens Preferences now, in the tray and in the GNOME
  menu. The GNOME menu didn't have Custom at all, so a custom setup showed no
  dot there. That needs extension version 16, and Check for Updates offers it.
- Long dropdown lists like the language list open as three columns, so they
  fit on the screen with your current choice showing.
- On the welcome screen, "Other options" was easy to miss. It's now a button
  that says what it's for: Change language, model or graphics card. The
  "Set it up" button isn't cut off at the bottom anymore either.
- In the AppImage, every emoji was blank on newer distros like Fedora,
  including the flags in the language list. It brought along an old copy of
  the library that draws the text, and that one can't draw today's color emoji
  font. It uses your system's copy now.
- Cancelling a model download in Preferences left the dropdown showing the
  model you cancelled, though the old one was still the one in use. It goes
  back now.
- After a model download, OK left Preferences open, so you had to click OK
  twice. OK closes now; Apply is the one that keeps the window open.

## [0.14.3] - 2026-10-10

Small one, mostly fixes. The main one came from Stefano on GNOME.

- On GNOME under Wayland, the dropdowns in Preferences couldn't be changed if
  the window was on a second monitor. The list was opening off screen where you
  couldn't see it. That's a GTK bug that never got fixed, so on Wayland the
  dropdowns open a different way now that the desktop itself places, and it
  works on any monitor. Thanks to Stefano Scipioni for tracking it down (#9).
- While fixing that I found GTK's normal dropdown is no good on KDE either. The
  first time you click one it opens squashed, with scroll arrows and the items
  cut in half, until you move the mouse. The new way doesn't do that. The list
  just drops down under the button.
- Ordinary sentences could get turned into email addresses. "Look at this. My
  car broke." came out as "Look@this.My car broke." because "my", "no", "it"
  and "in" are also the endings of some countries' web addresses. Spoken
  addresses like "john at gmail.com" still work.
- On KDE, TalkType's windows showed a generic "W" icon in the title bar and
  taskbar instead of TalkType's own. Every window was calling itself "python3",
  so KDE couldn't match it to the launcher.
- Opening Preferences straight to a tab, like Your Stats from the menu, showed
  the right page but left General highlighted on KDE.
- After a service restart on KDE, the log could say F8, F9 and Ctrl+Alt+V were
  already taken by KDE when they weren't. It checks again for about a second
  now before warning.
- Picking the Performance preset you're already on doesn't rerun the speed
  check and restart the service anymore. The GNOME menu sends a click even for
  the one with the dot next to it.
- First run on a graphics card shows one download window instead of two.
- New screenshots in the README and the software store listing. The old store
  ones were a year out of date.

## [0.14.2] - 2026-10-06

This one's mostly about setup. TalkType has a lot of settings now and it was
way too easy to end up on a slow combination without knowing it. I did it
myself, I ran Parakeet on the processor for weeks with a graphics card sitting
there doing nothing.

- First run picks a setup for you now. It looks at your graphics card and
  your language and shows one card that says what you'll get, something like
  "Parakeet on your NVIDIA GeForce RTX 4070 SUPER", and how big the download
  is. Click Set it up and that's exactly what gets downloaded. Other options
  lets you change the language, the model, or whether it uses the graphics
  card, and anything that won't work on your computer is greyed out with the
  reason. The separate model picker that came after the hotkey test is gone.
- AMD and Intel graphics get used at first run too now, through Vulkan.
  TalkType still checks the graphics card is really faster than your processor
  before it switches, and stays on the processor if it isn't. The big CUDA
  download isn't offered at first run anymore. It's still in Preferences.
- Parakeet is the default model for new installs.
- The Performance menu went from seven presets down to three: Recommended for
  this computer, Lightest and Battery saver. The old ones were named after
  models and half the time did something other than what the label said.
  Going back from Battery saver puts the auto-stop back to 5 minutes. The
  GNOME menu gets its presets from TalkType itself now, so it needs extension
  version 15, and Check for Updates will offer it.
- If you're already set up and there's a better setup for your computer, you
  get one notification about it after updating. Just the once, and nothing
  changes unless you pick it.
- The tray and GNOME menus show what's really running instead of just what the
  settings say. That turned up a few things that were quietly wrong. Large-v3
  on Vulkan was actually running as medium. AMD and Intel users were told
  large-v3 wouldn't run for them when it does. And Preferences warns you now
  when Parakeet can't do what your settings ask for.
- If a dictation doesn't make it into the window, TalkType tells you instead
  of failing silently. It's saved in Recent Dictations so you can paste it.
- The Voice Commands window and Help were behind. They never mentioned "no
  wait" or "scratch that" for correcting yourself, and Help still talked about
  a red indicator and menu items that don't exist anymore. Both are caught up,
  and they say the commands are English words whatever language you dictate in.
- The download sizes for the Whisper models were about half of what they
  really are. Small said 244 MB and downloads 486 MB. They're the real numbers
  now, everywhere they show up.

## [0.14.1] - 2026-10-04

Mostly keyboard fixes, and a lot of them came from guelz testing on a Swiss
keyboard.

- Typing mode works on keyboard layouts other than US English now. It used to
  send US key positions, so on a German or Swiss keyboard Y and Z came out
  swapped and umlauts couldn't be typed at all. TalkType reads the layout you
  have on and presses the keys that layout actually uses, accented letters
  included. If the layout has no way to type something, like Latin words on a
  Ukrainian keyboard, that dictation gets pasted instead. (#8)
- On X11, TalkType read the first layout in your list instead of the one you'd
  switched to, so Ukrainian came out as a row of 9s. It reads the active one
  now, and on X11 it can paste the text a layout can't type, which it couldn't
  do before.
- Pressing F8 also reached whatever app you were in, so a terminal showed a
  stray "~". On KDE and GNOME your hotkeys stay with TalkType while dictation is
  on, and go back to being normal keys when you turn it off. GNOME needs the
  updated extension (version 14), and Check for Updates will offer it.
- Dictations are marked so clipboard managers like Klipper leave them out of
  their history. There's also a new option to put back whatever you'd copied
  before the dictation. It's in Preferences, Advanced, under Text Injection,
  and it's off by default because I like being able to paste a dictation again
  when it lands in the wrong window. (#7)

## [0.14.0] - 2026-10-03

Parakeet can use your graphics card now, and dictating into a terminal works
on a lot more desktops.

- With the device set to Vulkan (any GPU), Parakeet runs on the graphics
  card. On my RTX 4070 Super a minute of talking takes about 0.2 seconds
  instead of 2, and it's just as accurate. Choosing Vulkan in Preferences
  downloads a copy of Parakeet made for the graphics engine (669 MB) and
  checks that your graphics card is really faster than your processor
  before it switches. The processor copy stays, so if the graphics card ever
  has trouble, TalkType goes back to it.
- Terminals need Ctrl+Shift+V to paste, so TalkType has to know when you're
  in one. That only worked on GNOME and KDE. Now it also works on Sway, i3,
  Hyprland and niri, and on X11 desktops like XFCE, MATE and Cinnamon.
  Hyprland is the one I couldn't try on a real machine, so if you're on
  Hyprland I'd like to hear whether dictating into a terminal works for you.
- Ghostty, GNOME Console, xfce4-terminal, Guake and more than a dozen other
  terminals were missing from TalkType's list and got the wrong paste. That's
  fixed on every desktop.
- On Vulkan, clicking OK in Preferences never closed the window. That's been
  there since 0.12.0 and it's fixed. The Device dropdown also closes now
  before the speed check pops up, instead of staying drawn on top of it.
- On the first-run screen, the Full and Light choices for an NVIDIA card
  stayed greyed out until you ticked the box above them, so it looked like
  Light couldn't be picked. Picking either one ticks the box for you now.
- A quick tap of the key with nothing said doesn't get typed out anymore.
  Parakeet would sometimes hear "Thank you." in that fraction of a second of
  background noise.
- Help has a link to the TalkType Discussions page, for questions or just
  telling me how it's going.

## [0.13.1] - 2026-10-03

The Performance presets know about Vulkan now.

- Picking Most Accurate from the tray menu used to need NVIDIA's CUDA
  libraries, and without them it either offered the 4.4 GB download or said
  it couldn't be done. Now an NVIDIA card gets the same Light (Vulkan) or Full
  (CUDA) choice as setup, and AMD or Intel graphics get offered Vulkan.
- If you're already set up with Vulkan, picking Balanced, Quality or Most
  Accurate keeps you on Vulkan. Before, it quietly moved you back to the
  processor because it didn't find CUDA.

## [0.13.0] - 2026-10-03

A much lighter way to use an NVIDIA graphics card.

- Until now, using an NVIDIA card meant downloading NVIDIA's CUDA libraries,
  about 1.4 GB. The Vulkan engine from 0.12.0 works on NVIDIA cards too, and
  on my RTX 4070 Super it was just as fast as CUDA: half a second for 11
  seconds of speech with the Large model, either way. It's a 24 MB download.
- When TalkType first sets up and finds an NVIDIA card, you now get to pick:
  Full (CUDA, 1.4 GB) like before, or Light (Vulkan, 24 MB). Full is still the
  default for now, since it's been in use a lot longer.
- In Preferences the device is now called Vulkan (any GPU), and it shows up
  on NVIDIA, AMD and Intel. If you have a graphics card plus graphics built
  into the processor, it uses the card.
- Picking the Large model without CUDA now offers Light (Vulkan) or Full
  (CUDA), instead of only the 4.4 GB CUDA download. The Light route is about
  1 GB all in, because the Large model is smaller in Vulkan's format too.
- If you're on AMD or Intel graphics, picking the Large model now offers to
  set up Vulkan, instead of saying it can't be done.

## [0.12.0] - 2026-10-03

TalkType keeps score now, if you want it to, and Whisper can use AMD and
Intel graphics.

### AMD and Intel graphics
- Until now only NVIDIA graphics cards could speed up the Whisper models. If
  your computer has AMD or Intel graphics, there's a new choice under Device
  in Preferences: AMD / Intel graphics.
- Picking it downloads a small graphics engine (24 MB) and the model in the
  format that engine uses, then times your graphics chip against your
  processor. TalkType only switches if the graphics chip is clearly faster,
  and tells you the numbers either way. The graphics built into some desktop
  processors is too small to help, and in that case it says so and keeps
  using the processor.
- Laptops with recent AMD or Intel graphics, and separate AMD or Intel
  graphics cards, are where this helps most.
- Parakeet isn't affected. It already runs fast on the processor.

### Your Stats
- Pick Your Stats from the tray menu (or Preferences, Stats tab) to see how
  many words you've dictated today, in the last 7 days and all time, how many
  dictations that was, how long you spent dictating, and about how much time
  it saved you over typing.
- There's a chart of the last two weeks, and it tells you how much faster you
  dictate than you type. Most people talk a lot faster than they type.
- Type in your own typing speed if you know it. Time saved goes by that
  instead of the usual 40 words a minute, so a fast typist doesn't get told
  they saved more time than they did.
- It only keeps the numbers, on your computer. It never saves what you said.
- You can turn it off or reset it from the same tab.

## [0.11.2] - 2026-10-02

A couple of fixes I found while testing Fix a Word on GNOME.

- If you set TalkType up before 0.10.1, launch at login might still be
  pointing at the AppImage you first downloaded, usually the one sitting in
  your Downloads folder. That means it started an old version at login, or
  nothing at all if you'd cleaned out Downloads, and on Ubuntu 26.04 that old
  version doesn't start at all. TalkType now notices this when it starts and
  points launch at login at the installed copy in ~/AppImages instead. If
  you turned launch at login off, it leaves it off.
- GNOME users: if TalkType's tray restarted while dictation kept running, the
  panel menu could stop working properly, Fix a Word included, and the panel
  icon could stop showing when you're recording. Fixed.
- The message you get when there's nothing to fix yet now points you to the
  right place in the menu.

## [0.11.1] - 2026-09-29

A small one, nothing changes in how TalkType works.

- The AppImage now has update information built in, so if you use
  AppImageUpdate or a manager like Gear Lever or AppImageLauncher, it can
  update TalkType for you and only downloads the parts that changed.
  TalkType's own Check for Updates works the same as before.

## [0.11.0] - 2026-09-29

You can teach TalkType words it keeps getting wrong now.

### Fix a Word
- If TalkType keeps writing "bamboo studio" when you mean BambuStudio, open
  Fix a Word from the tray menu. Pick the dictation, click the wrong word (or
  drag across a few), type the right spelling and click Always fix this. From
  then on it gets it right in every dictation.
- It works with every speech model, Parakeet included, because it fixes the
  words after they're heard.
- Your fixes show up in Preferences under Commands, where you can edit or
  remove them. There's a Fix a Word button there too.
- It warns you before you "fix" an everyday word like "four", since that
  would change it every single time you say it.
- If you want to paste the corrected sentence over the one that came out
  wrong, it can copy that for you too.

### Also
- If Preferences was already open behind another window, picking it from the
  tray again did nothing, and it looked like it wasn't opening at all. It
  comes to the front now. Same for Voice Commands and Fix a Word.
- Saving in Preferences could wipe out a voice command that was added while
  Preferences was open. Fixed.
- The text in Preferences was small in a few places and hard to read. It's
  normal size now.
- The smart quotes option in Preferences was missing the quotes it's supposed
  to show as an example.
- Preferences no longer shows GNOME extension settings on desktops that
  aren't GNOME.

## [0.10.3] - 2026-09-26

One more fix for systems that were missing a library.

### Fixes
- If your system didn't have PortAudio installed, the library TalkType uses to
  hear your microphone, TalkType popped up a window asking you to install it.
  A copy of PortAudio comes inside the AppImage now, along with the JACK
  library it needs, so it just works. If your system does have PortAudio,
  TalkType keeps using that one like it always has.

## [0.10.2] - 2026-09-26

The AppImage should now start on more systems.

### Fixes
- On Ubuntu 26.04 the AppImage wouldn't start at all unless you ran it with a
  special flag, and the menu entry and launch at login just silently did
  nothing. It was built with an old tool that needs a library called libfuse2,
  and 26.04 doesn't ship it anymore. It's built with the current tool now,
  which doesn't need libfuse2. I tested it on a clean 26.04 and it starts
  normally. It's also a bit smaller, 124 MB instead of 139.
- If your system didn't have the tray icon library (libayatana-appindicator3)
  installed, TalkType crashed as soon as it started. That library comes inside
  the AppImage now, and in the .deb and .rpm too.

## [0.10.1] - 2026-09-26

Mostly a fix for a stuck key I ran into while testing in a VM.

### Fixes
- Holding the dictation key could leave your desktop thinking that key was
  still held down, and it got worse by one every time you dictated. Most apps
  never notice. But a virtual machine window, a remote desktop session or a
  game does notice, and it starts repeating the key by itself. With F8 that
  meant a VM terminal filling up with tildes. TalkType now tells the desktop
  the key came back up before it takes over the keyboard, so it never gets
  out of step. If you already have a stuck key from an older version, logging
  out and back in clears it.
- Launch at login was pointing at whatever AppImage you ran setup from, which
  is usually the one sitting in Downloads. Clean out Downloads and TalkType
  quietly stopped starting at login. It points at the installed copy in
  ~/AppImages now.
- If you use Parakeet, the Device line in the menu says CPU now. Parakeet
  always runs on the CPU, so it was wrong for it to say cuda.
- The AI cleanup engine could get left running in the background after
  TalkType closed, sometimes for hours, holding on to about a gigabyte of
  memory. It gets shut down properly now, and anything left over from before
  gets cleaned up the next time TalkType starts.
- The welcome screen and the model tooltip in Preferences mention Parakeet
  now, not just Whisper.

## [0.10.0] - 2026-09-26

A hands-free option for the toggle key.

### Hands-free
- **Double-tap F9 (or whatever your toggle key is), talk, and just stop
  talking.** After a couple of seconds of quiet the recording ends and your
  text gets typed. No second key press needed. A short high beep lets you
  know the double-tap took.
- **A single tap works exactly like before.** It keeps recording until you
  tap again, however long you pause to think. So if you dictate long stuff,
  nothing changes for you unless you double-tap.
- It waits until you've actually started talking, a cough or a click doesn't
  count, and it learns how noisy your room is as it goes.
- It never cuts anything off the start or middle of what you said. The only
  audio it drops is the quiet bit at the end after you stopped.
- Off until you turn it on in Preferences under General, right below the
  toggle key. You can set the quiet time anywhere from half a second to ten
  seconds. Hold-to-talk isn't affected at all.

### Also
- On the Flatpak, if a toggle recording ended some other way (like pressing
  Esc), the next press of the toggle shortcut could do nothing. Fixed.

## [0.9.0] - 2026-09-26

New Dictation Cleanup options, and a handful of fixes for things that could go
wrong when a speech model wasn't downloaded yet.

### Dictation Cleanup
Both of these are off until you turn them on, in Preferences under Advanced.

- **Remove "um", "uh" and repeated words.** "Um, so the the van is ready"
  comes out as "So the van is ready". It's instant and there's nothing to
  download. It leaves alone the doubles people actually mean, like "that
  that" or "no, no, no".
- **Fix self-corrections with AI.** Say "order two boxes of screws, no wait,
  three boxes" and you get "Order three boxes of screws." A small AI model
  runs on your own computer to do it. It's a one-time 1.1 GB download when
  you turn it on, and it uses your graphics card if you have one (NVIDIA, AMD
  or Intel) or your processor if you don't.
- The AI only ever sees sentences where you corrected yourself, and TalkType
  doesn't just trust what it sends back. If the answer changes anything
  besides the correction, like rewording something or answering a question
  you dictated, it gets thrown out and your words go in exactly as you said
  them.

### Fixes
- **Cancel now means cancel.** If TalkType starts up and your speech model
  isn't downloaded, it asks first. On computers with an NVIDIA card, clicking
  Cancel was ignored and it downloaded anyway.
- **No more crash after that download.** When the model had to be downloaded
  at startup, the dictation service crashed right after the download
  finished.
- **Cancelling no longer leaves you without dictation.** TalkType switches to
  a model you already have, tells you which one, and keeps going. It only
  stops if you have no model downloaded at all.
- **Picking a preset or a text injection mode from the tray restarted
  dictation twice**, and briefly switched back to what you had before. It's
  once now.

## [0.8.0] - 2026-09-26

TalkType can now use NVIDIA's Parakeet model instead of Whisper. If you don't
have an NVIDIA graphics card this is the one to try. It's about as accurate as
Whisper large-v3, which was never usable without a GPU, and it runs on a plain
processor in well under a second.

### Parakeet
- New model choice in Preferences and on the first-run setup screen, and a new
  "Fast & Accurate" preset under Performance in the tray and the GNOME menu.
- It's a 670 MB download, same progress bar as the Whisper models. Nothing
  downloads unless you pick it.
- It handles English and 24 European languages and figures out which one you're
  speaking. It doesn't do Chinese, Japanese, Korean, Arabic and so on, so stick
  with a Whisper model for those.
- It always runs on the processor, even if you have an NVIDIA card, because it's
  already fast there.
- Spoken punctuation, custom commands and undo all work the same as with Whisper.

### Recent Dictations
- New "Recent Dictations" submenu right under Restart Service. It holds your last
  20 dictations. Hover over one to read the whole thing and click it to copy it,
  then paste wherever you want. Handy when a dictation lands in the wrong window
  or nowhere at all.
- The list is kept in memory only. It never touches the disk and it's gone when
  you log out. There's a Clear History item at the bottom if you want it gone
  sooner.
- In the GNOME panel menu each entry shows the first couple of lines and one
  click copies it.

### Also
- The last setup screen now has a link to the Discussions page. I'd like to hear
  how TalkType is working for people, good or bad.
- The GNOME extension is now version 10.

## [0.7.4] - 2026-09-05

Dictation into a terminal now works on KDE. It previously did nothing at all —
no text, no error, and TalkType played its usual "finished" beep as though it had
worked.

### Dictating into a terminal
- **Text now actually appears.** Terminals need Ctrl+Shift+V; plain Ctrl+V means
  something else entirely at a shell prompt, so nothing was inserted. TalkType
  knew this and had always sent the right keys — but only on GNOME, because the
  GNOME extension was the only thing that ever told it which window you were
  typing into. On KDE it never knew, so it always guessed "not a terminal".
  TalkType now asks KWin directly, so KDE gets the same treatment GNOME always
  had.
- **"new line" and "new paragraph" work in a terminal too.** Terminals have no
  "soft" Enter — Enter runs the command — so the keystroke TalkType sends for a
  line break was simply ignored and everything ran together on one line. In a
  terminal the line break is now part of the pasted text instead, which terminals
  insert normally. Everywhere else is unchanged: in a chat box a real line break
  would send your message, so those still get the keystroke.
- **Dictating into Claude Desktop is more reliable on KDE**, for the same reason —
  TalkType can now recognise it and use the input method that works with it.

### Note for terminal users
The line break relies on your shell's "bracketed paste" setting, which is on by
default in current versions of bash and zsh. If you have deliberately turned it
off, a dictated line break will run the command at that point instead of breaking
the line. Only affects dictation containing "new line" aimed at a terminal.

### Also
- Terminal recognition no longer depends on exact capitalisation, so terminals
  are identified consistently however your desktop reports them.

## [0.7.3] - 2026-09-05

This release is about settings that said they had been applied when they hadn't.
Several things you change in Preferences were never reaching the running
dictation service, and TalkType told you they had.

### Settings you change now actually take effect
- **Changing your hotkey works immediately again.** Picking a new record key (or
  switching between hold and toggle) saved correctly but the running service
  kept listening on the old key, with no hint anything was wrong. It now takes
  effect right away, and the old key stops working — as it always should have.
- **Custom voice commands take effect on your next dictation.** Adding or editing
  a command used to need a service restart; the Commands tab said so, while the
  Apply dialog claimed the opposite. No restart is needed now, and the tab says
  what is true.
- **Switching microphone actually switches microphone.** Choosing a different mic
  applied to the settings file but not to the running service, so dictation kept
  recording from the old device until the next restart.
- **Turning the auto-timeout on or off is respected immediately.** Unticking it
  used to leave the service still shutting itself down after the old interval.

### Custom commands are easier to get right
- **A command with a number in it now works either way it is heard.** Speech
  recognition decides on its own whether you said "one" or "1", and it is not
  consistent — so a command typed as "test phrase one" would quietly fail
  whenever it came through as "test phrase 1". Both spellings now match.

### Fixed
- **Cancelling a model download no longer leaves the wrong model saved.** If you
  picked a new model and cancelled or lost the download, Preferences kept the new
  name while the service went on using the old one — and trying again reported
  "your changes are already in effect" without switching.
- **Quitting no longer risks closing other TalkType windows.** The quit action
  matched too broadly and could take down the tray and Preferences along with the
  dictation service.
- **Dictating into Claude Desktop works again.** The app changed its identifier,
  so the workaround that makes text appear reliably in it had stopped running.
  (GNOME only — see below.)
- **Text typing can no longer hang forever** on setups that use `wtype`, and a
  package update that gets stuck waiting on your package manager now reports back
  instead of leaving the window frozen.
- **The update check no longer reverts settings.** Its once-a-day check could
  quietly undo anything you changed in Preferences while it was running.

### GNOME
- **Ready for GNOME 51.** The panel extension now declares support for GNOME 51,
  which ships on 16 September. Without this the extension would be disabled and,
  because stock GNOME has nowhere to show the fallback icon, you would have been
  left with no TalkType icon at all.

### Known limitation
- Terminal paste and the Claude Desktop fix rely on knowing which window has
  focus, which only the GNOME extension currently reports. On KDE and other
  desktops they stay inactive; support for those desktops is in progress.

## [0.7.2] - 2026-08-19

A small polish release for the AppImage, `.deb`, and `.rpm` builds. (A sandboxed
Flatpak edition is on its way to **Flathub** — see the README.)

### Fixed
- **The recording-indicator color picker now shows a visible checkmark** on the
  white and other light-colored swatches, so you can tell which color is selected.
- **Scrolling a Preferences or setup window no longer stalls** when the pointer is
  over a dropdown — the page scrolls as expected and the dropdown value is left
  alone (instead of you having to move the mouse off the dropdown first).

### Changed
- **Clearer update wording on `.deb`/`.rpm` installs:** the Updates tab now says
  plainly that TalkType downloads *and* installs updates for you (with your
  password), rather than implying you have to update through your distro yourself.

## [0.7.1] - 2026-08-16

This release fixes how TalkType updates itself, so that updating works correctly
no matter how you installed it — and makes the whole update experience
consistent across every desktop.

### Updating now matches how you installed
- **`.deb` / `.rpm` installs update through your package manager, in one click.**
  Before, "Check for Updates" on a Fedora or Debian install tried to download and
  run an AppImage — which failed with a confusing `libfuse.so.2` error and left
  you stuck. Now TalkType knows it was installed as a package: it downloads the
  new package, asks for your password once, and installs it properly with your
  system's own tools, so dependencies stay correct.
- **Arch (AUR) installs are pointed to the AUR helper** (`yay -S talktype-appimage`)
  instead of trying to update the wrong way.
- **AppImage installs keep updating in place**, exactly as before.
- TalkType picks the right method automatically based on how you installed — you
  don't have to think about it.

### One clear, consistent update window
- **"Check for Updates" goes straight to a single window** with your choices —
  Download & Install, or View on GitHub — instead of *also* opening the
  Preferences window on top of it.
- **The GNOME panel menu and the system-tray menu now behave identically.** Both
  open the same window; neither detours through Preferences.
- **The automatic daily check shows that same window** when an update is found,
  instead of a notification that was easy to miss.

### Fixed
- **TalkType now reliably restarts after an update.** The old restart could leave
  the app half-started and unresponsive — menus and windows would stop opening.
  It now shuts down cleanly and launches a fresh copy.
- **About, Help and Voice Commands windows now always open.** On some Wayland
  setups they could silently fail to appear.
- **The update window no longer hides the About / Help / Voice Commands windows**
  behind it.

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
