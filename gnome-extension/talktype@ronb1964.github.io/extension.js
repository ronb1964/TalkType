/* extension.js
 *
 * TalkType GNOME Shell Extension
 * Provides native GNOME integration for TalkType speech recognition
 */

import GLib from 'gi://GLib';
import GObject from 'gi://GObject';
import St from 'gi://St';
import Gio from 'gi://Gio';
import Clutter from 'gi://Clutter';
import Pango from 'gi://Pango';
import Meta from 'gi://Meta';
import Shell from 'gi://Shell';
import * as Main from 'resource:///org/gnome/shell/ui/main.js';
import * as PanelMenu from 'resource:///org/gnome/shell/ui/panelMenu.js';
import * as PopupMenu from 'resource:///org/gnome/shell/ui/popupMenu.js';
import {Extension} from 'resource:///org/gnome/shell/extensions/extension.js';

// D-Bus interface for TalkType
const TalkTypeIface = `
<node>
  <interface name="io.github.ronb1964.TalkType">
    <!-- Properties/Status -->
    <method name="IsRecording">
      <arg type="b" direction="out" name="recording"/>
    </method>
    <method name="IsServiceRunning">
      <arg type="b" direction="out" name="running"/>
    </method>
    <method name="GetCurrentModel">
      <arg type="s" direction="out" name="model"/>
    </method>
    <method name="GetDeviceType">
      <arg type="s" direction="out" name="device"/>
    </method>
    <method name="GetInjectionMode">
      <arg type="s" direction="out" name="mode"/>
    </method>
    <method name="GetStatus">
      <arg type="a{sv}" direction="out" name="status"/>
    </method>
    <method name="GetPresets">
      <arg type="a(sss)" direction="out" name="presets"/>
    </method>

    <!-- Actions -->
    <method name="StartRecording"/>
    <method name="StopRecording"/>
    <method name="ToggleRecording"/>
    <method name="StartService"/>
    <method name="StopService"/>
    <method name="RestartService"/>
    <method name="SetModel">
      <arg type="s" direction="in" name="model"/>
    </method>
    <method name="SetInjectionMode">
      <arg type="s" direction="in" name="mode"/>
    </method>
    <method name="SetFocusedWindowClass">
      <arg type="s" direction="in" name="wm_class"/>
    </method>
    <method name="ApplyPerformancePreset">
      <arg type="s" direction="in" name="preset"/>
    </method>
    <method name="GetRecentDictations">
      <arg type="as" direction="out" name="entries"/>
    </method>
    <method name="ClearRecentDictations"/>
    <method name="FixWordInDictation"/>
    <method name="OpenPreferences"/>
    <method name="OpenPreferencesUpdates"/>
    <method name="OpenPreferencesStats"/>
    <method name="ShowHelp"/>
    <method name="ShowVoiceCommands"/>
    <method name="ShowAbout"/>
    <method name="CheckForUpdates"/>
    <method name="Quit"/>

    <!-- Signals -->
    <signal name="RecordingStateChanged">
      <arg type="b" name="is_recording"/>
    </signal>
    <signal name="ServiceStateChanged">
      <arg type="b" name="is_running"/>
    </signal>
    <signal name="HotkeysChanged">
      <arg type="as" name="accelerators"/>
    </signal>
    <signal name="TranscriptionComplete">
      <arg type="s" name="text"/>
    </signal>
    <signal name="ModelChanged">
      <arg type="s" name="model_name"/>
    </signal>
    <signal name="InjectionModeChanged">
      <arg type="s" name="mode"/>
    </signal>
    <signal name="ErrorOccurred">
      <arg type="s" name="error_type"/>
      <arg type="s" name="message"/>
    </signal>
    <signal name="UpdateCheckComplete">
      <arg type="b" name="success"/>
      <arg type="s" name="current_version"/>
      <arg type="s" name="latest_version"/>
      <arg type="b" name="update_available"/>
      <arg type="i" name="extension_current"/>
      <arg type="i" name="extension_latest"/>
      <arg type="b" name="extension_update"/>
      <arg type="s" name="release_url"/>
      <arg type="s" name="error"/>
    </signal>
  </interface>
</node>`;

const TalkTypeProxy = Gio.DBusProxy.makeProxyWrapper(TalkTypeIface);

// Panel indicator for TalkType
const TalkTypeIndicator = GObject.registerClass(
class TalkTypeIndicator extends PanelMenu.Button {
    _init() {
        super._init(0.0, 'TalkType');

        // Create icon
        this._icon = new St.Icon({
            icon_name: 'audio-input-microphone-symbolic',
            style_class: 'system-status-icon',
        });
        this.add_child(this._icon);

        // State
        this._isRecording = false;
        this._isServiceRunning = false;
        this._currentModel = 'unknown';
        this._currentDevice = 'unknown';
        // Id of the active preset, worked out by the tray (recommend.match_preset).
        this._currentPreset = 'custom';
        this._currentInjectionMode = 'auto';
        this._dbusAvailable = false;

        // TalkType reads its hotkeys below the desktop, so GNOME Shell also
        // hands F8 to the focused app and a terminal prints "~". While the
        // service runs we grab the hotkeys here, which keeps them from the
        // app; TalkType still sees them. The list comes from the service via
        // the tray (HotkeysChanged / GetStatus) in accelerator syntax.
        // accelerator -> action id from grab_accelerator.
        this._hotkeys = [];
        this._grabs = new Map();

        // Connect to D-Bus
        this._connectDBus();

        // Build menu
        this._buildMenu();

        // Monitor D-Bus service availability (this will show/hide based on service presence)
        this._watchDBusService();

        // Start hidden - will be shown when D-Bus service is detected
        if (!this._dbusAvailable) {
            this.hide();
        } else {
            this._updateStatus();
        }
    }

    _connectDBus() {
        try {
            this._proxy = new TalkTypeProxy(
                Gio.DBus.session,
                'io.github.ronb1964.TalkType',
                '/io/github/ronb1964/TalkType'
            );

            // Connect to signals. Store every subscription id so destroy()
            // can disconnect them — otherwise the callbacks keep firing on
            // the disposed panel button after the extension is disabled
            // (e.g. on screen lock), throwing "already disposed" errors.
            this._signalIds = [];
            this._signalIds.push(this._proxy.connectSignal('RecordingStateChanged', (proxy, sender, [isRecording]) => {
                this._isRecording = isRecording;
                this._updateIcon();
            }));

            this._signalIds.push(this._proxy.connectSignal('ServiceStateChanged', (proxy, sender, [isRunning]) => {
                this._isServiceRunning = isRunning;
                this._updateIcon();
                this._updateMenu();  // Update menu when service state changes
                this._syncHotkeyGrabs();
            }));

            this._signalIds.push(this._proxy.connectSignal('HotkeysChanged', (proxy, sender, [accelerators]) => {
                this._hotkeys = accelerators;
                this._syncHotkeyGrabs();
            }));

            this._signalIds.push(this._proxy.connectSignal('ModelChanged', (proxy, sender, [modelName]) => {
                // Re-query rather than patching the model alone: a preset also
                // changes the device, and the preset dot is matched on both.
                // Updating just the model left "Device:" reading the old value
                // and the dot sitting on the wrong preset.
                this._currentModel = modelName;
                this._updateStatus();
            }));

            this._signalIds.push(this._proxy.connectSignal('InjectionModeChanged', (proxy, sender, [mode]) => {
                this._currentInjectionMode = mode;
                this._updateInjectionSelection(mode);
            }));

            this._signalIds.push(this._proxy.connectSignal('UpdateCheckComplete', (proxy, sender, params) => {
                this._handleUpdateCheckResult(params);
            }));

            this._dbusAvailable = true;
            console.log('TalkType: Connected to D-Bus service');

            // Track focused window class so TalkType can pick the right
            // paste keystroke (Ctrl+V for normal apps, Ctrl+Shift+V for terminals).
            this._setupFocusTracking();
        } catch (e) {
            this._dbusAvailable = false;
            console.error('TalkType: Failed to connect to D-Bus:', e);
        }
    }

    _setupFocusTracking() {
        if (!global.display) return;
        this._focusSignalId = global.display.connect(
            'notify::focus-window',
            () => this._pushFocusedWindowClass()
        );
        this._pushFocusedWindowClass();
    }

    _pushFocusedWindowClass() {
        if (!this._proxy || !this._dbusAvailable) {
            return;
        }
        try {
            const win = global.display && global.display.focus_window;
            const wmClass = (win && win.get_wm_class()) || '';
            this._proxy.SetFocusedWindowClassRemote(wmClass, () => {});
        } catch (e) {
            console.error('TalkType: focus push failed:', e);
        }
    }

    _watchDBusService() {
        // Watch for D-Bus name owner changes (detects when TalkType quits)
        this._nameWatcherId = Gio.DBus.session.watch_name(
            'io.github.ronb1964.TalkType',
            Gio.BusNameWatcherFlags.NONE,
            () => {
                // Service appeared - show the indicator
                this._dbusAvailable = true;
                this.show();
                this._updateStatus();
                // Re-push current focus so a freshly restarted Python service
                // doesn't sit at class=None until the user changes windows.
                this._pushFocusedWindowClass();
                console.log('TalkType: D-Bus service appeared - showing indicator');
            },
            () => {
                // Service vanished (TalkType quit) - hide the indicator
                this._dbusAvailable = false;
                this._isServiceRunning = false;
                this._isRecording = false;
                this._syncHotkeyGrabs();  // TalkType quit: give the keys back
                this.hide();
                console.log('TalkType: D-Bus service vanished (app quit) - hiding indicator');
            }
        );
    }

    _buildMenu() {
        // Service start/stop
        this._serviceItem = new PopupMenu.PopupSwitchMenuItem('Dictation Service', false);
        this._updatingToggle = false;  // Flag to prevent recursive updates
        this._serviceItem.connect('toggled', (item) => {
            // Only respond to user clicks, not programmatic changes
            if (this._updatingToggle)
                return;

            if (item.state) {
                this._proxy.StartServiceRemote();
            } else {
                this._proxy.StopServiceRemote();
            }
        });
        this.menu.addMenuItem(this._serviceItem);

        // Restart service
        let restartItem = new PopupMenu.PopupMenuItem('Restart Service');
        restartItem.connect('activate', () => {
            this._proxy.RestartServiceRemote();
        });
        this.menu.addMenuItem(restartItem);

        // Recent dictations. Refilled each time the panel menu opens, since
        // the list changes after every dictation. Mirrors the tray submenu.
        this._historySubMenu = new PopupMenu.PopupSubMenuMenuItem('Recent Dictations');
        this.menu.addMenuItem(this._historySubMenu);
        this.menu.connect('open-state-changed', (_menu, open) => {
            if (open) {
                this._refreshHistoryMenu();
                this._refreshPresets();
            }
        });

        // Fix a Word, top level right under Recent Dictations as in the tray.
        // The window has its own dictation picker and opens on the newest.
        const fixWordItem = new PopupMenu.PopupMenuItem('Fix a Word...');
        fixWordItem.connect('activate', () => this._proxy.FixWordInDictationRemote());
        this.menu.addMenuItem(fixWordItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Active model display (read-only)
        this._modelDisplayItem = new PopupMenu.PopupMenuItem('Active Model: Loading...', {reactive: false});
        this._modelDisplayItem.label.style = 'font-weight: bold;';
        this.menu.addMenuItem(this._modelDisplayItem);

        // Device mode display (read-only)
        this._deviceDisplayItem = new PopupMenu.PopupMenuItem('Device: Loading...', {reactive: false});
        this._deviceDisplayItem.label.style = 'font-weight: bold;';
        this.menu.addMenuItem(this._deviceDisplayItem);

        // (No separator here — Model/Device/Performance/Injection are one
        // contiguous block, matching the GTK tray and CLAUDE.md menu order.)

        // Performance submenu
        this._performanceSubMenu = new PopupMenu.PopupSubMenuMenuItem('Performance');
        // Filled from the tray's GetPresets each time the menu opens.
        this._presetItems = {};
        this.menu.addMenuItem(this._performanceSubMenu);

        // Text Injection Mode submenu
        this._injectionSubMenu = new PopupMenu.PopupSubMenuMenuItem('Text Injection Mode');
        this._injectionItems = {};
        // Order and labels must match the GTK tray exactly (see CLAUDE.md):
        // anyone following instructions like "the second item under Text
        // Injection Mode" has to land on the same option in both menus.
        const injectionModes = {
            'auto': {label: 'Auto', description: 'Smart Detection'},
            'type': {label: 'Keyboard Typing', description: 'Simulate keystrokes'},
            'paste': {label: 'Clipboard Paste', description: 'Copy and paste'}
        };
        for (let [key, mode] of Object.entries(injectionModes)) {
            let item = new PopupMenu.PopupMenuItem(`${mode.label} (${mode.description})`);
            item._modeKey = key;
            item.connect('activate', () => {
                this._proxy.SetInjectionModeRemote(key);
                this._updateInjectionSelection(key);
            });
            this._injectionItems[key] = item;
            this._injectionSubMenu.menu.addMenuItem(item);
        }
        this.menu.addMenuItem(this._injectionSubMenu);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Preferences
        let prefsItem = new PopupMenu.PopupMenuItem('Preferences...');
        prefsItem.connect('activate', () => {
            this._proxy.OpenPreferencesRemote();
        });
        this.menu.addMenuItem(prefsItem);

        // Voice Commands quick reference
        let voiceCmdsItem = new PopupMenu.PopupMenuItem('Voice Commands...');
        voiceCmdsItem.connect('activate', () => {
            this._proxy.ShowVoiceCommandsRemote();
        });
        this.menu.addMenuItem(voiceCmdsItem);

        // Usage stats: opens Preferences on its Stats tab
        let statsItem = new PopupMenu.PopupMenuItem('Your Stats...');
        statsItem.connect('activate', () => {
            this._proxy.OpenPreferencesStatsRemote();
        });
        this.menu.addMenuItem(statsItem);

        // Help
        let helpItem = new PopupMenu.PopupMenuItem('Help...');
        helpItem.connect('activate', () => {
            this._proxy.ShowHelpRemote();
        });
        this.menu.addMenuItem(helpItem);

        // About
        let aboutItem = new PopupMenu.PopupMenuItem('About TalkType...');
        aboutItem.connect('activate', () => {
            this._proxy.ShowAboutRemote();
        });
        this.menu.addMenuItem(aboutItem);

        // Check for Updates
        this._updatesItem = new PopupMenu.PopupMenuItem('Check for Updates...');
        this._updatesItem.connect('activate', () => {
            this._checkForUpdates();
        });
        this.menu.addMenuItem(this._updatesItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Quit TalkType
        let quitItem = new PopupMenu.PopupMenuItem('Quit TalkType');
        quitItem.connect('activate', () => {
            this._proxy.QuitRemote();
        });
        this.menu.addMenuItem(quitItem);
    }

    _checkForUpdates() {
        // Show checking notification
        Main.notify('TalkType', 'Checking for updates...');
        this._updatesItem.label.text = 'Checking...';
        this._updatesItem.setSensitive(false);

        // Call D-Bus method - results come via signal
        this._proxy.CheckForUpdatesRemote();

        // Re-enable menu item after timeout (in case signal fails).
        // The id is kept so a result arriving first can cancel it, and so
        // destroy() can remove it — an uncancelled source fires against a
        // destroyed menu item after the extension is disabled or the screen
        // locks, which logs errors and is a standard ego.gnome.org rejection.
        this._clearUpdateTimeout();
        this._updateTimeoutId = GLib.timeout_add_seconds(GLib.PRIORITY_DEFAULT, 30, () => {
            this._updateTimeoutId = null;
            this._restoreUpdatesItem();
            return GLib.SOURCE_REMOVE;
        });
    }

    _clearUpdateTimeout() {
        if (this._updateTimeoutId) {
            GLib.Source.remove(this._updateTimeoutId);
            this._updateTimeoutId = null;
        }
    }

    _restoreUpdatesItem() {
        if (!this._updatesItem) {
            return;
        }
        this._updatesItem.label.text = 'Check for Updates...';
        this._updatesItem.setSensitive(true);
    }

    _handleUpdateCheckResult(params) {
        // Result arrived — cancel the fallback timer before it can fire.
        this._clearUpdateTimeout();
        this._restoreUpdatesItem();

        const [success, currentVersion, latestVersion, updateAvailable,
               extCurrent, extLatest, extUpdate, releaseUrl, error] = params;

        if (!success) {
            Main.notify('TalkType', `Update check failed: ${error || 'Unknown error'}`);
            return;
        }

        // The app itself pops the result window for us via the D-Bus
        // CheckForUpdates handler: either "You're up to date" or the actionable
        // update dialog (Download & Install / View on GitHub). Opening
        // Preferences on top of that — the old behaviour — was a redundant,
        // clunky extra step, so we no longer do it for an app update.
        if (updateAvailable) {
            // App dialog handles it; nothing to add here.
        } else if (extUpdate) {
            // App is up to date but the GNOME extension has an update — the app
            // dialog can't offer that, so send the user to the Updates tab.
            Main.notify('TalkType', 'Extension update available — opening Updates…');
            this._proxy.OpenPreferencesUpdatesRemote();
        }
        // else: nothing — the app already showed the "up to date" window.
    }

    _updatePresetSelection(activePreset) {
        // Update checkmarks on preset menu items
        for (let [key, item] of Object.entries(this._presetItems)) {
            // Use ornament to show selection (like radio buttons)
            item.setOrnament(key === activePreset ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NONE);
        }
    }

    _updateInjectionSelection(activeMode) {
        // Update checkmarks on injection mode menu items
        for (let [key, item] of Object.entries(this._injectionItems)) {
            item.setOrnament(key === activeMode ? PopupMenu.Ornament.DOT : PopupMenu.Ornament.NONE);
        }
    }

    _refreshHistoryMenu() {
        const menu = this._historySubMenu.menu;
        menu.removeAll();
        this._proxy.GetRecentDictationsRemote((result, error) => {
            // On error `result` is null, so it cannot be destructured.
            const entries = result ? result[0] : null;
            if (error || !entries || entries.length === 0) {
                menu.addMenuItem(new PopupMenu.PopupMenuItem(
                    error ? 'TalkType Not Running' : 'No dictations yet', {reactive: false}));
                return;
            }
            menu.addMenuItem(new PopupMenu.PopupMenuItem(
                'Click one to copy it, then press Ctrl+V', {reactive: false}));
            for (const text of entries) {
                // GNOME cannot nest a submenu inside this one (it unfolds in
                // place), so instead of the tray's hover view each entry shows
                // up to ~100 characters wrapped onto two lines.
                const flat = text.split(/\s+/).join(' ');
                const label = flat.length <= 100 ? flat : `${flat.slice(0, 99).trimEnd()}\u2026`;
                const item = new PopupMenu.PopupMenuItem(label);
                item.label.style = 'max-width: 24em;';
                item.label.clutter_text.line_wrap = true;
                item.label.clutter_text.ellipsize = Pango.EllipsizeMode.NONE;
                item.connect('activate', () => {
                    St.Clipboard.get_default().set_text(St.ClipboardType.CLIPBOARD, text);
                });
                menu.addMenuItem(item);
            }
            menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());
            const clearItem = new PopupMenu.PopupMenuItem('Clear History');
            clearItem.connect('activate', () => this._proxy.ClearRecentDictationsRemote());
            menu.addMenuItem(clearItem);
        });
    }
    _updateStatus() {
        if (!this._proxy)
            return;

        // Get current status
        this._proxy.GetStatusRemote((result, error) => {
            if (error) {
                console.error('TalkType: Failed to get status:', error);
                return;
            }

            let [status] = result;
            this._isRecording = status.recording ? status.recording.deep_unpack() : false;
            this._isServiceRunning = status.service_running ? status.service_running.deep_unpack() : false;
            this._currentModel = status.model ? status.model.deep_unpack() : 'unknown';
            this._currentDevice = status.device ? status.device.deep_unpack() : 'unknown';

            // The tray works out which preset is active (recommend.match_preset).
            this._currentPreset = status.preset ? status.preset.deep_unpack() : 'custom';
            this._currentInjectionMode = status.injection_mode ? status.injection_mode.deep_unpack() : 'auto';
            // Absent from a TalkType older than 0.14.1: then nothing is grabbed,
            // which is how it always behaved.
            this._hotkeys = status.hotkeys ? status.hotkeys.deep_unpack() : [];

            this._updateIcon();
            this._updateMenu();
            this._syncHotkeyGrabs();
        });
    }

    _syncHotkeyGrabs() {
        // Grab exactly the service's hotkeys while it runs, and none otherwise:
        // with dictation off, F8 must be an ordinary key again.
        const wanted = (this._dbusAvailable && this._isServiceRunning) ? this._hotkeys : [];
        for (const [accel, action] of this._grabs) {
            if (!wanted.includes(accel)) {
                this._ungrabHotkey(action);
                this._grabs.delete(accel);
            }
        }
        for (const accel of wanted) {
            if (this._grabs.has(accel))
                continue;
            // The same two calls GNOME Shell's own GrabAccelerator makes.
            const action = global.display.grab_accelerator(accel, Meta.KeyBindingFlags.NONE);
            if (action === Meta.KeyBindingAction.NONE) {
                // Usually another shortcut already has it. Dictation still
                // works; the key just reaches the app too, as before.
                console.warn(`TalkType: could not hold ${accel} back from apps (already in use?)`);
                continue;
            }
            // ALL: also while the overview or a system modal is up, or the key
            // would leak there.
            Main.wm.allowKeybinding(Meta.external_binding_name_for_action(action), Shell.ActionMode.ALL);
            this._grabs.set(accel, action);
        }
    }

    _ungrabHotkey(action) {
        Main.wm.allowKeybinding(Meta.external_binding_name_for_action(action), Shell.ActionMode.NONE);
        global.display.ungrab_accelerator(action);
    }

    _refreshPresets() {
        // The tray owns the presets (recommend.py): build the submenu from them
        // each time the menu opens, so the two menus can't drift. Don't mark a
        // choice on click: the tray can refuse it (a cancelled download), and
        // the dot follows what actually took effect (status.preset).
        const menu = this._performanceSubMenu.menu;
        this._proxy.GetPresetsRemote((result, error) => {
            menu.removeAll();
            this._presetItems = {};
            const presets = result ? result[0] : null;
            if (error || !presets || presets.length === 0) {
                menu.addMenuItem(new PopupMenu.PopupMenuItem(
                    'Update TalkType to use presets', {reactive: false}));
                return;
            }
            for (const [id, label, description] of presets) {
                const item = new PopupMenu.PopupMenuItem(`${label} (${description})`);
                item.connect('activate', () => this._proxy.ApplyPerformancePresetRemote(id));
                this._presetItems[id] = item;
                menu.addMenuItem(item);
            }
            this._updatePresetSelection(this._currentPreset);
        });
    }

    _updateIcon() {
        // Update icon based on state
        if (!this._dbusAvailable) {
            // TalkType not running: very dimmed with slash
            this._icon.icon_name = 'microphone-sensitivity-muted-symbolic';
            this._icon.style_class = 'system-status-icon';
            this._icon.style = 'opacity: 0.3;';
        } else if (this._isRecording) {
            // Recording: bright red icon
            this._icon.icon_name = 'audio-input-microphone-symbolic';
            this._icon.style_class = 'system-status-icon';
            this._icon.style = 'color: #ff4444;';
        } else if (this._isServiceRunning) {
            // Service running but not recording: normal brightness
            this._icon.icon_name = 'audio-input-microphone-symbolic';
            this._icon.style_class = 'system-status-icon';
            this._icon.style = '';
        } else {
            // Service stopped: dimmed with slash (microphone-disabled or microphone-sensitivity-muted)
            this._icon.icon_name = 'microphone-sensitivity-muted-symbolic';
            this._icon.style_class = 'system-status-icon';
            this._icon.style = 'opacity: 0.5;';
        }
    }

    _updateMenu() {
        // Update service switch - prevent firing 'toggled' event
        this._updatingToggle = true;
        this._serviceItem.setToggleState(this._isServiceRunning);
        this._updatingToggle = false;

        // Disable menu items if D-Bus is unavailable
        this._serviceItem.setSensitive(this._dbusAvailable);
        this._performanceSubMenu.setSensitive(this._dbusAvailable);
        this._injectionSubMenu.setSensitive(this._dbusAvailable);

        // Update active model display
        if (!this._dbusAvailable) {
            this._modelDisplayItem.label.text = 'TalkType Not Running';
            this._deviceDisplayItem.label.text = 'Device: Unknown';
        } else {
            const modelNames = {
                'tiny': 'Tiny (fastest)',
                'base': 'Base',
                'small': 'Small',
                'medium': 'Medium',
                'large-v3': 'Large (best quality)',
                'large': 'Large (best quality)',
                'parakeet-v3': 'Parakeet'
            };
            const displayName = modelNames[this._currentModel] || this._currentModel;
            this._modelDisplayItem.label.text = `Active Model: ${displayName}`;

            // Update device display
            const deviceNames = {
                'cpu': 'CPU',
                'cuda': 'GPU (CUDA)',
                'vulkan': 'GPU (Vulkan)'
            };
            const deviceDisplay = deviceNames[this._currentDevice] || this._currentDevice.toUpperCase();
            this._deviceDisplayItem.label.text = `Device: ${deviceDisplay}`;

            // Update preset selection
            this._updatePresetSelection(this._currentPreset);

            // Update injection mode selection
            this._updateInjectionSelection(this._currentInjectionMode || 'auto');
        }
    }

    destroy() {
        // Cancel the update-check fallback timer so it can't fire against a
        // destroyed menu item after the extension is disabled.
        this._clearUpdateTimeout();

        // Never leave a key grabbed behind a disabled extension (screen lock
        // disables it too); it would swallow F8 with nothing listening.
        for (const action of this._grabs.values())
            this._ungrabHotkey(action);
        this._grabs.clear();

        // Clean up D-Bus name watcher
        if (this._nameWatcherId) {
            Gio.DBus.session.unwatch_name(this._nameWatcherId);
            this._nameWatcherId = null;
        }

        // Disconnect focus-window listener
        if (this._focusSignalId && global.display) {
            global.display.disconnect(this._focusSignalId);
            this._focusSignalId = null;
        }

        if (this._proxy) {
            // Disconnect every D-Bus signal subscription before dropping the
            // proxy, so no callback fires on the destroyed button afterward.
            if (this._signalIds) {
                for (const id of this._signalIds) {
                    try {
                        this._proxy.disconnectSignal(id);
                    } catch (e) {
                        // proxy may already be tearing down — ignore
                    }
                }
                this._signalIds = null;
            }
            this._proxy = null;
        }
        super.destroy();
    }
});

export default class TalkTypeExtension extends Extension {
    enable() {
        console.log('TalkType Extension: Enabling...');

        this._indicator = new TalkTypeIndicator();
        Main.panel.addToStatusArea('talktype', this._indicator);

        console.log('TalkType Extension: Enabled');
    }

    disable() {
        console.log('TalkType Extension: Disabling...');

        if (this._indicator) {
            this._indicator.destroy();
            this._indicator = null;
        }

        console.log('TalkType Extension: Disabled');
    }
}
