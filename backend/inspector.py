"""Firecrawl extracts text; PDFium only renders pages; Pillow draws overlays."""
import math
import pdf_inspector
import pypdfium2 as pdfium
from PIL import ImageDraw

FIELDS = ('text', 'page', 'x', 'y', 'width', 'height', 'font', 'font_size',
          'rotation', 'advance_known', 'is_bold', 'is_italic', 'item_type')


def inspect_pdf(data):
    positioned = pdf_inspector.extract_text_with_positions_and_rotations_bytes(data)
    items = [dict(id=i + 1, **{k: getattr(item, k) for k in FIELDS})
             for i, item in enumerate(positioned.items)
             if item.item_type.lower() == 'text' and item.text.strip()]
    turns = {r.page: r.rotation for r in positioned.page_rotations}
    return {'items': items, 'turns': turns}


def display_box(item, width, height, rotation=0, turn=None):
    """Convert extractor frame to rendered, top-left PDF points.

    Reverse Firecrawl's dominant-text rotation first, apply PDF /Rotate,
    then invert Y. See upstream geometry.rs and display_frame.rs.
    """
    x, y, w, h = (float(item[k]) for k in ('x', 'y', 'width', 'height'))
    if not all(math.isfinite(v) for v in (x, y, w, h)):
        raise ValueError('Non-finite text coordinates')
    x, y, w, h = min(x, x+w), min(y, y+h), abs(w), abs(h)
    if turn == 'ccw':
        x, y, w, h = -y-h, x, h, w
    elif turn == 'cw':
        x, y, w, h = y, -x-w, h, w
    rotation %= 360
    if rotation == 90:
        x, y, w, h = y, width-x-w, h, w
        height = width
    elif rotation == 180:
        x, y = width-x-w, height-y-h
    elif rotation == 270:
        x, y, w, h = height-y-h, x, h, w
        height = width
    return [x, height-y-h, x+w, height-y]


def render_page(data, page_index, items, turn=None, show_boxes=True, selected=None, scale=1.5):
    with pdfium.PdfDocument(data) as doc:
        page = doc[page_index]
        try:
            rotation = page.get_rotation()
            page.set_rotation(0)
            width, height = page.get_size()
            page.set_rotation(rotation)
            display_width, display_height = page.get_size()
            # Keep pathological large page sizes from allocating huge bitmaps.
            scale = min(scale, 3000 / max(display_width, display_height))
            bitmap = page.render(scale=scale)
            try:
                image = bitmap.to_pil().convert('RGB')
            finally:
                bitmap.close()
        finally:
            page.close()
    sx, sy = image.width/display_width, image.height/display_height
    draw = ImageDraw.Draw(image)
    rows = []
    for item in items:
        box = display_box(item, width, height, rotation, turn)
        rows.append(dict(item, bbox_top_left_pt=box))
        if show_boxes or item['id'] == selected:
            x0, y0, x1, y1 = box
            padding = 4
            draw.rectangle(((x0-padding)*sx, (y0-padding)*sy,
                            (x1+padding)*sx, (y1+padding)*sy),
                           outline='#dc2626', width=max(4, round(4*sx)))
    return image, rows
