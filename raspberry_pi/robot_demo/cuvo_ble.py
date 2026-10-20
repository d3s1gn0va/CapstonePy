#!/usr/bin/env python3
"""BlueZ BLE endpoint. Connecting never starts motion; completed dances enable idle eyes."""

import argparse
from collections import deque
import fcntl
import json
import math
import os
from pathlib import Path
import secrets
import signal
import stat
import subprocess
import sys
import time

import dbus
import dbus.mainloop.glib
import dbus.service
from gi.repository import GLib

from ble_control import BLEControl, CommandError, SERVICE_UUID, COMMAND_UUID, STATUS_UUID
from ble_credentials import CredentialStore
from idle_eyes import IdleEyes
from power_pose import PowerPose
from exhibit_control import ExhibitControl
from exhibit_sequences import ExhibitCatalog
from exhibit_media import VolumeController, RecordManager
from exhibit_worker import ExhibitWorker
from exhibit_http import MediaHTTPServer

PROPS = "org.freedesktop.DBus.Properties"
OBJECTS = "org.freedesktop.DBus.ObjectManager"
GATT_SERVICE = "org.bluez.GattService1"
GATT_CHAR = "org.bluez.GattCharacteristic1"
ADVERT = "org.bluez.LEAdvertisement1"
AGENT = "org.bluez.Agent1"
ROOT = "/org/cuvo/robot"
# Keep this v1 layout stable across daemon restarts; BlueZ allocates the CCC at 0x0105.
SERVICE_HANDLE, COMMAND_HANDLE, STATUS_HANDLE = 0x0100, 0x0102, 0x0104


class Rejected(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.Rejected"


class NotPermitted(dbus.exceptions.DBusException):
    _dbus_error_name = "org.bluez.Error.NotPermitted"


class DanceWorker:
    def __init__(self):
        self.process = subprocess.Popen([sys.executable, "-u", str(Path(__file__).with_name("ble_dance_worker.py")),
                                         "--confirm-5v-and-clear"], stdout=subprocess.PIPE,
                                        stdin=subprocess.DEVNULL)
        os.set_blocking(self.process.stdout.fileno(), False)
        self.buffer, self.terminal = bytearray(), None

    def poll(self):
        try:
            self.buffer.extend(os.read(self.process.stdout.fileno(), 8192))
        except BlockingIOError:
            pass
        exit_code = self.process.poll()
        if exit_code is not None:
            while True:
                chunk = os.read(self.process.stdout.fileno(), 8192)
                if not chunk:
                    break
                self.buffer.extend(chunk)
                if len(self.buffer) > 8192:
                    raise ValueError("Worker output too large")
        if len(self.buffer) > 8192:
            raise ValueError("Worker output too large")
        events = []
        while b"\n" in self.buffer:
            raw, _, rest = self.buffer.partition(b"\n")
            self.buffer = bytearray(rest)
            event = json.loads(raw)
            if set(event) != {"state", "phase", "progress"} or event["state"] not in ("running", "completed", "stopped", "error"):
                raise ValueError("Invalid worker status")
            if event["phase"] not in ("idle", "greeting", "prepare", "dance", "return", "goodbye"):
                raise ValueError("Invalid worker phase")
            if isinstance(event["progress"], bool) or not isinstance(event["progress"], (float, int)) or not math.isfinite(event["progress"]) or not 0 <= event["progress"] <= 1:
                raise ValueError("Invalid worker progress")
            if event["state"] != "running":
                self.terminal = event
            events.append(event)
        return events, exit_code

    def terminate(self):
        if self.process.poll() is None:
            self.process.send_signal(signal.SIGTERM)

    def kill(self):
        if self.process.poll() is None:
            self.process.kill()

    def close(self):
        self.process.wait(timeout=1)
        self.process.stdout.close()


class GATTObject(dbus.service.Object):
    def __init__(self, bus, path, interface, properties):
        super().__init__(bus, path)
        self.path, self.interface, self.properties = path, interface, properties

    @dbus.service.method(PROPS, in_signature="s", out_signature="a{sv}")
    def GetAll(self, interface):
        if interface != self.interface:
            raise NotPermitted("Unknown interface")
        return self.properties

    @dbus.service.method(PROPS, in_signature="ss", out_signature="v")
    def Get(self, interface, name):
        if interface != self.interface or name not in self.properties:
            raise NotPermitted("Unknown property")
        return self.properties[name]

    @dbus.service.method(PROPS, in_signature="ssv")
    def Set(self, interface, name, value):
        if interface != self.interface or name != "Handle" or name not in self.properties:
            raise NotPermitted("Read-only property")
        if int(value) != int(self.properties[name]):
            raise NotPermitted("The v1 GATT handle layout must not change")


class CommandCharacteristic(GATTObject):
    def __init__(self, bus, service_path, control):
        super().__init__(bus, service_path + "/command", GATT_CHAR,
                         {"UUID": COMMAND_UUID, "Service": dbus.ObjectPath(service_path),
                          "Handle": dbus.UInt16(COMMAND_HANDLE),
                          "Flags": dbus.Array(["write", "encrypt-write"], signature="s")})
        self.bus, self.control = bus, control

    @dbus.service.method(GATT_CHAR, in_signature="aya{sv}")
    def WriteValue(self, value, options):
        if int(options.get("offset", 0)) != 0 or options.get("prepare-authorize", False):
            raise NotPermitted("Only complete commands are accepted")
        device = str(options.get("device", ""))
        try:
            props = dbus.Interface(self.bus.get_object("org.bluez", device), PROPS)
            paired = bool(props.Get("org.bluez.Device1", "Paired"))
            connected = bool(props.Get("org.bluez.Device1", "Connected"))
            self.control.command(bytes(value), device, paired and connected)
        except (CommandError, dbus.exceptions.DBusException) as error:
            raise NotPermitted(str(error)) from error


class StatusCharacteristic(GATTObject):
    def __init__(self, bus, service_path, control):
        super().__init__(bus, service_path + "/status", GATT_CHAR,
                         {"UUID": STATUS_UUID, "Service": dbus.ObjectPath(service_path),
                          "Handle": dbus.UInt16(STATUS_HANDLE),
                          "Flags": dbus.Array(["read", "notify"], signature="s")})
        self.control, self.notifying = control, False
        self.frames, self.chunks = deque(), deque()
        self.sending = False
        self.read_frames = {}

    @dbus.service.method(GATT_CHAR, in_signature="a{sv}", out_signature="ay")
    def ReadValue(self, options):
        device, offset = str(options.get("device", "")), int(options.get("offset", 0))
        if offset == 0:
            if device not in self.read_frames and len(self.read_frames) >= 8:
                self.read_frames.pop(next(iter(self.read_frames)))
            snapshot = self.control.read_snapshot() if hasattr(self.control, "read_snapshot") else self.control.snapshot()
            self.read_frames[device] = json.dumps(snapshot, ensure_ascii=False,
                                                  separators=(",", ":")).encode() + b"\n"
        # A long GATT read must retain one snapshot across all Read Blob offsets.
        raw = self.read_frames.get(device)
        if raw is None or offset < 0 or offset > len(raw):
            raise NotPermitted("No matching status read")
        return dbus.Array(raw[offset:], signature="y")

    @dbus.service.method(GATT_CHAR)
    def StartNotify(self):
        self.notifying = True
        self.control.publish()

    @dbus.service.method(GATT_CHAR)
    def StopNotify(self):
        self.notifying = False
        self.frames.clear()
        self.chunks.clear()

    @dbus.service.signal(PROPS, signature="sa{sv}as")
    def PropertiesChanged(self, interface, changed, invalidated):
        pass

    def enqueue(self, snapshot):
        if not self.notifying:
            return
        # Queue whole frames: never drop half of a JSON notification frame.
        if len(self.frames) >= 32:
            self.frames.popleft()
        self.frames.append(json.dumps(snapshot, ensure_ascii=False, separators=(",", ":")).encode() + b"\n")
        if not self.sending:
            self.sending = True
            GLib.timeout_add(5, self.send_chunk)

    def send_chunk(self):
        if not self.notifying:
            self.sending = False
            return False
        if not self.chunks and self.frames:
            frame = self.frames.popleft()
            self.chunks.extend(frame[i:i + 20] for i in range(0, len(frame), 20))
        if not self.chunks:
            self.sending = False
            return False
        self.PropertiesChanged(GATT_CHAR, {"Value": dbus.Array(self.chunks.popleft(), signature="y")}, [])
        return True


class Application(dbus.service.Object):
    def __init__(self, bus, control):
        super().__init__(bus, ROOT)
        path = ROOT + "/service"
        self.status = StatusCharacteristic(bus, path, control)
        command = CommandCharacteristic(bus, path, control)
        service = GATTObject(bus, path, GATT_SERVICE,
                             {"UUID": SERVICE_UUID, "Primary": dbus.Boolean(True),
                              "Handle": dbus.UInt16(SERVICE_HANDLE),
                              "Characteristics": dbus.Array([command.path, self.status.path], signature="o")})
        self.objects = [service, command, self.status]

    @dbus.service.method(OBJECTS, out_signature="a{oa{sa{sv}}}")
    def GetManagedObjects(self):
        return {item.path: {item.interface: item.properties} for item in self.objects}


class Advertisement(GATTObject):
    def __init__(self, bus):
        super().__init__(bus, ROOT + "/advertisement", ADVERT,
                         {"Type": "peripheral", "LocalName": "CUVO",
                          "ServiceUUIDs": dbus.Array([SERVICE_UUID], signature="s")})

    @dbus.service.method(ADVERT)
    def Release(self):
        pass


class PairingAgent(dbus.service.Object):
    def __init__(self, bus, seconds):
        super().__init__(bus, ROOT + "/agent")
        self.deadline = time.monotonic() + seconds

    def check_window(self):
        if time.monotonic() > self.deadline:
            raise Rejected("Pairing window expired; ask the operator to reopen it")

    @dbus.service.method(AGENT)
    def Release(self):
        pass

    @dbus.service.method(AGENT, in_signature="o")
    def RequestAuthorization(self, device):
        self.check_window()

    @dbus.service.method(AGENT, in_signature="ou")
    def RequestConfirmation(self, device, passkey):
        self.check_window()

    @dbus.service.method(AGENT, in_signature="os")
    def AuthorizeService(self, device, uuid):
        if str(uuid).upper() != SERVICE_UUID:
            raise Rejected("Only the CUVO control service is authorized")

    @dbus.service.method(AGENT)
    def Cancel(self):
        pass


def private_runtime_directory():
    path = Path(f"/tmp/cuvo-ble-{os.getuid()}")
    path.mkdir(mode=0o700, exist_ok=True)
    info = path.lstat()
    if not stat.S_ISDIR(info.st_mode) or info.st_uid != os.getuid() or stat.S_IMODE(info.st_mode) != 0o700:
        raise RuntimeError("Runtime directory must be private and owned by this user")
    return path


def preflight():
    from dance_sequence import load_dance_config
    from motion_profile import load_profile
    from oled_renderer import load_calibration
    from test_dance_once import validate_test
    validate_test(load_profile(), load_calibration(), load_dance_config(), True)


def hardware_ready():
    # Presence check only: never open devices here, even when idle eyes are active.
    from serial_controller import find_serial_port, SerialControllerError
    import config
    try:
        find_serial_port(config.SERIAL_PORT)
    except SerialControllerError:
        return False
    runtime = Path(os.environ.get("XDG_RUNTIME_DIR", f"/run/user/{os.getuid()}"))
    return all(p.exists() for p in (runtime / "pipewire-0", Path("/dev/spidev0.0"), Path("/dev/spidev0.1")))


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--confirm-5v-and-clear", action="store_true", help="Allow only the approved five-axis dance")
    parser.add_argument("--home-on-start-stop", action="store_true", help="Park six calibrated axes on startup and clean service shutdown")
    parser.add_argument("--confirm-exhibit-scenes-and-clear", action="store_true",
                        help="Separately authorize the new bounded exhibit/filming presets after checking clearance")
    parser.add_argument("--allow-poweroff", action="store_true", help="Expose normal OS shutdown only when logind authorizes it")
    parser.add_argument("--enable-recording", action="store_true", help="Opt in to real camera recording; disabled by default")
    parser.add_argument("--records-root", type=Path, default=Path.home() / ".local/state/cuvo/records")
    parser.add_argument("--media-bind", default="127.0.0.1")
    parser.add_argument("--media-port", type=int, default=8765)
    parser.add_argument("--media-base-url", help="Explicit same-LAN URL, e.g. http://cuvo.local:8765; enables signed record downloads")
    parser.add_argument("--pairing-seconds", type=int, default=120, choices=range(1, 901))
    args = parser.parse_args(argv)
    if args.home_on_start_stop and not args.confirm_5v_and_clear:
        parser.error("--home-on-start-stop requires --confirm-5v-and-clear")
    if args.confirm_5v_and_clear:
        preflight()
    runtime = private_runtime_directory()
    with (runtime / "lock").open("a") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        code = f"{secrets.randbelow(1000000):06d}"
        descriptor = os.open(runtime / "connection-code", os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
        with os.fdopen(descriptor, "w") as file:
            os.fchmod(file.fileno(), 0o600)
            file.write(code + "\n")
        dbus.mainloop.glib.DBusGMainLoop(set_as_default=True)
        bus = dbus.SystemBus()
        managed = dbus.Interface(bus.get_object("org.bluez", "/"), OBJECTS).GetManagedObjects()
        adapters = [path for path, props in managed.items()
                    if "org.bluez.GattManager1" in props and "org.bluez.LEAdvertisingManager1" in props
                    and props.get("org.bluez.Adapter1", {}).get("Powered")]
        if not adapters:
            raise RuntimeError("No powered BLE peripheral adapter")
        adapter = bus.get_object("org.bluez", adapters[0])
        gatt = dbus.Interface(adapter, "org.bluez.GattManager1")
        advertising = dbus.Interface(adapter, "org.bluez.LEAdvertisingManager1")
        agent_manager = dbus.Interface(bus.get_object("org.bluez", "/org/bluez"), "org.bluez.AgentManager1")
        credentials = CredentialStore(Path.home() / ".local/state/cuvo/controller.json")
        idle_eyes = IdleEyes(runtime / "idle-eyes-enabled")
        power_pose = None
        if args.home_on_start_stop:
            from motion_profile import load_profile
            power_pose = PowerPose(load_profile(), runtime / "power-pose", confirmed=True)

        def start_dance():
            idle_eyes.before_dance()
            return DanceWorker()

        from motion_profile import load_profile
        from oled_renderer import load_calibration
        records = RecordManager(args.records_root, enabled=args.enable_recording)
        media_server = None
        if args.media_base_url:
            media_server = MediaHTTPServer(records, credentials, bind_host=args.media_bind,
                                          port=args.media_port, base_url=args.media_base_url)
            media_server.start()

        def start_exhibit(specification):
            idle_eyes.before_dance()
            return ExhibitWorker(specification)

        allow_poweroff = False
        if args.allow_poweroff:
            try:
                manager = dbus.Interface(bus.get_object("org.freedesktop.login1", "/org/freedesktop/login1"),
                                         "org.freedesktop.login1.Manager")
                allow_poweroff = str(manager.CanPowerOff()) == "yes"
            except dbus.exceptions.DBusException:
                pass
            if not allow_poweroff:
                print("[CUVO poweroff] unavailable: noninteractive logind permission required", file=sys.stderr)
        control = ExhibitControl(code, start_dance, confirmed=args.confirm_5v_and_clear,
                                 credentials=credentials, hardware_ready=hardware_ready,
                                 catalog=ExhibitCatalog(load_profile(), load_calibration(), args.confirm_exhibit_scenes_and_clear),
                                 exhibit_worker_factory=start_exhibit, volume=VolumeController(), records=records,
                                 allow_poweroff=allow_poweroff, media=(lambda: media_server.descriptor) if media_server else None)
        application, advertisement = Application(bus, control), Advertisement(bus)
        agent = PairingAgent(bus, args.pairing_seconds)
        loop, registered, shutting_down = GLib.MainLoop(), [], False
        normal_shutdown, parking_failed, requested_poweroff = False, False, False

        def publish(snapshot):
            application.status.enqueue(snapshot)
            temp = runtime / "status.tmp"
            with temp.open("w") as file:
                os.chmod(temp, 0o600)
                json.dump(dict(snapshot, pid=os.getpid(), pairing_open=time.monotonic() < agent.deadline,
                               eyes_idle_armed=idle_eyes.armed,
                               eyes_idle_pid=(idle_eyes.process.process.pid if idle_eyes.process else None)), file)
            temp.replace(runtime / "status.json")

        control.on_status = publish

        def device_changed(interface, changed, invalidated, path=None):
            if interface == "org.bluez.Device1" and "Connected" in changed and not changed["Connected"]:
                control.disconnected(str(path))

        bus.add_signal_receiver(device_changed, dbus_interface=PROPS, signal_name="PropertiesChanged",
                                bus_name="org.bluez", path_keyword="path")

        def shutdown(*unused, normal=True):
            nonlocal shutting_down, normal_shutdown
            shutting_down = True
            normal_shutdown = normal
            control.confirmed = False
            control.stop()
            control.publish()

        def requested_shutdown():
            nonlocal requested_poweroff
            requested_poweroff = True
            shutdown()

        control.on_shutdown_ready = requested_shutdown

        for sig in (signal.SIGINT, signal.SIGTERM):
            GLib.unix_signal_add(GLib.PRIORITY_DEFAULT, sig, lambda: (shutdown(), False)[1])

        def tick():
            control.tick()
            eye_state = (idle_eyes.armed, idle_eyes.process)
            try:
                # The filmed farewell ends with closed eyes, until another explicit scene.
                eye_mode = "stopped" if control.scene_id == "09" and control.state == "completed" else control.state
                idle_eyes.sync(eye_mode, busy=control.worker is not None, shutting_down=shutting_down)
            except (OSError, RuntimeError) as error:
                # An OLED-only failure must not crash the BLE watchdog or start motion.
                print(f"[CUVO eyes] {error}", file=sys.stderr, flush=True)
                idle_eyes.armed = False
                idle_eyes.marker.unlink(missing_ok=True)
            if eye_state != (idle_eyes.armed, idle_eyes.process):
                control.publish()
            if shutting_down and control.worker is None:
                loop.quit()
                return False
            return True

        def registration_failed(error):
            print(f"[CUVO BLE] registration failed: {error}", file=sys.stderr, flush=True)
            shutdown(normal=False)
            loop.quit()

        def advertise():
            registered.append("gatt")
            advertising.RegisterAdvertisement(advertisement.path, {},
                                              reply_handler=ready, error_handler=registration_failed)

        def ready():
            registered.append("advert")
            control.publish()
            print("[CUVO BLE] READY; no dance started; code is in the private runtime file", flush=True)

        try:
            if power_pose:
                power_pose.prepare()
            agent_manager.RegisterAgent(ROOT + "/agent", "NoInputNoOutput")
            registered.append("agent")
            agent_manager.RequestDefaultAgent(ROOT + "/agent")
            gatt.RegisterApplication(ROOT, {}, reply_handler=advertise, error_handler=registration_failed)
            GLib.timeout_add(50, tick)
            loop.run()
        finally:
            try:
                idle_eyes.pause()
            except (OSError, RuntimeError) as error:
                print(f"[CUVO eyes] cleanup: {error}", file=sys.stderr, flush=True)
            control.stop()
            deadline = time.monotonic() + 7
            while control.worker and time.monotonic() < deadline:
                control.tick()
                time.sleep(0.05)
            cleanup_safe = control.worker is None and control.state != "error"
            if control.worker:
                control.worker.kill()
                control.worker.close()
            if power_pose and normal_shutdown and "advert" in registered:
                if cleanup_safe:
                    try:
                        power_pose.finish()
                    except Exception as error:
                        parking_failed = True
                        print(f"[CUVO parking] shutdown failed: {error}", file=sys.stderr, flush=True)
                else:
                    parking_failed = True
                    print("[CUVO parking] skipped: motion cleanup failed; no automatic return", file=sys.stderr, flush=True)
            for kind in reversed(registered):
                try:
                    if kind == "advert":
                        advertising.UnregisterAdvertisement(advertisement.path)
                    elif kind == "gatt":
                        gatt.UnregisterApplication(ROOT)
                    else:
                        agent_manager.UnregisterAgent(ROOT + "/agent")
                except dbus.exceptions.DBusException:
                    pass
            (runtime / "connection-code").unlink(missing_ok=True)
            (runtime / "status.json").unlink(missing_ok=True)
            control.close()
            if media_server:
                media_server.close()
        if requested_poweroff and cleanup_safe and not parking_failed:
            # No forced halt or shell; existing STOP/normal parking must finish first.
            try:
                result = subprocess.run(["systemctl", "--no-ask-password", "poweroff"],
                                        stdin=subprocess.DEVNULL, timeout=5, check=False)
                if result.returncode:
                    print("[CUVO poweroff] OS rejected shutdown", file=sys.stderr)
                    return 1
            except (OSError, subprocess.TimeoutExpired):
                print("[CUVO poweroff] OS shutdown not confirmed", file=sys.stderr)
                return 1
        return 0 if "advert" in registered and not parking_failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
