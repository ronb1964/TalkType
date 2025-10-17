/* extension.js
 *
 * TalkType GNOME Shell Extension
 * Provides native GNOME integration for TalkType speech recognition
 */

import GObject from 'gi://GObject';
import St from 'gi://St';
import Gio from 'gi://Gio';
import Clutter from 'gi://Clutter';
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
    <method name="GetStatus">
      <arg type="a{sv}" direction="out" name="status"/>
    </method>

    <!-- Actions -->
    <method name="StartRecording"/>
    <method name="StopRecording"/>
    <method name="ToggleRecording"/>
    <method name="StartService"/>
    <method name="StopService"/>
    <method name="SetModel">
      <arg type="s" direction="in" name="model"/>
    </method>
    <method name="OpenPreferences"/>
    <method name="ShowHelp"/>
    <method name="Quit"/>

    <!-- Signals -->
    <signal name="RecordingStateChanged">
      <arg type="b" name="is_recording"/>
    </signal>
    <signal name="ServiceStateChanged">
      <arg type="b" name="is_running"/>
    </signal>
    <signal name="TranscriptionComplete">
      <arg type="s" name="text"/>
    </signal>
    <signal name="ModelChanged">
      <arg type="s" name="model_name"/>
    </signal>
    <signal name="ErrorOccurred">
      <arg type="s" name="error_type"/>
      <arg type="s" name="message"/>
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
        this._dbusAvailable = false;

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

            // Connect to signals
            this._proxy.connectSignal('RecordingStateChanged', (proxy, sender, [isRecording]) => {
                this._isRecording = isRecording;
                this._updateIcon();
            });

            this._proxy.connectSignal('ServiceStateChanged', (proxy, sender, [isRunning]) => {
                this._isServiceRunning = isRunning;
                this._updateIcon();
                this._updateMenu();  // Update menu when service state changes
            });

            this._proxy.connectSignal('ModelChanged', (proxy, sender, [modelName]) => {
                this._currentModel = modelName;
                this._updateMenu();
            });

            this._dbusAvailable = true;
            console.log('TalkType: Connected to D-Bus service');
        } catch (e) {
            this._dbusAvailable = false;
            console.error('TalkType: Failed to connect to D-Bus:', e);
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
                console.log('TalkType: D-Bus service appeared - showing indicator');
            },
            () => {
                // Service vanished (TalkType quit) - hide the indicator
                this._dbusAvailable = false;
                this._isServiceRunning = false;
                this._isRecording = false;
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

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Active model display (read-only)
        this._modelDisplayItem = new PopupMenu.PopupMenuItem('Active Model: Loading...', {reactive: false});
        this._modelDisplayItem.label.style = 'font-weight: bold;';
        this.menu.addMenuItem(this._modelDisplayItem);

        // Device mode display (read-only)
        this._deviceDisplayItem = new PopupMenu.PopupMenuItem('Device: Loading...', {reactive: false});
        this._deviceDisplayItem.label.style = 'font-weight: bold;';
        this.menu.addMenuItem(this._deviceDisplayItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Preferences
        let prefsItem = new PopupMenu.PopupMenuItem('Preferences...');
        prefsItem.connect('activate', () => {
            this._proxy.OpenPreferencesRemote();
        });
        this.menu.addMenuItem(prefsItem);

        // Help
        let helpItem = new PopupMenu.PopupMenuItem('Help...');
        helpItem.connect('activate', () => {
            this._proxy.ShowHelpRemote();
        });
        this.menu.addMenuItem(helpItem);

        this.menu.addMenuItem(new PopupMenu.PopupSeparatorMenuItem());

        // Quit TalkType
        let quitItem = new PopupMenu.PopupMenuItem('Quit TalkType');
        quitItem.connect('activate', () => {
            this._proxy.QuitRemote();
        });
        this.menu.addMenuItem(quitItem);
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

            this._updateIcon();
            this._updateMenu();
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
                'large': 'Large (best quality)'
            };
            const displayName = modelNames[this._currentModel] || this._currentModel;
            this._modelDisplayItem.label.text = `Active Model: ${displayName}`;

            // Update device display
            const deviceNames = {
                'cpu': 'CPU',
                'cuda': 'GPU (CUDA)'
            };
            const deviceDisplay = deviceNames[this._currentDevice] || this._currentDevice.toUpperCase();
            this._deviceDisplayItem.label.text = `Device: ${deviceDisplay}`;
        }
    }

    destroy() {
        // Clean up D-Bus name watcher
        if (this._nameWatcherId) {
            Gio.DBus.session.unwatch_name(this._nameWatcherId);
            this._nameWatcherId = null;
        }

        if (this._proxy) {
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
