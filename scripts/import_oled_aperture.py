"""Convert a millimetre DXF (one square + one closed spline) to an OLED aperture."""

import argparse
import hashlib
import json
import math
from pathlib import Path


def convert(dxf_path, top_left=3, top_right=2, va_side=28.86, tolerance=0.01):
    import ezdxf
    from ezdxf.math import Vec3

    if not math.isfinite(tolerance) or not 0 < tolerance <= 0.05:
        raise ValueError("Flattening tolerance must be in (0, 0.05] mm")
    doc = ezdxf.readfile(dxf_path)
    if doc.units != 4:
        raise ValueError("DXF units must be millimetres ($INSUNITS=4)")
    space = doc.modelspace()
    splines, rectangles = list(space.query("SPLINE")), list(space.query("LWPOLYLINE"))
    if len(splines) != 1 or len(rectangles) != 1:
        raise ValueError("Export exactly one eye-opening SPLINE and one VA LWPOLYLINE")
    spline, rectangle = splines[0], rectangles[0]
    if abs(rectangle.dxf.elevation) > 1e-6 or any(
            abs(actual - expected) > 1e-6
            for actual, expected in zip(rectangle.dxf.extrusion, (0, 0, 1))):
        raise ValueError("Export the VA square on its XY plane with the standard normal")
    vertices = list(rectangle.get_points("xyb"))
    if not rectangle.closed or len(vertices) != 4 or any(abs(p[2]) > 1e-9 for p in vertices):
        raise ValueError("VA must be a closed, straight-sided four-vertex square")
    if top_left not in range(4) or top_right not in range(4) or (top_left - top_right) % 4 not in (1, 3):
        raise ValueError("Top-left and top-right must be adjacent square vertices")
    corners = [Vec3(float(x), float(y), 0) for x, y, _ in vertices]
    bottom_left = next(i for i in range(4) if i != top_right and (i - top_left) % 4 in (1, 3))
    bottom_right = next(i for i in range(4) if i not in (top_left, top_right, bottom_left))
    origin = corners[top_left]
    x_edge, y_edge = corners[top_right] - origin, corners[bottom_left] - origin
    if any(not math.isclose(edge.magnitude, va_side, abs_tol=1e-4) for edge in (x_edge, y_edge)):
        raise ValueError("VA square sides must match va_side_mm")
    if abs(x_edge.dot(y_edge)) > 1e-4 or (corners[bottom_right] - origin - x_edge - y_edge).magnitude > 1e-4:
        raise ValueError("VA corners must form an orthogonal square")
    x_axis, y_axis = x_edge.normalize(), y_edge.normalize()
    sampled = list(spline.flattening(distance=tolerance, segments=8))
    if len(sampled) < 4 or (sampled[0] - sampled[-1]).magnitude > 1e-6:
        raise ValueError("Eye-opening spline endpoints must coincide")
    if any(abs(p.z) > 1e-6 for p in sampled):
        raise ValueError("Export the sketch on its XY plane")
    points = []
    for p in sampled[:-1]:
        delta = p - origin
        point = [round(delta.dot(x_axis), 5), round(delta.dot(y_axis), 5)]
        if not all(0 <= value <= va_side for value in point):
            raise ValueError("Eye-opening curve must fit inside VA")
        if not points or point != points[-1]:
            points.append(point)
    if not 3 <= len(points) <= 512:
        raise ValueError("Curve needs 3..512 samples at the chosen tolerance")
    return {
        "schema_version": 1,
        "units": "va_mm",
        "va_side_mm": va_side,
        "status": "cad_derived_unverified_physical_fit",
        "source": {
            "file": Path(dxf_path).name,
            "sha256": hashlib.sha256(Path(dxf_path).read_bytes()).hexdigest(),
            "parser": f"ezdxf {ezdxf.__version__}",
            "spline_handle": spline.dxf.handle,
            "va_handle": rectangle.dxf.handle,
            "top_left_vertex": top_left,
            "top_right_vertex": top_right,
            "flattening_tolerance_mm": tolerance,
            "note": "Viewer-left; VA top-left origin, x right/y down. AA centering and physical fit still require verification."
        },
        "right_mirrors_left": True,
        "left_points_mm": points,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("dxf", type=Path)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--top-left", type=int, default=3)
    parser.add_argument("--top-right", type=int, default=2)
    parser.add_argument("--tolerance-mm", type=float, default=0.01)
    args = parser.parse_args()
    profile = convert(args.dxf, args.top_left, args.top_right, tolerance=args.tolerance_mm)
    args.output.write_text(json.dumps(profile, indent=2) + "\n", encoding="utf-8")
    print(f"Wrote {len(profile['left_points_mm'])} CAD boundary points to {args.output}")


if __name__ == "__main__":
    main()
