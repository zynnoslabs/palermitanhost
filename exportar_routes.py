"""
exportar_routes.py — Exportación de informes en PDF y Excel para Palermitan Host
PDF con branding profesional (reportlab) y Excel con formato (openpyxl).
"""
from flask import Blueprint, send_file, abort, session, redirect, url_for
from functools import wraps
import io
import os
import re
from datetime import datetime

exportar_bp = Blueprint("exportar", __name__)

COLOR_ARENA = "C8C09A"
COLOR_ARENA_OSCURO = "A89A72"
COLOR_BLANCO = "FFFFFF"
COLOR_GRIS_CLARO = "F5F5F0"
COLOR_TEXTO = "1A1A1A"


def _seguro(v):
    """### CAMBIO AQUÍ ### un texto que empieza con = + - @ Excel lo ejecutaría como fórmula."""
    if isinstance(v, str) and v[:1] in ("=", "+", "-", "@"):
        return "'" + v
    return v


def _xml(texto):
    """Texto seguro para reportlab."""
    from xml.sax.saxutils import escape
    return escape(str(texto or ""))


def _md(texto):
    """**negrita** → <b>negrita</b>, con el resto escapado."""
    return re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", _xml(texto)).replace("*", "")


def get_db():
    from database import get_db_connection
    return get_db_connection()


def _release(conn):
    from database import release_db
    release_db(conn)


# ### CAMBIO AQUÍ ### — antes cualquiera sin login podía descargar los informes
def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get("logged_in"):
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated


# ════════════════════════════════════════════════════════════════════════════
# PDF
# ════════════════════════════════════════════════════════════════════════════

@exportar_bp.route("/informes/<int:informe_id>/pdf")
@login_required
def exportar_pdf(informe_id):
    """Genera y devuelve un PDF profesional del informe."""
    try:
        from reportlab.lib.pagesizes import A4
        from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
        from reportlab.lib.units import cm
        from reportlab.lib import colors
        from reportlab.platypus import (
            SimpleDocTemplate, Paragraph, Spacer,
            Table, TableStyle, HRFlowable, KeepTogether
        )
        from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
    except ImportError:
        abort(500, "reportlab no está instalado")

    import database as _db
    # ### CAMBIO AQUÍ ### consulta con devolución segura de la conexión (antes un error la dejaba tomada)
    row = _db.query_one("SELECT id, titulo, tipo, contenido, fecha_generado FROM informes WHERE id = %s", (informe_id,))
    if not row:
        abort(404, "Informe no encontrado")

    informe_id, titulo, tipo, contenido, fecha_gen = (row["id"], row["titulo"], row["tipo"],
                                                      row["contenido"], row["fecha_generado"])

    # ── Colores ──────────────────────────────────────────────────────────────
    c_arena = colors.HexColor(f"#{COLOR_ARENA}")
    c_arena_osc = colors.HexColor(f"#{COLOR_ARENA_OSCURO}")
    c_gris = colors.HexColor(f"#{COLOR_GRIS_CLARO}")
    c_texto = colors.HexColor(f"#{COLOR_TEXTO}")

    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=2.5*cm, rightMargin=2.5*cm,
        topMargin=2*cm, bottomMargin=2*cm,
        title=titulo,
        author="Palermitan Host",
    )

    styles = getSampleStyleSheet()

    s_titulo_marca = ParagraphStyle(
        "TituloMarca", fontName="Helvetica-Bold",
        fontSize=18, textColor=c_texto, alignment=TA_CENTER, spaceAfter=4
    )
    s_subtitulo_marca = ParagraphStyle(
        "SubtituloMarca", fontName="Helvetica",
        fontSize=10, textColor=c_arena_osc, alignment=TA_CENTER, spaceAfter=2
    )
    s_h1 = ParagraphStyle(
        "H1PH", fontName="Helvetica-Bold",
        fontSize=14, textColor=c_texto, spaceBefore=16, spaceAfter=8
    )
    s_h2 = ParagraphStyle(
        "H2PH", fontName="Helvetica-Bold",
        fontSize=11, textColor=c_arena_osc, spaceBefore=12, spaceAfter=6
    )
    s_body = ParagraphStyle(
        "BodyPH", fontName="Helvetica",
        fontSize=10, textColor=c_texto, leading=15, spaceAfter=6
    )
    s_meta = ParagraphStyle(
        "MetaPH", fontName="Helvetica",
        fontSize=8, textColor=colors.grey, alignment=TA_CENTER
    )

    story = []

    # ── Header de marca ───────────────────────────────────────────────────────
    story.append(Paragraph("PALERMITAN HOST", s_titulo_marca))
    story.append(Paragraph("★★★★★", s_subtitulo_marca))
    story.append(HRFlowable(width="100%", thickness=1.5, color=c_arena, spaceAfter=12))
    story.append(Paragraph(_xml(titulo), s_h1))
    fecha_str = fecha_gen.strftime("%d/%m/%Y %H:%M") if fecha_gen else datetime.now().strftime("%d/%m/%Y %H:%M")
    story.append(Paragraph(f"Generado el {fecha_str}", s_meta))
    story.append(Spacer(1, 0.5*cm))

    # ── Contenido ─────────────────────────────────────────────────────────────
    # ### CAMBIO AQUÍ ### el texto de la IA se "escapa" (un "<" rompía el PDF), las **negritas** se ven
    # como negrita y las tablas se muestran como filas de texto (antes desaparecían)
    if contenido:
        for line in contenido.split("\n"):
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.3*cm))
            elif re.match(r"^\|?\s*:?-{3,}", line):
                continue   # separador de tabla markdown
            elif line.startswith("|"):
                celdas = [c.strip() for c in line.strip("|").split("|")]
                story.append(Paragraph(_md(" · ".join(c for c in celdas if c)), s_body))
            elif line.startswith("#"):
                nivel = len(line) - len(line.lstrip("#"))
                story.append(Paragraph(_md(line.lstrip("#").strip()), s_h1 if nivel == 1 else s_h2))
            elif line.startswith(("- ", "* ", "• ")):
                story.append(Paragraph(f"• {_md(line[2:])}", s_body))
            else:
                story.append(Paragraph(_md(line), s_body))

    story.append(Spacer(1, 1*cm))
    story.append(HRFlowable(width="100%", thickness=0.5, color=c_arena, spaceBefore=12))
    story.append(Paragraph("Palermitan Host — Sistema de gestión de alquileres temporarios", s_meta))

    doc.build(story)
    buf.seek(0)

    nombre_archivo = f"informe_{informe_id}_{datetime.now().strftime('%Y%m%d')}.pdf"
    return send_file(
        buf,
        mimetype="application/pdf",
        as_attachment=True,
        download_name=nombre_archivo,
    )


# ════════════════════════════════════════════════════════════════════════════
# EXCEL
# ════════════════════════════════════════════════════════════════════════════

@exportar_bp.route("/informes/<int:informe_id>/excel")
@login_required
def exportar_excel(informe_id):
    """Genera y devuelve un Excel profesional del informe."""
    try:
        from openpyxl import Workbook
        from openpyxl.styles import (
            Font, Fill, PatternFill, Alignment, Border, Side, numbers
        )
        from openpyxl.utils import get_column_letter
    except ImportError:
        abort(500, "openpyxl no está instalado")

    import database as _db
    import metricas
    inf = _db.query_one("SELECT * FROM informes WHERE id = %s", (informe_id,))
    if not inf:
        abort(404, "Informe no encontrado")
    titulo, contenido, fecha_gen = inf["titulo"], inf["contenido"], inf["fecha_generado"]

    # ### CAMBIO AQUÍ ### el Excel usa el MISMO período y propiedad del informe (antes exportaba todo
    # el historial) y separa pesos de dólares (antes los sumaba juntos)
    desde = inf.get("fecha_desde") or "2000-01-01"
    hasta = inf.get("fecha_hasta") or datetime.now().date().isoformat()
    pid = inf.get("propiedad_id")
    props = _db.query("SELECT * FROM propiedades" + (" WHERE id=%s" if pid else "") + " ORDER BY nombre",
                      (pid,) if pid else ())
    reservas = metricas.filtrar_reservas(_db.query("SELECT * FROM reservas"), desde, hasta, pid)
    props_data = []
    for p in props:
        for mon in ("ARS", "USD"):
            sel = [r for r in reservas if r["propiedad_id"] == p["id"] and (r.get("moneda") or "ARS") == mon]
            if not sel:
                continue
            m = metricas.calcular_metricas(sel, desde, hasta)
            props_data.append((p["nombre"], p.get("barrio") or "", mon, m["total_reservas"], m["noches_ocupadas"],
                               m["ingreso_bruto"], m["ingreso_neto"], m["canceladas"]))
    nombres = {p["id"]: p["nombre"] for p in props}
    reservas_data = [(nombres.get(r["propiedad_id"], ""), r.get("huesped_nombre") or "",
                      metricas._parse(r.get("fecha_inicio")), metricas._parse(r.get("fecha_fin")), r.get("noches"),
                      r.get("moneda") or "ARS", r.get("ingreso_bruto") or 0, r.get("ingreso_neto") or 0,
                      r.get("estado") or "completada")
                     for r in sorted(reservas, key=lambda x: str(x.get("fecha_inicio")), reverse=True)]

    wb = Workbook()

    # ── Estilos ───────────────────────────────────────────────────────────────
    fill_arena = PatternFill("solid", fgColor=COLOR_ARENA)
    fill_arena_osc = PatternFill("solid", fgColor=COLOR_ARENA_OSCURO)
    fill_gris = PatternFill("solid", fgColor="F0EDE4")
    fill_blanco = PatternFill("solid", fgColor="FFFFFF")

    font_header = Font(name="Calibri", bold=True, color="FFFFFF", size=11)
    font_titulo = Font(name="Calibri", bold=True, color=COLOR_ARENA_OSCURO, size=14)
    font_normal = Font(name="Calibri", size=10)
    font_total = Font(name="Calibri", bold=True, size=11)

    alin_centro = Alignment(horizontal="center", vertical="center")
    alin_izq = Alignment(horizontal="left", vertical="center")
    alin_der = Alignment(horizontal="right", vertical="center")

    borde = Border(
        left=Side(style="thin", color="D0C8A8"),
        right=Side(style="thin", color="D0C8A8"),
        top=Side(style="thin", color="D0C8A8"),
        bottom=Side(style="thin", color="D0C8A8"),
    )

    def estilo_header(cell):
        cell.fill = fill_arena_osc
        cell.font = font_header
        cell.alignment = alin_centro
        cell.border = borde

    def estilo_fila(cell, par=True):
        cell.fill = fill_gris if par else fill_blanco
        cell.font = font_normal
        cell.alignment = alin_izq
        cell.border = borde

    # ════ Hoja 1: Resumen ════════════════════════════════════════════════════
    ws1 = wb.active
    ws1.title = "Resumen"

    ws1.merge_cells("A1:G1")
    ws1["A1"] = "PALERMITAN HOST — " + titulo
    ws1["A1"].font = font_titulo
    ws1["A1"].alignment = alin_centro

    ws1["A2"] = f"Generado: {(fecha_gen or datetime.now()).strftime('%d/%m/%Y %H:%M')}"
    ws1["A2"].font = Font(name="Calibri", italic=True, color="888888", size=9)

    ws1.row_dimensions[3].height = 8  # espaciado

    ws1["A3"] = f"Período: {metricas._parse(desde).strftime('%d/%m/%Y')} al {metricas._parse(hasta).strftime('%d/%m/%Y')}"
    ws1["A3"].font = Font(name="Calibri", italic=True, color="888888", size=9)
    headers_resumen = ["Propiedad", "Barrio", "Moneda", "Reservas", "Noches", "Ingreso bruto", "Ingreso neto", "Canceladas"]
    for col, h in enumerate(headers_resumen, 1):
        estilo_header(ws1.cell(row=4, column=col, value=h))
    ws1.row_dimensions[4].height = 22
    fila = 5
    for row_data in props_data:
        for col, val in enumerate(row_data, 1):
            c = ws1.cell(row=fila, column=col, value=_seguro(val))
            estilo_fila(c, fila % 2 == 0)
            if col in (6, 7):
                c.number_format = "#,##0.00"
                c.alignment = alin_der
        fila += 1
    for mon in ("ARS", "USD"):   # un total por moneda
        filas_m = [r for r in props_data if r[2] == mon]
        if not filas_m:
            continue
        valores = ["TOTAL " + ("PESOS" if mon == "ARS" else "DÓLARES"), "", mon, sum(r[3] for r in filas_m),
                   sum(r[4] for r in filas_m), sum(r[5] for r in filas_m), sum(r[6] for r in filas_m),
                   sum(r[7] for r in filas_m)]
        for col, val in enumerate(valores, 1):
            c = ws1.cell(row=fila, column=col, value=val)
            c.font = font_total
            c.fill = fill_arena
            c.border = borde
            if col in (6, 7):
                c.number_format = "#,##0.00"
                c.alignment = alin_der
        fila += 1
    if not props_data:
        ws1.cell(row=5, column=1, value="Sin reservas en el período.")

    for col, ancho in enumerate([28, 16, 9, 10, 9, 16, 16, 11], 1):
        ws1.column_dimensions[get_column_letter(col)].width = ancho

    # ════ Hoja 2: Reservas ═══════════════════════════════════════════════════
    ws2 = wb.create_sheet("Reservas")

    ws2.merge_cells("A1:I1")
    ws2["A1"] = "PALERMITAN HOST — Detalle de Reservas"
    ws2["A1"].font = font_titulo
    ws2["A1"].alignment = alin_centro
    ws2.row_dimensions[2].height = 8

    headers_res = ["Propiedad", "Huésped", "Check-in", "Check-out", "Noches", "Moneda", "Bruto", "Neto", "Estado"]
    for col, h in enumerate(headers_res, 1):
        c = ws2.cell(row=3, column=col, value=h)
        estilo_header(c)
    ws2.row_dimensions[3].height = 22

    for row_idx, row_data in enumerate(reservas_data, 4):
        par = row_idx % 2 == 0
        for col, val in enumerate(row_data, 1):
            c = ws2.cell(row=row_idx, column=col, value=_seguro(val))
            estilo_fila(c, par)
            if col in (3, 4) and val:
                c.number_format = "DD/MM/YYYY"
            if col in (7, 8):
                c.number_format = "#,##0.00"
                c.alignment = alin_der

    # ════ Hoja 3: el texto del informe ══════════════════════════════════════
    ws3 = wb.create_sheet("Informe")
    ws3.column_dimensions["A"].width = 120
    for i, linea in enumerate((contenido or "").split("\n"), 1):
        c = ws3.cell(row=i, column=1, value=_seguro(linea.replace("**", "").lstrip("#").strip()) or None)
        c.alignment = Alignment(wrap_text=True, vertical="top")
        if linea.startswith("#"):
            c.font = font_titulo

    anchos2 = [28, 20, 12, 12, 8, 9, 14, 14, 12]
    for col, ancho in enumerate(anchos2, 1):
        ws2.column_dimensions[get_column_letter(col)].width = ancho

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)

    nombre_archivo = f"informe_{informe_id}_{datetime.now().strftime('%Y%m%d')}.xlsx"
    return send_file(
        buf,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name=nombre_archivo,
    )
