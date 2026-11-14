"""Презентации PowerPoint (python-pptx). outline = {"title", "subtitle", "slides": [{"title", "bullets", "notes"}]}"""
import os
import re


def build(outline, folder):
    from pptx import Presentation
    from pptx.dml.color import RGBColor
    from pptx.util import Inches, Pt
    navy, blue, ink, pale = RGBColor(0x1F, 0x3A, 0x5F), RGBColor(0x6F, 0x8F, 0xC7), RGBColor(0x22, 0x2B, 0x38), RGBColor(0xF4, 0xF7, 0xFB)
    prs = Presentation()
    prs.slide_width, prs.slide_height = Inches(13.333), Inches(7.5)
    blank = prs.slide_layouts[6]

    def box(slide, x, y, w, h, text, size, color, bold=False):
        tb = slide.shapes.add_textbox(Inches(x), Inches(y), Inches(w), Inches(h))
        tf = tb.text_frame
        tf.word_wrap = True
        lines = text if isinstance(text, list) else [text]
        for i, line in enumerate(lines):
            p = tf.paragraphs[0] if i == 0 else tf.add_paragraph()
            r = p.add_run()
            r.text = str(line)
            r.font.size, r.font.bold, r.font.color.rgb, r.font.name = Pt(size), bold, color, "Segoe UI"
            p.space_after = Pt(size * 0.5)
        return tb

    def bg(slide, color):
        f = slide.background.fill
        f.solid()
        f.fore_color.rgb = color

    def bar(slide, x, y, w, h, color):
        s = slide.shapes.add_shape(1, Inches(x), Inches(y), Inches(w), Inches(h))
        s.fill.solid()
        s.fill.fore_color.rgb = color
        s.line.fill.background()

    title = str(outline.get("title") or "Презентация")
    s = prs.slides.add_slide(blank)
    bg(s, navy)
    bar(s, 0.9, 3.55, 1.6, 0.06, blue)
    box(s, 0.9, 1.9, 11.5, 1.6, title, 44, RGBColor(255, 255, 255), True)
    if outline.get("subtitle"):
        box(s, 0.9, 3.8, 11.5, 1.0, str(outline["subtitle"]), 22, RGBColor(0xD6, 0xE2, 0xF3))
    for i, sl in enumerate(outline.get("slides") or [], 1):
        s = prs.slides.add_slide(blank)
        bg(s, pale)
        bar(s, 0, 0, 0.28, 7.5, navy)
        box(s, 0.9, 0.55, 11.5, 1.1, str(sl.get("title") or ""), 32, navy, True)
        bar(s, 0.9, 1.6, 1.2, 0.05, blue)
        bullets = ["•  " + str(b) for b in (sl.get("bullets") or [])][:7]
        if bullets:
            box(s, 0.9, 2.0, 11.4, 4.6, bullets, 22 if len(bullets) <= 5 else 19, ink)
        box(s, 12.2, 6.85, 0.9, 0.4, str(i + 1), 12, blue)
        if sl.get("notes"):
            s.notes_slide.notes_text_frame.text = str(sl["notes"])
    os.makedirs(folder, exist_ok=True)
    base = re.sub(r'[\\/:*?"<>|]+', " ", title).strip()[:60] or "Презентация"
    path = os.path.join(folder, base + ".pptx")
    k = 1
    while os.path.exists(path):
        k += 1
        path = os.path.join(folder, f"{base} ({k}).pptx")
    prs.save(path)
    return path


def parse_outline(text):
    """Достаёт JSON из ответа модели (даже если он в ```json … ```)."""
    import json
    m = re.search(r"\{.*\}", text or "", re.S)
    if not m:
        return None
    try:
        d = json.loads(m.group(0))
    except ValueError:
        return None
    return d if isinstance(d, dict) and d.get("slides") else None
