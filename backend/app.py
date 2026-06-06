from __future__ import annotations

import csv
import io
import json
import os
import secrets
import zipfile
import tempfile
from datetime import datetime
from flask import Flask, jsonify, request, send_from_directory, send_file

from services.db import init_db, save_memorial, get_memorial, increment_emission
from services.geo_utils import SUPPORTED_CRS, DEFAULT_OUTPUT_EPSG, DISPLAY_EPSG, reproject_coords, validate_coords, polygon_metrics, coords_to_geojson_polygon
from services.pdf_service import make_pdf

BASE_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
FRONTEND_DIR = os.path.join(BASE_DIR, "frontend")
OUTPUT_DIR = os.path.join(BASE_DIR, "outputs")

app = Flask(__name__, static_folder=FRONTEND_DIR, static_url_path="")
init_db()


@app.get("/")
def index():
    return send_from_directory(FRONTEND_DIR, "index.html")


@app.get("/exemplos/<path:filename>")
def exemplos(filename):
    return send_from_directory(os.path.join(BASE_DIR, "exemplos"), filename)

@app.get("/api/crs")
def crs_options():
    return jsonify(SUPPORTED_CRS)


@app.post("/api/parse/csv")
def parse_csv():
    file = request.files.get("file")
    input_crs = request.form.get("input_crs", "sirgas_utm_23s")
    if not file:
        return jsonify({"error": "Arquivo CSV não enviado."}), 400
    content = file.read().decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(content))
    rows = sorted(list(reader), key=lambda r: int(r.get("ordem", 0)))
    coords = [(float(r["x"].replace(",", ".")), float(r["y"].replace(",", "."))) for r in rows]
    return _process_coords(coords, input_crs, original_format="csv")


@app.post("/api/parse/geojson")
def parse_geojson():
    file = request.files.get("file")
    input_crs = request.form.get("input_crs", "sirgas_utm_23s")
    if not file:
        return jsonify({"error": "Arquivo GeoJSON não enviado."}), 400
    data = json.loads(file.read().decode("utf-8-sig"))
    geom = data.get("geometry", data)
    if data.get("type") == "FeatureCollection":
        geom = data["features"][0]["geometry"]
    if geom.get("type") != "Polygon":
        return jsonify({"error": "Nesta POC, envie um GeoJSON Polygon."}), 400
    coords = [(float(x), float(y)) for x, y in geom["coordinates"][0][:-1]]
    return _process_coords(coords, input_crs, original_format="geojson")


@app.post("/api/parse/shapefile")
def parse_shapefile():
    file = request.files.get("file")
    input_crs = request.form.get("input_crs", "sirgas_utm_23s")
    if not file:
        return jsonify({"error": "Shapefile ZIP não enviado."}), 400
    try:
        import shapefile  # pyshp
        with tempfile.TemporaryDirectory() as tmp:
            zip_path = os.path.join(tmp, "input.zip")
            file.save(zip_path)
            with zipfile.ZipFile(zip_path) as zf:
                zf.extractall(tmp)
            shp_files = [os.path.join(root, f) for root, _, files in os.walk(tmp) for f in files if f.lower().endswith(".shp")]
            if not shp_files:
                return jsonify({"error": "O ZIP não contém arquivo .shp."}), 400
            reader = shapefile.Reader(shp_files[0])
            shapes = reader.shapes()
            if not shapes:
                return jsonify({"error": "Shapefile sem feições."}), 400
            shp = shapes[0]
            if shp.shapeType not in [5, 15, 25, 31]:
                return jsonify({"error": "Nesta POC, envie shapefile de polígono."}), 400
            pts = shp.points
            if shp.parts:
                start = shp.parts[0]
                end = shp.parts[1] if len(shp.parts) > 1 else len(pts)
                pts = pts[start:end]
            coords = [(float(x), float(y)) for x, y in pts]
            if coords and coords[0] == coords[-1]:
                coords = coords[:-1]
            return _process_coords(coords, input_crs, original_format="shapefile")
    except Exception as exc:
        return jsonify({"error": f"Falha ao ler shapefile: {exc}"}), 400


@app.post("/api/process/manual")
def process_manual():
    body = request.get_json(force=True)
    coords = [(float(x), float(y)) for x, y in body["coords"]]
    input_crs = body.get("input_crs", "wgs84")
    return _process_coords(coords, input_crs, original_format="manual")


def _process_coords(coords, input_crs, original_format):
    validation = validate_coords(coords, input_crs)
    final_coords = reproject_coords(coords, input_crs, DEFAULT_OUTPUT_EPSG)
    display_coords = reproject_coords(coords, input_crs, DISPLAY_EPSG)
    metrics = polygon_metrics(final_coords)
    display_vertices = [{"nome": f"V{i+1}", "lon": x, "lat": y} for i, (x, y) in enumerate(display_coords)]
    return jsonify({
        "original_format": original_format,
        "input_crs": input_crs,
        "input_crs_label": SUPPORTED_CRS[input_crs]["label"],
        "src_saida_label": "SIRGAS 2000 / UTM 23S",
        "validation": validation,
        "coordenadas_originais": coords,
        "coordenadas_reprojetadas": final_coords,
        "metrics": metrics,
        "map_geojson": coords_to_geojson_polygon(display_coords),
        "display_vertices": display_vertices,
    })


@app.post("/api/memorial/emitir")
def emitir_memorial():
    body = request.get_json(force=True)
    protocolo = _new_protocol()
    chave = _new_key()
    payload = body | {
        "protocolo": protocolo,
        "chave_validacao": chave,
        "data_emissao": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "primeira_emissao": datetime.now().strftime("%d/%m/%Y %H:%M"),
        "emissao_atual": "1ª emissão",
    }
    pdf_path = os.path.join(OUTPUT_DIR, f"{protocolo}.pdf")
    make_pdf(payload, pdf_path)
    save_memorial(protocolo, chave, payload, pdf_path)
    return jsonify({
        "protocolo": protocolo,
        "chave_validacao": chave,
        "pdf_url": f"/api/memorial/download/{protocolo}/{chave}",
    })


@app.get("/api/memorial/download/<protocolo>/<chave>")
def download_memorial(protocolo, chave):
    item = get_memorial(protocolo, chave)
    if not item:
        return jsonify({"error": "Memorial não encontrado ou chave inválida."}), 404
    return send_file(item["pdf_path"], as_attachment=True, download_name=f"{protocolo}.pdf")


@app.post("/api/memorial/recuperar")
def recuperar_memorial():
    body = request.get_json(force=True)
    protocolo = body.get("protocolo")
    chave = body.get("chave_validacao")
    item = get_memorial(protocolo, chave)
    if not item:
        return jsonify({"error": "Memorial não encontrado ou chave inválida."}), 404
    return jsonify({
        "protocolo": item["protocolo"],
        "chave_validacao": item["chave_validacao"],
        "primeira_emissao": item["primeira_emissao"],
        "ultima_emissao": item["ultima_emissao"],
        "total_emissoes": item["total_emissoes"],
        "payload": item["payload"],
        "pdf_url": f"/api/memorial/download/{protocolo}/{chave}",
    })


@app.post("/api/memorial/reemitir")
def reemitir_memorial():
    body = request.get_json(force=True)
    protocolo = body.get("protocolo")
    chave = body.get("chave_validacao")
    item = get_memorial(protocolo, chave)
    if not item:
        return jsonify({"error": "Memorial não encontrado ou chave inválida."}), 404
    if item["total_emissoes"] >= 5:
        return jsonify({"error": "Limite de 5 emissões atingido."}), 400
    increment_emission(protocolo)
    return jsonify({"message": "Reemissão registrada.", "pdf_url": f"/api/memorial/download/{protocolo}/{chave}"})


def _new_protocol():
    year = datetime.now().year
    return f"MEM-{year}-{secrets.randbelow(999999):06d}"


def _new_key():
    return "-".join(secrets.token_hex(2).upper() for _ in range(3))


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
