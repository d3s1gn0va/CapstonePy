import importlib.util
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch


def load_endpoint():
    # Model only D-Bus types/decorators; this never registers Bluetooth or opens hardware.
    class Object:
        def __init__(self, bus, path):
            pass

    def decorator(*args, **kwargs):
        return lambda function: function

    service = SimpleNamespace(Object=Object, method=decorator, signal=decorator)
    dbus = SimpleNamespace(service=service, exceptions=SimpleNamespace(DBusException=Exception),
                           ObjectPath=str, UInt16=int, Boolean=bool,
                           Array=lambda items, **kwargs: list(items))
    modules = {"dbus": dbus, "dbus.service": service,
               "dbus.mainloop": SimpleNamespace(), "dbus.mainloop.glib": SimpleNamespace(),
               "gi": SimpleNamespace(), "gi.repository": SimpleNamespace(GLib=SimpleNamespace())}
    path = Path(__file__).resolve().parents[1] / "raspberry_pi/robot_demo/cuvo_ble.py"
    spec = importlib.util.spec_from_file_location("cuvo_ble_under_test", path)
    endpoint = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, modules), patch.object(sys, "path", [str(path.parent)] + sys.path):
        spec.loader.exec_module(endpoint)
    return endpoint


class BLEGattTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.endpoint = load_endpoint()

    def test_v1_handles_are_identical_after_recreating_application(self):
        endpoint = self.endpoint
        first = endpoint.Application(None, None).GetManagedObjects()
        second = endpoint.Application(None, None).GetManagedObjects()
        self.assertEqual(first, second)
        self.assertEqual(first[endpoint.ROOT + "/service"][endpoint.GATT_SERVICE]["Handle"], 0x0100)
        self.assertEqual(first[endpoint.ROOT + "/service/command"][endpoint.GATT_CHAR]["Handle"], 0x0102)
        self.assertEqual(first[endpoint.ROOT + "/service/status"][endpoint.GATT_CHAR]["Handle"], 0x0104)

    def test_bluez_can_read_handle_but_cannot_reallocate_it(self):
        endpoint = self.endpoint
        application = endpoint.Application(None, None)
        status = application.status
        self.assertEqual(status.Get(endpoint.GATT_CHAR, "Handle"), endpoint.STATUS_HANDLE)
        status.Set(endpoint.GATT_CHAR, "Handle", endpoint.STATUS_HANDLE)
        with self.assertRaises(endpoint.NotPermitted):
            status.Set(endpoint.GATT_CHAR, "Handle", endpoint.STATUS_HANDLE + 1)
        with self.assertRaises(endpoint.NotPermitted):
            status.Set(endpoint.GATT_CHAR, "UUID", "different")
        with self.assertRaises(endpoint.NotPermitted):
            status.Get(endpoint.GATT_SERVICE, "Handle")

    def test_status_preserves_a_whole_unicode_frame_in_small_chunks(self):
        endpoint = self.endpoint
        status = endpoint.Application(None, None).status
        status.notifying = True
        status.sending = True
        status.enqueue({"message": "CUVO 준비", "revision": 1})
        emitted = []
        status.PropertiesChanged = lambda interface, changed, invalid: emitted.append(bytes(changed["Value"]))
        while status.send_chunk():
            pass
        self.assertTrue(all(len(chunk) <= 20 for chunk in emitted))
        self.assertEqual(b"".join(emitted).decode(), '{"message":"CUVO 준비","revision":1}\n')
        status.StopNotify()
        self.assertFalse(status.notifying)
        self.assertFalse(status.frames)
        self.assertFalse(status.chunks)

    def test_long_read_retains_one_snapshot_without_renewing_control(self):
        endpoint = self.endpoint

        class Control:
            revision = 0

            def snapshot(self):
                self.revision += 1
                return {"revision": self.revision, "message": "CUVO 준비"}

        control = Control()
        status = endpoint.Application(None, control).status
        first = bytes(status.ReadValue({"device": "phone", "offset": 0}))
        continuation = bytes(status.ReadValue({"device": "phone", "offset": 10}))
        self.assertEqual(continuation, first[10:])
        self.assertEqual(control.revision, 1)
        self.assertIn(b'"revision":2', bytes(status.ReadValue({"device": "phone", "offset": 0})))
        with self.assertRaises(endpoint.NotPermitted):
            status.ReadValue({"device": "unknown", "offset": 10})


if __name__ == "__main__":
    unittest.main()
