import gi
gi.require_version("Gtk", "3.0")
gi.require_version("AppIndicator3", "0.1")
from gi.repository import Gtk, AppIndicator3
import subprocess

SERVICE = "ron-dictation.service"

def start_service(_):
    subprocess.call(["systemctl", "--user", "start", SERVICE])

def stop_service(_):
    subprocess.call(["systemctl", "--user", "stop", SERVICE])

def restart_service(_):
    subprocess.call(["systemctl", "--user", "restart", SERVICE])

def quit_app(_):
    Gtk.main_quit()

def build_menu():
    menu = Gtk.Menu()

    start_item = Gtk.MenuItem(label="Start")
    stop_item = Gtk.MenuItem(label="Stop")
    restart_item = Gtk.MenuItem(label="Restart")
    quit_item = Gtk.MenuItem(label="Quit tray")

    start_item.connect("activate", start_service)
    stop_item.connect("activate", stop_service)
    restart_item.connect("activate", restart_service)
    quit_item.connect("activate", quit_app)

    for item in (start_item, stop_item, restart_item, Gtk.SeparatorMenuItem(), quit_item):
        menu.append(item)
    menu.show_all()
    return menu

def main():
    indicator = AppIndicator3.Indicator.new(
        "ron-dictation",
        "microphone-sensitivity-medium",  # themed icon name
        AppIndicator3.IndicatorCategory.APPLICATION_STATUS
    )
    indicator.set_status(AppIndicator3.IndicatorStatus.ACTIVE)
    indicator.set_menu(build_menu())
    Gtk.main()

if __name__ == "__main__":
    main()
