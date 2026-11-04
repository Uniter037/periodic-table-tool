"""Shared save/crop policy and hit geometry from the actual saved raster."""
from io import BytesIO

from matplotlib.backends.backend_agg import FigureCanvasAgg
from PIL import Image


def save_options(style):
    return {"dpi": style.get("dpi", 100),
            "bbox_inches": "tight" if style.get("bbox_tight", True) else None,
            "pad_inches": .1, "transparent": style.get("transparent", False)}


def rasterize(fig, hit_map=None, tight=False, *, transparent=False):
    """Return detached RGBA pixels and clipped hit boxes in image coordinates.

    Savefig temporarily changes transforms for tight cropping. Capture the LAST
    draw's transform while that crop is in effect instead of guessing offsets
    from a separate draw (which can differ with text metrics/layout engines).
    """
    canvas = FigureCanvasAgg(fig)
    geometry = []

    def capture(event):
        if fig.axes:
            ax = fig.axes[0]
            geometry[:] = [ax.transData.frozen(), ax.bbox.frozen()]

    callback = canvas.mpl_connect("draw_event", capture)
    try:
        with BytesIO() as buffer:
            fig.savefig(buffer, format="png", **save_options(
                {"dpi": fig.dpi, "bbox_tight": tight, "transparent": transparent}))
            buffer.seek(0)
            with Image.open(buffer) as image:
                source = image.convert("RGBA")
    finally:
        canvas.mpl_disconnect(callback)
    boxes = {}
    if geometry:
        transform, bounds = geometry
        for (x0, y0, x1, y1), symbol in (hit_map or {}).items():
            (xa, ya), (xb, yb) = transform.transform(((x0, y0), (x1, y1)))
            left = max(min(xa, xb), bounds.x0, 0)
            right = min(max(xa, xb), bounds.x1, source.width)
            bottom = max(min(ya, yb), bounds.y0, 0)
            top = min(max(ya, yb), bounds.y1, source.height)
            if right > left and top > bottom:
                boxes[(left, source.height - top, right, source.height - bottom)] = symbol
    return source, boxes
