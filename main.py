import os
import time

import dbus
from dbus.mainloop.glib import DBusGMainLoop
from gi.repository import GLib

PLAYER_INTERFACE = "org.mpris.MediaPlayer2.Player"
DBUS_NAME_SERVICE = "org.freedesktop.DBus"
DOUBLE_TAP_WINDOW = 1000
COOLDOWN_AFTER_SKIP = 1500

first_tap_time = None
tap_count = 0
cooldown_until = 0.0
current_player_name = None

DBusGMainLoop(set_as_default=True)

try:
    session_bus = dbus.SessionBus()
    dbus_proxy = session_bus.get_object(DBUS_NAME_SERVICE, "/org/freedesktop/DBus")
    dbus_interface = dbus.Interface(dbus_proxy, DBUS_NAME_SERVICE)
except dbus.exceptions.DBusException as e:
    print(f"FATAL: D-Bus connection error: {e}")
    exit(1)


def get_all_players():
    try:
        active_names = dbus_interface.ListNames()
        mpris_services = [
            s for s in active_names if s.startswith("org.mpris.MediaPlayer2.")
        ]
        return mpris_services
    except Exception:
        return []


def get_player(player_name):
    try:
        player_proxy = session_bus.get_object(player_name, "/org/mpris/MediaPlayer2")
        player_interface = dbus.Interface(player_proxy, PLAYER_INTERFACE)
        return player_interface
    except Exception:
        return None


def execute_skip(player_name):
    global cooldown_until

    player = get_player(player_name)
    if not player:
        return

    try:
        player.Next()
        cooldown_until = time.time() + (COOLDOWN_AFTER_SKIP / 1000.0)
        print(
            f"[{time.strftime('%H:%M:%S')}] Skipped to next track on {player_name.replace('org.mpris.MediaPlayer2.', '')}"
        )
    except Exception:
        pass


def reset_tap_detection():
    global first_tap_time, tap_count

    first_tap_time = None
    tap_count = 0
    return GLib.SOURCE_REMOVE


def seeked_handler(position, sender=None):
    global first_tap_time, tap_count, cooldown_until

    current_time = time.time()

    if current_time < cooldown_until:
        return

    if first_tap_time is None:
        first_tap_time = current_time
        tap_count = 1
        GLib.timeout_add(DOUBLE_TAP_WINDOW, reset_tap_detection)
        return

    time_since_first = (current_time - first_tap_time) * 1000

    if time_since_first < DOUBLE_TAP_WINDOW:
        tap_count += 1

        if tap_count == 2:
            execute_skip(sender)
            first_tap_time = None
            tap_count = 0
    else:
        first_tap_time = current_time
        tap_count = 1
        GLib.timeout_add(DOUBLE_TAP_WINDOW, reset_tap_detection)


def setup_signal_handlers():
    players = get_all_players()

    if players:
        print("--- Initial Player Status ---")

    for player_name in players:
        try:
            session_bus.add_signal_receiver(
                lambda pos, sender=player_name: seeked_handler(pos, sender),
                signal_name="Seeked",
                dbus_interface=PLAYER_INTERFACE,
                bus_name=player_name,
                path="/org/mpris/MediaPlayer2",
            )
            print(f"Listening to: {player_name.replace('org.mpris.MediaPlayer2.', '')}")
        except Exception:
            pass

    if players:
        print("-----------------------------")


def on_name_owner_changed(name, old_owner, new_owner):
    if not name.startswith("org.mpris.MediaPlayer2."):
        return

    player_short_name = name.replace("org.mpris.MediaPlayer2.", "")

    if new_owner:
        try:
            session_bus.add_signal_receiver(
                lambda pos, sender=name: seeked_handler(pos, sender),
                signal_name="Seeked",
                dbus_interface=PLAYER_INTERFACE,
                bus_name=name,
                path="/org/mpris/MediaPlayer2",
            )
            print(f"Player started: {player_short_name}")
        except Exception:
            pass

    elif old_owner:
        print(f"Player closed: {player_short_name}")


def main():
    if os.geteuid() == 0:
        print("WARNING: This script should NOT be run with sudo.")
        exit(1)

    print("AirPod Double-Tap Skip Initialized.")
    print(
        f"Double-tap window: {DOUBLE_TAP_WINDOW}ms, Skip Cooldown: {COOLDOWN_AFTER_SKIP}ms"
    )

    setup_signal_handlers()

    session_bus.add_signal_receiver(
        on_name_owner_changed,
        signal_name="NameOwnerChanged",
        dbus_interface=DBUS_NAME_SERVICE,
    )

    print("Listening for taps...")

    try:
        loop = GLib.MainLoop()
        loop.run()
    except KeyboardInterrupt:
        print("\nExiting...")
        pass
    except Exception:
        pass


if __name__ == "__main__":
    main()
