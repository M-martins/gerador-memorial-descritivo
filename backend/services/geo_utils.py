from __future__ import annotations

import math
from typing import Dict, List, Tuple
from pyproj import Transformer
from shapely.geometry import Polygon
from shapely.validation import explain_validity

DEFAULT_OUTPUT_EPSG = 31983  # SIRGAS 2000 / UTM zone 23S
DISPLAY_EPSG = 4326          # WGS84 lat/lon para Leaflet

SUPPORTED_CRS = {
    "sirgas_utm_23s": {"label": "SIRGAS 2000 / UTM 23S", "epsg": 31983},
    "wgs84": {"label": "WGS84 Latitude/Longitude", "epsg": 4326},
    "sad69_utm_23s": {"label": "SAD69 / UTM 23S", "epsg": 29183},
    "corrego_alegre_utm_23s": {"label": "Córrego Alegre / UTM 23S", "epsg": 22523},
}


def close_ring(coords: List[Tuple[float, float]]) -> List[Tuple[float, float]]:
    if not coords:
        return coords
    return coords if coords[0] == coords[-1] else coords + [coords[0]]


def reproject_coords(coords: List[Tuple[float, float]], input_key: str, output_epsg: int = DEFAULT_OUTPUT_EPSG) -> List[Tuple[float, float]]:
    if input_key not in SUPPORTED_CRS:
        raise ValueError(f"Sistema de coordenadas não suportado: {input_key}")
    input_epsg = SUPPORTED_CRS[input_key]["epsg"]
    if input_epsg == output_epsg:
        return [(float(x), float(y)) for x, y in coords]
    transformer = Transformer.from_crs(input_epsg, output_epsg, always_xy=True)
    return [transformer.transform(float(x), float(y)) for x, y in coords]


def coords_to_geojson_polygon(coords: List[Tuple[float, float]]) -> Dict:
    ring = close_ring(coords)
    return {"type": "Polygon", "coordinates": [[list(c) for c in ring]]}


def validate_coords(coords: List[Tuple[float, float]], input_key: str) -> Dict:
    issues = []
    level = "green"

    if len(coords) < 3:
        return {"level": "red", "messages": ["Informe pelo menos 3 vértices para formar um polígono."]}

    xs = [c[0] for c in coords]
    ys = [c[1] for c in coords]
    looks_latlon = all(-180 <= x <= 180 for x in xs) and all(-90 <= y <= 90 for y in ys)
    looks_utm = all(100000 <= x <= 900000 for x in xs) and all(6000000 <= y <= 10000000 for y in ys)

    if input_key == "wgs84" and not looks_latlon:
        level = "red"
        issues.append("O sistema escolhido é latitude/longitude, mas os valores não parecem graus decimais.")
    if input_key != "wgs84" and looks_latlon:
        level = "red"
        issues.append("Os valores parecem latitude/longitude, mas o sistema escolhido é projetado/UTM.")
    if input_key != "wgs84" and not looks_utm:
        level = "red" if level == "red" else "yellow"
        issues.append("Os valores não parecem estar na faixa típica de coordenadas UTM para o Brasil.")

    try:
        final = reproject_coords(coords, input_key, DEFAULT_OUTPUT_EPSG)
        poly = Polygon(close_ring(final))
        if not poly.is_valid:
            level = "red"
            issues.append(f"A geometria resultante não é válida: {explain_validity(poly)}.")
        if poly.area <= 0:
            level = "red"
            issues.append("Área calculada igual ou menor que zero. Verifique a ordem dos vértices ou cruzamentos.")
        if poly.area > 10_000_000:
            level = "yellow" if level != "red" else level
            issues.append("Área muito grande para um lote. Confirme se o sistema de coordenadas está correto.")

        display = reproject_coords(coords, input_key, DISPLAY_EPSG)
        lon = sum(x for x, _ in display) / len(display)
        lat = sum(y for _, y in display) / len(display)
        if not (-75 <= lon <= -30 and -35 <= lat <= 7):
            level = "yellow" if level != "red" else level
            issues.append("A geometria não parece cair no território brasileiro após a reprojeção. Confirme o SRC informado.")
    except Exception as exc:
        level = "red"
        issues.append(f"Falha ao reprojetar/validar coordenadas: {exc}")

    if not issues:
        issues.append("Coordenadas compatíveis com o sistema informado.")
    return {"level": level, "messages": issues}


def polygon_metrics(final_coords: List[Tuple[float, float]]) -> Dict:
    ring = close_ring(final_coords)
    poly = Polygon(ring)
    vertices = [{"nome": f"V{i+1}", "x": round(x, 3), "y": round(y, 3)} for i, (x, y) in enumerate(ring[:-1])]
    faces = []
    for i in range(len(vertices)):
        a = vertices[i]
        b = vertices[(i + 1) % len(vertices)]
        dx = b["x"] - a["x"]
        dy = b["y"] - a["y"]
        dist = math.hypot(dx, dy)
        az = math.degrees(math.atan2(dx, dy))
        if az < 0:
            az += 360
        faces.append({
            "id": f"{a['nome']}-{b['nome']}",
            "origem": a["nome"],
            "destino": b["nome"],
            "distancia_m": round(dist, 3),
            "azimute_decimal": round(az, 6),
            "azimute_dms": decimal_to_dms(az),
        })
    return {
        "area_m2": round(poly.area, 2),
        "perimetro_m": round(poly.length, 2),
        "vertices": vertices,
        "faces": faces,
        "geojson": coords_to_geojson_polygon(ring),
    }


def decimal_to_dms(deg: float) -> str:
    d = int(deg)
    m_float = (deg - d) * 60
    m = int(m_float)
    s = round((m_float - m) * 60, 2)
    return f"{d}°{m:02d}'{s:05.2f}\""
