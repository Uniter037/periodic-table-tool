"""Read-only reference images; SVG is deliberately restricted to self-contained art.

SVG support: resvg_py==0.5.0 (Python >=3.10), binary Windows wheels.
PyInstaller: --collect-all resvg_py includes the Rust extension; no Cairo required.
No style inference is performed. Inputs are never rewritten.
"""
from __future__ import annotations

from io import BytesIO
from pathlib import Path
import base64
import math
import re
import warnings
import xml.etree.ElementTree as ET

from PIL import Image, ImageOps

MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_PIXELS = 16_000_000
MAX_SIDE = 8192

# Exact SVG 1.1 identifiers only. Strip before either XML parser or renderer sees
# the declaration: its system URL is an identifier, never a resource to fetch.
_SVG11_DOCTYPE = re.compile(
    r'''<!DOCTYPE\s+svg\s+PUBLIC\s+(?:"-//W3C//DTD SVG 1\.1//EN"|'-//W3C//DTD SVG 1\.1//EN')\s+'''
    r'''(?:"http://www\.w3\.org/Graphics/SVG/1\.1/DTD/svg11\.dtd"|'http://www\.w3\.org/Graphics/SVG/1\.1/DTD/svg11\.dtd')\s*>'''
)
_XML_PROLOG = re.compile(r'\s*(?:<\?xml\s+[^?]*\?>\s*)?(?:<!--(?:(?!-->).)*-->\s*)*', re.S)


class ReferenceImageError(ValueError):
    """A readable error suitable for displaying directly in the UI."""


def _check_size(width, height):
    if (width <= 0 or height <= 0 or width > MAX_SIDE or height > MAX_SIDE
            or width * height > MAX_PIXELS):
        raise ReferenceImageError("图片尺寸过大或无效：单边最多 8192，最多 1600 万像素。")


def snapshot_image(image):
    """Return an independent RGBA snapshot; never close or mutate the caller's image."""
    if image is None:
        return None
    if not isinstance(image, Image.Image):
        raise ReferenceImageError("当前预览必须是 PIL.Image 或 None。")
    _check_size(*image.size)
    return image.convert("RGBA")


def _safe_css(value):
    # Disallow escaped identifiers rather than attempting to decode ambiguous CSS.
    value = re.sub(r"/\*.*?\*/", "", value, flags=re.S)
    if "\\" in value or "@" in value or "/*" in value:
        raise ReferenceImageError("SVG 含不支持的 CSS 转义或导入规则。")
    for match in re.finditer(r"url\s*\((.*?)\)", value, re.I | re.S):
        target = match.group(1).strip().strip("\"'")
        if not re.fullmatch(r"#[\w.:-]+", target):
            raise ReferenceImageError("SVG 不允许外部 CSS url 引用（包括网络、本地文件及 data）。")
    # Reject malformed URL functions too; the renderer must not reinterpret them.
    remainder = re.sub(r"url\s*\([^)]*\)", "", value, flags=re.I | re.S)
    if re.search(r"url\s*\(", remainder, re.I):
        raise ReferenceImageError("SVG CSS url 格式无效。")


def _embedded_raster(value):
    """Validate only inert PNG/JPEG data; no nested SVG or resource resolution."""
    match = re.fullmatch(r"data:image/(png|jpeg);base64,([A-Za-z0-9+/=\s]+)", value)
    if match is None:
        raise ReferenceImageError("SVG 内嵌图像仅支持 base64 PNG/JPEG，不允许外部文件或嵌套 SVG。")
    try:
        data = base64.b64decode(re.sub(r"\s", "", match[2]), validate=True)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format != {"png": "PNG", "jpeg": "JPEG"}[match[1]]:
                    raise ValueError("图像格式与 data 类型不符")
                _check_size(*image.size)
                image.load()
                return image.width * image.height
    except ReferenceImageError:
        raise
    except Exception as exc:
        raise ReferenceImageError(f"SVG 内嵌图像无效：{exc}") from exc


def sanitize_svg(data):
    """Validate XML and all resource-bearing values before invoking native code."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as exc:
        raise ReferenceImageError("SVG 必须使用 UTF-8 编码。") from exc
    declarations = list(re.finditer(r"<!\s*(DOCTYPE|ENTITY)", text, re.I))
    if declarations:
        declaration = declarations[0]
        standard = _SVG11_DOCTYPE.match(text, declaration.start())
        if (len(declarations) != 1 or standard is None
                or _XML_PROLOG.fullmatch(text[:declaration.start()]) is None):
            raise ReferenceImageError("SVG 仅允许无内部 subset/ENTITY 的标准 SVG 1.1 PUBLIC DOCTYPE；其他 DTD 均被拒绝。")
        text = text[:standard.start()] + text[standard.end():]
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise ReferenceImageError("SVG XML 格式无效。") from exc
    if root.tag not in ("svg", "{http://www.w3.org/2000/svg}svg"):
        raise ReferenceImageError("文件不是 SVG 图像。")
    embedded_pixels = 0
    for element in root.iter():
        tag = element.tag.rsplit("}", 1)[-1].lower()
        if tag in {"script", "foreignobject", "feimage", "animate",
                   "animatetransform", "animatemotion", "set", "discard"}:
            raise ReferenceImageError("SVG 含脚本、嵌入图像或动态内容；仅支持静态自包含矢量图。")
        for key, value in element.attrib.items():
            name = key.rsplit("}", 1)[-1].lower()
            if name.startswith("on") or name == "base":
                raise ReferenceImageError("SVG 不允许事件脚本或外部资源基址。")
            if name in {"href", "src"}:
                if tag == "image" and name == "href":
                    embedded_pixels += _embedded_raster(value.strip())
                    if embedded_pixels > MAX_PIXELS:
                        raise ReferenceImageError("SVG 内嵌图像总像素超过 1600 万限制。")
                elif not re.fullmatch(r"#[\w.:-]+", value.strip()):
                    raise ReferenceImageError("SVG 不允许外部 href/src 引用（网络或本地文件）。")
            _safe_css(value)
        if tag == "style":
            _safe_css("".join(element.itertext()))
    viewbox = root.get("viewBox", "").replace(",", " ").split()
    def dimension(name, index):
        raw = root.get(name)
        if raw is None or raw.endswith("%"):
            if len(viewbox) != 4:
                raise ReferenceImageError("SVG 需要明确的宽高或 viewBox。")
            return float(viewbox[index])
        match = re.fullmatch(r"\s*([+\-\d.eE]+)\s*(px|pt|pc|in|cm|mm)?\s*", raw)
        if not match:
            raise ReferenceImageError("SVG 宽高单位不支持。")
        return float(match[1]) * {None: 1, "px": 1, "pt": 96/72, "pc": 16,
                                  "in": 96, "cm": 96/2.54, "mm": 96/25.4}[match[2]]
    try:
        width, height = dimension("width", 2), dimension("height", 3)
        if not math.isfinite(width) or not math.isfinite(height):
            raise ValueError()
        _check_size(width, height)
        size = math.ceil(width), math.ceil(height)
        _check_size(*size)
    except (ValueError, OverflowError) as exc:
        if isinstance(exc, ReferenceImageError):
            raise
        raise ReferenceImageError("SVG 宽高或 viewBox 数值无效。") from exc
    return ET.tostring(root, encoding="unicode"), size


def load_reference_image(path):
    """Load PNG/JPEG/SVG as owned RGBA pixels, with bounded input and output."""
    try:
        path = Path(path)
        if path.suffix.lower() not in {".png", ".jpg", ".jpeg", ".svg"}:
            raise ReferenceImageError("仅支持 PNG、JPG/JPEG 和 SVG。")
        with path.open("rb") as stream:
            data = stream.read(MAX_FILE_BYTES + 1)
        if len(data) > MAX_FILE_BYTES:
            raise ReferenceImageError("参考文件过大，最大允许 20 MiB。")
        if path.suffix.lower() == ".svg":
            svg, (width, height) = sanitize_svg(data)
            try:
                import resvg_py
            except ImportError as exc:
                raise ReferenceImageError("SVG 支持需要安装 resvg_py==0.5.0（Python ≥3.10）。") from exc
            data = resvg_py.svg_to_bytes(svg_string=svg, width=width, height=height,
                                         dpi=96, resources_dir=None)
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                if image.format not in {"PNG", "JPEG"}:
                    raise ReferenceImageError("文件内容不是 PNG/JPEG 图像。")
                _check_size(*image.size)
                return ImageOps.exif_transpose(image).convert("RGBA")
    except ReferenceImageError:
        raise
    except Exception as exc:
        raise ReferenceImageError(f"无法读取参考图：{exc}") from exc
