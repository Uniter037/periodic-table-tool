"""Per-text glyph fallback without changing legacy ASCII font selection."""
from functools import lru_cache

from matplotlib import font_manager
from matplotlib.ft2font import FT2Font
from matplotlib.text import Text


@lru_cache(maxsize=1)
def _fallback_fonts():
    preferred = ("Microsoft YaHei", "SimHei", "Noto Sans CJK SC", "SimSun")
    entries = sorted(font_manager.fontManager.ttflist,
                     key=lambda entry: preferred.index(entry.name)
                     if entry.name in preferred else len(preferred))
    fonts = []
    seen = set()
    for entry in entries:
        if entry.name in seen:
            continue
        try:
            glyphs = frozenset(FT2Font(entry.fname).get_charmap())
        except (OSError, RuntimeError):
            continue
        seen.add(entry.name)
        fonts.append((entry.name, glyphs))
    return fonts


def apply_text_fallbacks(fig):
    """Append installed fonts covering non-ASCII characters to each text artist."""
    for artist in fig.findobj(match=Text):
        needed = {ord(char) for char in artist.get_text() if ord(char) > 127}
        if not needed:
            continue
        families = list(artist.get_fontfamily())
        for name, glyphs in _fallback_fonts():
            if needed & glyphs:
                if name not in families:
                    families.append(name)
                needed -= glyphs
            if not needed:
                break
        artist.set_fontfamily(families)
