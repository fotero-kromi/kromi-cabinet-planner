"""kromi_app.presentation — render a KROMI-branded plan deck (.pptx).

Builds the slides from the pure content model in engine.deck, in the KROMI house
style observed in the corporate decks: white background, dark/bright green stat
cards with big white numbers, the green KROMI logo top-right, MetaOT fonts.

This module does I/O (python-pptx) and is intentionally kept out of the pure
engine. v1 produces a cover slide + a plan-summary stat-card slide; the per-
supply-point machine line-up elevation is a planned follow-up.
"""

from __future__ import annotations

import os
from io import BytesIO

from PIL import Image
from pptx import Presentation
from pptx.dml.color import RGBColor
from pptx.enum.shapes import MSO_SHAPE
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.util import Inches, Pt

from engine.deck import (
    KROMI_BODY_FONT,
    KROMI_GREEN_BRIGHT,
    KROMI_GREEN_DARK,
    KROMI_GREEN_MINT,
    KROMI_HEADER_FONT,
    DeckStats,
    cover_lines,
    lineup_total_width_mm,
    lineup_units,
    summary_pyramid,
    summary_subtitle,
)

_DARK = RGBColor.from_string(KROMI_GREEN_DARK)
_BRIGHT = RGBColor.from_string(KROMI_GREEN_BRIGHT)
_MINT = RGBColor.from_string(KROMI_GREEN_MINT)
_WHITE = RGBColor.from_string("FFFFFF")
_GREY = RGBColor.from_string("808080")
_DARKGREY = RGBColor.from_string("3A3A3A")

_SLIDE_W = Inches(13.333)
_SLIDE_H = Inches(7.5)


def _set_font(run, name: str, size: int, color: RGBColor, bold: bool = False) -> None:
    run.font.name = name
    run.font.size = Pt(size)
    run.font.color.rgb = color
    run.font.bold = bold


def _add_text(slide, left, top, width, height, lines, align=PP_ALIGN.LEFT, anchor=MSO_ANCHOR.TOP):
    """lines: list of (text, font_name, size, color, bold) -> each its own paragraph."""
    box = slide.shapes.add_textbox(left, top, width, height)
    tf = box.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = anchor
    for i, (text, name, size, color, bold) in enumerate(lines):
        para = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
        para.alignment = align
        run = para.add_run()
        run.text = text
        _set_font(run, name, size, color, bold)
    return box


def _add_logo(slide, logo_path: str) -> None:
    if logo_path and os.path.exists(logo_path):
        # 591x187 aspect; height 0.85" -> width ~2.69"
        slide.shapes.add_picture(
            logo_path, _SLIDE_W - Inches(3.0), Inches(0.35), height=Inches(0.85)
        )


def _add_footer(slide, date_str: str, page: int) -> None:
    _add_text(
        slide,
        Inches(0.5),
        _SLIDE_H - Inches(0.5),
        Inches(5),
        Inches(0.4),
        [(date_str or "", KROMI_BODY_FONT, 10, _GREY, False)],
    )
    _add_text(
        slide,
        _SLIDE_W - Inches(1.2),
        _SLIDE_H - Inches(0.5),
        Inches(0.7),
        Inches(0.4),
        [(str(page), KROMI_BODY_FONT, 10, _GREY, False)],
        align=PP_ALIGN.RIGHT,
    )


def _add_card(slide, left, top, width, height, value, label, dark: bool) -> None:
    shape = slide.shapes.add_shape(MSO_SHAPE.ROUNDED_RECTANGLE, left, top, width, height)
    shape.fill.solid()
    shape.fill.fore_color.rgb = _DARK if dark else _BRIGHT
    shape.line.fill.background()
    shape.shadow.inherit = False
    tf = shape.text_frame
    tf.word_wrap = True
    tf.vertical_anchor = MSO_ANCHOR.MIDDLE
    p_num = tf.paragraphs[0]
    p_num.alignment = PP_ALIGN.CENTER
    r_num = p_num.add_run()
    r_num.text = value
    _set_font(r_num, KROMI_HEADER_FONT, 40, _WHITE, True)
    p_lab = tf.add_paragraph()
    p_lab.alignment = PP_ALIGN.CENTER
    r_lab = p_lab.add_run()
    r_lab.text = label
    _set_font(r_lab, KROMI_BODY_FONT, 14, _WHITE, False)


def _blank_slide(prs):
    return prs.slides.add_slide(prs.slide_layouts[6])  # blank layout


def _rect(slide, left, top, w, h, fill=None, line_color=None, line_pt=0.0):
    shp = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, left, top, w, h)
    if fill is None:
        shp.fill.background()
    else:
        shp.fill.solid()
        shp.fill.fore_color.rgb = fill
    if line_color is None:
        shp.line.fill.background()
    else:
        shp.line.color.rgb = line_color
        shp.line.width = Pt(line_pt or 1.0)
    shp.shadow.inherit = False
    return shp


def _draw_machine(slide, kind: str, left, top, w, h) -> None:
    """Draw a simple, recognisable KROMI cabinet silhouette of the given kind.

    helix_master: cabinet with the panoramic monitor; helix_slave: same body, no
    monitor; carousel: vertical coil rack; locker: grid of compartment boxes.
    """
    # Cabinet body
    _rect(slide, left, top, w, h, fill=_WHITE, line_color=_DARK, line_pt=1.75)

    if kind in ("helix_master", "helix_slave"):
        if kind == "helix_master":
            # Panoramic monitor near the top
            _rect(
                slide,
                left + int(w * 0.16),
                top + int(h * 0.09),
                int(w * 0.68),
                int(h * 0.20),
                fill=_DARK,
            )
        # Door handle
        _rect(
            slide,
            left + int(w * 0.80),
            top + int(h * 0.42),
            int(w * 0.05),
            int(h * 0.16),
            fill=_DARKGREY,
        )
    elif kind == "carousel":
        # Vertical coil rack — evenly spaced thin bars behind "glass"
        inner_l = left + int(w * 0.14)
        inner_w = int(w * 0.72)
        bars = 7
        for i in range(bars):
            bx = inner_l + int(inner_w * i / (bars - 1))
            _rect(slide, bx, top + int(h * 0.08), int(w * 0.015), int(h * 0.84), fill=_MINT)
        _rect(
            slide,
            left + int(w * 0.80),
            top + int(h * 0.42),
            int(w * 0.05),
            int(h * 0.16),
            fill=_DARKGREY,
        )
    elif kind == "locker":
        # Grid of compartment boxes
        cols, rows = 2, 7
        pad_x, pad_y = int(w * 0.12), int(h * 0.08)
        gx, gy = int(w * 0.06), int(h * 0.02)
        cell_w = (w - 2 * pad_x - (cols - 1) * gx) // cols
        cell_h = (h - 2 * pad_y - (rows - 1) * gy) // rows
        for r in range(rows):
            for c in range(cols):
                cx = left + pad_x + c * (cell_w + gx)
                cy = top + pad_y + r * (cell_h + gy)
                _rect(slide, cx, cy, cell_w, cell_h, fill=_MINT, line_color=_DARK, line_pt=0.5)


_MACHINE_IMG = {
    "carousel": "machine_carousel.png",
    "helix_master": "machine_helix_master.png",
    "helix_slave": "machine_helix_slave.png",
    "locker": "machine_locker.png",
}


def _machine_render_path(assets_dir: str, kind: str) -> str:
    fn = _MACHINE_IMG.get(kind)
    if not assets_dir or not fn:
        return ""
    p = os.path.join(assets_dir, fn)
    return p if os.path.exists(p) else ""


def _add_lineup_slide(prs, stats: DeckStats, logo_path: str, page: int) -> None:
    units = lineup_units(stats)
    s = _blank_slide(prs)
    _add_logo(s, logo_path)
    _add_text(
        s,
        Inches(0.6),
        Inches(0.45),
        Inches(9),
        Inches(1.4),
        [
            ("CABINET LINE-UP", KROMI_HEADER_FONT, 36, _DARK, True),
            (summary_subtitle(stats), KROMI_HEADER_FONT, 22, _BRIGHT, True),
        ],
    )
    if not units:
        return

    # Scale: cabinets share a common display height so they line up on a floor.
    assets_dir = os.path.dirname(logo_path) if logo_path else ""
    draw_h = Inches(3.4)

    # Resolve each unit's real KROMI render + display width (scaled to the common
    # height). Falls back to a schematic silhouette only if a render is missing.
    placed = []  # (unit, render_path_or_"", width_emu)
    for u in units:
        path = _machine_render_path(assets_dir, u.kind)
        if path:
            with Image.open(path) as im:
                aspect = im.width / im.height
            w = int(draw_h * aspect)
        else:
            w = int(u.width_mm * (draw_h / 2000.0))
        placed.append((u, path, w))

    group_gap = Inches(0.6)
    total = sum(w for _, _, w in placed) + group_gap * (len(placed) - 1)
    start_x = int((_SLIDE_W - total) / 2)
    base_top = Inches(2.0)
    floor_y = base_top + draw_h

    # Floor band
    _rect(s, start_x - Inches(0.3), floor_y, total + Inches(0.6), Inches(0.16), fill=_DARK)

    x = start_x
    for u, path, w in placed:
        cx = x + w / 2
        if path:
            s.shapes.add_picture(path, int(x), int(base_top), height=draw_h)
        else:
            _draw_machine(s, u.kind, int(x), int(base_top), w, draw_h)
        # Label under the floor, with the count folded in (e.g. "3× Carousel")
        label = f"{u.count}\u00d7 {u.label}" if u.count > 1 else u.label
        _add_text(
            s,
            int(cx - Inches(1.2)),
            int(floor_y + Inches(0.24)),
            Inches(2.4),
            Inches(0.6),
            [(label, KROMI_HEADER_FONT, 14, _DARK, True)],
            align=PP_ALIGN.CENTER,
        )
        x += w + group_gap

    # Caption: total cabinets + line-up width in metres
    line_m = lineup_total_width_mm(stats) / 1000.0
    _add_text(
        s,
        Inches(0.6),
        _SLIDE_H - Inches(0.92),
        Inches(12),
        Inches(0.5),
        [
            (
                f"{stats.total_cabinets} cabinets  \u00b7  ~{line_m:.1f} m total floor line  "
                f"\u00b7  cabinets ~2.0 m tall",
                KROMI_BODY_FONT,
                13,
                _GREY,
                False,
            )
        ],
        align=PP_ALIGN.CENTER,
    )
    _add_footer(s, stats.date_str, page)


def build_summary_deck(stats: DeckStats, logo_path: str = "") -> bytes:
    """Return a KROMI-branded .pptx (cover + plan-summary) as bytes."""
    prs = Presentation()
    prs.slide_width = _SLIDE_W
    prs.slide_height = _SLIDE_H

    title, subtitle, date_str = cover_lines(stats)

    # --- Cover slide ---
    cover = _blank_slide(prs)
    _add_logo(cover, logo_path)
    _add_text(
        cover,
        Inches(0.7),
        Inches(2.6),
        Inches(11),
        Inches(2.2),
        [
            (title, KROMI_HEADER_FONT, 48, _DARK, True),
            (subtitle, KROMI_HEADER_FONT, 26, _BRIGHT, True),
        ],
        align=PP_ALIGN.LEFT,
        anchor=MSO_ANCHOR.MIDDLE,
    )
    _add_footer(cover, date_str, 1)

    # --- Summary slide ---
    s = _blank_slide(prs)
    _add_logo(s, logo_path)
    _add_text(
        s,
        Inches(0.6),
        Inches(0.45),
        Inches(9),
        Inches(1.4),
        [
            ("SUMMARY", KROMI_HEADER_FONT, 36, _DARK, True),
            (summary_subtitle(stats), KROMI_HEADER_FONT, 22, _BRIGHT, True),
        ],
    )

    # Three stacked, centred tiers form a pyramid: scope on top (supply points,
    # cabinets total), the cabinet-type breakdown in the middle, and the item
    # split on the bottom (items managed, KTC, Kanban). Each tier is centred, so
    # a narrower top row sits above the wider item row.
    tiers = summary_pyramid(stats)
    card_w = Inches(3.2)
    card_h = Inches(1.25)
    gap = Inches(0.3)
    row_gap = Inches(0.4)
    top0 = Inches(2.1)
    idx = 0
    for r, tier in enumerate(tiers):
        n = len(tier)
        row_w = n * card_w + gap * (n - 1)
        start_x = int((_SLIDE_W - row_w) / 2)
        top = top0 + r * (card_h + row_gap)
        x = start_x
        for card in tier:
            _add_card(
                s, int(x), int(top), card_w, card_h, card.value, card.label,
                dark=(idx % 2 == 0),
            )
            x += card_w + gap
            idx += 1
    _add_footer(s, date_str, 2)

    # --- Cabinet line-up elevation slide ---
    _add_lineup_slide(prs, stats, logo_path, page=3)

    buf = BytesIO()
    prs.save(buf)
    return buf.getvalue()
