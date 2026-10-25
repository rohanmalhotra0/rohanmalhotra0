"""Text to SVG path outlines with real kerning (HarfBuzz shaping, fontTools outlines).

The fonts are the ones on rohanm.org: Hubot Sans for the name, Mona Sans for text. Both are OFL
with Reserved Font Names, so no font files live in this repo: font() downloads the official
@fontsource-variable packages from npm (pinned and hash-checked) and builds static instances
in .fonts/ on first use. The SVGs only ever contain outlines.
"""
import base64
import functools
import hashlib
import io
import os
import tarfile
import urllib.request

import uharfbuzz as hb
from fontTools.pens.svgPathPen import SVGPathPen
from fontTools.pens.transformPen import TransformPen
from fontTools.ttLib import TTFont
from fontTools.varLib import instancer

CACHE = os.path.join(os.path.dirname(os.path.abspath(__file__)), ".fonts")
PACKAGES = {
    "hubot-sans": (
        "https://registry.npmjs.org/@fontsource-variable/hubot-sans/-/hubot-sans-5.3.0.tgz",
        "sha512-iFwlxVR7VgQ73VC6CwWwr389wYSNBPpiG8R91kPqRObtxuO3RBpRkwjlGBMtOBgLfpfOGLNSF/EOJvG9QLVKlA==",
    ),
    "mona-sans": (
        "https://registry.npmjs.org/@fontsource-variable/mona-sans/-/mona-sans-5.3.0.tgz",
        "sha512-PkxRB3KI4z9Gjpk7vVqgO3GMSyQuOIIj4TaRDbvbcDj8SzWwI38jvLTQxJM/cTRorhcT7h8qjcllR+qjRtM/Fg==",
    ),
}


def font(family, wdth, wght):
    """Path to a static TTF of `family` at the given width and weight, built on first use."""
    path = os.path.join(CACHE, f"{family}-{wdth}-{wght}.ttf")
    if os.path.exists(path):
        return path
    url, integrity = PACKAGES[family]
    with urllib.request.urlopen(url, timeout=60) as r:
        data = r.read()
    algo, want = integrity.split("-", 1)
    if base64.b64encode(hashlib.new(algo, data).digest()).decode() != want:
        raise SystemExit(f"{url}: integrity check failed")
    with tarfile.open(fileobj=io.BytesIO(data)) as tar:
        woff2 = tar.extractfile(f"package/files/{family}-latin-wdth-normal.woff2").read()
    static = instancer.instantiateVariableFont(TTFont(io.BytesIO(woff2)), {"wdth": wdth, "wght": wght})
    static.flavor = None
    os.makedirs(CACHE, exist_ok=True)
    static.save(path)
    return path


@functools.lru_cache(maxsize=None)
def _load(path):
    tt = TTFont(path)
    return hb.Font(hb.Face(hb.Blob.from_file_path(path))), tt["head"].unitsPerEm, tt.getGlyphSet(), tt.getGlyphOrder()


def _fmt(v):
    s = f"{v:.2f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "") else s


def text_path(text, font_path, size, x=0.0, y=0.0, tracking=0.0):
    """Shape `text` and return (svg_path_d, advance_width) with the baseline at y.
    tracking is in em, e.g. -0.025."""
    hbfont, upem, glyphset, order = _load(font_path)
    buf = hb.Buffer()
    buf.add_str(text)
    buf.guess_segment_properties()
    hb.shape(hbfont, buf, {"kern": True, "liga": True})
    scale = size / upem
    pen = SVGPathPen(glyphset, ntos=_fmt)
    cx = 0.0
    n = len(buf.glyph_infos)
    for i, (info, pos) in enumerate(zip(buf.glyph_infos, buf.glyph_positions)):
        gx = x + (cx + pos.x_offset) * scale
        gy = y - pos.y_offset * scale
        glyphset[order[info.codepoint]].draw(TransformPen(pen, (scale, 0, 0, -scale, gx, gy)))
        cx += pos.x_advance + (tracking * upem if i < n - 1 else 0)
    return pen.getCommands(), cx * scale
