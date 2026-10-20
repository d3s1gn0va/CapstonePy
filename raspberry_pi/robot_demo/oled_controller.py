"""Single-owner OLED output adapter; importing this module never touches GPIO."""

from contextlib import ExitStack
from pathlib import Path

from oled_renderer import SIZE

# (SPI device, BCM DC, BCM RST): CE0 physical 18/22; CE1 physical 7/12.
PANELS = ((0, 24, 25), (1, 4, 18))


def open_displays(stack, config, factory=None, serial_factory=None):
    if factory is None or serial_factory is None:
        from luma.core.interface.serial import spi
        from luma.oled.device import sh1107
        factory, serial_factory = sh1107, spi
    displays = []
    for device, dc, rst in PANELS:
        serial = serial_factory(port=0, device=device, gpio_DC=dc, gpio_RST=rst,
                                bus_speed_hz=1000000)
        try:
            display = factory(serial, width=SIZE, height=SIZE, rotate=0)
        except BaseException:
            serial.cleanup()
            raise
        stack.callback(display.cleanup)
        display.contrast(config["contrast"])
        displays.append(display)
    return displays


class EyeController:
    """One coordinator calls show(pose) each frame; no sleeps or servo access here."""

    def __init__(self, renderer, swap=False):
        self.renderer = renderer
        self.swap = swap
        self._stack = None
        self._displays = []

    def __enter__(self):
        import fcntl
        if self._stack is not None:
            raise RuntimeError("OLED controller is already open")
        stack = ExitStack()
        try:
            lock = stack.enter_context(Path("/tmp/cuvo-oled-pair.lock").open("a"))
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as error:
                raise RuntimeError("Another paired-eye controller is running") from error
            self._displays = open_displays(stack, self.renderer.config)
        except BaseException:
            stack.close()
            raise
        self._stack = stack
        return self

    def show(self, pose):
        if self._stack is None:
            raise RuntimeError("OLED controller is not open")
        frames = self.renderer.frames(pose.openness, pose.offset_x, pose.offset_y)
        if self.swap:
            frames = frames[::-1]
        for display, frame in zip(self._displays, frames):
            display.display(frame)

    def __exit__(self, *exception):
        try:
            return self._stack.__exit__(*exception)
        finally:
            self._displays = []
            self._stack = None
