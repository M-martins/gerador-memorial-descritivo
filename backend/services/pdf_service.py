from __future__ import annotations
import os
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.graphics.shapes import Drawing, Polygon as RLPolygon, String, Line, Circle


def make_pdf(payload: dict, output_path: str):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    doc = SimpleDocTemplate(
        output_path,
        pagesize=A4,
        rightMargin=1.5 * cm,
        leftMargin=1.5 * cm,
        topMargin=1.2 * cm,
        bottomMargin=1.2 * cm,
    )
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name="TitleCenter", parent=styles["Title"], alignment=1, fontSize=18, spaceAfter=10))
    styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontSize=8, leading=10))
    styles.add(ParagraphStyle(name="Justify", parent=styles["BodyText"], alignment=4, leading=14))
    story = []

    imovel = payload["dados_imovel"]
    metrics = payload["metrics"]

    story.append(Paragraph("MEMORIAL DESCRITIVO", styles["TitleCenter"]))
    resumo = [
        ["Protocolo", payload["protocolo"], "Chave", payload["chave_validacao"]],
        ["Proprietário", imovel.get("proprietario", ""), "Município", imovel.get("municipio", "")],
        ["Quadra", imovel.get("quadra", ""), "Lote", imovel.get("lote", "")],
        ["Área calculada", f"{float(metrics['area_m2']):,.2f} m²".replace(',', 'X').replace('.', ',').replace('X', '.'), "Perímetro", f"{float(metrics['perimetro_m']):,.2f} m".replace(',', 'X').replace('.', ',').replace('X', '.')],
        ["SRC de saída", payload.get("src_saida_label", "SIRGAS 2000 / UTM 23S"), "Emissão", payload.get("data_emissao", "")],
    ]
    story.append(_table(resumo, col_widths=[3.2 * cm, 6 * cm, 3 * cm, 5.5 * cm]))
    story.append(Spacer(1, 0.4 * cm))

    story.append(_make_croqui_drawing(metrics["vertices"]))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph("Confrontações resumidas", styles["Heading3"]))
    conf_rows = [["Face", "Tipo", "Descrição"]] + [
        [c["face"], _tipo_label(c), c["descricao"]] for c in payload["confrontacoes"]
    ]
    story.append(_table(conf_rows, header=True))
    story.append(Spacer(1, 0.2 * cm))
    story.append(Paragraph(
        "Documento gerado automaticamente a partir das informações fornecidas pelo usuário. "
        "Cabe ao responsável técnico a conferência e validação do conteúdo antes da utilização oficial.",
        styles["Small"],
    ))

    story.append(PageBreak())
    story.append(Paragraph("Descrição do imóvel", styles["Heading2"]))
    story.append(Paragraph(_build_memorial_text(payload), styles["Justify"]))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Histórico de emissões", styles["Heading3"]))
    story.append(Paragraph(
        f"Primeira emissão: {payload.get('primeira_emissao', payload.get('data_emissao', ''))}<br/>"
        f"Emissão atual: {payload.get('emissao_atual', '1ª emissão')}",
        styles["Normal"],
    ))

    story.append(PageBreak())
    story.append(Paragraph("Quadro de coordenadas", styles["Heading2"]))
    v_rows = [["Vértice", "E/X", "N/Y"]] + [
        [v["nome"], f"{float(v['x']):.3f}", f"{float(v['y']):.3f}"] for v in metrics["vertices"]
    ]
    story.append(_table(v_rows, header=True))
    story.append(Spacer(1, 0.5 * cm))
    story.append(Paragraph("Quadro de azimutes e distâncias", styles["Heading2"]))
    f_rows = [["Face", "Azimute", "Distância (m)"]] + [
        [f["id"], f["azimute_dms"], f"{float(f['distancia_m']):.3f}"] for f in metrics["faces"]
    ]
    story.append(_table(f_rows, header=True))

    doc.build(story)


def _tipo_label(c: dict) -> str:
    if c.get("tipo") == "Outro" and c.get("tipo_outro"):
        return f"Outro - {c.get('tipo_outro')}"
    return c.get("tipo", "")


def _table(rows, header=False, col_widths=None):
    t = Table(rows, colWidths=col_widths, hAlign="LEFT")
    style = [
        ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#c9d1d9")),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("FONTNAME", (0, 0), (-1, -1), "Helvetica"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#eef3f8") if header else colors.white),
    ]
    t.setStyle(TableStyle(style))
    return t


def _make_croqui_drawing(vertices):
    # Desenha direto como vetor no PDF. Não usa renderPM/PNG, evitando erro rlPyCairo no Windows.
    width, height = 15 * cm, 10 * cm
    xs = [float(v["x"]) for v in vertices]
    ys = [float(v["y"]) for v in vertices]
    minx, maxx, miny, maxy = min(xs), max(xs), min(ys), max(ys)
    pad = 35
    scale = min((width - 2 * pad) / (maxx - minx or 1), (height - 2 * pad) / (maxy - miny or 1))
    pts = []
    xy_by_name = {}
    for v in vertices:
        x = pad + (float(v["x"]) - minx) * scale
        y = height - (pad + (float(v["y"]) - miny) * scale)
        pts.extend([x, y])
        xy_by_name[v["nome"]] = (x, y)
    d = Drawing(width, height)
    d.add(RLPolygon(pts, strokeColor=colors.HexColor("#1f4e79"), fillColor=colors.HexColor("#eaf3ff"), strokeWidth=2))
    for v in vertices:
        x, y = xy_by_name[v["nome"]]
        d.add(Circle(x, y, 4, strokeColor=colors.HexColor("#1f4e79"), fillColor=colors.white, strokeWidth=1))
        d.add(String(x + 6, y + 6, v["nome"], fontSize=9, fillColor=colors.HexColor("#1f4e79")))
    # norte simples
    d.add(Line(width - 45, 70, width - 45, 30, strokeColor=colors.black, strokeWidth=1.5))
    d.add(String(width - 50, 76, "N", fontSize=12))
    return d


def _build_memorial_text(payload: dict) -> str:
    imovel = payload["dados_imovel"]
    metrics = payload["metrics"]
    face_by_id = {c["face"]: c for c in payload["confrontacoes"]}
    area = f"{float(metrics['area_m2']):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    per = f"{float(metrics['perimetro_m']):,.2f}".replace(',', 'X').replace('.', ',').replace('X', '.')
    txt = (
        f"O imóvel de propriedade de {imovel.get('proprietario')}, situado no município de {imovel.get('municipio')}, "
        f"identificado como Quadra {imovel.get('quadra')} e Lote {imovel.get('lote')}, possui área calculada de "
        f"{area} m² e perímetro de {per} m. "
        f"A descrição foi elaborada no sistema de referência {payload.get('src_saida_label', 'SIRGAS 2000 / UTM 23S')}.<br/><br/>"
    )
    if imovel.get("area_declarada"):
        txt += f"Área declarada informada pelo usuário: {imovel.get('area_declarada')} m².<br/><br/>"
    txt += "Inicia-se a descrição deste perímetro no vértice V1. "
    for f in metrics["faces"]:
        c = face_by_id.get(f["id"], {})
        dist = f"{float(f['distancia_m']):,.3f}".replace(',', 'X').replace('.', ',').replace('X', '.')
        txt += (
            f"Do vértice {f['origem']} segue até o vértice {f['destino']}, com azimute de {f['azimute_dms']} "
            f"e distância de {dist} m, confrontando com {c.get('descricao', '')} "
            f"({_tipo_label(c)}). "
        )
    txt += "Assim fecha-se o perímetro descrito."
    return txt
