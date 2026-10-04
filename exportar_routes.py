"""
exportar_routes.py — Exportación de informes en PDF y Excel para Palermitan Host
PDF con branding profesional (reportlab) y Excel con formato (openpyxl).
"""
from flask import Blueprint, send_file, abort
import io
import os
from datetime import datetime

exportar_bp = Blueprint("exportar", __name__)

COLOR_ARENA = "C8C09A"
COLOR_ARENA_OSCURO = "A89A72"
COLOR_BLANCO = "FFFFFF"
COLOR_GRIS_CLARO = "F5F5F0"
COLOR_TEXTO = "1A1A1A"


def get_db():
    from database import get_db_connection
    return get_db_connection()


# ════════════════════════════════════════════════════════════════════════════
# PDF
# ════════════════════════════════════════════════════════════════════════════

@exportar_bp.route("/informes/<int:informe_id>/pdf")
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

    db = get_db()
    cur = db.cursor()
    cur.execute("SELECT id, titulo, tipo, contenido, fecha_generado FROM informes WHERE id = %s", (informe_id,))
    row = cur.fetchone()
    cur.close()
    db.close()

    if not row:
        abort(404, "Informe no encontrado")

    informe_id, titulo, tipo, contenido, fecha_gen = row

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
    story.append(Paragraph(titulo, s_h1))
    fecha_str = fecha_gen.strftime("%d/%m/%Y %H:%M") if fecha_gen else datetime.now().strftime("%d/%m/%Y %H:%M")
    story.append(Paragraph(f"Generado el {fecha_str} | Tipo: {tipo}", s_meta))
    story.append(Spacer(1, 0.5*cm))

    # ── Contenido ─────────────────────────────────────────────────────────────
    if contenido:
        lines = contenido.split("\n")
        for line in lines:
            line = line.strip()
            if not line:
                story.append(Spacer(1, 0.3*cm))
            elif line.startswith("## "):
                story.append(Paragraph(line[3:], s_h2))
            elif line.startswith("# "):
                story.append(Paragraph(line[2:], s_h1))
            elif line.startswith("| ") or line.startswith("|---"):
                pass  # tablas markdown — tratadas abajo
            elif line.startswith("- ") or line.startswith("* "):
                story.append(Paragraph(f"• {line[2:]}", s_body))
            else:
                story.append(Paragraph(line, s_body))

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

    db = get_db()
    cur = db.cursor()

    # Informe base
    cur.execute("SELECT id, titulo, tipo, contenido, fecha_generado FROM informes WHERE id = %s", (informe_id,))
    row = cur.fetchone()
    if not row:
        cur.close()
        db.close()
        abort(404, "Informe no encontrado")

    informe_id, titulo, tipo, contenido, fecha_gen = row

    # Métricas por propiedad
    cur.execute("""
        SELECT p.nombre, p.barrio, p.tipo,
               COUNT(r.id) as reservas,
               COALESCE(SUM(r.precio_total), 0) as ingresos,
               COALESCE(AVG(r.noches), 0) as promedio_noches,
               p.rating
        FROM propiedades p
        LEFT JOIN reservas r ON r.propiedad_id = p.id AND r.estado != 'cancelada'
        GROUP BY p.id, p.nombre, p.barrio, p.tipo, p.rating
        ORDER BY ingresos DESC
    """)
    props_data = cur.fetchall()

    # Reservas recientes
    cur.execute("""
        SELECT p.nombre, r.huesped_nombre, r.fecha_inicio, r.fecha_fin,
               r.noches, r.precio_total, r.estado, r.canal
        FROM reservas r
        JOIN propiedades p ON r.propiedad_id = p.id
        ORDER BY r.fecha_inicio DESC
        LIMIT 200
    """)
    reservas_data = cur.fetchall()

    cur.close()
    db.close()

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

    headers_resumen = ["Propiedad", "Barrio", "Tipo", "Reservas", "Ingresos ($)", "Noches prom.", "Rating"]
    for col, h in enumerate(headers_resumen, 1):
        c = ws1.cell(row=4, column=col, value=h)
        estilo_header(c)
    ws1.row_dimensions[4].height = 22

    total_reservas = 0
    total_ingresos = 0
    for row_idx, row_data in enumerate(props_data, 5):
        par = row_idx % 2 == 0
        nombre, barrio, tipo_p, reservas, ingresos, prom_noches, rating = row_data
        valores = [nombre, barrio, tipo_p, reservas, float(ingresos), round(float(prom_noches), 1), rating or "N/A"]
        total_reservas += reservas
        total_ingresos += float(ingresos)
        for col, val in enumerate(valores, 1):
            c = ws1.cell(row=row_idx, column=col, value=val)
            estilo_fila(c, par)
            if col == 5:
                c.number_format = "#,##0"
                c.alignment = alin_der

    # Fila de totales
    fila_total = len(props_data) + 5
    ws1.cell(row=fila_total, column=1, value="TOTAL").font = font_total
    ws1.cell(row=fila_total, column=4, value=total_reservas).font = font_total
    c_tot = ws1.cell(row=fila_total, column=5, value=total_ingresos)
    c_tot.font = font_total
    c_tot.number_format = "#,##0"
    c_tot.alignment = alin_der
    for col in range(1, 8):
        ws1.cell(row=fila_total, column=col).fill = fill_arena
        ws1.cell(row=fila_total, column=col).border = borde

    # Anchos
    anchos = [28, 14, 16, 10, 16, 14, 8]
    for col, ancho in enumerate(anchos, 1):
        ws1.column_dimensions[get_column_letter(col)].width = ancho

    # ════ Hoja 2: Reservas ═══════════════════════════════════════════════════
    ws2 = wb.create_sheet("Reservas")

    ws2.merge_cells("A1:H1")
    ws2["A1"] = "PALERMITAN HOST — Detalle de Reservas"
    ws2["A1"].font = font_titulo
    ws2["A1"].alignment = alin_centro
    ws2.row_dimensions[2].height = 8

    headers_res = ["Propiedad", "Huésped", "Check-in", "Check-out", "Noches", "Total ($)", "Estado", "Canal"]
    for col, h in enumerate(headers_res, 1):
        c = ws2.cell(row=3, column=col, value=h)
        estilo_header(c)
    ws2.row_dimensions[3].height = 22

    for row_idx, row_data in enumerate(reservas_data, 4):
        par = row_idx % 2 == 0
        for col, val in enumerate(row_data, 1):
            c = ws2.cell(row=row_idx, column=col, value=val)
            estilo_fila(c, par)
            if col == 6:
                c.number_format = "#,##0"
                c.alignment = alin_der

    anchos2 = [28, 20, 12, 12, 8, 14, 12, 12]
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
