"""Pre-projected world map for the static site (no mapping library in the browser).

Natural Earth 1:50m countries (public domain, via world-atlas@2.0.2 TopoJSON) are
decoded, projected with Equal Earth (Šavrič, Patterson & Jenny 2018), simplified
with Douglas-Peucker in screen space and written as SVG path strings keyed by ISO3.
"""
from __future__ import annotations

import json
import math
from pathlib import Path

from .reference import REFERENCE_DIR, places

A1, A2, A3, A4 = 1.340264, -0.081106, 0.000893, 0.003796
M = math.sqrt(3) / 2
WIDTH = 1000.0
# Features without an ISO numeric code in world-atlas, matched by name.
NAME_TO_ISO3 = {"Kosovo": "XKX", "N. Cyprus": "CYP", "Somaliland": "SOM", "Siachen Glacier": "IND"}


def equal_earth(lon: float, lat: float) -> tuple[float, float]:
    lam, phi = math.radians(lon), math.radians(lat)
    theta = math.asin(M * math.sin(phi))
    t2 = theta * theta
    t6 = t2 * t2 * t2
    x = lam * math.cos(theta) / (M * (A1 + 3 * A2 * t2 + t6 * (7 * A3 + 9 * A4 * t2)))
    y = theta * (A1 + A2 * t2 + t6 * (A3 + A4 * t2))
    return x, y


X_MAX = equal_earth(180, 0)[0]
Y_MAX = equal_earth(0, 90)[1]
SCALE = WIDTH / (2 * X_MAX)
LAT_MIN = -58.0  # crop Antarctica and the far southern ocean
HEIGHT = (Y_MAX - equal_earth(0, LAT_MIN)[1]) * SCALE + 0.0


def to_screen(lon: float, lat: float) -> tuple[float, float]:
    x, y = equal_earth(lon, lat)
    return (x + X_MAX) * SCALE, (Y_MAX - y) * SCALE


def _decode_arcs(topology: dict) -> list[list[tuple[float, float]]]:
    sx, sy = topology["transform"]["scale"]
    tx, ty = topology["transform"]["translate"]
    arcs = []
    for arc in topology["arcs"]:
        x = y = 0
        points = []
        for dx, dy in arc:
            x += dx
            y += dy
            points.append((x * sx + tx, y * sy + ty))
        arcs.append(points)
    return arcs


def _ring(indices: list[int], arcs) -> list[tuple[float, float]]:
    points: list[tuple[float, float]] = []
    for index in indices:
        arc = arcs[index] if index >= 0 else list(reversed(arcs[~index]))
        points.extend(arc if not points else arc[1:])
    return points


def _clip(ring: list[tuple[float, float]], boundary: float, keep_below: bool) -> list[tuple[float, float]]:
    """Sutherland-Hodgman clip of a ring against the vertical line lon = boundary."""
    def inside(point):
        return point[0] <= boundary if keep_below else point[0] >= boundary

    def cross(a, b):
        t = (boundary - a[0]) / (b[0] - a[0])
        return boundary, a[1] + t * (b[1] - a[1])

    out: list[tuple[float, float]] = []
    for i, current in enumerate(ring):
        previous = ring[i - 1]
        if inside(current):
            if not inside(previous):
                out.append(cross(previous, current))
            out.append(current)
        elif inside(previous):
            out.append(cross(previous, current))
    return out


def split_antimeridian(ring: list[tuple[float, float]]) -> list[list[tuple[float, float]]]:
    """Rings that jump across +/-180 degrees are unwrapped, then cut into one piece per side."""
    if not any(abs(b[0] - a[0]) > 180 for a, b in zip(ring, ring[1:])):
        return [ring]
    unwrapped = [ring[0]]
    for lon, lat in ring[1:]:
        previous = unwrapped[-1][0]
        while lon - previous > 180:
            lon -= 360
        while lon - previous < -180:
            lon += 360
        unwrapped.append((lon, lat))
    pieces = []
    for shift in (-360.0, 0.0, 360.0):
        piece = [(lon + shift, lat) for lon, lat in unwrapped]
        piece = _clip(_clip(piece, -180.0, keep_below=False), 180.0, keep_below=True)
        if len(piece) >= 3:
            pieces.append(piece)
    return pieces


def _simplify(points: list[tuple[float, float]], tolerance: float) -> list[tuple[float, float]]:
    if len(points) < 4:
        return points
    if points[0] == points[-1]:
        # A closed ring has a zero-length baseline; split at the farthest vertex and simplify both halves.
        x0, y0 = points[0]
        far = max(range(len(points)), key=lambda i: (points[i][0] - x0) ** 2 + (points[i][1] - y0) ** 2)
        if far in (0, len(points) - 1):
            return points
        return _simplify(points[:far + 1], tolerance)[:-1] + _simplify(points[far:], tolerance)
    keep = [False] * len(points)
    keep[0] = keep[-1] = True
    stack = [(0, len(points) - 1)]
    while stack:
        start, end = stack.pop()
        (x1, y1), (x2, y2) = points[start], points[end]
        dx, dy = x2 - x1, y2 - y1
        norm = math.hypot(dx, dy) or 1e-12
        best, index = -1.0, -1
        for i in range(start + 1, end):
            px, py = points[i]
            distance = abs(dy * px - dx * py + x2 * y1 - y2 * x1) / norm
            if distance > best:
                best, index = distance, i
        if best > tolerance:
            keep[index] = True
            stack.extend([(start, index), (index, end)])
    return [p for p, k in zip(points, keep) if k]


def _area(ring: list[tuple[float, float]]) -> float:
    return 0.5 * sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]))


def _centroid(ring: list[tuple[float, float]]) -> tuple[float, float]:
    a = _area(ring)
    if abs(a) < 1e-9:
        xs, ys = zip(*ring)
        return sum(xs) / len(xs), sum(ys) / len(ys)
    cx = cy = 0.0
    for (x1, y1), (x2, y2) in zip(ring, ring[1:] + ring[:1]):
        cross = x1 * y2 - x2 * y1
        cx += (x1 + x2) * cross
        cy += (y1 + y2) * cross
    return cx / (6 * a), cy / (6 * a)


def build_map(tolerance: float = 0.35) -> dict:
    topology = json.loads((REFERENCE_DIR / "world-atlas-countries-50m.json").read_text())
    arcs = _decode_arcs(topology)
    numeric = {p.iso_numeric: p.iso3 for p in places().values() if p.iso_numeric}
    shapes: dict[str, dict] = {}
    for geometry in topology["objects"]["countries"]["geometries"]:
        name = geometry.get("properties", {}).get("name", "")
        iso3 = numeric.get(str(geometry.get("id", "")).zfill(3)) or NAME_TO_ISO3.get(name)
        if not iso3 or iso3 == "ATA":
            continue
        polygons = geometry["arcs"] if geometry["type"] == "MultiPolygon" else [geometry["arcs"]] if geometry["type"] == "Polygon" else []
        entry = shapes.setdefault(iso3, {"d": [], "area": 0.0, "largest": None, "largest_area": 0.0})
        for polygon in polygons:
            pieces = [(k, piece) for k, ring_indices in enumerate(polygon) for piece in split_antimeridian(_ring(ring_indices, arcs))]
            for k, piece in pieces:
                ring = [to_screen(lon, max(lat, LAT_MIN)) for lon, lat in piece]
                if all(y >= HEIGHT - 0.5 for _, y in ring):
                    continue
                simple = _simplify(ring, tolerance)
                if len(simple) < 4:
                    simple = _simplify(ring, tolerance / 8)  # tiny islands and city-states: finer tolerance
                if len(simple) < 3:
                    continue
                area = abs(_area(simple))
                if k > 0 and area < 0.05:
                    continue  # specks inside a country's outline (lakes, enclaves)
                entry["d"].append("M" + "L".join(f"{x:.1f},{y:.1f}" for x, y in simple) + "Z")
                if k == 0:
                    entry["area"] += area
                    if area > entry["largest_area"]:
                        entry["largest_area"], entry["largest"] = area, simple
    out = {}
    for iso3, entry in shapes.items():
        if not entry["d"]:
            continue
        cx, cy = _centroid(entry["largest"]) if entry["largest"] else (0, 0)
        out[iso3] = {"d": "".join(entry["d"]), "c": [round(cx, 1), round(cy, 1)], "a": round(entry["area"], 1)}
    return {"width": WIDTH, "height": round(HEIGHT, 1), "projection": "Equal Earth", "source": "Natural Earth 1:50m via world-atlas@2.0.2 (public domain)",
            "countries": out}


def point(lat: float, lon: float) -> list[float]:
    x, y = to_screen(lon, max(lat, LAT_MIN))
    return [round(x, 1), round(y, 1)]


def write_map(path: Path) -> dict:
    data = build_map()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, separators=(",", ":")))
    return data
