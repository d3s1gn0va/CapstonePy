import json
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from import_oled_aperture import convert

try:
    import ezdxf
except ImportError:
    ezdxf = None


@unittest.skipIf(ezdxf is None, "Offline CAD import tests require ezdxf (not needed on Pi)")
class ApertureImportTests(unittest.TestCase):
    source = ROOT / "docs/assets/cad_exports/eye_opening_left.dxf"

    def test_checked_in_profile_is_reproducible(self):
        generated = convert(self.source)
        stored = json.loads((ROOT / "raspberry_pi/robot_demo/oled_aperture.json").read_text())
        self.assertEqual(generated["left_points_mm"], stored["left_points_mm"])
        self.assertEqual(generated["source"]["sha256"], stored["source"]["sha256"])
        self.assertEqual(len(generated["left_points_mm"]), 103)
        self.assertEqual(generated["source"]["flattening_tolerance_mm"], 0.01)

    def test_rotated_square_maps_to_upright_va_mm(self):
        points = convert(self.source)["left_points_mm"]
        xs, ys = zip(*points)
        for actual, expected in zip((min(xs), min(ys), max(xs), max(ys)),
                                    (6.38127, 1.74815, 27.59083, 28.19389)):
            self.assertAlmostEqual(actual, expected, places=4)

    def test_wrong_units_and_nonplanar_rectangle_rejected(self):
        for change in ("units", "elevation", "extrusion"):
            with self.subTest(change=change):
                doc = ezdxf.readfile(self.source)
                rectangle = list(doc.modelspace().query("LWPOLYLINE"))[0]
                if change == "units":
                    doc.units = 1
                elif change == "elevation":
                    rectangle.dxf.elevation = 1
                else:
                    rectangle.dxf.extrusion = (0, 0, -1)
                with patch.object(ezdxf, "readfile", return_value=doc), self.assertRaises(ValueError):
                    convert(self.source)

    def test_invalid_orientation_size_and_tolerance_rejected(self):
        for arguments in ({"top_left": 3, "top_right": 1}, {"va_side": 30},
                          {"tolerance": 0}, {"tolerance": float("nan")}, {"tolerance": 1}):
            with self.subTest(arguments=arguments), self.assertRaises(ValueError):
                convert(self.source, **arguments)


if __name__ == "__main__":
    unittest.main()
