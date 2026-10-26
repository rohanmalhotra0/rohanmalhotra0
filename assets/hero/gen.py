#!/usr/bin/env python3
"""
Profile hero for github.com/rohanmalhotra0: Washington Square Park, home of NYU Courant, as a flat
editorial illustration. Light: golden hour, low sun from the west, long shadows. Dark: the same square at
night under the park lamps. The Washington Square Arch is drawn in elevation from its dimensions (77 ft
tall, 30 x 47 ft opening), with Fifth Avenue running off through it in one-point perspective to the
Empire State Building.

Computed here (stdlib only), then baked into SMIL:
  * the fountain: ten ring jets and two plume groups (25 sub-jets), every droplet on its exact ballistic
    trajectory in 3D, projected with an orthographic camera, so each path is a true parabola with screen
    gravity g*s*cos(elevation). Each jet stream is drawn as a quadratic Bezier (an exact parabola); the
    drops on it are a 6-frame flipbook in which every displayed frame puts every drop where gravity says
    (flight times 1.5 / 2.4 / 1.8 s with 5 / 8 / 6 drops per jet all repeat every 0.3 s). The basin is a
    granite coping 0.45 m high with the water 0.3 m below its top, so the near coping hides exactly the water
    its line of sight cuts off; the water shades by Fresnel reflectance and mirrors the arch through the same
    camera; ripples spread at the deep-water speed of a 0.6 s wave; the central column rises to the plume
    drops' own apex and keeps radius x sqrt(speed) constant (continuity).
  * the pigeons: a boids flock (separation, alignment, cohesion, a guide loop, arrive-and-land) sampled at
    20 fps. Each bird is one sprite with a discrete translate and an additive rotate (its heading) that also
    pick its drawing from a strip: four flapping drawings in flight, stand/peck on the ground. They take off in
    a wave, wheel round once and land back on their own spots.
  * falling leaves: the Andersen-Pesavento-Wang quasi-steady falling-plate model (fluttering regime),
    integrated with RK4; the leaf rides the computed path and rocks with the computed plate angle.
  * the light: every cast shadow runs along SUN at 2.6 x its caster's height, a sun 18.5 deg up at azimuth
    238 deg, within 3 deg of the real sun over the square at 4:10 pm on 25 October 2026.
  * giant soap bubbles (section "life"): a busker's wands blow tubes that pinch off into bubbles drifting on
    a gusty breeze with eddies (incompressible, 12 s periodic), integrated with RK4 from the Maxey-Riley
    equation: drag, the air inside plus its added mass, and the film's weight for a slow sink. Also a
    squirrel, chess players, NYU flags, and at night the Empire State Building's beacon.

Frame-locked: every animation is discrete and changes only on a shared 20 fps grid. Every flipbook is a
filmstrip (frames stored 2000 units apart, off the card, stepped by one discrete translate): measured in
Chrome, discrete translates and rotates are skipped when unchanged, but discrete `d`, `href` and
animateMotion animations repaint the whole image every tick, so none are used. Every duration divides the
12 s period, so t=0 and t=12 s are the same frame.

Reduced motion: animated content sits in <g class="anim">, a static copy in <g class="still"> (pigeons
on the ground, the fountain caught mid-spray). All lettering is outlines (Hubot Sans Wide ExtraBold).
No scripts, text, filters or external references.

usage: pip install -r requirements.txt && python3 gen.py [--out DIR] [--check]
Writes hero-dark.svg and hero-light.svg into assets/ by default.
"""
import argparse
import math
import os
import random
import re

from textpath import font, text_path

HERE = os.path.dirname(os.path.abspath(__file__))

W, H = 1600, 640
FPS = 20
PERIOD = 12.0
NF = int(round(PERIOD * FPS))                        # 240 frames on the grid
G = 9.81


# ------------------------------------------------------------------ formatting
def fm(v, d=1):
    s = f"{v:.{d}f}"
    if "." in s:
        s = s.rstrip("0").rstrip(".")
    if s.startswith("0."):
        s = s[1:]
    elif s.startswith("-0."):
        s = "-" + s[2:]
    return "0" if s in ("", "-", "-0") else s


def pp(x, y, d=1):
    return f"{fm(x, d)} {fm(y, d)}"


def poly(pts, d=1, close=True):
    return "M" + " ".join(pp(x, y, d) for x, y in pts) + ("Z" if close else "")


def ell(cx, cy, rx, ry, d=1):
    return (f"M{pp(cx - rx, cy, d)}a{fm(rx, d)} {fm(ry, d)} 0 1 0 {fm(2 * rx, d)} 0"
            f"a{fm(rx, d)} {fm(ry, d)} 0 1 0 {fm(-2 * rx, d)} 0Z")


def circ(cx, cy, r, d=1):
    return ell(cx, cy, r, r, d)


def lerp(a, b, t):
    return a + (b - a) * t


def mix(c1, c2, t):
    a = [int(c1[i:i + 2], 16) for i in (1, 3, 5)]
    b = [int(c2[i:i + 2], 16) for i in (1, 3, 5)]
    return "#" + "".join(f"{round(lerp(x, y, t)):02X}" for x, y in zip(a, b))


def filmstrip(frames, dur, begin=0.0, step=2000, attrs="", axis="y"):
    """A flipbook that only uses a discrete translate: frame k is stored `step*k` units away (off the card) and
    the strip jumps one frame per step. Browsers skip repaints for unchanged discrete transforms, which they do
    not do for discrete `d` or `href` animations."""
    def off(k):
        return f"0 {step * k}" if axis == "y" else f"{step * k} 0"
    vals = ";".join(("0 " + str(-step * k)) if axis == "y" else (str(-step * k) + " 0") for k in range(len(frames)))
    b = f' begin="-{fm(begin, 3)}s"' if begin else ""
    body = "".join(fr if k == 0 else f'<g transform="translate({off(k)})">{fr}</g>' for k, fr in enumerate(frames))
    return (f'<g{attrs}><animateTransform attributeName="transform" type="translate" values="{vals}" dur="{fm(dur, 3)}s"{b} '
            f'calcMode="discrete" repeatCount="indefinite"/>{body}</g>')


def kt(f):
    """keyTime for grid frame f."""
    return fm(f / NF, 5)


# ------------------------------------------------------------------ palettes
PAL = {
    "light": dict(
        sky=[("0", "#EFC270"), (".5", "#F4D7A0"), ("1", "#F2D9AE")],
        haze="#EBD2A9", haze2="#E2C49B", haze_lit="#F3DDB4",
        brick="#B8583D", lime="#E6CBA2", brick_lit="#CB6B48", brick_dk="#93432F", trim="#F4E4C7", win="#5E3D3F", glint="#F6CF7E",
        stone="#FBEDD4", stone_hi="#FFF6E3", band="#DCC4A3", line="#D5BC98", stone_dk="#C7AC8D",
        inner_l="#C9B097", inner_r="#F9DCA8", soffit="#C0A487", soffit_line="#AE9276", floor="#D2B48F",
        v_sky="#F6DFB3", v_lit="#EBB46F", v_lit2="#D9A06A", v_sh="#AF918C", v_sh2="#9F8381", v_end="#E4BC8A",
        v_street="#C7AA93", v_side="#D9BFA0", v_esb="#BFA6A1", v_esb_lit="#EDCFA9", v_line="#CFA06C", v_line2="#A98D85",
        fol=[("#F3C451", "#D99430"), ("#EDAE3E", "#C9762C"), ("#DE8A3C", "#B5592F"), ("#BEC084", "#919B66"),
             ("#F5BE4A", "#D4882E")],
        fol_off=(-0.21, -0.23), trunk="#5C4237", trunk_hi="#8C674E",
        lawn="#ADB27B", lawn_dk="#939B68", fence="#3F3A3B",
        plaza="#EFD5A4", ring="#E5C892", shadow="#D8BFAA",
        rim_out="#E8D0A9", rim_sh="#C9AC8F", rim_top="#F6E6C8", wall_in="#B59C84",
        water="#8DB4AB", water_dk="#7AA39B", water_hi="#D2E4D8", jet="#FFFFFF", drop="#FFFFFF", foam="#FFFDF6",
        ripple="#E9F2EA",
        lamp="#35303A", globe="#FFF3DA", banner="#57068C", torch="#FFFFFF",
        name="#57068C",
        bird_fill="#8C899E", bird_col="#5F5C72", bird_tail="#45424E", white_fill="#F5F0E8", white_col="#D9D2C9",
        g_body="#7D7B8F", g_wing="#A5A2B4", g_head="#625F75", g_neck="#7FA08A", g_beak="#3E3A40", g_leg="#C47B6C",
        g_shadow="#D8BFAA",
        leaf=["#F2BE4C", "#E59D33", "#CB6431", "#B9B677"], leaf_rib="#9A5B2A", twig="#523A30",
        coat=["#7E9271", "#B8583D", "#DDA03B", "#3F3B4D", "#A9B49C"], skin="#B9805E", hair="#3B2C2A",
        stars=False, night=False,
    ),
    "dark": dict(
        sky=[("0", "#0E1828"), (".6", "#142136"), ("1", "#1B2A44")],
        haze="#1D2A40", haze2="#223049", haze_lit="#2A3852",
        brick="#4B2F2E", lime="#4E4642", brick_lit="#57373 4".replace(" ", ""), brick_dk="#3A2424", trim="#6E5D55", win="#1B2130", glint="#F3C670",
        stone="#EADCC1", stone_hi="#F6EAD2", band="#C9B595", line="#C4AF8E", stone_dk="#A99678",
        inner_l="#B9A585", inner_r="#D6C29F", soffit="#D9C6A4", soffit_line="#B9A482", floor="#6F6457",
        v_sky="#1C2A43", v_lit="#2F3A50", v_lit2="#2A3449", v_sh="#252E40", v_sh2="#212A3A", v_end="#333E55",
        v_street="#2A2F3A", v_side="#353944", v_esb="#3B465E", v_esb_lit="#4C5873", v_line="#E8B868", v_line2="#D9A75A",
        fol=[("#3F4A34", "#2B3527"), ("#4A4632", "#322F23"), ("#4D3A2C", "#34271F"), ("#36443A", "#26302A"),
             ("#4B4430", "#332E22")],
        fol_off=(0.0, 0.26), trunk="#1E1C21", trunk_hi="#3A3230",
        lawn="#26332C", lawn_dk="#1F2A25", fence="#0D1016",
        plaza="#2B3141", ring="#323A4C", shadow="#252A38",
        rim_out="#4A4A52", rim_sh="#383943", rim_top="#5E5C62", wall_in="#2C3340",
        water="#1F3B53", water_dk="#1A3247", water_hi="#5C86A0", jet="#FFF3DC", drop="#FFF1D4", foam="#F3EBDC",
        ripple="#9DBBCB",
        lamp="#11151E", globe="#FFE7AE", banner="#6A16A6", torch="#FFF1DA",
        name="#F1D9A6",
        bird_fill="#8C87A6", bird_col="#6F6A88", bird_tail="#5B586C", white_fill="#E9E3DA", white_col="#BDB6AD",
        g_body="#6E6B80", g_wing="#8F8BA2", g_head="#57546A", g_neck="#5F7F6D", g_beak="#2E2A30", g_leg="#9C6458",
        g_shadow="#1E2330",
        leaf=["#D9A548", "#C28634", "#A1552E", "#8E8D55"], leaf_rib="#6E4422", twig="#15151A",
        coat=["#4F5D4A", "#7A3C2C", "#8E6A2C", "#2A2834", "#6F7666"], skin="#7E5A45", hair="#1F1818",
        stars=True, night=True,
    ),
}
PAL["dark"]["brick_lit"] = "#573734"


# ------------------------------------------------------------------ the arch (feet, origin at base centre)
SCENERY_PAL = {
    "light": dict(
        # crowns per foliage index: (lit, deep, base); 0 gold, 1 orange, 2 russet, 3 late green
        sc_fol=[("#F8CB5E", "#B4702F", "#E0A03D"), ("#F4AA4C", "#9F4F2D", "#D47C33"), ("#EE9858", "#9F4F2D", "#C6653A"),
                ("#D7CF88", "#7D8453", "#A9AA68")],
        sc_trunk="#6A4C3B", sc_trunk_lit="#A27A57",
        sc_granite="#E7CA96", sc_shadow_soft="#E7C899",
        sc_marble="#F7EBD3", sc_iron="#2F2B30", sc_lime_sh="#CFB38F",
        sc_street="#D4BA97", sc_pier="#D9BE98",
        sc_relief="#EBD6B5",
    ),
    "dark": dict(
        # (lamp-lit, deep, base)
        sc_fol=[("#6E5B34", "#192019", "#283126"), ("#76593A", "#221C1B", "#332E29"), ("#755339", "#221C1B", "#352B27"),
                ("#605E3D", "#162020", "#232F2B")],
        sc_trunk="#17171C", sc_trunk_lit="#2B2827",
        sc_granite="#30374A", sc_shadow_soft="#2B3141",
        sc_marble="#7E756A", sc_iron="#0C0F15", sc_lime_sh="#756C61",
        sc_street="#262B38", sc_pier="#1F2A3F",
        sc_relief="#DAC8A6",
    ),
}
for _t in PAL:
    PAL[_t].update(SCENERY_PAL[_t])

AX, AY, U = 1196.0, 452.0, 4.96           # screen position of the base centre, units per foot
VPX, VPY = -2.5, 9.0                      # vanishing point in arch feet (eye level 9 ft)
DEPTH, DC = 24.0, 150.0                   # arch thickness, camera distance used for the vista
FB = DC / (DC + DEPTH)


def A(x, y):
    return AX + x * U, AY - y * U


def persp(x, y, z):
    k = DC / (DC + z)
    return A(VPX + (x - VPX) * k, VPY + (y - VPY) * k)


SIL_R = [(31.8, 0), (31.8, 3.0), (31.4, 3.0), (31.4, 3.7), (31.0, 3.7), (31.0, 55.6), (31.6, 56.2), (32.7, 56.6),
         (32.7, 58.6), (32.1, 59.4), (30.9, 59.4), (30.9, 60.6), (30.4, 60.6), (30.4, 74.4), (31.3, 74.6),
         (31.3, 76.1), (29.6, 76.1), (29.6, 77.0)]
OPEN_HW, SPRING, CROWN = 15.0, 32.0, 47.0


def opening_path(scale_fn):
    """Opening outline (rect + semicircle) through scale_fn(x, y) -> screen."""
    x0, y0 = scale_fn(-OPEN_HW, 0)
    x1, y1 = scale_fn(-OPEN_HW, SPRING)
    x2, y2 = scale_fn(OPEN_HW, SPRING)
    x3, y3 = scale_fn(OPEN_HW, 0)
    r = (x2 - x1) / 2
    return f"M{pp(x0, y0)}L{pp(x1, y1)}A{fm(r)} {fm(r)} 0 0 1 {pp(x2, y2)}L{pp(x3, y3)}Z"


def back_fn(x, y):
    return persp(x, y, DEPTH)


def star(cx, cy, ro, ri, rot=-90):
    pts = []
    for i in range(10):
        r = ro if i % 2 == 0 else ri
        a = math.radians(rot + 36 * i)
        pts.append((cx + r * math.cos(a), cy + r * math.sin(a)))
    return poly(pts)


# Spandrel Victories (after MacMonnies) and the keystone eagle, south face, in arch feet. The right-hand figure
# reclines along the archivolt, head and wreath towards the keystone, wing filling the upper corner, drapery
# trailing to the impost; the left one is its mirror. Every point stays above the archivolt (r > 17.3 ft about the
# springing centre) and below the frieze band (48.9 ft).
VICTORY = [
    # wing, swept up from the shoulders into the upper corner, feathered along its trailing edge
    [("M", 14.6, 46.5), ("C", 16.0, 48.1, 19.5, 48.6, 23.5, 48.5), ("C", 26.0, 48.45, 28.0, 48.0, 29.6, 47.0),
     ("Q", 29.1, 45.8, 28.0, 46.0), ("Q", 27.8, 44.7, 26.5, 45.2), ("Q", 26.2, 43.9, 24.9, 44.5),
     ("Q", 24.5, 43.4, 23.2, 44.0), ("C", 21.0, 44.2, 18.0, 44.6, 16.2, 45.2), ("Z",)],
    # body in flight along the archivolt, the robe billowing behind to the impost
    [("M", 12.3, 46.9), ("C", 13.6, 47.0, 14.6, 46.6, 15.4, 45.9), ("C", 16.4, 45.0, 17.2, 44.0, 18.2, 43.0),
     ("C", 20.5, 42.6, 23.5, 42.0, 26.6, 40.9), ("Q", 27.6, 40.6, 28.6, 40.9), ("Q", 27.6, 40.0, 27.9, 39.0),
     ("Q", 26.6, 39.4, 25.8, 38.9), ("C", 24.2, 38.2, 22.8, 37.0, 22.0, 35.6), ("L", 21.6, 34.7),
     ("C", 20.6, 34.9, 19.6, 35.6, 19.0, 36.6), ("C", 18.5, 37.6, 18.2, 38.8, 17.6, 40.0),
     ("C", 17.0, 41.3, 16.0, 42.6, 14.9, 43.6), ("C", 14.0, 44.4, 13.0, 45.2, 12.1, 45.9), ("Z",)],
    # both arms reaching for the keystone
    [("M", 12.9, 46.85), ("L", 10.1, 47.8), ("L", 9.9, 47.35), ("L", 12.6, 46.2), ("Z",)],
]
VICTORY_RINGS = [(11.7, 47.25, 0.84, 0.0), (12.45, 47.65, 0.46, 0.0), (9.1, 47.85, 0.7, 0.34)]   # head, hair, wreath
EAGLE = [
    # left wing raised; the right one is its mirror
    [("M", -0.6, 49.6), ("C", -1.6, 50.6, -3.0, 51.6, -4.9, 52.6), ("Q", -4.6, 51.6, -5.3, 51.4),
     ("Q", -4.5, 50.8, -5.0, 50.3), ("Q", -4.1, 49.9, -4.4, 49.2), ("Q", -3.4, 49.0, -3.5, 48.3),
     ("C", -2.4, 48.4, -1.4, 48.6, -0.6, 48.6), ("Z",)],
    # body, tail fan and the head turned west
    [("M", 0.0, 50.9), ("C", 0.9, 50.6, 1.0, 49.0, 0.7, 48.0), ("L", 1.3, 46.6), ("L", 0.0, 47.0), ("L", -1.3, 46.6),
     ("L", -0.7, 48.0), ("C", -1.0, 49.0, -0.9, 50.6, 0.0, 50.9), ("Z",),
     ("M", 0.35, 50.6), ("C", 0.4, 51.6, -0.6, 52.0, -1.0, 51.5), ("L", -1.75, 51.35), ("L", -1.0, 51.0),
     ("C", -0.7, 50.6, -0.3, 50.4, 0.35, 50.6), ("Z",)],
]


def feet_d(cmds, mirror=False, off=(0.0, 0.0)):
    """Path data from commands in arch feet (M/L/Q/C/Z), optionally mirrored about the arch axis and offset."""
    s = []
    for k, *v in cmds:
        pts = []
        for j in range(0, len(v), 2):
            x, y = (-v[j] if mirror else v[j]) + off[0], v[j + 1] + off[1]
            pts.append(pp(*A(x, y)))
        s.append(k + " ".join(pts))
    return "".join(s)


def feet_rel(cmds, mirror=False, off=(0.0, 0.0), d=0):
    """Like feet_d, written with relative commands from rounded absolute points (no drift)."""
    s, cur, start = [], None, None
    for k, *v in cmds:
        if k == "Z":
            s.append("Z")
            cur = start
            continue
        pts = []
        for j in range(0, len(v), 2):
            x, y = A((-v[j] if mirror else v[j]) + off[0], v[j + 1] + off[1])
            pts.append((round(x, d), round(y, d)))
        if k == "M":
            s.append(f"M{pp(*pts[0], d)}")
            cur = start = pts[0]
            continue
        s.append(k.lower() + " ".join(pp(px - cur[0], py - cur[1], d) for px, py in pts))
        cur = pts[-1]
    return re.sub(r" -", "-", "".join(s))


def relief_svg(P):
    """The reliefs in a slightly darker stone, raised: each casts a thin shadow east and below (path data, drawn
    with the arch's other shade) and the bodies (one path; the left Victory and eagle wing mirror the right ones)."""
    out = {}
    for name, off in (("sh", (0.24, -0.2)), ("bd", (0.0, 0.0))):
        d = []
        for mirror in (False, True):
            d += [feet_rel(s, mirror, off) for s in VICTORY]
            for cx, cy, r, ri in VICTORY_RINGS:
                px, py = A((-cx if mirror else cx) + off[0], cy + off[1])
                d.append(circ(px, py, r * U))
                if ri:
                    d.append(f"M{pp(px - ri * U, py)}a{fm(ri * U)} {fm(ri * U)} 0 1 1 {fm(2 * ri * U)} 0"
                             f"a{fm(ri * U)} {fm(ri * U)} 0 1 1 {fm(-2 * ri * U)} 0Z")
            d.append(feet_rel(EAGLE[0], not mirror, off))
        d.append(feet_rel(EAGLE[1], False, off))
        out[name] = "".join(d)
    return out["sh"], f'<path d="{out["bd"]}" fill="{P["sc_relief"]}"/>'


def arch_svg(P, rng):
    o = []
    sil = SIL_R + [(-x, y) for x, y in reversed(SIL_R)]
    body = poly([A(x, y) for x, y in sil]) + opening_path(A)
    # intrados in perspective: floor, the two pier faces, the barrel vault
    fl = [A(-15, 0), A(15, 0), back_fn(15, 0), back_fn(-15, 0)]
    lf = [A(-15, 0), A(-15, SPRING), back_fn(-15, SPRING), back_fn(-15, 0)]
    rf = [A(15, 0), A(15, SPRING), back_fn(15, SPRING), back_fn(15, 0)]
    fa, fb_ = A(-15, SPRING), A(15, SPRING)
    ba, bb = back_fn(-15, SPRING), back_fn(15, SPRING)
    rfront = 15 * U
    rback = (bb[0] - ba[0]) / 2
    vault = (f"M{pp(*fa)}A{fm(rfront)} {fm(rfront)} 0 0 1 {pp(*fb_)}L{pp(*bb)}"
             f"A{fm(rback)} {fm(rback)} 0 0 0 {pp(*ba)}Z")
    o.append(f'<path d="{poly(fl)}" fill="{P["floor"]}"/>')
    o.append(f'<path d="{poly(lf)}" fill="{P["inner_l"]}"/>')
    o.append(f'<path d="{poly(rf)}" fill="{P["inner_r"]}"/>')
    o.append(f'<path d="{vault}" fill="{P["soffit"]}"/>')
    # coffers: lines along the depth and two intermediate arcs
    cof = []
    c0 = A(0, SPRING)
    for k in range(1, 12):
        a = math.radians(180 - 15 * k)
        p0 = A(15 * math.cos(a), SPRING + 15 * math.sin(a))
        p1 = back_fn(15 * math.cos(a), SPRING + 15 * math.sin(a))
        cof.append(f"M{pp(*p0)}L{pp(*p1)}")
    for j in (1, 2):
        z = DEPTH * j / 3
        pa, pb = persp(-15, SPRING, z), persp(15, SPRING, z)
        r = (pb[0] - pa[0]) / 2
        cof.append(f"M{pp(*pa)}A{fm(r)} {fm(r)} 0 0 1 {pp(*pb)}")
        cof.append(f"M{pp(*persp(-15, 0, z))}L{pp(*pa)}M{pp(*persp(15, 0, z))}L{pp(*pb)}")
    o.append(f'<path d="{"".join(cof)}" fill="none" stroke="{P["soffit_line"]}" stroke-width="1.1"/>')
    o.append(f'<path d="{body}" fill="{P["stone"]}" fill-rule="evenodd"/>')

    bands = []          # shade under projections (light: sun from the west, high-ish; dark: floodlit)

    def hb(y0, y1, x0, x1):
        p, q = A(x0, y1), A(x1, y0)
        bands.append(f"M{pp(*p)}H{fm(q[0])}V{fm(q[1])}H{fm(p[0])}Z")
    hb(2.6, 3.0, -31.8, 31.8)                       # plinth cap shadow
    for s in (-1, 1):
        x0, x1 = sorted((s * 15, s * 31.0))
        hb(30.1, 30.6, x0, x1)                      # under the impost
    hb(48.9, 49.4, -31.0, -17.6)
    hb(48.9, 49.4, 17.6, 31.0)
    hb(54.7, 55.6, -31.0, 31.0)                     # cornice shadow on the frieze
    hb(73.6, 74.4, -30.4, 30.4)                     # under the top cornice
    hb(58.6, 59.4, -32.7, 32.7)                     # cornice corona underside line
    lines = []
    for y, x0, x1 in [(3.7, -31.4, 31.4), (32.4, -31.0, -15), (32.4, 15, 31.0), (49.4, -31, 31), (50.8, -31, 31),
                      (52.0, -31, 31), (56.6, -32.7, 32.7), (60.6, -30.9, 30.9), (61.8, -24.6, 24.6),
                      (73.0, -24.6, 24.6), (76.1, -31.3, 31.3)]:
        p, q = A(x0, y), A(x1, y)
        lines.append(f"M{pp(*p)}H{fm(q[0])}")
    for x in (-24.6, 24.6):
        p, q = A(x, 61.8), A(x, 73.0)
        lines.append(f"M{pp(*p)}V{fm(q[1])}")
    # archivolt outer edge
    pa, pb = A(-17.3, SPRING), A(17.3, SPRING)
    lines.append(f"M{pp(*pa)}A{fm(17.3 * U)} {fm(17.3 * U)} 0 0 1 {pp(*pb)}")
    pa, pb = A(-16.1, SPRING), A(16.1, SPRING)
    lines.append(f"M{pp(*pa)}A{fm(16.1 * U)} {fm(16.1 * U)} 0 0 1 {pp(*pb)}")
    # pier panels
    for s in (-1, 1):
        xa, xb = sorted((s * 18.4, s * 27.6))
        p, q = A(xa, 28.6), A(xb, 5.4)
        lines.append(f"M{pp(*p)}H{fm(q[0])}V{fm(q[1])}H{fm(p[0])}Z")
    o.append(f'<path d="{"".join(lines)}" fill="none" stroke="{P["line"]}" stroke-width="1.3"/>')
    # recessed panel shadow strips (left and top inner edges, light from the west)
    strips = []
    for s in (-1, 1):
        xa, xb = sorted((s * 18.4, s * 27.6))
        p, q = A(xa, 28.6), A(xa + 0.55, 5.4)
        strips.append(f"M{pp(*p)}H{fm(q[0])}V{fm(q[1])}H{fm(p[0])}Z")
        p, q = A(xa, 28.6), A(xb, 28.05)
        strips.append(f"M{pp(*p)}H{fm(q[0])}V{fm(q[1])}H{fm(p[0])}Z")
    # keystone
    key = [A(-1.9, 44.4), A(1.9, 44.4), A(2.5, 51.0), A(-2.5, 51.0)]
    ks = [A(1.9, 44.4), A(2.5, 51.0), A(3.1, 50.6), A(2.3, 44.4)]
    relief_sh, relief_body = relief_svg(P)
    o.append(f'<path d="{"".join(bands)}{"".join(strips)}{poly(ks)}{relief_sh}" fill="{P["band"]}"/>')
    o.append(f'<path d="{poly(key)}" fill="{P["stone_hi"]}" stroke="{P["line"]}" stroke-width="1.2"/>')
    # dentils under the cornice: one dashed stroke
    p, q = A(-30.8, 55.9), A(30.8, 55.9)
    o.append(f'<path d="M{pp(*p)}H{fm(q[0])}" stroke="{P["stone_dk"]}" stroke-width="{fm(0.55 * U)}" '
             f'stroke-dasharray="{fm(0.55 * U)} {fm(0.5 * U)}"/>')
    # frieze: thirteen stars
    st = []
    for i in range(13):
        x = -27.6 + i * 4.6
        cx, cy = A(x, 54.1)
        st.append(star(cx, cy, 1.15 * U, 0.46 * U))
    o.append(f'<path d="{"".join(st)}" fill="{P["stone_dk"]}"/>')
    # attic inscription: three lines of carved letters, a short signature line
    ins = []
    for y, wft in ((70.9, 44.0), (68.2, 46.0), (65.5, 38.0), (63.0, 15.0)):
        x = -wft / 2
        segs = []
        while x < wft / 2 - 0.6:
            wl = rng.choice((0.62, 0.7, 0.78, 0.86, 0.5))
            segs.append((x, wl))
            x += wl + 0.32
            if rng.random() < 0.16:
                x += 0.75
        p = A(segs[0][0], y)
        s = f"M{pp(*p)}"
        cur = segs[0][0]
        for xs, wl in segs:
            if xs > cur + 1e-6:
                s += f"m{fm((xs - cur) * U)} 0"
            s += f"h{fm(wl * U)}"
            cur = xs + wl
        ins.append(s)
    o.append(f'<path d="{"".join(ins)}" stroke="{P["stone_dk"]}" stroke-width="{fm(1.25 * U)}"/>')
    o.append(relief_body)
    return "\n".join(o)


def sun_altaz(lat, lon, utc_hours, doy):
    """NOAA approximation of the sun's elevation and azimuth (degrees; azimuth from north, clockwise)."""
    g = 2 * math.pi / 365 * (doy - 1 + (utc_hours - 12) / 24)
    eq = 229.18 * (0.000075 + 0.001868 * math.cos(g) - 0.032077 * math.sin(g) - 0.014615 * math.cos(2 * g)
                   - 0.040849 * math.sin(2 * g))
    dec = (0.006918 - 0.399912 * math.cos(g) + 0.070257 * math.sin(g) - 0.006758 * math.cos(2 * g)
           + 0.000907 * math.sin(2 * g) - 0.002697 * math.cos(3 * g) + 0.00148 * math.sin(3 * g))
    ha = math.radians((utc_hours * 60 + eq + 4 * lon) / 4 - 180)
    la = math.radians(lat)
    cz = math.sin(la) * math.sin(dec) + math.cos(la) * math.cos(dec) * math.cos(ha)
    el = 90 - math.degrees(math.acos(max(-1.0, min(1.0, cz))))
    az = math.degrees(math.atan2(math.sin(ha), math.cos(ha) * math.sin(la) - math.tan(dec) * math.cos(la))) + 180
    return el, az % 360


def _arc_polys(d):
    """Polygons (arcs sampled) from path data written by arcs_d: M, relative circular arcs, Z."""
    polys, cur, start, poly_ = [], None, None, []
    for cmd, args in re.findall(r"([MaZ])([^MaZ]*)", d):
        if cmd == "M":
            x, y = (float(v) for v in re.findall(r"-?\d*\.?\d+", args))
            cur, start, poly_ = (x, y), (x, y), [(x, y)]
        elif cmd == "a":
            m = re.match(r"(\d+) (\d+) 0 ([01])([01])(-?\d+)\s?(-?\d+)", args)
            r = float(m.group(1))
            large, sweep = int(m.group(3)), int(m.group(4))
            x1, y1 = cur[0] + float(m.group(5)), cur[1] + float(m.group(6))
            dx, dy = (x1 - cur[0]) / 2, (y1 - cur[1]) / 2
            q = math.hypot(dx, dy)
            r = max(r, q)
            h = math.sqrt(max(0.0, r * r - q * q))
            sgn = 1 if large != sweep else -1
            ux, uy = (-dy / q, dx / q) if q else (0, 0)
            cx, cy = cur[0] + dx + sgn * h * ux, cur[1] + dy + sgn * h * uy
            a0, a1 = math.atan2(cur[1] - cy, cur[0] - cx), math.atan2(y1 - cy, x1 - cx)
            da = (a1 - a0) % (2 * math.pi) if sweep else -((a0 - a1) % (2 * math.pi))
            n = max(2, int(abs(da) / 0.2))
            poly_ += [(cx + r * math.cos(a0 + da * k / n), cy + r * math.sin(a0 + da * k / n)) for k in range(1, n + 1)]
            cur = (x1, y1)
        elif cmd == "Z":
            polys.append(poly_)
            cur = start
    return polys


def _seg_dist(p, a, b):
    (ax, ay), (bx, by) = a, b
    L2 = (bx - ax) ** 2 + (by - ay) ** 2
    t = 0.0 if L2 == 0 else max(0.0, min(1.0, ((p[0] - ax) * (bx - ax) + (p[1] - ay) * (by - ay)) / L2))
    return math.hypot(p[0] - ax - t * (bx - ax), p[1] - ay - t * (by - ay))


def _inside(polys, px, py):
    c = False
    for pts in polys:
        for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
            if (y0 > py) != (y1 > py) and px < x0 + (py - y0) * (x1 - x0) / (y1 - y0):
                c = not c
    return c


def check_scenery(out_dir, data):
    sd = data.get("scenery", {})
    print("== scenery: light")
    u = _unit(*SUN)
    gx_, gz_ = u[0] / SF, -u[1] / (SF * SE)              # ground metres per page unit along SUN (east, north)
    per = math.hypot(gx_, gz_)
    el = math.degrees(math.atan(1 / (SHADOW_K * SF * CE * per)))
    az = (math.degrees(math.atan2(gx_, gz_)) + 180) % 360
    print(f"  every cast shadow runs along SUN and is {SHADOW_K} x the caster's height on the page: the sun stands "
          f"{el:.1f} deg up at azimuth {az:.0f} deg")
    best = None
    for k in range(16 * 60, 23 * 60):
        e, a = sun_altaz(40.7308, -73.9973, k / 60, 298)
        if best is None or abs(e - el) < abs(best[1] - el):
            best = (k, e, a)
    k, e, a = best
    print(f"  the real sun over Washington Square (40.731 N, 73.997 W) on 25 Oct 2026 is {e:.1f} deg up at "
          f"{(k // 60 - 16):d}:{k % 60:02d} pm EDT, azimuth {a:.0f} deg ({abs(a - az):.0f} deg from the drawing's)")
    kk = SHADOW_K * SF * CE
    for (bx, by), ht, h0, h1, rc in WEST_TREES:
        print(f"  tree west of the frame at x={bx}: trunk shadow {kk * ht:.0f} units, crown shadow {kk * (h1 - h0):.0f} "
              f"units long and {2 * rc * SF * SE * 1.25:.0f} across (stretched {kk * (h1 - h0) / (2.2 * 2 * rc * SF * SE * 1.25):.1f}x)")
    lamps = [f"{127 * s / 30 * SHADOW_K:.0f}" for x, y, s, _ in LAMPS]
    print(f"  lamp shadows {', '.join(lamps)} units (= {SHADOW_K} x post height)")
    print("== scenery: crowns")
    ms = tree_models()
    kinds = [m["kind"] for m in ms]
    print(f"  {kinds.count('plane')} London planes, {kinds.count('elm')} elms: {sum(len(m['clumps']) for m in ms)} clumps, "
          f"{sum(len(m['lobes']) - m['fillers'] for m in ms)} leafy lobes; {sum(m['fillers'] for m in ms)} enclosed "
          f"pockets between clumps filled, so no crown is pierced")
    for theme in ("light", "dark"):
        svg = open(os.path.join(out_dir, f"hero-{theme}.svg")).read()
        P = PAL[theme]
        tone_cols = {c for f in P["sc_fol"] for c in f[:2]}
        paths = [(c, d) for d, c in re.findall(r'<path d="(M[^"]*a[^"]*)" fill="(#[0-9A-F]{6})"/>', svg) if c in tone_cols]
        polys = [(c, _arc_polys(d)) for c, d in paths]
        narcs = sum(d.count("a") for c, d in paths)
        boxes = [m["box"] for m in ms]
        n_pts = n_multi = n_edge = 0
        for bx0, by0, bx1, by1 in boxes:
            y = by0 + 1.3
            while y < by1:
                x = bx0 + 1.1
                while x < bx1:
                    hits = [pl for c, pl in polys if _inside(pl, x, y)]
                    n_pts += 1
                    if len(hits) > 1:
                        dmin = min(_seg_dist((x, y), a, b) for pl in hits for pts_ in pl for a, b in zip(pts_, pts_[1:] + pts_[:1]))
                        if dmin < 1.0:
                            n_edge += 1
                        else:
                            n_multi += 1
                    x += 4.3
                y += 4.3
        sil_cols = {f[2] for f in P["sc_fol"]}
        holes = 0
        for d, c in re.findall(r'<path d="(M[^"]*a[^"]*)" fill="(#[0-9A-F]{6})"/>', svg):
            if c in sil_cols:
                pl = _arc_polys(d)
                holes += sum(1 for k, a in enumerate(pl) if any(j != k and _inside([b], *a[0]) for j, b in enumerate(pl)))
        print(f"  {theme}: crown silhouettes have {holes} enclosed holes; lit{' and lee-side' if theme == 'light' else ''} "
              f"tones in {len(paths)} paths, {narcs} arcs; {n_pts} sample points: {n_multi} inside two tones "
              f"({n_edge} within 1 unit of a shared edge, integer rounding)")
    print("== scenery: the Row, the arch, the paving, the flags")
    for theme in ("light", "dark"):
        print(f"  {theme}: {len(row_windows(theme))} Row windows drawn (the rest hide behind crowns or the arch)")
    pts = []
    for shape in VICTORY:
        cur = None
        for k, *v in shape:
            if k == "M" or k == "L":
                cur = (v[0], v[1])
                pts.append(cur)
            elif k in "QC":
                ctrl = [cur] + [(v[j], v[j + 1]) for j in range(0, len(v), 2)]
                for t in (i / 24 for i in range(1, 25)):
                    pp_ = ctrl
                    while len(pp_) > 1:
                        pp_ = [((1 - t) * a[0] + t * b[0], (1 - t) * a[1] + t * b[1]) for a, b in zip(pp_, pp_[1:])]
                    pts.append(pp_[0])
                cur = ctrl[-1]
    for cx, cy, r, ri in VICTORY_RINGS:
        pts += [(cx + r * math.cos(a), cy + r * math.sin(a)) for a in (i * math.pi / 12 for i in range(24))]
    clear = min(math.hypot(x, y - SPRING) for x, y in pts) - 17.3
    print(f"  Victories: {len(pts)} outline points, all above the archivolt (closest {clear:.2f} ft), below the frieze "
          f"band (top {max(y for _, y in pts):.2f} < 48.9 ft), inside the pier (x <= {max(x for x, _ in pts):.1f} < 31 ft)")
    cut = [r for r in PAVE_RINGS if FY - SF * r * SE < HORIZON + 1]
    print(f"  paving rings {PAVE_RINGS} m: {len(cut)} would cross the far edge of the plaza and are cut at y={HORIZON + 1:g}")
    fr = sd.get("flag_frames", 4)
    print(f"  NYU flags: one filmstrip of {fr} frames x 0.2 s = {fr * 0.2:.1f} s, {PERIOD / (fr * 0.2):.0f} waves per loop; "
          f"one animation element for both flags")


# ------------------------------------------------------------------ the vista up Fifth Avenue
def _opening_poly(n=40):
    """The far (north) mouth of the arch on the page, as a convex polygon (arc sampled)."""
    (x0, y0), (x1, y1) = back_fn(-OPEN_HW, 0), back_fn(-OPEN_HW, SPRING)
    (x2, y2), (x3, y3) = back_fn(OPEN_HW, SPRING), back_fn(OPEN_HW, 0)
    cx, r = (x1 + x2) / 2, (x2 - x1) / 2
    arc = [(cx - r * math.cos(math.pi * k / n), y1 - r * math.sin(math.pi * k / n)) for k in range(n + 1)]
    return [(x0, y0)] + arc + [(x3, y3)]


def _clip_convex(pts, clip):
    """Sutherland-Hodgman: polygon pts clipped to the convex polygon clip."""
    sgn = 1 if sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(clip, clip[1:] + clip[:1])) > 0 else -1
    out = pts
    for (ax, ay), (bx, by) in zip(clip, clip[1:] + clip[:1]):
        if not out:
            break
        def side(p):
            return sgn * ((bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax))
        inp, out = out, []
        for p, q in zip(inp, inp[1:] + inp[:1]):
            sp, sq = side(p), side(q)
            if sp >= 0:
                out.append(p)
            if (sp >= 0) != (sq >= 0):
                t = sp / (sp - sq)
                out.append((p[0] + (q[0] - p[0]) * t, p[1] + (q[1] - p[1]) * t))
    return out


def _clip_seg(a, b, clip):
    """Cyrus-Beck: the part of segment ab inside the convex polygon clip, or None."""
    sgn = 1 if sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(clip, clip[1:] + clip[:1])) > 0 else -1
    t0, t1 = 0.0, 1.0
    for (ax, ay), (bx, by) in zip(clip, clip[1:] + clip[:1]):
        def side(p):
            return sgn * ((bx - ax) * (p[1] - ay) - (by - ay) * (p[0] - ax))
        sa, sb = side(a), side(b)
        if sa < 0 and sb < 0:
            return None
        if sa < 0 or sb < 0:
            t = sa / (sa - sb)
            if sa < 0:
                t0 = max(t0, t)
            else:
                t1 = min(t1, t)
    if t1 <= t0:
        return None
    return ((a[0] + (b[0] - a[0]) * t0, a[1] + (b[1] - a[1]) * t0), (a[0] + (b[0] - a[0]) * t1, a[1] + (b[1] - a[1]) * t1))


def vista_svg(P, rng):
    """Fifth Avenue through the arch to the Empire State Building, in one-point perspective. Everything is clipped
    to the arch's far mouth here, in Python, so the page needs no clip path."""
    o = []
    clip = _opening_poly()

    def cp(pts, d=1):
        c = _clip_convex(pts, clip)
        return poly(c, d) if len(c) > 2 else ""
    vp = A(VPX, VPY)
    o.append(f'<path d="{opening_path(back_fn)}" fill="url(#vsky)"/>')
    xl, xr = clip[0][0], clip[-1][0]
    bot = clip[0][1]
    # ground: cross street, then the avenue converging
    o.append(f'<path d="{cp([(xl, vp[1]), (xr, vp[1]), (xr, bot), (xl, bot)])}" fill="{P["v_side"]}"/>')
    road = [persp(-35, 0, 30), persp(35, 0, 30), persp(35, 0, 60000), persp(-35, 0, 60000)]
    cross = [persp(-400, 0, 26), persp(400, 0, 26), persp(400, 0, 96), persp(-400, 0, 96)]
    o.append(f'<path d="{cp(road)}{cp(cross)}" fill="{P["v_street"]}"/>')
    # Empire State Building at 34th St: south face, west of the avenue
    zE, xE = 6900.0, -175.0
    prof = [(0, 80, 100), (80, 280, 76), (280, 1000, 58), (1000, 1035, 48), (1035, 1062, 40), (1062, 1100, 31),
            (1100, 1150, 21), (1150, 1240, 13), (1240, 1268, 8.5), (1268, 1298, 5), (1298, 1454, 1.4)]
    pts_l, pts_r = [], []
    for y0, y1, hw in prof:
        pts_r += [persp(xE + hw, y0, zE), persp(xE + hw, y1, zE)]
        pts_l += [persp(xE - hw, y0, zE), persp(xE - hw, y1, zE)]
    esb = pts_r + list(reversed(pts_l))
    o.append(f'<path d="{poly(esb, 2)}" fill="{P["v_esb"]}"/>')
    lit = []
    for y0, y1, hw in prof[:8]:
        a, b = persp(xE - hw, y0, zE), persp(xE - hw * 0.45, y1, zE)
        lit.append(f"M{pp(a[0], a[1], 2)}H{fm(b[0], 2)}V{fm(b[1], 2)}H{fm(a[0], 2)}Z")
    o.append(f'<path d="{"".join(lit)}" fill="{P["v_esb_lit"]}"/>')
    if P["night"]:
        a, b = persp(xE - 22, 1100, zE), persp(xE + 22, 1268, zE)
        o.append(f'<path d="M{pp(a[0], a[1], 2)}H{fm(b[0], 2)}V{fm(b[1], 2)}H{fm(a[0], 2)}Z" fill="#9B5CE0"/>')
        a, b = persp(xE - 9, 1240, zE), persp(xE + 9, 1298, zE)
        o.append(f'<path d="M{pp(a[0], a[1], 2)}H{fm(b[0], 2)}V{fm(b[1], 2)}H{fm(a[0], 2)}Z" fill="#C79BF0"/>')
    # facades along both sides: quads on the planes x = +-50 ft never overlap, so merge them by colour; three
    # steps of haze up the avenue
    night_lines = []
    for side in (-1, 1):
        z = 330.0
        by_col, lines = {}, []
        while z < 9000:
            ln = rng.uniform(110, 260) * (1 + z / 3000)
            h = rng.choice([70, 85, 100, 120, 140, 160, 190, 230]) * rng.uniform(0.9, 1.1)
            z0, z1 = z, z + ln
            haze = round(min(0.8, (z0 / 9000.0) ** 0.9) * 3) / 3
            cf = mix(P["v_lit"] if side > 0 else P["v_sh"], P["v_sky"], haze)
            xb = 50.0 * side
            q = [persp(xb, 0, z0), persp(xb, h, z0), persp(xb, h, z1), persp(xb, 0, z1)]
            by_col.setdefault(cf, []).append(cp(q))
            if z0 < 2600:
                for yy in range(14, int(h) - 6, 12):
                    s = _clip_seg(persp(xb, yy, z0), persp(xb, yy, z1), clip)
                    if s:
                        lines.append(f"M{pp(*s[0])}L{pp(*s[1])}")
            z = z1
        for col, ds in by_col.items():
            if "".join(ds):
                o.append(f'<path d="{"".join(ds)}" fill="{col}"/>')
        col = P["v_line"] if (side > 0 or P["night"]) else P["v_line2"]
        if P["night"]:
            night_lines += lines                       # lit windows: both sides share colour and dash
        else:
            o.append(f'<path d="{"".join(lines)}" stroke="{col}" stroke-width=".7" opacity=".7"/>')
    if night_lines:
        o.append(f'<path d="{"".join(night_lines)}" stroke="{P["v_line"]}" stroke-width=".9" stroke-dasharray="1.6 2.4" opacity=".85"/>')
    return "\n".join(o)


# ------------------------------------------------------------------ backdrop: towers, the Row, trees
ROW_YG = 434.0                                       # pavement line of Washington Square North
ROW_HIDE = 300                                       # the Row hides everything behind it below this line


def _cut(pts):
    """A backdrop silhouette ending at ROW_HIDE instead of the ground (the Row covers the rest)."""
    return [(x, min(y, ROW_HIDE)) for x, y in pts]
ONE5 = [(1392, 452), (1392, 206), (1404, 206), (1404, 170), (1418, 170), (1418, 140), (1432, 140), (1432, 112),
        (1446, 112), (1446, 96), (1474, 96), (1474, 112), (1488, 112), (1488, 140), (1502, 140), (1502, 170),
        (1516, 170), (1516, 206), (1528, 206), (1528, 452)]
NYU_E = (1540.0, 1612.0, 190.0)                      # an NYU building on Washington Square East: x0, x1, roof
NYU_POLES = [(NYU_E[0] + 14, NYU_E[2] - 3), (NYU_E[0] + 44, NYU_E[2] - 3)]
_ROW = {}


def _row_hidden(x, y, w, h):
    """True when a facade detail is hidden behind a crown or the arch."""
    if x > AX - 31.0 * U + 1 and x + w < AX + 31.0 * U - 1:
        return True
    return all(tree_cover(px, py, 1.0) for px, py in ((x, y), (x + w, y), (x, y + h), (x + w, y + h),
                                                     (x + w / 2, y + h / 2), (x + w / 2, y), (x + w / 2, y + h)))


def row_windows(theme):
    """Visible windows of the Row as (x, y, w, h), for anything that wants to light one up."""
    return _ROW.get(theme, [])


def flag_frames(n=3, length=17.0, drop=11.0):
    """NYU flag on a pole at the origin streaming west (the leaves drift west): a travelling wave, n frames."""
    out = []
    for f in range(n):
        ph = 2 * math.pi * f / n
        top, bot = [], []
        for k in range(7):
            u = k / 6
            yw = 1.9 * u * math.sin(2 * math.pi * (1.1 * u) - ph)
            x = -length * u * (1 - 0.06 * math.cos(2 * math.pi * 1.1 * u - ph) * u)
            top.append((x, yw))
            bot.append((x, drop * (1 - 0.1 * u) + yw * 1.15))
        out.append(top + bot[::-1])
    return out


def backdrop_svg(P, rng):
    o = []
    night = P["night"]
    theme = "dark" if night else "light"
    # hazy towers behind the Row: 2 Fifth Ave on the west, One Fifth Ave (1929, Art Deco) east of the arch
    o.append(f'<path d="M-10 {ROW_HIDE}V272H70V250H190V262H232V236H330V{ROW_HIDE}Z" fill="{P["haze"]}"/>')
    nx0, nx1, ny0 = NYU_E
    o.append(f'<path d="{poly(_cut(ONE5))}M{fm(nx0)} {ROW_HIDE}V{fm(ny0)}H{fm(nx1)}V{ROW_HIDE}Z" fill="{P["haze2"]}"/>')
    lit = [(1392, 452), (1392, 206), (1404, 206), (1404, 170), (1418, 170), (1418, 140), (1432, 140), (1432, 112),
           (1446, 112), (1446, 96), (1452, 96), (1452, 452)]
    ledges = "".join(f"M{xa} {y - 1}H{xb}v2H{xa}Z" for (xa, y), (xb, y2) in zip(ONE5, ONE5[1:]) if y == y2 and y < 450)
    o.append(f'<path d="{poly(_cut(lit))}{ledges}M{fm(nx0 - 2)} {fm(ny0 - 3)}H{fm(nx1)}V{fm(ny0)}H{fm(nx0 - 2)}Z" '
             f'fill="{P["haze_lit"]}"/>')
    # its brick piers run unbroken to the setbacks; each setback ledge catches the light
    piers = []
    for x in range(1458, 1527, 6):
        top = min(y for (xa, y), (xb, _) in zip(ONE5, ONE5[1:]) if xa <= x <= xb and xa != xb) if False else None
        ys = [y for (xa, y), (xb, y2) in zip(ONE5, ONE5[1:]) if y == y2 and min(xa, xb) <= x <= max(xa, xb)]
        piers.append(f"M{x} {min(ys) + 3}V{ROW_HIDE}")
    for x in range(1397, 1452, 6):
        ys = [y for (xa, y), (xb, y2) in zip(ONE5, ONE5[1:]) if y == y2 and min(xa, xb) <= x <= max(xa, xb)]
        piers.append(f"M{x} {min(ys) + 3}V{ROW_HIDE}")
    nx0, nx1, ny0 = NYU_E
    piers += [f"M{fm(x)} {y}v8" for y in range(199, 250, 13) for x in (nx0 + 7, nx0 + 17, nx0 + 27, nx0 + 37, nx0 + 47,
                                                                        nx0 + 57, nx0 + 66)]
    o.append(f'<path d="{"".join(piers)}" stroke="{P["sc_pier"]}" stroke-width="1.6"/>')
    if night:
        wl = []
        for y in range(120, 440, 9):
            for x in range(1452, 1520, 9):
                if rng.random() < 0.32 and (y > 210 or 1438 < x < 1482) and y < ROW_HIDE:
                    wl.append(f"M{x + 1} {y}h2.4v4.6h-2.4Z")
        o.append(f'<path d="{"".join(wl)}" fill="#E7B865" opacity=".75"/>')
    # the Row: Greek Revival red brick on Washington Square North, frontal, beyond the arch
    yg, ytop = ROW_YG, 284.0
    houses = []
    x = 1050.0
    while x > -80:
        w = rng.uniform(66, 82)
        houses.append((x - w, x, ytop + rng.uniform(-6, 10)))
        x -= w
    x = 1334.0
    while x < 1680:
        w = rng.uniform(66, 82)
        houses.append((x, x + w, ytop + rng.uniform(-6, 10)))
        x += w
    drnd = random.Random(1833)                         # the Row's details (keeps the shared sequence as it was)
    L = {k: [] for k in ("brick", "lime", "trim", "lintel", "win", "glint", "lit", "chim", "sh", "lsh", "door",
                         "marble", "iron", "fence", "transom", "rail")}
    windows = []
    for i, (x0, x1, yt) in enumerate(houses):
        yt = round(ytop + 0.35 * (yt - ytop))          # the Row keeps an almost even cornice line
        x0, x1 = round(x0), round(x1)
        stone = rng.random() < 0.18
        L["lime" if stone else "brick"].append(f"M{x0} {yt}H{x1}V{fm(yg)}H{x0}Z")
        L["trim"].append(f"M{x0 - 2} {yt - 7}H{x1 + 2}v3H{x0 - 2}ZM{x0 - 1} {yt - 4}H{x1 + 1}V{yt}H{x0 - 1}Z")
        if not night:
            L["lsh" if stone else "sh"].append(f"M{x0} {yt}H{x1}v2H{x0}Z")
        if rng.random() < 0.6:
            cx = round(rng.uniform(x0 + 8, x1 - 16))
            L["chim"].append(f"M{cx} {yt - 7}V{yt - 22}h9V{yt - 7}Z")
        bw = (x1 - x0) / 3
        door_bay = 0 if i % 2 == 0 else 2
        for fl in range(4):
            wy = yt + 12 + fl * 34
            for b in range(3):
                wx = round(x0 + b * bw + bw / 2 - 5.4)
                r = rng.random()
                if fl == 3 and b == door_bay:
                    continue
                if _row_hidden(wx - 1.5, wy - 3, 14, 23):
                    continue
                windows.append((wx, wy, 11, 20))
                L["win"].append(f"M{wx + 5.5} {wy}v20")             # windows are 11-wide strokes
                L["lintel"].append(f"M{wx - 1.5} {wy - 1.5}h14")
                if not night and r < 0.16:
                    L["glint"].append(f"M{wx + 5.5} {wy}v9")
                if night and r < 0.42:
                    L["lit"].append(f"M{wx + 5.5} {wy}v20")
        # parlor-floor entrance: marble portico (two columns and an entablature), door and transom, a marble
        # stoop with iron railings; an areaway with basement windows behind an iron fence
        wy3 = yt + 12 + 3 * 34
        dx = round(x0 + door_bay * bw + bw / 2 - 6)
        sill = wy3 + 21
        sh = round(yg - sill)
        if not _row_hidden(dx - 6, wy3 - 8, 24, yg - wy3 + 8):
            L["door"].append(f"M{dx} {wy3 + 3}h12v18h-12Z")
            L["transom" if night else "glint"].append(f"M{dx + 6} {wy3}v3")
            L["marble"].append(f"M{dx - 5} {wy3 - 6}h22v4h-22Z"                            # entablature
                               f"M{dx - 4} {wy3 - 2}h3v23h-3ZM{dx + 13} {wy3 - 2}h3v23h-3Z"
                               f"M{dx - 4} {sill}h20l3 {sh}h-26Z")                          # stoop
            L["lsh"].append(f"M{dx - 5} {sill + sh / 3:g}h22v1h-22ZM{dx - 6} {sill + 2 * sh / 3:g}h24v1h-24Z")
            L["door"].append(f"M{dx - 5.6} {sill - 7}h1.3V{fm(yg)}h-1.3ZM{dx + 16.4} {sill - 7}h1.3V{fm(yg)}h-1.3Z")
            if not night:                                # the portico throws its shadow east on the brick
                L["lsh" if stone else "sh"].append(f"M{dx + 16} {wy3 - 2}h3v23h-3ZM{dx + 17} {wy3 - 6}h3v4h-3Z")
        # areaway: basement windows and the iron fence, both sides of the stoop
        for b in range(3):
            if b == door_bay:
                continue
            bx = round(x0 + b * bw + bw / 2 - 5.4)
            if not _row_hidden(bx - 3, yg - 11, 17, 11):
                L["win"].append(f"M{bx + 5.5} {fm(yg - 10)}v6")
        fx0, fx1 = (dx + 18, x1) if door_bay == 0 else (x0, dx - 6)
        if not _row_hidden(fx0, yg - 8, fx1 - fx0, 8):
            L["fence"].append(f"M{fx0} {fm(yg - 8)}H{fx1}")
            L["door"].append(f"M{fx0} {fm(yg - 8.7)}H{fx1}v1.4H{fx0}Z")
    L["door"] += [f"M{pp(x - 0.6, y - 27)}h1.2v27h-1.2Z" for x, y in NYU_POLES]       # flagpoles
    # pavement and street in front of the Row (by day the street shares the stone-shade path; at night the stoop
    # steps share the street's)
    street = f"M-10 {fm(yg)}H1610V446H-10Z"
    if night:
        o.append(f'<path d="{street}{"".join(L["lsh"])}" fill="{P["sc_street"]}"/>')
        L["lsh"] = []
    else:
        L["lsh"].insert(0, street)
    L["marble"].append(f"M-10 {fm(yg)}H1610v3.5H-10Z")                       # the pavement
    o.append(f'<path d="{"".join(L["brick"])}" fill="{P["brick"]}"/>')
    o.append(f'<path d="{"".join(L["lime"])}" fill="{P["lime"]}"/>')
    o.append(f'<path d="{"".join(L["chim"] + L["sh"])}" fill="{P["brick_dk"]}"/>')
    o.append(f'<path d="{"".join(L["trim"])}" fill="{P["trim"]}"/>')
    o.append(f'<path d="{"".join(L["lintel"])}" stroke="{P["trim"]}" stroke-width="3"/>')
    o.append(f'<path d="{"".join(L["win"])}" stroke="{P["win"]}" stroke-width="11"/>')
    if L["glint"]:
        o.append(f'<path d="{"".join(L["glint"])}" stroke="{P["glint"]}" stroke-width="11"/>')
    o.append(f'<path d="{"".join(L["door"])}" fill="{P["sc_iron"]}"/>')
    if L["lit"] or L["transom"]:
        o.append(f'<path d="{"".join(L["lit"] + L["transom"])}" stroke="#F1C470" stroke-width="11"/>')
    o.append(f'<path d="{"".join(L["marble"])}" fill="{P["sc_marble"]}"/>')
    if L["lsh"]:
        o.append(f'<path d="{"".join(L["lsh"])}" fill="{P["sc_lime_sh"]}"/>')      # street, shade on stone, steps
    # the areaway fences' pickets: one dashed stroke
    pick = "".join(s.replace(f" {fm(yg - 8)}H", f" {fm(yg - 4)}H") for s in L["fence"])
    o.append(f'<path d="{pick}" stroke="{P["sc_iron"]}" stroke-width="8" stroke-dasharray="1.4 4.6"/>')
    _ROW[theme] = windows
    return "\n".join(o)


def nyu_flags_svg(P, data=None):
    """Two NYU flags streaming west from poles on the roof of the building on Washington Square East: one tiny
    3-frame filmstrip for both (0.2 s per frame, 0.6 s cycle)."""
    frames = []
    for fr in flag_frames():
        frames.append("".join(poly([(x + px - 0.6, y + py - 26) for x, y in fr]) for px, py in NYU_POLES))
    if data is not None:
        data["scenery"] = dict(flag_frames=len(frames))
    return (filmstrip([f'<path d="{d}"/>' for d in frames], 0.2 * len(frames), attrs=f' class="anim" fill="{P["banner"]}"')
            + f'<path class="still" fill="{P["banner"]}" d="{frames[1]}"/>')


def crown(rng, cx, cy, rx, ry, k):
    cs = []
    for _ in range(k):
        while True:
            u, v = rng.uniform(-1, 1), rng.uniform(-1, 1)
            if u * u + v * v <= 1:
                break
        wf = 0.82 + 0.18 * (-v)                        # elm: a vase, wider at the top
        r = rng.uniform(0.21, 0.33) * min(rx, ry)
        cs.append((cx + u * (rx - r * 0.75) * wf, cy + v * (ry - r * 0.8), r))
    return cs


def cpath(cs, d=1):
    return "".join(f"M{pp(x - r, y, d)}a{fm(r, d)} {fm(r, d)} 0 1 0 {fm(2 * r, d)} 0a{fm(r, d)} {fm(r, d)} 0 1 0 {fm(-2 * r, d)} 0"
                   for x, y, r in cs)


TREES_L = [(52, 462, 328, 112, 94, 0), (214, 466, 330, 98, 98, 2), (356, 460, 330, 100, 88, 1),
           (516, 465, 346, 90, 78, 3), (660, 460, 318, 104, 102, 0), (808, 464, 340, 96, 84, 1),
           (944, 462, 354, 76, 72, 2)]
TREES_R = [(1452, 462, 346, 84, 84, 3), (1566, 466, 318, 100, 104, 1)]


# Crowns are drawn the way an illustrator inks them: five to seven big clumps (London planes as broad domes, elms
# as vases), a scalloped leafy edge of small lobes that take the tone of their clump, a gap or two of sky with a twig
# across, and a branching skeleton that shows below the crown. Light, golden hour: the side of the crown facing the
# low sun is lit (every point from which a step towards the sun leaves the crown), front clumps catch a lit lens of
# their own, and every clump has a shade crescent on its far side, bigger low down and in the back. Night: the crowns
# are dark masses whose edges facing a park lamp glow. Each tone is the exact boundary of a boolean region over discs,
# traced as circular arcs by a small arrangement routine (arc_loops), so each tone of each tree is a few clean outlines
# that never overlap another tone: crisp at any size and cheap to rasterise.
TREE_KIND = ("plane", "elm", "plane", "plane", "elm", "plane", "plane", "plane", "elm")
TREE_SUN2 = (-0.92, -0.40)              # towards the low western sun, on the page
TREE_SHADE2 = (0.62, 0.78)              # the far side of a clump: east and below
TREE_CELL = 16.0


def _unit(x, y):
    m = math.hypot(x, y) or 1.0
    return x / m, y / m


def _tree_model(i):
    """Clumps (cx, cy, r, z), lobes (cx, cy, r, clump), gaps and limbs of tree i; the same in both themes."""
    x, yb, cy, rx, ry, fi = (TREES_L + TREES_R)[i]
    kind = TREE_KIND[i]
    rnd = random.Random(4100 + i)
    C = (x + rnd.uniform(-0.05, 0.05) * rx, cy + 0.04 * ry)
    m0 = min(rx, ry)
    flip = rnd.choice((-1, 1))
    if kind == "plane":   # (angle, radial factor, size factor, depth)
        spec = [(-118, .42, .43, 1.7), (-52, .44, .45, 1.5), (178, .5, .37, 1.1), (4, .52, .38, 1.0),
                (138, .42, .35, 2.3), (44, .44, .34, 2.1), (-86, .58, .3, .6)]
    else:
        spec = [(-130, .5, .38, 1.5), (-50, .5, .38, 1.4), (-90, .52, .33, .7), (-166, .64, .3, 1.0),
                (-14, .64, .3, 1.1), (152, .6, .25, 1.9), (28, .6, .25, 2.0)]
    clumps = []
    for a, f, s, z in spec:
        a = 180 - a if flip < 0 else a
        ar = math.radians(a + rnd.uniform(-8, 8))
        ff = f * rnd.uniform(0.94, 1.06)
        clumps.append((C[0] + ff * rx * math.cos(ar), C[1] + ff * ry * math.sin(ar), s * m0 * rnd.uniform(0.9, 1.1),
                       z + rnd.uniform(-0.15, 0.15)))
    # leafy lobes along the exposed rim of every clump
    lobes = []
    for k, (cx, cy_, r, z) in enumerate(clumps):
        t = rnd.uniform(0, 0.4)
        while t < 2 * math.pi:
            rs = m0 * rnd.uniform(0.095, 0.14)
            px, py = cx + (r - 0.3 * rs) * math.cos(t), cy_ + (r - 0.3 * rs) * math.sin(t)
            rim = (cx + r * math.cos(t), cy_ + r * math.sin(t))
            hidden = any((rim[0] - c[0]) ** 2 + (rim[1] - c[1]) ** 2 < (c[2] - 1) ** 2 for j, c in enumerate(clumps) if j != k)
            low = math.sin(t) > 0.55 and kind == "plane"
            if not hidden and not low and rnd.random() < 0.9:
                lobes.append((px, py, rs, k))
            t += (2.0 * rs / r) * rnd.uniform(0.9, 1.25)
    # the skeleton: trunk to a fork, two or three limbs, each forking again towards the clumps; twigs across the gaps
    fork = (x + rnd.uniform(-2, 2), C[1] + (0.52 if kind == "plane" else 0.9) * ry)
    order = sorted(range(len(clumps)), key=lambda k: clumps[k][0])
    groups = [order[:3], order[3:5], order[5:]] if kind == "elm" else [order[:2], order[2:5], order[5:]]
    limbs = []
    for g in groups:
        if not g:
            continue
        mx = sum(clumps[k][0] for k in g) / len(g)
        my = sum(clumps[k][1] for k in g) / len(g)
        mid = (fork[0] + (mx - fork[0]) * 0.5, fork[1] + (my - fork[1]) * 0.5)
        limbs.append((fork, mid, 5.6 if kind == "plane" else 5.2, 3.6, rnd.uniform(-0.12, 0.12)))
        for k in g:
            cx, cy_, r, z = clumps[k]
            limbs.append((mid, (cx + rnd.uniform(-0.2, 0.2) * r, cy_ + 0.1 * r), 3.6, 1.4, rnd.uniform(-0.15, 0.15)))
    ntwig = len(limbs)
    holes, bites = [], []                            # no enclosed gaps: the crown is never pierced
    fillers = _pocket_fillers(clumps, lobes)
    lobes += fillers
    cs = clumps + lobes
    box = (min(c[0] - c[2] for c in cs), min(c[1] - c[2] for c in cs), max(c[0] + c[2] for c in cs),
           max(c[1] + c[2] for c in cs))
    m = dict(x=x, yb=yb, C=C, rx=rx, ry=ry, m0=m0, fi=fi, kind=kind, clumps=clumps, lobes=lobes, holes=holes,
             bites=bites, fork=fork, limbs=limbs, ntwig=ntwig, box=box, fillers=len(fillers))
    # spatial buckets for the point tests
    grid = {}
    for kind_, lst in (("c", clumps), ("l", lobes)):
        for k, c in enumerate(lst):
            for gx in range(int((c[0] - c[2]) // TREE_CELL), int((c[0] + c[2]) // TREE_CELL) + 1):
                for gy in range(int((c[1] - c[2]) // TREE_CELL), int((c[1] + c[2]) // TREE_CELL) + 1):
                    grid.setdefault((gx, gy), ([], []))[0 if kind_ == "c" else 1].append(k)
    m["grid"] = grid
    return m


_TREES = {}


def _pocket_fillers(clumps, lobes, h=2.0):
    """Discs that fill every pocket enclosed by a crown's clumps and lobes (found on a grid: uncovered cells the
    outside cannot reach), each owned by the nearest clump, so a crown never shows an enclosed hole."""
    discs = [c[:3] for c in clumps] + [c[:3] for c in lobes]
    x0 = min(c[0] - c[2] for c in discs) - 2 * h
    y0 = min(c[1] - c[2] for c in discs) - 2 * h
    nx = int((max(c[0] + c[2] for c in discs) - x0) / h) + 3
    ny = int((max(c[1] + c[2] for c in discs) - y0) / h) + 3
    cov = [[False] * nx for _ in range(ny)]
    for cx, cy, r in discs:
        for j in range(max(0, int((cy - r - y0) / h)), min(ny, int((cy + r - y0) / h) + 2)):
            dy = y0 + j * h - cy
            for i in range(max(0, int((cx - r - x0) / h)), min(nx, int((cx + r - x0) / h) + 2)):
                if (x0 + i * h - cx) ** 2 + dy * dy < r * r:
                    cov[j][i] = True
    seen = [[False] * nx for _ in range(ny)]
    stack = [(i, j) for i in range(nx) for j in (0, ny - 1)] + [(i, j) for j in range(ny) for i in (0, nx - 1)]
    while stack:
        i, j = stack.pop()
        if 0 <= i < nx and 0 <= j < ny and not seen[j][i] and not cov[j][i]:
            seen[j][i] = True
            stack += [(i + 1, j), (i - 1, j), (i, j + 1), (i, j - 1)]
    out = []
    for j in range(ny):
        for i in range(nx):
            if cov[j][i] or seen[j][i]:
                continue
            comp, stack = [], [(i, j)]
            while stack:
                a, b = stack.pop()
                if 0 <= a < nx and 0 <= b < ny and not seen[b][a] and not cov[b][a]:
                    seen[b][a] = True
                    comp.append((x0 + a * h, y0 + b * h))
                    stack += [(a + 1, b), (a - 1, b), (a, b + 1), (a, b - 1)]
            mx = sum(p[0] for p in comp) / len(comp)
            my = sum(p[1] for p in comp) / len(comp)
            r = max(math.hypot(p[0] - mx, p[1] - my) for p in comp) + 1.5 * h
            k = min(range(len(clumps)), key=lambda q: math.hypot(clumps[q][0] - mx, clumps[q][1] - my) - clumps[q][2])
            out.append((mx, my, r, k))
    return out


def _limb_dist(p, limb):
    """Distance from p to a limb's centre line (the quadratic of _limb)."""
    (ax, ay), (bx, by), w0, w1, bend = limb
    L = math.hypot(bx - ax, by - ay) or 1.0
    cx, cy = (ax + bx) / 2 - (by - ay) / L * bend * L, (ay + by) / 2 + (bx - ax) / L * bend * L
    best = 1e9
    for k in range(11):
        t = k / 10
        x = (1 - t) ** 2 * ax + 2 * (1 - t) * t * cx + t * t * bx
        y = (1 - t) ** 2 * ay + 2 * (1 - t) * t * cy + t * t * by
        best = min(best, math.hypot(p[0] - x, p[1] - y) - (w0 + (w1 - w0) * t) / 2)
    return best


def tree_models():
    if not _TREES:
        for i in range(len(TREES_L + TREES_R)):
            _TREES[i] = _tree_model(i)
    return [_TREES[i] for i in range(len(_TREES))]


def _owner(m, px, py, gaps=True):
    """Clump that owns a page point of tree m (front clump, else the clump of the lobe), or -1 (outside, or sky)."""
    cell = m["grid"].get((int(px // TREE_CELL), int(py // TREE_CELL)))
    if cell is None:
        return -1
    for hx, hy, hr in (m["holes"] if gaps else ()):
        if (px - hx) ** 2 + (py - hy) ** 2 < hr * hr and \
                not any((px - bx) ** 2 + (py - by) ** 2 < br * br for bx, by, br in m["bites"]):
            return -1
    best, bz = -1, -1e9
    cl = m["clumps"]
    for k in cell[0]:
        cx, cy, r, z = cl[k]
        if z > bz and (px - cx) ** 2 + (py - cy) ** 2 < r * r:
            best, bz = k, z
    if best >= 0:
        return best
    lo = m["lobes"]
    for k in cell[1]:
        cx, cy, r, kk = lo[k]
        if (px - cx) ** 2 + (py - cy) ** 2 < r * r:
            return kk
    return -1


def _in_clumps(m, px, py):
    """Inside one of tree m's big clumps (lobes and gaps ignored): the light's view of the crown's mass."""
    return any((px - cx) ** 2 + (py - cy) ** 2 < r * r for cx, cy, r, z in m["clumps"])


def _in_shrunk(m, px, py, d):
    """Inside tree m's silhouette shrunk by d units (gaps grown by d)."""
    if m["grid"].get((int(px // TREE_CELL), int(py // TREE_CELL))) is None:
        return False
    for hx, hy, hr in m["holes"]:
        if (px - hx) ** 2 + (py - hy) ** 2 < (hr + d) ** 2 and \
                not any((px - bx) ** 2 + (py - by) ** 2 < max(0.0, br - d) ** 2 for bx, by, br in m["bites"]):
            return False
    return any((px - cx) ** 2 + (py - cy) ** 2 < max(0.0, r - d) ** 2 for cx, cy, r, *_ in m["clumps"] + m["lobes"])


def tree_cover(px, py, margin=0.0):
    """True if the page point lies inside some crown, gaps excluded (margin > 0: and stays inside a disc that far)."""
    for m in tree_models():
        if _owner(m, px, py) >= 0:
            if margin <= 0:
                return True
            if all(_owner(m, px + margin * math.cos(a), py + margin * math.sin(a)) >= 0 for a in (0, 1.57, 3.14, 4.71)):
                return True
    return False


def _cap(cx, cy, r, w, horn, u):
    """Disc whose outside, within the clump (cx, cy, r), is a cap of width w*r on side u ending at +-horn rad."""
    s = (1 - (1 - w) ** 2) / (2 * (1 - w - math.cos(horn)))
    rho = 1 - w + s
    return cx - s * r * u[0], cy - s * r * u[1], rho * r


def _tone_setup(m, theme):
    """Per clump lit lens and shade disc; plus the crown-level light shift and, at night, the lamp that lights it."""
    C, rx, ry, m0 = m["C"], m["rx"], m["ry"], m["m0"]
    zs = [c[3] for c in m["clumps"]]
    zlo, zhi = min(zs), max(zs)
    lens, shade = [], []
    lamp = None
    if theme == "dark":
        best = None
        for lx, ly, sc, _ in LAMPS:
            gx, gy = lx, ly - 116 * sc / 30.0
            d = math.hypot(gx - C[0], gy - C[1])
            if best is None or d < best[0]:
                best = (d, gx, gy)
        if best[0] < 330:
            lamp = (best[1], best[2], 250.0)
    for cx, cy, r, z in m["clumps"]:
        u, v = (cx - C[0]) / rx, (cy - C[1]) / ry
        lens.append(None)
        if theme == "light":
            # a lee-side band along the lower-east edge of the clump, a crescent following its outline: wider on the
            # side of the crown away from the sun and low down, never a fat interior mass
            f = u * TREE_SUN2[0] + v * TREE_SUN2[1]
            w = min(0.26, 0.13 + 0.12 * max(0.0, -f) + 0.1 * max(0.0, v))
            shade.append(_cap(cx, cy, r, w, math.radians(62 + 14 * w), TREE_SHADE2))
        else:
            shade.append(None)                             # night: a silhouette with a lamp-lit rim, nothing inside
    if theme == "light":
        w = 0.36 * rx
        shift = (w * TREE_SUN2[0], w * TREE_SUN2[1])
    else:
        shift = None
        if lamp:
            ux, uy = _unit(lamp[0] - C[0], lamp[1] - C[1])
            shift = (11.0 * ux, 11.0 * uy)
    return lens, shade, shift, lamp


def arc_loops(circles, label, keys, box=None, eps=2e-3):
    """Boundaries of the regions {p : label(p)[key]} that run along the given circles, as closed loops of arcs
    (cx, cy, r, t0, t1), the region on the right of the direction of travel. One pass serves every key."""
    TAU = 2 * math.pi
    arcs = {key: [] for key in keys}
    for i, (cx, cy, r) in enumerate(circles):
        if box and (cx + r < box[0] or cx - r > box[2] or cy + r < box[1] or cy - r > box[3]):
            continue
        angs = []
        for j, (cx2, cy2, r2) in enumerate(circles):
            if j == i:
                continue
            dx, dy = cx2 - cx, cy2 - cy
            if abs(dx) > r + r2 or abs(dy) > r + r2:
                continue
            d = math.hypot(dx, dy)
            if d >= r + r2 or d <= abs(r - r2) or d < 1e-9:
                continue
            base = math.atan2(dy, dx)
            off = math.acos(max(-1.0, min(1.0, (r * r - r2 * r2 + d * d) / (2 * d * r))))
            angs += [(base - off) % TAU, (base + off) % TAU]
        angs.sort()
        segs = [(0.0, TAU)] if not angs else \
            [(angs[k], angs[k + 1]) for k in range(len(angs) - 1)] + [(angs[-1], angs[0] + TAU)]
        for t0, t1 in segs:
            if t1 - t0 < 1e-7:
                continue
            tm = (t0 + t1) / 2
            ux, uy = math.cos(tm), math.sin(tm)
            mx, my = cx + r * ux, cy + r * uy
            if box and not (box[0] <= mx <= box[2] and box[1] <= my <= box[3]):
                continue
            a = label(mx - eps * ux, my - eps * uy)
            b = label(mx + eps * ux, my + eps * uy)
            for key in keys:
                if a[key] != b[key]:
                    arcs[key].append((cx, cy, r, t0, t1) if a[key] else (cx, cy, r, t1, t0))
    out = {}
    for key in keys:
        A = arcs[key]
        starts = {}
        for k, (cx, cy, r, t0, t1) in enumerate(A):
            starts.setdefault((round((cx + r * math.cos(t0)) * 100), round((cy + r * math.sin(t0)) * 100)), []).append(k)
        used = [False] * len(A)
        loops = []
        for k0 in range(len(A)):
            if used[k0]:
                continue
            loop, k = [], k0
            while k is not None:
                used[k] = True
                cx, cy, r, t0, t1 = A[k]
                if loop and loop[-1][:3] == (cx, cy, r) and (math.cos(loop[-1][4] - t0) > 1 - 1e-9) and \
                        (loop[-1][4] - loop[-1][3]) * (t1 - t0) > 0:
                    p = loop[-1]                        # same circle, same direction: extend the arc
                    loop[-1] = (cx, cy, r, p[3], p[4] + (t1 - t0))
                else:
                    loop.append(A[k])
                ex, ey = round((cx + r * math.cos(t1)) * 100), round((cy + r * math.sin(t1)) * 100)
                k = None
                for ddx, ddy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (-1, -1), (1, -1), (-1, 1)):
                    for cand in starts.get((ex + ddx, ey + ddy), ()):
                        if not used[cand]:
                            k = cand
                            break
                    if k is not None:
                        break
            if len(loop) > 1 and loop[0][:3] == loop[-1][:3] and (loop[-1][4] - loop[-1][3]) * (loop[0][4] - loop[0][3]) > 0:
                p, q = loop[-1], loop[0]
                loop = [(q[0], q[1], q[2], p[3], p[4] + (q[4] - q[3]))] + loop[1:-1]
            loops.append(loop)
        out[key] = loops
    return out


def loop_area(loop):
    """Signed-area magnitude of an arc loop (each arc sampled)."""
    pts = []
    for cx, cy, r, t0, t1 in loop:
        n = max(2, int(abs(t1 - t0) / 0.3) + 1)
        pts += [(cx + r * math.cos(t0 + (t1 - t0) * k / n), cy + r * math.sin(t0 + (t1 - t0) * k / n)) for k in range(n)]
    return 0.5 * abs(sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1])))


def arcs_d(loops, min_area=0.0):
    """Arc loops -> compact path data (integer coordinates and radii, relative arcs, flags packed)."""
    out = []
    for loop in loops:
        if min_area and loop_area(loop) < min_area:
            continue
        if len(loop) == 1 and abs(loop[0][4] - loop[0][3]) > 6.28:
            cx, cy, r = loop[0][:3]
            out.append(circ(cx, cy, r, 0))
            continue
        x0 = round(loop[0][0] + loop[0][2] * math.cos(loop[0][3]))
        y0 = round(loop[0][1] + loop[0][2] * math.sin(loop[0][3]))
        s, cur, n = f"M{x0} {y0}", (x0, y0), 0
        for cx, cy, r, t0, t1 in loop:
            ex, ey = round(cx + r * math.cos(t1)), round(cy + r * math.sin(t1))
            if (ex, ey) == cur:
                continue
            large = 1 if abs(t1 - t0) > math.pi else 0
            sweep = 1 if t1 > t0 else 0
            rr = max(1, round(r))
            dx, dy = ex - cur[0], ey - cur[1]
            s += f"a{rr} {rr} 0 {large}{sweep}{dx}{'' if dy < 0 else ' '}{dy}"
            cur, n = (ex, ey), n + 1
        if n >= 2:
            out.append(s + "Z")
    return "".join(out)


def _limb(p0, p1, w0, w1, bend):
    """A tapered, gently bent limb from p0 to p1: two quadratic edges, integer coordinates."""
    (ax, ay), (bx, by) = p0, p1
    dx, dy = bx - ax, by - ay
    L = math.hypot(dx, dy) or 1.0
    nx_, ny_ = -dy / L, dx / L
    cx, cy = (ax + bx) / 2 + nx_ * bend * L, (ay + by) / 2 + ny_ * bend * L
    h0, h1, hc = w0 / 2, w1 / 2, (w0 + w1) / 4

    def q(v):
        return f"{round(v[0])} {round(v[1])}"
    return (f"M{q((ax + nx_ * h0, ay + ny_ * h0))}Q{q((cx + nx_ * hc, cy + ny_ * hc))} {q((bx + nx_ * h1, by + ny_ * h1))}"
            f"L{q((bx - nx_ * h1, by - ny_ * h1))}Q{q((cx - nx_ * hc, cy - ny_ * hc))} {q((ax - nx_ * h0, ay - ny_ * h0))}Z")


def trees_svg(P, rng):
    theme = "dark" if P["night"] else "light"
    ms = tree_models()
    n = len(ms)
    o = []
    # trunks with a flared foot, the limbs that can show, the lit (west) side, plane-bark mottling
    trunk, trunk_lit, bark = [], [], []
    for i, m in enumerate(ms):
        x, yb = m["x"], m["yb"]
        fx, fy = m["fork"]
        w0, w1, wf = 7.0, 4.4, 3.6
        trunk.append(f"M{pp(x - w0, yb)}Q{pp(x - w1, yb - 1.5)} {pp(x - w1, yb - 9)}L{pp(fx - wf, fy)}L{pp(fx + wf, fy)}"
                     f"L{pp(x + w1, yb - 9)}Q{pp(x + w1, yb - 1.5)} {pp(x + w0, yb)}Z")
        trunk_lit.append(f"M{pp(x - w0, yb)}Q{pp(x - w1, yb - 1.5)} {pp(x - w1, yb - 9)}L{pp(fx - wf, fy)}"
                         f"L{pp(fx - wf + 2.4, fy)}L{pp(x - w1 + 2.8, yb - 9)}Q{pp(x - w1 + 2.4, yb - 1)} {pp(x - w0 + 4.8, yb)}Z")
        for li, (p0, p1, a, b, bend) in enumerate(m["limbs"]):
            twig = li == m["ntwig"]
            vis = any(_owner(m, p0[0] + (p1[0] - p0[0]) * t, p0[1] + (p1[1] - p0[1]) * t, twig) < 0
                      for t in (k / 12 for k in range(1, 13)))
            if vis:
                trunk.append(_limb(p0, p1, a, b, bend))
        if m["kind"] == "plane":
            brnd = random.Random(900 + i)
            for k in range(3):
                by = yb - 10 - k * (yb - fy - 14) / 3 - brnd.uniform(0, 5)
                bxp = x + brnd.uniform(0.8, 2.6)
                w, hh = brnd.uniform(1.0, 1.6), brnd.uniform(3.0, 5.0)
                bark.append(poly([(bxp - w, by), (bxp - 0.3 * w, by - hh), (bxp + w, by - 0.5 * hh), (bxp + 0.5 * w, by + hh * 0.7),
                                  (bxp - 0.8 * w, by + hh * 0.5)]))
    o.append(f'<path d="{"".join(trunk)}" fill="{P["sc_trunk"]}"/>')
    o.append(f'<path d="{"".join(trunk_lit + bark)}" fill="{P["sc_trunk_lit"]}"/>')
    # crowns: silhouettes back to front (one path per tree), then the deep and lit tones of all trees merged per
    # colour (each tone cut by the silhouettes of the trees in front, so no tone overlaps another)
    order = sorted(range(n), key=lambda i: (ms[i]["yb"], i))
    rank = {i: r for r, i in enumerate(order)}
    tones = {"deep": {}, "lit": {}}
    base = {}
    for i in order:
        m = ms[i]
        lens, shade, shift, lamp = _tone_setup(m, theme)
        x0, y0, x1, y1 = m["box"]
        fronts = [ms[j] for j in range(n) if rank[j] > rank[i] and ms[j]["box"][0] < x1 and ms[j]["box"][2] > x0]

        def label(px, py):
            k = _owner(m, px, py)
            if k < 0:
                return (False, False, False)
            for f in fronts:
                if _owner(f, px, py) >= 0:
                    return (not any(_in_shrunk(g, px, py, 1.0) for g in fronts), False, False)
            lit = False
            if shift is not None and _owner(m, px + shift[0], py + shift[1], False) < 0 and \
                    _owner(m, px + 2 * shift[0], py + 2 * shift[1], False) < 0:      # the light clears the crown
                lit = lamp is None or (px - lamp[0]) ** 2 + (py - lamp[1]) ** 2 < lamp[2] ** 2
            if not lit:
                L = lens[k]
                lit = L is not None and (px - L[0]) ** 2 + (py - L[1]) ** 2 < L[2] * L[2]
            if lit:
                return (True, False, True)
            D = shade[k]
            return (True, D is not None and (px - D[0]) ** 2 + (py - D[1]) ** 2 > D[2] * D[2], False)
        own = [c[:3] for c in m["clumps"] + m["lobes"]] + list(m["holes"]) + list(m["bites"])
        circles = own + [c for c in lens if c] + [c for c in shade if c]
        if shift is not None:
            for s_ in (1, 2):
                circles += [(cx - s_ * shift[0], cy - s_ * shift[1], r) for cx, cy, r in own[:len(m["clumps"]) + len(m["lobes"])]]
        if lamp:
            circles.append(lamp)
        for f in fronts:
            fc = [c[:3] for c in f["clumps"] + f["lobes"]]
            circles += fc + list(f["holes"]) + list(f["bites"])
            circles += [(cx, cy, r - 1.0) for cx, cy, r in fc if r > 1.5] + [(cx, cy, r + 1.0) for cx, cy, r in f["holes"]]
            circles += [(cx, cy, r - 1.0) for cx, cy, r in f["bites"] if r > 1.5]
        res = arc_loops(circles, label, (0, 1, 2), box=(x0 - 1, y0 - 1, x1 + 1, y1 + 1))
        pal = P["sc_fol"][m["fi"]]
        base.setdefault(pal[2], []).append(arcs_d(res[0]))
        tones["deep"].setdefault(pal[1], []).append(arcs_d(res[1], 30.0))
        tones["lit"].setdefault(pal[0], []).append(arcs_d(res[2], 30.0))
    for col, ds in base.items():
        o.append(f'<path d="{"".join(ds)}" fill="{col}"/>')
    for key in ("deep", "lit"):
        for col, ds in tones[key].items():
            if "".join(ds):
                o.append(f'<path d="{"".join(ds)}" fill="{col}"/>')
    return "\n".join(o)


# ------------------------------------------------------------------ ground plane
FX, FY, SF = 1196.0, 556.0, 25.0                    # fountain centre (plaza level), units per metre
EL = math.radians(11.0)
SE, CE = math.sin(EL), math.cos(EL)
G_SCREEN = SF * G * CE                               # screen gravity, units/s^2


def proj(X, Y, Z):
    return FX + SF * X, FY - SF * (Y * CE + Z * SE)


SUN = (1.0, -0.12)                                   # long-shadow direction on the page (to the east)


SHADOW_K = 2.6                                       # cast-shadow length per unit of height on the page (as people_svg)
PAVE_RINGS = (12.4, 15.6, 19.5, 24.5, 30.5, 38.0)    # granite rings around the fountain (m)
HORIZON = 446.0                                      # far edge of the plaza on the page


def ring_arc(r, y_cut=HORIZON + 1):
    """A paving ring of radius r (m) on the plaza, drawn only below the far edge of the plaza."""
    rx, ry = SF * r, SF * r * SE
    if FY - ry >= y_cut:
        return ell(FX, FY, rx, ry)
    dx = rx * math.sqrt(max(0.0, 1 - ((FY - y_cut) / ry) ** 2))
    return f"M{pp(FX - dx, y_cut)}A{fm(rx)} {fm(ry)} 0 1 0 {pp(FX + dx, y_cut)}"


def _streak(p0, p1, t0, t1):
    """A cast-shadow streak from p0 to p1, half-thickness t0 at p0 and t1 at p1, with round ends."""
    (ax, ay), (bx, by) = p0, p1
    L = math.hypot(bx - ax, by - ay) or 1.0
    nx_, ny_ = -(by - ay) / L * 1.0, (bx - ax) / L

    def q(x, y):
        return f"{round(x, 1):g} {round(y, 1):g}"
    return (f"M{q(ax + nx_ * t0, ay + ny_ * t0)}L{q(bx + nx_ * t1, by + ny_ * t1)}"
            f"A{fm(t1)} {fm(t1)} 0 0 0 {q(bx - nx_ * t1, by - ny_ * t1)}L{q(ax - nx_ * t0, ay - ny_ * t0)}"
            f"A{fm(t0)} {fm(t0)} 0 0 0 {q(ax + nx_ * t0, ay + ny_ * t0)}Z")


# trees standing west of the frame: base on the page, trunk height and crown from/to height (m), crown radius (m)
WEST_TREES = [((-150, 630), 3.4, 3.2, 10.6, 4.0), ((-118, 548), 3.6, 3.4, 10.0, 3.3)]
SUN_DEG = math.degrees(math.atan2(SUN[1], SUN[0]))


def west_shadows_svg(P):
    """Golden-hour shadows of trees standing west of the frame. A trunk throws a thin band along SUN; a crown
    throws its own silhouette squashed across and stretched along the sun: clumps, leafy lobes and sun flecks,
    traced exactly as arcs in a frame rotated to SUN and scaled by the stretch."""
    srnd = random.Random(31)
    k = SHADOW_K * SF * CE                              # page units of shadow per metre of height
    trunks, crowns = [], []
    for (bx, by), ht, h0, h1, rc in WEST_TREES:
        e0 = (bx + k * ht * SUN[0], by + k * ht * SUN[1])
        trunks.append(_streak((bx, by), e0, 2.4, 1.6))
        L = k * (h1 - h0)                               # along the sun
        Wd = 2 * rc * SF * SE * 1.25                    # across the sun
        sx = L / (2.2 * Wd)
        Lu = L / sx
        discs, holes = [], []
        n = 6
        for j in range(n):
            u = Lu * (0.1 + 0.8 * j / (n - 1)) + srnd.uniform(-3, 3)
            env = math.sin(math.pi * (0.12 + 0.76 * j / (n - 1)))
            discs.append((u, srnd.uniform(-0.14, 0.14) * Wd, Wd * (0.3 + 0.2 * env) * srnd.uniform(0.9, 1.1)))
        for cu, cv, r in list(discs):
            t = srnd.uniform(0, 1)
            while t < 2 * math.pi:
                rs = r * srnd.uniform(0.32, 0.44)
                if abs(math.sin(t)) > 0.35:               # leafy lobes on the long edges only
                    discs.append((cu + (r - 0.3 * rs) * math.cos(t), cv + (r - 0.3 * rs) * math.sin(t), rs))
                t += srnd.uniform(1.4, 2.0)
        for j in range(3):
            cu, cv, r = discs[srnd.randrange(1, n - 1)]
            a = srnd.uniform(0, 2 * math.pi)
            holes.append((cu + 0.45 * r * math.cos(a), cv + 0.45 * r * math.sin(a), r * srnd.uniform(0.1, 0.17)))

        def lab(x, y):
            if any((x - u) ** 2 + (y - v) ** 2 < r * r for u, v, r in holes):
                return (False,)
            return (any((x - u) ** 2 + (y - v) ** 2 < r * r for u, v, r in discs),)
        o0 = (bx + k * h0 * SUN[0], by + k * h0 * SUN[1])
        crowns.append(stretched_arcs_d(arc_loops(discs + holes, lab, (0,))[0], o0, SUN_DEG, sx))
    return f'<path d="{"".join(trunks)}{"".join(crowns)}" fill="{P["sc_shadow_soft"]}"/>'


def stretched_arcs_d(loops, origin, deg, sx):
    """Arc loops drawn in a frame at `origin`, rotated by deg and stretched by sx along its x axis: every circular
    arc becomes an elliptical arc (rx = sx*r, ry = r, rotated by deg), written in page coordinates."""
    ca, sa = math.cos(math.radians(deg)), math.sin(math.radians(deg))

    def T(u, v):
        return origin[0] + ca * sx * u - sa * v, origin[1] + sa * sx * u + ca * v
    out = []
    for loop in loops:
        cx, cy, r, t0, t1 = loop[0]
        x0, y0 = T(cx + r * math.cos(t0), cy + r * math.sin(t0))
        cur = (round(x0), round(y0))
        s, n = f"M{cur[0]} {cur[1]}", 0
        for cx, cy, r, t0, t1 in loop:
            ex, ey = T(cx + r * math.cos(t1), cy + r * math.sin(t1))
            e = (round(ex), round(ey))
            if e == cur:
                continue
            large = 1 if abs(t1 - t0) > math.pi else 0
            sweep = 1 if t1 > t0 else 0
            dx, dy = e[0] - cur[0], e[1] - cur[1]
            s += f"a{fm(sx * r, 0)} {fm(r, 0)} {fm(deg, 1)} {large}{sweep}{dx}{'' if dy < 0 else ' '}{dy}"
            cur, n = e, n + 1
        if n >= 2:
            out.append(s + "Z")
    return "".join(out)


def plaza_svg(P, rng):
    o = []
    o.append(f'<path d="M-10 446H1610V650H-10Z" fill="{P["plaza"]}"/>')
    # a granite curb round the fountain, then the rings and the joints between their stones
    joints = []
    for r0, r1, step, off in ((13.0, 15.6, 7.5, 0.0), (15.6, 19.5, 6.0, 3.0)):
        a = off
        while a < 360:
            ca, sa = math.cos(math.radians(a)), math.sin(math.radians(a))
            p, q = (FX + SF * (r0 + 0.08) * ca, FY + SF * (r0 + 0.08) * SE * sa), (FX + SF * (r1 - 0.08) * ca, FY + SF * (r1 - 0.08) * SE * sa)
            p, q = (round(p[0]), round(p[1])), (round(q[0]), round(q[1]))
            if min(p[1], q[1]) > HORIZON + 2 and abs(q[0] - p[0]) + abs(q[1] - p[1]) > 3:
                joints.append(f"M{p[0]} {p[1]}l{q[0] - p[0]} {q[1] - p[1]}h1l{p[0] - q[0]} {p[1] - q[1]}Z")
            a += step
    # a granite curb round the fountain and the joints between the paving stones (one path), then the rings
    o.append(f'<path d="{ell(FX, FY, SF * 13.0, SF * 13.0 * SE)}{ell(FX, FY, SF * 12.4, SF * 12.4 * SE)}{"".join(joints)}" '
             f'fill="{P["sc_granite"]}" fill-rule="evenodd"/>')
    o.append(f'<path d="{"".join(ring_arc(r) for r in PAVE_RINGS)}" fill="none" stroke="{P["ring"]}" stroke-width="2.2"/>')
    if not P["night"]:
        o.append(west_shadows_svg(P))
    # lawn strips and the hoop fence along the far edge of the plaza
    o.append(f'<path d="M-10 446H1030V468H-10ZM1366 446H1610V468H1366Z" fill="{P["lawn"]}"/>')
    ts = []
    if not P["night"]:
        # the trunks of the back row throw long shadows east across the lawn
        for m in tree_models():
            x, yb = m["x"], m["yb"]
            L = min(SHADOW_K * (yb - m["fork"][1]), (yb - HORIZON - 1) / -SUN[1])
            ts.append(_streak((x + 2, yb - 0.5), (x + 2 + L * SUN[0], yb - 0.5 + L * SUN[1]), 3.4, 1.6))
    o.append(f'<path d="M-10 462H1030V468H-10ZM1366 462H1610V468H1366Z{"".join(ts)}" fill="{P["lawn_dk"]}"/>')
    hoops = []
    for x0, x1 in ((-10, 1030), (1366, 1610)):
        s = f"M{x0} 469"
        n = int((x1 - x0) / 14)
        for _ in range(n):
            s += "q7-9 14 0"
        hoops.append(s)
    o.append(f'<path d="{"".join(hoops)}" fill="none" stroke="{P["fence"]}" stroke-width="1.6"/>')
    return "\n".join(o)


LAMPS = [(298, 604, 31.0, True), (884, 486, 21.0, False), (1534, 614, 32.0, False)]


def lamp_shape(x, y, s):
    """Henry Bacon park lamppost: base, post, acorn globe. s = units per metre."""
    k = s / 30.0
    def P_(px, py):
        return x + px * k, y + py * k
    post = [P_(-5.2, 0), P_(-4.2, -13), P_(-2.2, -17), P_(-1.5, -18), P_(-1.5, -96), P_(-3.2, -98), P_(-3.2, -101),
            P_(3.2, -101), P_(3.2, -98), P_(1.5, -96), P_(1.5, -18), P_(2.2, -17), P_(4.2, -13), P_(5.2, 0)]
    cap = [P_(-4.6, -103), P_(4.6, -103), P_(2.6, -107), P_(-2.6, -107)]
    gx, gy = P_(0, -116)
    globe = (f"M{pp(*P_(-6.4, -107))}C{pp(*P_(-8, -114))} {pp(*P_(-5, -124))} {pp(*P_(0, -127))}"
             f"C{pp(*P_(5, -124))} {pp(*P_(8, -114))} {pp(*P_(6.4, -107))}Z")
    fin = circ(*P_(0, -129), 1.6 * k)
    return poly(post) + poly(cap) + fin, globe, (gx, gy), 127 * k


def lamps_svg(P, front):
    """Henry Bacon lampposts, merged per tone: shadows (or night pools and halos), posts, the NYU banner, globes."""
    o, shadows, bodies, globes, flags = [], [], [], [], []
    for x, y, s, banner in LAMPS:
        if (y > 560) != front:
            continue
        body, globe, gc, hgt = lamp_shape(x, y, s)
        k = s / 30.0
        if not P["night"]:
            # the same sun as everyone else: shadow length SHADOW_K x height, along SUN; the globe's shadow at the end
            L = hgt * SHADOW_K
            gx, gy = x + SUN[0] * L * 116 / 127, y + SUN[1] * L * 116 / 127
            shadows.append(_streak((x + 1, y + 1), (gx - 9 * k, gy + 0.6), 2.4 * k, 1.1 * k)
                           + ell(gx, gy + 0.6, 10 * k, 2.6 * k) + ell(x + 3, y + 1.2, 8 * k, 2.4 * k))
        else:
            o.append(f'<ellipse cx="{fm(x + 6)}" cy="{fm(y + 3)}" rx="{fm(s * 4.6)}" ry="{fm(s * 1.0)}" fill="url(#pool)"/>')
            o.append(f'<circle cx="{fm(gc[0])}" cy="{fm(gc[1])}" r="{fm(s * 1.9)}" fill="url(#halo)"/>')
        bodies.append(body)
        globes.append(globe)
        if banner:
            bx, by = x + 1.5 * k, y - 84 * k
            bodies.append(f"M{pp(bx, by - 2.8 * k)}h{fm(18 * k)}v{fm(1.6 * k)}h{fm(-18 * k)}Z")
            flags.append(f"M{pp(bx + 3 * k, by)}h{fm(14 * k)}v{fm(30 * k)}l{fm(-7 * k)} {fm(-4 * k)}l{fm(-7 * k)} {fm(4 * k)}Z")
            tx, ty = bx + 10 * k, by + 8 * k
            globes.append(f"M{pp(tx - 1.3 * k, ty + 6 * k)}h{fm(2.6 * k)}l{fm(1.4 * k)} {fm(-4.6 * k)}h{fm(-5.4 * k)}Z"
                          f"M{pp(tx, ty - 5.6 * k)}c{fm(2.8 * k)} {fm(2 * k)} {fm(2.6 * k)} {fm(4.4 * k)} {fm(0.4 * k)} {fm(5.6 * k)}"
                          f"c{fm(-2.6 * k)} {fm(-0.8 * k)} {fm(-2.6 * k)} {fm(-3.8 * k)} {fm(-0.4 * k)} {fm(-5.6 * k)}Z")
    if shadows:
        o.insert(0, f'<path d="{"".join(shadows)}" fill="{P["shadow"]}"/>')
    o.append(f'<path d="{"".join(bodies)}" fill="{P["lamp"]}"/>')
    if flags:
        o.append(f'<path d="{"".join(flags)}" fill="{P["banner"]}"/>')
    o.append(f'<path d="{"".join(globes)}" fill="{P["globe"]}"/>')
    return "\n".join(o)


def person(x, y, k, coat, P, kind):
    """Small flat figures. kind: stand | sit | sitread | walk."""
    def Q(px, py):
        return x + px * k, y + py * k
    o = []
    if kind in ("stand", "walk"):
        legs = poly([Q(-3.6, -14), Q(-1.0, -14), Q(-0.8, 0), Q(-3.4, 0)]) + poly([Q(1.0, -14), Q(3.6, -14), Q(3.4, 0), Q(0.8, 0)])
        if kind == "walk":
            legs = poly([Q(-2.6, -14), Q(0.2, -14), Q(-3.2, 0), Q(-6.0, 0)]) + poly([Q(-0.2, -14), Q(2.6, -14), Q(5.8, 0), Q(3.0, 0)])
        coatp = (f"M{pp(*Q(-5.4, -31))}C{pp(*Q(-5.6, -34.5))} {pp(*Q(5.6, -34.5))} {pp(*Q(5.4, -31))}"
                 f"L{pp(*Q(6.4, -12))}L{pp(*Q(-6.4, -12))}Z")
        head = circ(*Q(0, -38.4), 4.1 * k)
        hair = f"M{pp(*Q(-4.2, -38.6))}A{fm(4.2 * k)} {fm(4.2 * k)} 0 0 1 {pp(*Q(4.2, -38.6))}Z"
        o.append(f'<path d="{legs}" fill="{P["hair"]}"/>')
        o.append(f'<path d="{coatp}" fill="{coat}"/>')
        o.append(f'<path d="{head}" fill="{P["skin"]}"/><path d="{hair}" fill="{P["hair"]}"/>')
    else:
        legs = poly([Q(-2, -12.5), Q(9, -12.5), Q(9.6, 0), Q(6.8, 0), Q(6.4, -9.6), Q(-2, -9.6)])
        coatp = (f"M{pp(*Q(-4.8, -27.5))}C{pp(*Q(-4.6, -30.6))} {pp(*Q(4.2, -30.8))} {pp(*Q(4.4, -27.4))}"
                 f"L{pp(*Q(5.4, -11))}L{pp(*Q(-5.6, -10.6))}Z")
        hx, hy = (1.6, -34.2) if kind == "sit" else (3.0, -33.0)
        head = circ(*Q(hx, hy), 4.0 * k)
        o.append(f'<path d="{legs}" fill="{P["hair"]}"/>')
        o.append(f'<path d="{coatp}" fill="{coat}"/>')
        o.append(f'<path d="{head}" fill="{P["skin"]}"/>')
        o.append(f'<path d="M{pp(*Q(hx - 4.1, hy - 0.4))}A{fm(4.1 * k)} {fm(4.1 * k)} 0 0 1 {pp(*Q(hx + 4.1, hy - 0.4))}Z" fill="{P["hair"]}"/>')
        if kind == "sitread":
            o.append(f'<path d="{poly([Q(3.6, -21), Q(11, -24.5), Q(11.8, -20.5), Q(4.4, -17.5)])}" fill="{P["trim"] if not P["night"] else "#E9DCC0"}"/>')
    return "".join(o)


PEOPLE = [(150, 616, 1.08, 2, "walk"), (1446, 630, 1.1, 3, "stand")]


def people_svg(P, which):
    o = []
    for i, (x, y, k, ci, kind) in enumerate(PEOPLE):
        if i not in which:
            continue
        if not P["night"]:
            hgt = 40 * k if kind in ("stand", "walk") else 34 * k
            L = hgt * 2.6
            dx, dy = SUN[0] * L, SUN[1] * L
            w = 5.5 * k
            sh = poly([(x - w, y + 1), (x + dx - w * 0.3, y + dy - 2), (x + dx + w * 0.6, y + dy + 1.6), (x + w, y + 2.6)])
            sh += ell(x + dx + 2, y + dy, 4.2 * k, 2.2 * k)
            o.append(f'<path d="{sh}" fill="{P["shadow"]}"/>')
        o.append(person(x, y, k, P["coat"][ci], P, kind))
    return "\n".join(o)


# ------------------------------------------------------------------ fountain (physics)
# The basin is Washington Square's low granite ring: a coping 0.45 m high and 0.8 m deep that people sit on, the
# water 0.3 m below its top. Seen 11 deg down, the front coping hides the near 1.5 m of water and the far inner wall
# shows above the waterline. Basin, water and jets go through the plaza camera proj(). Reflections are the scene
# mirrored in the water plane through the camera that draws each thing: proj() for the basin wall and the plume,
# persp() (eye 9 ft up, 150 ft south of the arch) for the arch, the Empire State Building and the trees.
R_OUT, R_IN, Y_RIM, Y_WATER = 11.0, 10.2, 0.45, 0.15
F_SHK = 2.6                                           # people_svg: a shadow is 2.6 x its caster's page height
F_SHV = (F_SHK * CE * SUN[0], -F_SHK * CE * SUN[1] / SE)       # ... so its ground offset (X, Z) per metre of height
_F = math.sqrt(F_SHV[0] ** 2 + 1 + F_SHV[1] ** 2)
F_SUN = (-F_SHV[0] / _F, 1 / _F, -F_SHV[1] / _F)                  # unit vector toward the sun
F_EYE = 20.0                                          # Fresnel: an eye 20 m south, seeing the centre 11 deg down
F_TB, F_TR = 0.15, 0.6                                # surface waves on the column, ripples: periods (s)
F_LAM = G * F_TR ** 2 / (2 * math.pi)                 # deep-water wavelength of a 0.6 s ripple (0.56 m)
F_LD = 0.6                                            # ripple fade e-fold (m): scattered by the neighbouring impacts
F_FR, F_R0, F_AMP = 6, 0.22, 0.75                     # ripple frames per period, splash radius (m), peak opacity
F_YW = Y_WATER / 0.3048                               # the water plane in arch feet above the plaza
F_ESB = (6900.0, -175.0, ((0, 80, 100), (80, 280, 76), (280, 1000, 58), (1000, 1035, 48), (1035, 1062, 40),
                          (1062, 1100, 31), (1100, 1150, 21), (1150, 1240, 13), (1240, 1268, 8.5),
                          (1268, 1298, 5), (1298, 1454, 1.4)))                # z, x, profile (as vista_svg)
F_CYW, F_CYR = proj(0, Y_WATER, 0)[1], proj(0, Y_RIM, 0)[1]
F_RX, F_RY = SF * R_IN, SF * R_IN * SE
F_DW = F_CYW - F_CYR                                  # height of the far inner wall above the water, on the page

FOUNTAIN_PAL = {
    "light": dict(
        f_top="#F7E7CA", f_lit="#F3D29C", f_mid="#E2C094", f_sh="#C4A387", f_edge="#FFF7E4", f_joint="#7E5E40",
        f_wall="#E6C69B", f_wall_sh="#C6A788", f_wet="#A98B6B", f_cast="#8A6840", f_occ="#A88866",
        f_body="#26968C", f_env="#F4DFB6", f_ripple="#F7F3E4", f_foam="#FFFDF6", f_foam_sh="#D3DFDC",
        f_sheath="#FFFFFF", f_sheath_sh="#C5D5D4", f_glint="#FFF4C8", f_arch_ref="#FBEDD4",
    ),
    "dark": dict(
        f_top="#5A5761", f_lit="#655B52", f_mid="#4A4549", f_sh="#35363F", f_edge="#9E8E74", f_joint="#10121A",
        f_wall="#344555", f_wall_sh="#2A3443", f_wet="#1D2632", f_cast="#000000", f_occ="#141821",
        f_body="#0B2B3F", f_env="#24344F", f_ripple="#A9C9D7", f_foam="#F3EBDC", f_foam_sh="#B7C4CA",
        f_sheath="#FFF3DC", f_sheath_sh="#DCD3C3", f_glint="#FFE6A8", f_arch_ref="#F2D9A6",
    ),
}
for _t in PAL:
    PAL[_t].update(FOUNTAIN_PAL[_t])


def f_num(vals, d=1):
    """Path numbers, separated only where the grammar needs it."""
    out, last = [], ""
    for v in vals:
        s = fm(v, d)
        if out and s[0] != "-" and not (s[0] == "." and "." in last):
            out.append(" ")
        out.append(s)
        last = s
    return "".join(out)


def f_d(pts, d=1, close=True):
    """Compact polyline: absolute M, then relative l between points rounded to the grid (no drift)."""
    q = [(round(x, d), round(y, d)) for x, y in pts]
    rel = [c for (x0, y0), (x1, y1) in zip(q, q[1:]) for c in (x1 - x0, y1 - y0)]
    return "M" + f_num(q[0], d) + ("l" + f_num(rel, d) if rel else "") + ("Z" if close else "")


def f_hd(dashes):
    """Horizontal dashes (x, y, length) as one path of relative moves: M x y h l m dx dy h l ..."""
    out, pen = [], None
    for x, y, ln in sorted(dashes, key=lambda d: (d[1], d[0])):
        out.append(("M" + f_num((x, y)) if pen is None else "m" + f_num((x - pen[0], y - pen[1]))) + "h" + fm(ln))
        pen = (x + ln, y)
    return "".join(out)


def f_halfplane(pts, x0, side):
    """Clip a closed polygon to x >= x0 (side 1) or x <= x0 (side -1) (Sutherland-Hodgman)."""
    out = []
    for (ax, ay), (bx_, by_) in zip(pts, pts[1:] + pts[:1]):
        ina, inb = side * (ax - x0) >= 0, side * (bx_ - x0) >= 0
        if ina:
            out.append((ax, ay))
        if ina != inb:
            t = (x0 - ax) / (bx_ - ax)
            out.append((x0, ay + t * (by_ - ay)))
    return out


def f_xy(R, th, Y):
    t = math.radians(th)
    return proj(R * math.cos(t), Y, R * math.sin(t))


def f_arc(R, Y, a0, a1, step=4.0):
    n = max(1, int(math.ceil(abs(a1 - a0) / step)))
    return [f_xy(R, a0 + (a1 - a0) * i / n, Y) for i in range(n + 1)]


def f_strip(frames, dur, idp, still, step=2000):
    """filmstrip() with an id on frame `still`, so the reduced-motion still can <use> that frame for ~30 bytes."""
    vals = ";".join(f"0 {-step * k}" for k in range(len(frames)))
    body = "".join("<g" + (f' id="{idp}"' if k == still else "") + (f' transform="translate(0 {step * k})"' if k else "")
                   + f">{fr}</g>" for k, fr in enumerate(frames))
    return (f'<g><animateTransform attributeName="transform" type="translate" values="{vals}" dur="{fm(dur, 3)}s" '
            f'calcMode="discrete" repeatCount="indefinite"/>{body}</g>')


def f_still(idp, k, step=2000):
    return f'<use href="#{idp}"' + (f' y="{-step * k}"' if k else "") + "/>"


# colour in linear light (sRGB transfer), for physically mixed water colours
def f_lin(c):
    return [v / 255 / 12.92 if v <= 10 else ((v / 255 + .055) / 1.055) ** 2.4 for v in (int(c[i:i + 2], 16) for i in (1, 3, 5))]


def f_hex(lin):
    out = []
    for x in lin:
        x = min(1.0, max(0.0, x))
        out.append(round(255 * (12.92 * x if x <= .0031308 else 1.055 * x ** (1 / 2.4) - .055)))
    return "#" + "".join(f"{v:02X}" for v in out)


def f_fresnel(ci, n=1.333):
    """Unpolarised Fresnel reflectance of water for an incidence with cosine ci."""
    st = math.sqrt(max(0.0, 1 - ci * ci)) / n
    ct = math.sqrt(1 - st * st)
    return (((ci - n * ct) / (ci + n * ct)) ** 2 + ((ct - n * ci) / (ct + n * ci)) ** 2) / 2


def f_R(y):
    """Reflectance of the water seen at page row y (centre line), for the eye F_EYE m south and 11 deg up."""
    Z = ((FY - y) / SF - Y_WATER * CE) / SE
    return f_fresnel(math.sin(math.atan2(F_EYE * math.tan(EL), F_EYE + Z)))


def f_gap(P, y):
    """Water where the ripples scatter the reflection: (1 - R) light from the basin floor + R the sky."""
    R = f_R(y)
    return f_hex([(1 - R) * a + R * b for a, b in zip(f_lin(P["f_body"]), f_lin(P["f_env"]))])


def f_refl(P, y, obj, k=1.0):
    """A strip of water mirroring `obj`: the gap colour with R x (obj - sky) added, in linear light."""
    R = f_R(y) * k
    return f_hex([g + R * (o - e) for g, o, e in zip(f_lin(f_gap(P, y)), f_lin(obj), f_lin(P["f_env"]))])


def f_vis(y, below=0.0):
    """Half-width of the water visible at page row y (inside the water, under the far wall's reflection band
    when below = F_DW, above the front coping's inner edge)."""
    w = 1.0
    a = (F_CYW + below - y) / F_RY
    b = (y - F_CYR) / F_RY
    if a > 0:
        w = min(w, 1 - a * a)
    if b > 0:
        w = min(w, 1 - b * b)
    return F_RX * math.sqrt(w) if w > 0 else 0.0


def f_vm(vg):
    """Page row of the water plane at the depth whose ground line is page row vg (persp camera)."""
    vh = A(VPX, VPY)[1]
    return vg - F_YW * (vg - vh) / VPY


def f_arch_hw(y):
    best = 0.0
    for (x0, y0), (x1, y1) in zip(SIL_R, SIL_R[1:]):
        if min(y0, y1) <= y <= max(y0, y1):
            best = max(best, x0, x1) if y1 == y0 else max(best, x0 + (x1 - x0) * (y - y0) / (y1 - y0))
    return best


def f_open_hw(y):
    if y < SPRING:
        return OPEN_HW
    return math.sqrt(max(0.0, OPEN_HW ** 2 - (y - SPRING) ** 2))


def f_trees():
    """Crown ellipses (x, ground row, centre row, rx, ry, palette index) from TREES_L/TREES_R, if they parse."""
    out = []
    for t in list(globals().get("TREES_L", ())) + list(globals().get("TREES_R", ())):
        try:
            x, yb, cy, rx, ry = (float(v) for v in t[:5])
            out.append((x, yb, cy, rx, ry, int(t[5]) if len(t) > 5 else 0))
        except (TypeError, ValueError):
            pass
    return out


def jets():
    """Return stream definitions: list of dict(name, T, K, period_frames, subjets=[(x0,y0,z0,vx,vy,vz)], layer)."""
    out = []
    ring = []
    for j in range(10):
        a = 2 * math.pi * j / 10 + math.radians(9)
        r0, r1, T, y0 = 1.3, 6.2, 1.5, Y_WATER + 0.06
        vr = (r1 - r0) / T
        vy = (Y_WATER - y0 + 0.5 * G * T * T) / T
        ring.append((r0 * math.cos(a), y0, r0 * math.sin(a), vr * math.cos(a), vy, vr * math.sin(a)))
    out.append(dict(name="ring", T=1.5, K=5, sub=ring, width=2.6))
    plA = []
    for j in range(7):
        a = 2 * math.pi * j / 7 + 0.4
        vr = 0.22 + 0.5 * ((j * 3) % 7) / 6
        T, y0 = 2.4, Y_WATER + 0.12
        vy = (Y_WATER - y0 + 0.5 * G * T * T) / T
        plA.append((0.15 * math.cos(a), y0, 0.15 * math.sin(a), vr * math.cos(a), vy, vr * math.sin(a)))
    out.append(dict(name="plA", T=2.4, K=8, sub=plA, width=3.0))
    plB = []
    for j in range(8):
        a = 2 * math.pi * j / 8 + 0.1
        vr = 0.95 + 0.6 * ((j * 5) % 8) / 7
        T, y0 = 1.8, Y_WATER + 0.12
        vy = (Y_WATER - y0 + 0.5 * G * T * T) / T
        plB.append((0.2 * math.cos(a), y0, 0.2 * math.sin(a), vr * math.cos(a), vy, vr * math.sin(a)))
    out.append(dict(name="plB", T=1.8, K=6, sub=plB, width=2.7))
    for s in out:
        s["pf"] = int(round(s["T"] / s["K"] * FPS))            # frames between drops = pattern period
        assert abs(s["pf"] / FPS - s["T"] / s["K"]) < 1e-9
        assert abs(PERIOD / (s["pf"] / FPS) - round(PERIOD / (s["pf"] / FPS))) < 1e-9
    return out


def ball(sj, t):
    x0, y0, z0, vx, vy, vz = sj
    return x0 + vx * t, y0 + vy * t - 0.5 * G * t * t, z0 + vz * t


def stream_frames(s, layer):
    """Discrete d values (one per frame of the pattern) for one stream group and depth layer. Each drop is a short
    streak along its motion (its position 0.024 s earlier), written with relative moves from the last pen point on
    the 0.1-unit grid, so the drawn drop lands exactly on the rounded ballistic position kept in `tracks`."""
    frames = []
    tracks = []
    for f in range(s["pf"]):
        d, pen = [], None
        for si, sj in enumerate(s["sub"]):
            if (sj[2] + sj[5] * s["T"] * 0.5 > 0) != (layer == "far"):
                continue
            for k in range(s["K"]):
                age = (f + k * s["pf"]) / FPS
                X, Y, Z = ball(sj, age)
                x, y = proj(X, Y, Z)
                Xb, Yb, Zb = ball(sj, max(0.0, age - 0.024))
                xb, yb = proj(Xb, Yb, Zb)
                if abs(xb - x) < 0.25 and abs(yb - y) < 0.25:
                    yb = y + 0.3
                tx, ty = round(xb - x), round(yb - y)
                if tx == 0 and ty == 0:
                    ty = 1
                xr, yr = float(fm(x)), float(fm(y))
                d.append(("M" + f_num((xr, yr)) if pen is None else "m" + f_num((xr - pen[0], yr - pen[1])))
                         + "l" + f_num((tx, ty), 0))
                pen = (xr + tx, yr + ty)
                tracks.append((s["name"], si, age, xr, yr))    # as emitted
        frames.append("".join(d))
    return frames, tracks


def stream_paths(s):
    """Static parabola for each sub-jet as a quadratic Bezier (exact)."""
    out = {"far": [], "near": []}
    for sj in s["sub"]:
        T = s["T"]
        p0 = proj(*ball(sj, 0))
        p2 = proj(*ball(sj, T))
        x0, y0, z0, vx, vy, vz = sj
        vxs = SF * vx
        vys = -SF * (vy * CE + vz * SE)
        p1 = (p0[0] + vxs * T / 2, p0[1] + vys * T / 2)
        layer = "far" if (z0 + vz * T * 0.5 > 0) else "near"
        out[layer].append(f"M{pp(*p0)}Q{pp(*p1)} {pp(*p2)}")
    return out


def f_ripple_amp(r, r0, ld):
    """Ripple amplitude: 1/sqrt(r) spreading, exp(-r/ld) damping, born inside the splash."""
    return math.sqrt(r0 / r) * math.exp(-(r - r0) / ld) * min(1.0, (r - r0) / (0.35 * F_LAM))


def ripple_frames(s):
    """Ripples where the ring jets land. A crest leaves each landing every F_TR s and runs out at the phase speed
    c = L / T of that wave (deep water, L = g T^2 / 2 pi; surface tension changes L by 0.2%), damped as 1/sqrt(r)
    (spreading) times exp(-r / F_LD). F_FR frames of F_TR / F_FR s: frame F_FR is frame 0 with every crest one
    wavelength further out, so the strip loops. Each frame is one path per opacity, all ten landings in it.
    Returns the frames (svg), the landing points and the drawn radii per frame (for the check)."""
    T = s["T"]
    lands = [(ball(sj, T)[0], ball(sj, T)[2]) for sj in s["sub"]]
    pts = [proj(X, Y_WATER, Z) for X, Z in lands]
    frames, radii = [], []
    for f in range(F_FR):
        by_op, rs = {}, []
        for k in range(2):
            r = F_R0 + F_LAM * (k + f / F_FR)
            q = math.floor(F_AMP * f_ripple_amp(r, F_R0, F_LD) * 20) / 20
            if q >= 0.05:
                rx, ry = SF * r, SF * r * SE
                by_op.setdefault(q, []).append((rx, ry))
                rs.append(r)
        o = []
        for q, rings in sorted(by_op.items()):
            d, pen = [], None
            for rx, ry in rings:
                arc = f"a{f_num((rx, ry))} 0 1 0 {fm(2 * rx)} 0a{f_num((rx, ry))} 0 1 0 {fm(-2 * rx)} 0"
                for x, y in pts:
                    x0, y0 = round(x - rx, 1), round(y, 1)
                    d.append(("M" + f_num((x0, y0)) if pen is None else "m" + f_num((x0 - pen[0], y0 - pen[1]))) + arc)
                    pen = (x0, y0)
            o.append(f'<path d="{"".join(d)}" stroke-opacity="{fm(q, 2)}"/>')
        frames.append(f'<g class="fq">{"".join(o)}</g>')
        radii.append(rs)
    return frames, lands, radii


def f_column(H, r0=0.33):
    """The central column, a vertical jet rising to H: speed v(h) = sqrt(v0^2 - 2 g h). By continuity (area x speed
    constant) its radius grows as r0 sqrt(v0 / v); a parcel reaches h after tau(h) = (v0 - v(h)) / g, so the waves
    the nozzle makes every F_TB seconds ride up with the water and crowd under the crown."""
    v0 = math.sqrt(2 * G * H)

    def v(h):
        return math.sqrt(max(1e-9, v0 * v0 - 2 * G * h))

    def tau(h):
        return (v0 - v(h)) / G

    def rad(h):
        return r0 * math.sqrt(v0 / v(min(h, 0.97 * H)))
    return v0, v, tau, rad


def f_curtain(streams):
    """Radius of the falling curtain (plA) on its way down, at height h above the water."""
    pl = next(s for s in streams if s["name"] == "plA")

    def rc(h):
        best = 0.0
        for x0, y0, z0, vx, vy, vz in pl["sub"]:
            d = vy * vy - 2 * G * (h - y0 + Y_WATER)
            if d >= 0:
                t = (vy + math.sqrt(d)) / G
                best = max(best, math.hypot(x0 + vx * t, z0 + vz * t))
        return best
    return rc


def plume_core_frames(P, H, streams):
    """The central plume, F_TB-periodic: column (lit and shaded halves, a dense core, streaks), crown and the
    churning foam at its foot. Returns the frames, the column radius and the curtain radius (functions of h)."""
    v0, v, tau, rad = f_column(H)
    tH = v0 / G
    bx, by = proj(0, Y_WATER, 0)
    sc = SF * CE
    night = P["night"]
    term = 0.53 if not night else 2.0          # the sun from the WSW lights all but the east quarter of a cylinder
    hs = 0.88 * H
    hts = [hs * (1 - (1 - i / 13) ** 1.7) for i in range(14)]
    frames = []
    for f in range(int(round(F_TB * FPS))):
        t = f / FPS
        lit_l, lit_r, sh_r, core_l, core_r = [], [], [], [], []
        for h in hts:
            r, u = rad(h), tau(h) / tH
            a = 0.04 + 0.24 * u * u
            ph = 2 * math.pi * (t - tau(h)) / F_TB
            sw = 0.05 * u * math.sin(ph + 1.1)
            xl = -r * (1 + a * math.sin(ph)) + sw
            xr = r * (1 + a * math.sin(ph + 2.4)) + sw
            xt = min(xr, term * r + sw)
            y = by - sc * h
            lit_l.append((bx + SF * xl, y))
            lit_r.append((bx + SF * xt, y))
            sh_r.append((bx + SF * xr, y))
            if h < 0.68 * H:
                fade = 1.0 - max(0.0, (h - 0.5 * H) / (0.18 * H)) ** 2
                c = (-0.32 * r if not night else 0.0) + sw
                rc = 0.34 * r * fade * (1 + 0.5 * a * math.sin(ph + 0.8))
                core_l.append((bx + SF * (c - rc), y))
                core_r.append((bx + SF * (c + rc), y))
        o = []
        o.append(f'<path d="{f_d(core_l + core_r[::-1])}" fill="{P["f_sheath"]}"/>')
        # streaks above the core: parcels released every F_TB at 0.5 H, carried up by the flow (h = v0 tau - g tau^2 / 2)
        st = []
        tex = []
        for x0, dt0, ha, hb, dst in ((-0.42, 0.0, .5, .9, st), (0.2, 0.07, .5, .9, st), ):
            tj = tau(ha * H) + (t + dt0) % F_TB
            while tj < tau(hb * H):
                h0, h1 = v0 * tj - G * tj * tj / 2, v0 * (tj + .035) - G * (tj + .035) ** 2 / 2
                dst.append(f_d([(bx + SF * x0 * rad(h0), by - sc * h0), (bx + SF * x0 * rad(h1), by - sc * h1)], close=False))
                tj += F_TB
        o.append(f'<path d="{"".join(st)}" stroke="{P["f_sheath"]}" stroke-width="1.5" stroke-linecap="round"/>')

        # crown: the column keeps flaring (continuity) and rounds over at the apex into one lobed bloom
        (lx, ly), (rx_, ry_) = lit_l[-1], sh_r[-1]
        cxt, half, top = (lx + rx_) / 2, (rx_ - lx) / 2 * 1.18, sc * (H + 0.12 - hs)
        cap = []
        for j in range(1, 12):
            al = math.pi * (1 - j / 12)
            lob = 1 + 0.09 * math.sin(2 * math.pi * t / F_TB + 2.3 * j) + (0.08 if j % 2 else -0.03)
            cap.append((cxt + half * math.cos(al) * lob, ly - top * math.sin(al) * lob))
        xs_top = lit_r[-1][0]
        cap_l = [p_ for p_ in cap if p_[0] <= xs_top]
        cap_r = [p_ for p_ in cap if p_[0] > xs_top]
        if night:
            cap_l, cap_r = cap, []
        split = [(xs_top, ly - top * 0.9)] if cap_r else []
        o.insert(0, f'<path d="{f_d(lit_l + cap_l + split + lit_r[::-1])}" '
                    + (f'fill="{P["f_sheath"]}" fill-opacity=".8"/>' if not night else 'fill="url(#fnL)"/>'))
        if not night:
            o.insert(1, f'<path d="{f_d(lit_r + split + cap_r + sh_r[::-1])}" fill="{P["f_sheath_sh"]}" fill-opacity=".85"/>')
        # the foam mound where the column leaves the water
        top = []
        for k in range(9):
            s_ = -1 + 2 * k / 8
            hm = 0.42 * math.sqrt(max(0.0, 1 - s_ * s_)) * (1 + 0.2 * math.sin(2 * math.pi * t / F_TB + 2.3 * k))
            top.append((bx + SF * 0.82 * s_, by - sc * hm))
        foot = [proj(0.82 * math.cos(math.radians(a)), Y_WATER, 0.82 * math.sin(math.radians(a))) for a in range(0, -181, -45)]
        mound = top + foot
        if not night:                  # split at the terminator: the shaded side joins the sheath's shade path
            xs_ = bx + SF * 0.82 * term
            o[1] = o[1].replace('" fill=', f_d(f_halfplane(mound, xs_, 1)) + '" fill=', 1)
            mound = f_halfplane(mound, xs_, -1)
        o.append(f'<path d="{f_d(mound)}" fill="{P["f_foam"]}"/>')
        frames.append("".join(o))
    rc = f_curtain(streams)
    if night:
        frames[0] = (f'<defs><linearGradient id="fnL" gradientUnits="userSpaceOnUse" x1="0" y1="{fm(by)}" x2="0" '
                     f'y2="{fm(by - sc * H)}"><stop offset="0" stop-color="#FFF4DE" stop-opacity=".92"/><stop offset=".55" '
                     f'stop-color="#FFEFD2" stop-opacity=".7"/><stop offset="1" stop-color="#FFE4B8" stop-opacity=".66"/>'
                     f'</linearGradient></defs>') + frames[0]
    return frames, rad, rc


def fountain_static(P, part, rng=None, ctx=None):
    o = []
    night = P["night"]
    cx = FX
    if part == "ground":
        if not night:
            # the coping's shadow on the plaza: the base circle swept along the sun's ground offset (a crescent)
            dX, dZ = F_SHV[0] * Y_RIM, F_SHV[1] * Y_RIM
            a = math.degrees(math.atan2(dZ, dX))
            n = 36
            outer = [proj(R_OUT * math.cos(math.radians(a - 90 + 180 * i / n)) + dX, 0,
                          R_OUT * math.sin(math.radians(a - 90 + 180 * i / n)) + dZ) for i in range(n + 1)]
            inner = [proj(R_OUT * math.cos(math.radians(a + 90 - 180 * i / n)), 0,
                          R_OUT * math.sin(math.radians(a + 90 - 180 * i / n))) for i in range(n + 1)]
            o.append(f'<path d="{f_d(outer + inner)}" fill="{P["f_cast"]}" fill-opacity=".26"/>')
        o.append(f'<path d="{f_d(f_arc(R_OUT + 0.04, 0, 180, 360, 6), close=False)}" fill="none" stroke="{P["f_occ"]}" '
                 f'stroke-width="2.4"/>')
    elif part == "basin":
        rx, ry = F_RX, F_RY
        # inner wall: lit, its shaded west part, the wet line and the shadow under the coping's lip
        o.append(f'<path d="{ell(cx, F_CYR, rx, ry)}" fill="{P["f_wall"]}"/>')
        if not night:
            th = 180 - math.degrees(math.atan(F_SUN[0] / F_SUN[2]))         # where the inner face turns from the sun
            o.append(f'<path d="{f_d(f_arc(R_IN, Y_RIM, th, 180) + f_arc(R_IN, Y_WATER, 180, th))}" fill="{P["f_wall_sh"]}"/>')
        o.append(f'<path d="{f_d(f_arc(R_IN, Y_WATER, 0, 180, 5), close=False)}{f_d(f_arc(R_IN, Y_RIM, 0, 180, 5), close=False)}" '
                 f'fill="none" stroke="{P["f_wet"]}" stroke-width="2.2"/>')
        # the water: Fresnel from the eye, paler (more sky) at the back, deeper in front
        y0, y1 = F_CYW - ry, F_CYR + ry
        stops = "".join(f'<stop offset="{fm(k / 3, 2)}" stop-color="{f_gap(P, y0 + (y1 - y0) * k / 3)}"/>' for k in range(4))
        o.append(f'<defs><linearGradient id="fnW" gradientUnits="userSpaceOnUse" x1="0" y1="{fm(y0)}" x2="0" y2="{fm(y1)}">'
                 f'{stops}</linearGradient></defs>')
        o.append(f'<path d="{ell(cx, F_CYW, rx, ry)}" fill="url(#fnW)"/>')
    elif part == "coping":
        # outer face in light bands, the ring of the top, joints between the stones, the lit bullnose
        def lum(th):
            t = math.radians(th)
            if not night:
                return F_SUN[0] * math.cos(t) + F_SUN[2] * math.sin(t)
            lx, ly = max(LAMPS, key=lambda l: l[1])[:2]
            LX, LZ = (lx - FX) / SF, (FY - ly) / (SF * SE)
            px, pz = R_OUT * math.cos(t), R_OUT * math.sin(t)
            dx, dy, dz = LX - px, 4.0, LZ - pz
            dd = math.sqrt(dx * dx + dy * dy + dz * dz)
            return (math.cos(t) * dx + math.sin(t) * dz) / dd * (14.0 / dd) ** 2
        cuts = (0.45, 0.0) if not night else (1.6, 0.6)
        cls = []
        for th in range(180, 361):
            L = lum(th)
            cls.append(0 if L > cuts[0] else (1 if L > cuts[1] else 2))
        cols = (P["f_lit"], P["f_mid"], P["f_sh"])
        i = 0
        while i < len(cls):
            j = i
            while j + 1 < len(cls) and cls[j + 1] == cls[i]:
                j += 1
            a0, a1 = 180 + i, 180 + j + 1 if j + 1 < len(cls) else 360
            o.append(f'<path d="{f_d(f_arc(R_OUT, Y_RIM, a0, a1, 5) + f_arc(R_OUT, 0, a1, a0, 5))}" fill="{cols[cls[i]]}"/>')
            i = j + 1
        o.append(f'<path d="{ell(cx, F_CYR, SF * R_OUT, SF * R_OUT * SE)}{ell(cx, F_CYR, F_RX, F_RY)}" fill="{P["f_top"]}" '
                 f'fill-rule="evenodd"/>')
        jt = []
        for k in range(24):
            th = 7.5 + 15 * k
            a, b = f_xy(R_OUT, th, Y_RIM), f_xy(R_IN, th, Y_RIM)
            jt.append(f_d([b, a] + ([(a[0], a[1] + SF * CE * Y_RIM)] if th > 180 else []), close=False))
        o.append(f'<path d="{"".join(jt)}" fill="none" stroke="{P["f_joint"]}" stroke-opacity=".3" stroke-width=".9"/>')
        lit = [th for th in range(180, 361) if lum(th) > (0.25 if not night else 1.9)]
        if lit:
            o.append(f'<path d="{f_d(f_arc(R_OUT, Y_RIM, lit[0], lit[-1], 5), close=False)}" fill="none" stroke="{P["f_edge"]}" '
                     f'stroke-width="1.5" stroke-linecap="round"/>')
        if not night:
            o.append(f'<path d="{f_d(f_arc(R_IN, Y_RIM, 8, 172, 6), close=False)}" fill="none" stroke="{P["f_edge"]}" stroke-width="1"/>')
    return "\n".join(o)


def f_reflection(P, rng, H, rad, rc):
    """The water's reflections as broken horizontal strips. Each row of water sees, through its own camera, the
    mirror image of what stands behind it: the plume (proj, below its foot), then through persp the trees, the arch
    (mirrored about the water line at its depth, so row v shows the pier at height (v - AY + 2 yw U) / U), and
    through the opening Fifth Avenue's sky and the Empire State Building. Elsewhere the gaps' sky colour stands for
    the reflection. Ripples shift each row sideways and break it. Returns static svg, shimmer frames, check rows.
    (The far inner wall's own reflection is f_wall_band.)"""
    night = P["night"]
    bx, by = proj(0, Y_WATER, 0)
    sc = SF * CE
    zE, xE, prof = F_ESB
    kE = DC / (DC + zE)
    trees = [(x, 2 * f_vm(yb) - cy, rx, ry, fi) for x, yb, cy, rx, ry, fi in f_trees()]
    xbl, xbr = VPX + (-OPEN_HW - VPX) * FB, VPX + (OPEN_HW - VPX) * FB

    def tree_col(fi):
        try:
            return P["fol"][fi][1]
        except (KeyError, IndexError, TypeError):
            return P["v_sh"]
    cols = {"stone": P["f_arch_ref"], "in_l": P["inner_l"], "sky": P["v_sky"], "esb": P["v_esb"], "esb_top": "#9B5CE0",
            "col": P["f_sheath"], "veil": P["f_sheath"]}
    gain = {"veil": 0.45}

    def material(x, v):
        h = (v - by) / sc
        if h > 0:
            dx = abs(x - bx) / SF
            if dx < rad(h) * 1.1:
                return "col"
            if dx < rc(h):
                return "veil"
        for tx, cyr, rx_, ry_, fi in trees:
            if abs(v - cyr) < ry_ and abs(x - tx) < rx_ * math.sqrt(1 - ((v - cyr) / ry_) ** 2):
                cols.setdefault(f"t{fi}", tree_col(fi))
                return f"t{fi}" if not night else None
        yft = (v - AY + 2 * F_YW * U) / U
        xa = (x - AX) / U
        if abs(xa) <= f_arch_hw(yft):
            if abs(xa) >= f_open_hw(yft):
                return "stone"
            if xa < xbl:
                return "in_l" if not night else "stone"
            if xa > xbr:
                return "stone"
            yE = 2 * F_YW - VPY - ((AY - v) / U - VPY) / kE
            for y0_, y1_, hw in prof:
                if y0_ <= yE < y1_ and VPX + (xE - hw - VPX) * kE <= xa <= VPX + (xE + hw - VPX) * kE:
                    return "esb_top" if night and 1100 <= yE < 1268 else "esb"
            return "sky"
        return None

    rows = []
    y = F_CYW - F_RY + F_DW + 1.0
    yend = F_CYR + F_RY - 0.8
    while y < yend:
        u = (y - (F_CYW - F_RY)) / (yend - (F_CYW - F_RY))
        band = min(2, int(u * 3))
        th = (1.4, 2.0, 2.6)[band]
        rows.append((y + th / 2, th, u, band))
        y += th + (1.6 + 4.6 * u) * rng.uniform(0.75, 1.3)
    by_col, bright, check_rows = {}, [], []
    band_y = [F_CYW - F_RY + F_DW + (yend - F_CYW + F_RY - F_DW) * (b + 0.5) / 3 for b in range(3)]
    for yc, th, u, band in rows:
        hw = f_vis(yc, F_DW) - 1.5
        if hw < 4:
            continue
        dlt = rng.gauss(0, 0.6 + 3.6 * u)               # the ripple under this row tilts it sideways
        runs = []
        x = FX - hw
        while x < FX + hw:
            m = material(x - dlt, yc)
            if runs and runs[-1][0] == m:
                runs[-1][2] = x + 1
            else:
                if runs:                                # the exact edge, by bisection
                    lo, hi = x - 1.0, x
                    for _ in range(14):
                        mid = (lo + hi) / 2
                        lo, hi = (mid, hi) if material(mid - dlt, yc) == runs[-1][0] else (lo, mid)
                    runs[-1][2] = (lo + hi) / 2
                runs.append([m, runs[-1][2] if runs else x, x + 1])
            x += 1.0
        runs[-1][2] = min(runs[-1][2], FX + hw)
        check_rows.append((yc, dlt, [tuple(r) for r in runs]))
        for m, x0, x1 in runs:
            if m is None or x1 - x0 < 2:
                continue
            k = gain.get(m, 1.0) * (1 - 0.35 * (band + 0.5) / 3)   # rougher water nearer the jets scatters the image
            col = f_refl(P, band_y[band], cols[m], k)
            base = f_gap(P, band_y[band])
            if sum(abs(int(col[i:i + 2], 16) - int(base[i:i + 2], 16)) for i in (1, 3, 5)) < 9:
                continue
            e0, e1 = x0 + rng.uniform(-1, 2) * (1 + 2 * u), x1 - rng.uniform(-1, 2) * (1 + 2 * u)
            xs = e0 + rng.uniform(0, 3)
            while xs < e1 - 2:
                ln = min(e1 - xs, 2.5 + rng.expovariate(1 / (9 * (1.1 - 0.6 * u))))
                if rng.random() < (0.86 - 0.36 * u) * (0.6 if m[0] == "t" else 1.0) and ln > th:
                    by_col.setdefault((th, col), []).append((round(xs + th / 2, 1), round(yc, 1), round(ln - th, 1)))
                    if m in ("stone", "col") or (night and m == "esb_top"):
                        bright.append((xs, xs + ln, yc, th, m))
                xs += ln + rng.uniform(1.6, 4.5) * (0.6 + 1.6 * u)
    out = ['<g fill="none" stroke-linecap="round">']
    for w in sorted({k[0] for k in by_col}):
        out.append(f'<g stroke-width="{fm(w)}">')
        out += [f'<path d="{f_hd(ds)}" stroke="{c}"/>' for (th, c), ds in by_col.items() if th == w]
        out.append("</g>")
    out.append("</g>")
    # shimmer: the brightest strips break up and re-form, 4 frames
    shim = []
    hi = P["f_edge"] if not night else "#FFE7B0"
    for f in range(F_FR):
        ds = []
        for _ in range(9 if night else 6):
            if not bright:
                break
            x0, x1, yc, th, m = rng.choice(bright)
            ln = rng.uniform(3, 8)
            xs = rng.uniform(x0, max(x0, x1 - ln))
            ds.append((round(xs, 1), round(yc, 1), round(ln, 1)))
        shim.append(f'<path d="{f_hd(ds)}" stroke="{hi}" stroke-width="1.6" stroke-opacity="{".55" if not night else ".8"}"/>')
    return "\n".join(out), shim, check_rows


def f_wall_band(P):
    """The far inner wall mirrored in the water (proj): a band as tall as the wall under the far waterline."""
    o = []
    th_s = 180 - math.degrees(math.atan(F_SUN[0] / F_SUN[2])) if not P["night"] else 181.0
    parts = ((0.5, th_s, P["f_wall"]), (th_s, 179.5, P["f_wall_sh"]))
    for a0, a1, col in parts:
        if a1 <= a0:
            continue
        top, bot = [], []
        n = max(2, int((a1 - a0) / 3))
        for i in range(n + 1):
            th = math.radians(a0 + (a1 - a0) * i / n)
            x = FX + F_RX * math.cos(th)
            yb = F_CYW - F_RY * math.sin(th)
            yf = F_CYR + F_RY * math.sin(th)
            y2 = min(yb + F_DW + 0.5 * math.sin(x * 0.23), yf)
            if y2 > yb:
                top.append((x, yb))
                bot.append((x, y2))
        if len(top) > 1:
            yc = F_CYW - F_RY + F_DW / 2
            o.append(f'<path d="{f_d(top + bot[::-1])}" fill="{f_refl(P, yc, col)}"/>')
    return "\n".join(o)


def f_water_shadow(P):
    """Light theme: the coping's shadow on the water by the sunward (WSW) wall: the water disc minus the disc moved
    by the shadow offset of the wall's 0.3 m above the water. Seen through the water: R sky + (1-R) half the floor."""
    if P["night"]:
        return ""
    sX, sZ = F_SHV[0] * (Y_RIM - Y_WATER), F_SHV[1] * (Y_RIM - Y_WATER)
    ds = math.hypot(sX, sZ)
    phs = math.degrees(math.atan2(sZ, sX))
    da = math.degrees(math.acos(ds / (2 * R_IN)))
    a0, a1 = phs + da, phs + 360 - da
    c0 = [proj(R_IN * math.cos(math.radians(a)), Y_WATER, R_IN * math.sin(math.radians(a)))
          for a in (a0 + (a1 - a0) * i / 40 for i in range(41))]
    # back along the moved circle, inside the water
    p1 = (R_IN * math.cos(math.radians(a1)) - sX, R_IN * math.sin(math.radians(a1)) - sZ)
    p0 = (R_IN * math.cos(math.radians(a0)) - sX, R_IN * math.sin(math.radians(a0)) - sZ)
    b1, b0 = math.degrees(math.atan2(p1[1], p1[0])) % 360, math.degrees(math.atan2(p0[1], p0[0])) % 360
    if b0 > b1:
        b0 -= 360
    c1 = [proj(sX + R_IN * math.cos(math.radians(a)), Y_WATER, sZ + R_IN * math.sin(math.radians(a)))
          for a in (b1 - (b1 - b0) * i / 40 for i in range(41))]
    R = f_R(F_CYW)
    col = f_hex([(1 - R) * 0.5 * a + R * b for a, b in zip(f_lin(P["f_body"]), f_lin(P["f_env"]))])
    return f'<path d="{f_d(c0 + c1)}" fill="{col}"/>'


def f_churn(P, rng, rc):
    """White water where the curtain lands (plA, r 0.7-1.9 m) and the skirt's splashes (plB, r 1.9-3 m)."""
    bx, by = proj(0, Y_WATER, 0)
    r1 = rc(0.0) + 0.15
    o = [f'<path d="{ell(bx, by, SF * r1, SF * r1 * SE)}{ell(bx, by, SF * 0.5, SF * 0.5 * SE)}" fill="{P["f_foam"]}" '
         f'fill-opacity="{".4" if not P["night"] else ".5"}" fill-rule="evenodd"/>']
    blobs, spots = [], []
    for i in range(11):
        a = 2 * math.pi * (i + rng.uniform(-.3, .3)) / 11
        r = rng.uniform(0.75, r1 - 0.2)
        x, y = proj(r * math.cos(a), Y_WATER, r * math.sin(a))
        blobs.append(ell(x, y, rng.uniform(4.5, 8.5), rng.uniform(1.3, 2.1)))
    for i in range(9):
        a = 2 * math.pi * (i + rng.uniform(-.3, .3)) / 9 + .2
        r = rng.uniform(r1 + 0.1, 2.9)
        x, y = proj(r * math.cos(a), Y_WATER, r * math.sin(a))
        spots.append(ell(x, y, rng.uniform(2.5, 4.5), rng.uniform(.9, 1.3)))
    o.append(f'<path d="{"".join(blobs)}" fill="{P["f_foam"]}"/>')
    o.append(f'<path d="{"".join(spots)}" fill="{P["f_foam"]}" fill-opacity=".75"/>')
    return "\n".join(o)


def f_splashes(P, lands):
    """Where each ring jet lands: a foam patch the size of the splash crater (about 0.3 m)."""
    d = "".join(ell(*proj(X, Y_WATER, Z), 7.0, 1.6) for X, Z in lands)
    return f'<path d="{d}" fill="{P["f_foam"]}" fill-opacity=".85"/>'


def f_spark(x, y, s):
    k = 0.24 * s
    return f_d([(x, y - s), (x + k, y - k), (x + s, y), (x + k, y + k), (x, y + s), (x - k, y + k), (x - s, y), (x - k, y - k)])


def f_glints(P, rng, lands):
    """Sun glints (light) / lamp glints (dark) where the water is steep enough to send the light to the eye: in the
    skirt's splash zone round the plume and on the ring jets' splashes. Calm water cannot: the sun is behind the
    viewer's left shoulder, so a facet would have to tilt ~73 deg. Each glint lasts two frames of the water strip."""
    spots = []
    for _ in range(F_FR // 2):
        g = []
        for _ in range(3):
            if rng.random() < 0.5:
                a = math.radians(rng.uniform(100, 260))
                rr = rng.uniform(2.2, 2.9)
                x, y = proj(rr * math.cos(a), Y_WATER, rr * math.sin(a))
            else:
                X, Z = rng.choice([l for l in lands if l[0] < 1.0] or lands)
                x, y = proj(X, Y_WATER, Z)
                x += rng.uniform(-5, 5)
            g.append(f_spark(x, y - 1.6, rng.uniform(2.4, 3.6)))
        spots.append(g)
    frames = []
    for f in range(F_FR):
        d = spots[f // 2] + spots[((f + 1) // 2) % len(spots)][:1]
        frames.append(f'<path d="{"".join(d)}" fill="{P["f_glint"]}"/>')
    return frames


def f_night_lights(P, streams):
    """Dark theme: the lights in the basin. A glow on the water round the plume's foot and a lamp at each ring-jet
    nozzle (the jets are lit from below)."""
    if not P["night"]:
        return ""
    bx, by = proj(0, Y_WATER, 0)
    o = ['<defs><radialGradient id="fnG"><stop offset="0" stop-color="#FFE7B4" stop-opacity=".6"/>'
         '<stop offset=".45" stop-color="#FFD58E" stop-opacity=".2"/><stop offset="1" stop-color="#FFD58E" stop-opacity="0"/>'
         '</radialGradient></defs>']
    o.append(f'<ellipse cx="{fm(bx)}" cy="{fm(by)}" rx="120" ry="24" fill="url(#fnG)"/>')
    d = "".join(ell(*proj(sj[0], Y_WATER, sj[2]), 3.2, 1.1) for sj in streams[0]["sub"])
    o.append(f'<path d="{d}" fill="#FFF2CF"/>')
    return "\n".join(o)


F_SITTERS = ((962.0, 0.98, 0, "sitread"), (1018.0, 1.0, 1, "sit"))      # x on the front coping, scale, coat, kind


def f_seat(x, k):
    """Feet row for a person sitting on the coping top just behind its outer edge at page x (person(): the thighs'
    underside is 9.6 k above the feet). Their feet hang in front of the face, a little above the plaza."""
    u = (x - FX) / (SF * R_OUT)
    edge = F_CYR + SF * R_OUT * SE * math.sqrt(1 - u * u)
    return edge - 1.2 + 9.6 * k, edge


def f_sitters(P):
    """The two people on the rim, with their shadows where the sun puts them: the body's shadow lies on the coping top
    and runs ENE off its inner edge onto the water (0.3 m lower, so it jumps on by 0.3 m x the shadow ratio), the
    dangling shins throw a short shadow onto the face. Same shadow ratio and direction as people_svg."""
    o = []
    for x, k, ci, kind in F_SITTERS:
        y, edge = f_seat(x, k)
        if not P["night"]:
            L = 26.0 * k * F_SHK                       # the body stands 26 k units above the seat, shadow 2.6 x that
            dx, dy = SUN[0] * L, SUN[1] * L
            seat = y - 9.6 * k
            body = [(x - 5 * k, seat + 0.6), (x + dx * 0.55 - 2 * k, seat + dy * 0.55 - 1.2), (x + dx * 0.55 + 3 * k, seat + dy * 0.55 + 0.9),
                    (x + 6 * k, seat + 1.4)]
            o.append(f'<path d="{f_d(body)}" fill="{P["f_sh"]}" fill-opacity=".55"/>')
            shin = [(x + 7 * k, y - 8.5 * k), (x + 12.5 * k, y - 9.2 * k), (x + 13.5 * k, y - 0.4 * k), (x + 9.8 * k, y)]
            o.append(f'<path d="{f_d(shin)}" fill="{P["f_sh"]}" fill-opacity=".6"/>')
        o.append(person(x, y, k, P["coat"][ci], P, kind))
    return "\n".join(o)


def check_fountain(out_dir, data):
    """Proofs for the fountain, recomputed from the cameras and from the emitted SVG."""
    fd = data["fountain"]
    print("== fountain")
    d_hid = (Y_RIM - Y_WATER) / math.tan(EL)
    yv = proj(0, Y_WATER, -R_IN + d_hid)[1]
    print(f"  basin: coping {Y_RIM} m high ({SF * CE * Y_RIM:.1f} units) and {R_OUT - R_IN:.1f} m deep, water {Y_RIM - Y_WATER:.2f} m "
          f"below its top: far wall shows {F_DW:.2f} units; the front coping hides the near {d_hid:.2f} m of water "
          f"(line of sight over its inner edge meets the water {abs(yv - (F_CYR + F_RY)):.1e} units from where drawn)")
    el, az = math.degrees(math.asin(F_SUN[1])), math.degrees(math.atan2(-F_SUN[0], -F_SUN[2]))
    print(f"  sun from people_svg's shadows (2.6 x height along SUN): elevation {el:.1f} deg, {az:.0f} deg east of north toward "
          f"the shadow; coping shadow reaches {Y_RIM * math.hypot(*F_SHV):.2f} m past the rim (crescent, no wedge)")
    y0, y1 = F_CYW - F_RY, F_CYR + F_RY
    print(f"  Fresnel (n = 1.333, eye {F_EYE:.0f} m south, {F_EYE * math.tan(EL):.1f} m up): R = {f_R(y0):.2f} at the far wall, "
          f"{f_R((y0 + y1) / 2):.2f} mid-basin, {f_R(y1):.2f} at the front coping")
    # the arch mirrored in the water plane through persp(), against the strips' material edges
    worst, nrow, hts = 0.0, 0, []
    yw = F_YW
    for yc, dlt, runs in fd["rows"]:
        edges = [(x0, x1) for m, x0, x1 in runs if m == "stone"]
        if not edges:
            continue
        yft = None
        lo, hi = -5.0, 80.0                 # height whose mirror image projects onto this row, by bisection on persp
        for _ in range(60):
            mid = (lo + hi) / 2
            if persp(31.0, 2 * yw - mid, 0)[1] < yc:
                lo = mid
            else:
                hi = mid
        yft = (lo + hi) / 2
        hts.append(yft)
        xbr = persp(OPEN_HW, 2 * yw - yft, DEPTH)[0]   # the lit right intrados (seen to the back face) reads as stone
        want = sorted([persp(s_ * f_arch_hw(yft), 2 * yw - yft, 0)[0] for s_ in (-1, 1)] +
                      [persp(-f_open_hw(yft), 2 * yw - yft, 0)[0], xbr])
        got = sorted([e for x0, x1 in edges for e in (x0, x1)])
        lim = [x for x in (FX - f_vis(yc, F_DW) + 1.5, FX + f_vis(yc, F_DW) - 1.5)]
        for w_, g_ in zip(want, (got[0], got[1], got[-2], got[-1]) if len(got) >= 4 else got):
            w_ += dlt
            if lim[0] + 1 < w_ < lim[1] - 1:
                worst = max(worst, abs(w_ - g_))
        nrow += 1
    print(f"  arch reflection: the arch mirrored in the water plane (y -> {2 * yw:.2f} ft - y) through persp: {nrow} rows show the "
          f"piers from {min(hts):.1f} to {max(hts):.1f} ft; strip edges match the mirrored silhouette (+ each row's ripple "
          f"shift) to {worst:.3f} units")
    zE, xE, prof = F_ESB
    tip = persp(xE, 2 * yw - prof[-1][1], zE)
    esb_rows = [yc for yc, dlt, runs in fd["rows"] if any(m.startswith("esb") for m, _, _ in runs if m)]
    print(f"  Empire State Building upside down in the opening: its mirror image spans rows {persp(xE, 2 * yw, zE)[1]:.1f} "
          f"(base, above the water) to {tip[1]:.1f} (spire); drawn in {len(esb_rows)} rows "
          f"{min(esb_rows):.1f}-{max(esb_rows):.1f}, below that the plume's own reflection is nearer and covers it")
    # ripples: dispersion and the seam of the 12-frame strip
    lam_c = F_LAM
    for _ in range(40):                      # capillary-gravity: w^2 = g k + (sigma / rho) k^3 at w = 2 pi / T
        kk = 2 * math.pi / lam_c
        w2 = (2 * math.pi / F_TR) ** 2
        kk = w2 / (G + 7.28e-5 * kk * kk)
        lam_c = 2 * math.pi / kk
    radii = fd["rip_r"]
    n = len(radii)
    nxt = [F_R0 + F_LAM * (k + 1) for k in range(2)]
    nxt = [r for r in nxt if math.floor(F_AMP * f_ripple_amp(r, F_R0, F_LD) * 20) / 20 >= 0.05]
    seam = max(abs(a - b) for a, b in zip(sorted(radii[0]), nxt)) if len(radii[0]) == len(nxt) else float("nan")
    gone = math.floor(F_AMP * f_ripple_amp(F_R0 + 2 * F_LAM, F_R0, F_LD) * 20) / 20     # where it would be next
    print(f"  ripples: T = {F_TR} s, deep-water L = g T^2 / 2 pi = {F_LAM:.3f} m (with surface tension {lam_c:.3f} m), crests at "
          f"c = {F_LAM / F_TR:.2f} m/s, {F_LAM / F_FR * 100:.1f} cm per {F_TR / F_FR:.1f} s frame; frame {n} = frame 0 with every "
          f"crest one wavelength out (radii within {seam * 100:.1f} cm); the crest leaving the strip is drawn at opacity {gone:.2f}")
    # plume: apex, continuity, and the streaks riding up with the water (from the emitted frames)
    H = fd["H"]
    v0 = math.sqrt(2 * G * H)
    plA = next(st for st in data["streams"] if st["name"] == "plA")
    apex = max(ball(sj, sj[4] / G)[1] for sj in plA["sub"]) - Y_WATER
    rad = fd["rad"]
    cont = max(abs(rad(h) * math.sqrt(math.sqrt(max(1e-9, v0 * v0 - 2 * G * h))) - rad(0) * math.sqrt(v0)) / (rad(0) * math.sqrt(v0))
               for h in [H * i / 20 for i in range(18)])
    sc = SF * CE
    by = proj(0, Y_WATER, 0)[1]
    worst_v, nd = 0.0, 0
    fr = fd["plume_fr"]
    for f in range(len(fr)):
        a = re.findall(r'<path d="([^"]+)" stroke="#FFFFFF" stroke-width="1.5"', fr[f])
        b = re.findall(r'<path d="([^"]+)" stroke="#FFFFFF" stroke-width="1.5"', fr[(f + 1) % len(fr)])
        if not a or not b:
            continue
        def tails(dd):
            out = []
            for m in re.finditer(r"M(-?[\d.]+) (-?[\d.]+)l(-?[\d.]+)[ ]?(-?[\d.]+)", dd.replace("-", " -").replace("l ", "l")):
                out.append((float(m.group(1)), (by - float(m.group(2))) / sc))
            return out
        ha, hb = tails(a[0]), tails(b[0])
        for x, h in ha:
            tau_ = (v0 - math.sqrt(max(0.0, v0 * v0 - 2 * G * h))) / G + 1 / FPS
            if tau_ >= (v0 - math.sqrt(v0 * v0 - 2 * G * 0.9 * H)) / G:
                continue                    # this parcel leaves the streak zone
            h2 = v0 * tau_ - G * tau_ * tau_ / 2
            best = min((abs(h2 - hh) for xx, hh in hb if abs(xx - x) < 3), default=None)
            if best is not None:
                worst_v = max(worst_v, best)
                nd += 1
    print(f"  plume: column apex {H:.2f} m = plA apex {apex:.2f} m; v0 = {v0:.1f} m/s; radius x sqrt(speed) constant to {cont:.1e} "
          f"(continuity); {nd} streaks checked one frame on: they sit where the water carries them to {worst_v * 100:.1f} cm")
    # people on the rim
    for x, k_, ci, kind in F_SITTERS:
        y, edge = f_seat(x, k_)
        base = edge + SF * CE * Y_RIM
        print(f"  {kind} at x={x:.0f}: thighs {edge - (y - 9.6 * k_):.1f} units behind the coping edge, feet {base - y:.1f} units "
              f"({(base - y) / sc * 100:.0f} cm) above the plaza")
    # the drops as drawn: re-read the relative paths from the SVG
    svg = open(os.path.join(out_dir, "hero-light.svg")).read()
    got = []
    strips = re.findall(r'<g><animateTransform attributeName="transform" type="translate" values="[^"]*" dur="\.3s"[^>]*/>'
                        r'(.*?)</g></g>', svg)
    for body in strips:
        if 'class="d' not in body:
            continue
        if True:
            for dd in re.findall(r'<path d="([^"]+)" class="d\d"/>', body):
                toks = re.findall(r"[Mml]|-?\d*\.?\d+", dd)
                i, pen, cmd = 0, (0.0, 0.0), None
                while i < len(toks):
                    if toks[i] in "Mml":
                        cmd = toks[i]
                        i += 1
                    xv, yv_ = float(toks[i]), float(toks[i + 1])
                    i += 2
                    if cmd == "M":
                        pen = (xv, yv_)
                        got.append(pen)
                        cmd = "l"
                    elif cmd == "m":
                        pen = (pen[0] + xv, pen[1] + yv_)
                        got.append(pen)
                        cmd = "l"
                    else:
                        pen = (pen[0] + xv, pen[1] + yv_)
                        cmd = "m"
    want = [(x, y) for _, _, _, x, y in data["tracks"]]
    got = [(round(x, 6), round(y, 6)) for x, y in got]
    err = max(math.dist(a, b) for a, b in zip(sorted(got), sorted(want))) if len(got) == len(want) else float("nan")
    print(f"  drops: {len(got)} drawn with relative moves, positions re-read from the SVG match the ballistic tracks to {err:.3f} units")


# ------------------------------------------------------------------ pigeons (boids)
def homes_layout(rng):
    pts = []
    tries = 0
    while len(pts) < 13 and tries < 5000:
        tries += 1
        x, y = rng.uniform(372, 880), rng.uniform(556, 628)
        if any(math.hypot(x - a, (y - b) * 1.6) < 40 for a, b, _ in pts):
            continue
        if abs(x - 298) < 30:
            continue
        pts.append((x, y, rng.choice((1, -1))))
    pts.sort(key=lambda p: p[1])
    return pts


GUIDE = dict(cx=650.0, cy=338.0, rx=440.0, ry=96.0, phi0=math.radians(68), t0=1.30, t1=8.05)


def guide_pt(t):
    g = GUIDE
    u = min(1.0, max(0.0, (t - g["t0"]) / (g["t1"] - g["t0"])))
    # ease the loop a little: faster along the bottom, slower over the top
    u2 = u - 0.035 * math.sin(2 * math.pi * u)
    ph = g["phi0"] - 2 * math.pi * u2
    return g["cx"] + g["rx"] * math.cos(ph), g["cy"] + g["ry"] * math.sin(ph)


def simulate_flock(homes, rng):
    N = len(homes)
    sub = 3
    dt = 1.0 / (FPS * sub)
    xs = [h[0] for h in homes]
    xmin, xmax = min(xs), max(xs)
    toff = [26 + int(round(7 * (h[0] - xmin) / (xmax - xmin))) + rng.randint(0, 2) for h in homes]
    offs = []
    for i in range(N):
        a, r = rng.uniform(0, 2 * math.pi), rng.uniform(10, 62)
        offs.append((r * math.cos(a), r * math.sin(a) * 0.5))
    land_start = [GUIDE["t1"] - 1.25 + 0.55 * rng.random() for _ in range(N)]
    pos = [[h[0], h[1]] for h in homes]
    vel = [[0.0, 0.0] for _ in homes]
    state = ["ground"] * N
    frames = [[None] * NF for _ in range(N)]
    vmax, vcr = 400.0, 300.0
    landed = [None] * N
    for step in range(NF * sub):
        t = step * dt
        f = step // sub
        for i in range(N):
            if state[i] == "ground" and landed[i] is None and f >= toff[i]:
                state[i] = "fly"
                vel[i] = [rng.uniform(-20, 70), rng.uniform(-330, -280)]
        acc = [[0.0, 0.0] for _ in range(N)]
        for i in range(N):
            if state[i] == "ground":
                continue
            px, py = pos[i]
            vx, vy = vel[i]
            sep = [0.0, 0.0]
            ali = [0.0, 0.0]
            coh = [0.0, 0.0]
            na = nc = 0
            for j in range(N):
                if j == i or state[j] == "ground":
                    continue
                dx, dy = px - pos[j][0], py - pos[j][1]
                d = math.hypot(dx, dy) + 1e-6
                if d < 52:
                    s = (52 - d) / 52
                    sep[0] += dx / d * s * s * 7000
                    sep[1] += dy / d * s * s * 7000
                if d < 95:
                    ali[0] += vel[j][0]
                    ali[1] += vel[j][1]
                    na += 1
                if d < 150:
                    coh[0] += pos[j][0]
                    coh[1] += pos[j][1]
                    nc += 1
            ax, ay = sep
            if na:
                ax += (ali[0] / na - vx) * 1.4
                ay += (ali[1] / na - vy) * 1.4
            if nc:
                ax += (coh[0] / nc - px) * 0.9
                ay += (coh[1] / nc - py) * 0.9
            if state[i] == "fly" and t >= land_start[i]:
                state[i] = "land"
            if state[i] == "fly":
                gx, gy = guide_pt(t + 0.35)
                tx, ty = gx + offs[i][0], gy + offs[i][1]
                dx, dy = tx - px, ty - py
                d = math.hypot(dx, dy) + 1e-6
                want = min(vmax, 160 + d * 1.6)
                ax += (dx / d * want - vx) * 2.6
                ay += (dy / d * want - vy) * 2.6
            else:   # arrive at home, coming in from above
                hx, hy = homes[i][0], homes[i][1]
                el = t - land_start[i]
                tx, ty = hx, hy - max(0.0, 60 - 60 * el)
                dx, dy = tx - px, ty - py
                d = math.hypot(dx, dy) + 1e-6
                want = min(vcr, d * 2.2)
                ax = ax * max(0.0, 1 - el) + (dx / d * want - vx) * (3.0 + 2.0 * el)
                ay = ay * max(0.0, 1 - el) + (dy / d * want - vy) * (3.0 + 2.0 * el)
                if d < 2.0 and math.hypot(vx, vy) < 30 and landed[i] is None:
                    landed[i] = f + 1
            amax = 1500.0
            am = math.hypot(ax, ay)
            if am > amax:
                ax, ay = ax / am * amax, ay / am * amax
            acc[i] = [ax, ay]
        for i in range(N):
            if state[i] == "ground":
                continue
            vel[i][0] += acc[i][0] * dt
            vel[i][1] += acc[i][1] * dt
            sp = math.hypot(*vel[i])
            if sp > vmax:
                vel[i] = [vel[i][0] / sp * vmax, vel[i][1] / sp * vmax]
            pos[i][0] += vel[i][0] * dt
            pos[i][1] += vel[i][1] * dt
            if landed[i] is not None:
                state[i] = "ground"
                pos[i] = [homes[i][0], homes[i][1]]
                vel[i] = [0.0, 0.0]
        if step % sub == sub - 1:
            for i in range(N):
                frames[i][f] = (pos[i][0], pos[i][1])
    for i in range(N):
        if landed[i] is None:
            raise SystemExit(f"bird {i} did not land")
    # exact touch-down: blend the last 14 frames onto the home spot (sub-unit corrections)
    for i in range(N):
        L = landed[i]
        hx, hy = homes[i][0], homes[i][1]
        ex, ey = hx - frames[i][L - 1][0], hy - frames[i][L - 1][1]
        for f in range(max(toff[i] + 1, L - 14), L):
            s = (f - (L - 14)) / 13.0
            s = s * s * (3 - 2 * s)
            frames[i][f] = (frames[i][f][0] + ex * s, frames[i][f][1] + ey * s)
        for f in range(L, NF):
            frames[i][f] = (hx, hy)
        for f in range(0, toff[i] + 1):
            frames[i][f] = (hx, hy)
    return frames, toff, landed


def flap_states(fr, toff, land):
    """Per frame: 'g' ground, 'f' flapping, 'l' gliding (from the sim: climbing or speeding up -> flap)."""
    st = []
    for f in range(NF):
        if f <= toff or f >= land:
            st.append("g")
            continue
        p0 = fr[max(0, f - 1)]
        p1 = fr[f]
        p2 = fr[min(NF - 1, f + 1)]
        vy = (p2[1] - p0[1]) * FPS / 2
        sp1 = math.dist(p0, p1)
        sp2 = math.dist(p1, p2)
        climbing = vy < -70
        speeding = sp2 - sp1 > 0.9
        st.append("f" if (f - toff < 16 or land - f < 8 or climbing or speeding) else "l")
    # minimum run length 5 frames
    out = st[:]
    i = 0
    while i < NF:
        j = i
        while j < NF and out[j] == out[i]:
            j += 1
        if out[i] == "l" and j - i < 6:
            for k in range(i, j):
                out[k] = "f"
        i = j
    return out


def bird_sprites(P):
    """defs: flight frames w0..w3, glide, flap phase groups fA..fD, ground gR/gRp/gL/gLp."""
    o = []

    def cubic(p0, p1, p2, p3, n=6):
        return [tuple((1 - t) ** 3 * a + 3 * (1 - t) ** 2 * t * b + 3 * (1 - t) * t * t * c + t ** 3 * d
                      for a, b, c, d in zip(p0, p1, p2, p3)) for t in (k / n for k in range(1, n + 1))]

    def ccw(pts):
        a = sum(x0 * y1 - x1 * y0 for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]))
        return pts if a < 0 else pts[::-1]

    def frame(tx, ty, sw):
        up = [(2.4, -2.2)] + cubic((2.4, -2.2), (2.6 + sw, ty * 0.45), (tx + 3.2, ty * 0.86), (tx, ty)) + \
             cubic((tx, ty), (tx - 3.6, ty * 0.72), (-6.2, ty * 0.38), (-5.6, -2.2))
        dn = [(x, -y) for x, y in up]
        body = [(9.5 + 2.7 * math.cos(a), 2.7 * math.sin(a)) for a in (k * math.pi / 4 for k in range(-3, 4))]
        body += [(5.0, 2.6), (-1, 3.2), (-6, 2.5), (-14.2, 4.4), (-14.8, 0), (-14.2, -4.4), (-6, -2.5), (-1, -3.2), (5.0, -2.6)]
        return "".join(poly(ccw(pp_), 1) for pp_ in (up, dn, body))

    specs = {"w0": (-3.0, -17.0, 0), "w1": (0.6, -10.5, 1.5), "w2": (-7.0, -13.5, -1), "w3": (-9.2, -6.8, -1.5)}
    for k, (tx, ty, sw) in specs.items():
        o.append(f'<path id="{k}" d="{frame(tx, ty, sw)}"/>')
    # ground pigeon, side view facing +x, feet at the origin; shadow points east (light) / pools under (dark)
    if not P["night"]:
        shadow = f'<path d="M-6 0.4C2 -1.2 18 -3.6 30 -3.2C31.6 -2.4 31 -1 29 -0.2C18 1.6 4 2.2 -5 2Z" fill="{P["g_shadow"]}"/>'
    else:
        shadow = f'<ellipse cx="0" cy="0.6" rx="10" ry="2.2" fill="{P["g_shadow"]}"/>'
    bodyp = (f'<path d="M9 -9C9.2 -3.4 4.4 -0.6 -2 -1.2L-14 -4.6-13.8 -7C-8 -7.2-4 -11 2 -12.2C5.2 -12.6 8.4 -11.8 9 -9Z" fill="{P["g_body"]}"/>'
             f'<path d="M-1.6 -10.2C2.8 -10.6 5 -7.6 3.4 -5.2L-10.4 -5.6ZM5 -11.2C7 -11.8 8.6 -10.4 8.4 -8.4L5.6 -7.6Z" fill="{P["g_wing"]}"/>')
    head_up = f'<path d="M5.3 -13a3.3 3.3 0 1 1 6.6 0l2.1 .1-2.3 .8a3.3 3.3 0 0 1 -6.4 -.9Z" fill="{P["g_head"]}"/>'
    head_dn = f'<path d="M7.3 -8a3.3 3.3 0 1 1 6.6 0l.3 3.4-1.9 -1.1a3.3 3.3 0 0 1 -5 -2.3Z" fill="{P["g_head"]}"/>'
    legs = f'<path d="M0.4 -1.4V0M3 -1.4L3.6 0" stroke="{P["g_leg"]}" stroke-width="1.2"/>'
    stand = shadow + legs + bodyp + head_up
    peck = shadow + legs + f'<g transform="rotate(14 -2 -4)">{bodyp}</g>' + head_dn
    o.append(f'<g id="gR">{stand}</g><g id="gRp">{peck}</g>')
    # facing -x: the motion path holds the bird with tangent 180 deg, so pre-rotate by 180 deg and mirror
    o.append(f'<g id="gL">{shadow}<g transform="scale(-1 1)">{legs}{bodyp}{head_up}</g></g>')
    o.append(f'<g id="gLp">{shadow}<g transform="scale(-1 1)">{legs}<g transform="rotate(14 -2 -4)">{bodyp}</g>{head_dn}</g></g>')
    return "\n".join(o)


OFFCARD = 700.0                                     # y below the card where the flying sprite waits


BIRD_STRIP = ("peck", "stand", "#w1", "#w0", "#w2", "#w3")   # drawing j sits at x = LIFE_LF * (j - 1)


def birds_svg(P, homes, frames, toff, land, rng):
    """Each pigeon is ONE sprite moved by two discrete transforms on the 20 fps grid: a translate and an additive
    rotate for its heading (measured: a discrete animateMotion repaints on every tick even when unchanged, while
    unchanged translates and rotates are skipped). Its six drawings sit in a strip along its own x axis, LIFE_LF apart:
    peck, stand, then the four flap drawings. The translate subtracts the rotated offset of the drawing on show,
    so exactly that one lands on the bird and the others stay at least LIFE_LF away, off the card. On the ground the
    sprite does not change at all except when the bird pecks. Positions are the simulated points (rounded, as the
    motion path had them); the heading is what rotate="auto" showed: the direction of the last frame's motion."""
    anim, still = [], []
    LIFE_TRACKS["birds"] = []
    for i, (hx, hy, face) in enumerate(homes):
        fr = frames[i]
        white = i in (3, 10)
        fill = P["white_fill"] if white else P["bird_fill"]
        gsym = "#gR" if face > 0 else "#gL"
        psym = "#gRp" if face > 0 else "#gLp"
        hx, hy = round(hx), round(hy)
        homes[i] = (hx, hy, face)
        q = [(hx, OFFCARD)] + [(round(fr[f][0]), round(fr[f][1])) for f in range(toff[i] + 1, land[i])] + [(hx, OFFCARD)]
        # ground states, the same random draws as before: stand, peck (4 frames, three times), away
        seq = ["s"] * NF
        for f in range(toff[i] + 1, land[i]):
            seq[f] = "a"
        ground = [f for f in range(NF) if seq[f] == "s" and (f < toff[i] - 4 or f > land[i] + 3)]
        for _ in range(3):
            f0 = rng.choice(ground)
            for f in range(f0, f0 + 4):
                if f in ground:
                    seq[f] = "p"
        tv, rv = [], []
        head = 0.0
        for f in range(NF):
            if seq[f] == "a":
                (x0, y0), (x1, y1) = q[f - toff[i] - 1], q[f - toff[i]]
                if (x0, y0) != (x1, y1):
                    head = math.degrees(math.atan2(y1 - y0, x1 - x0))
                hd = round(head)
                k = 2 + (f + i % 4) % 4                      # the old flap filmstrip's frame at this grid frame
                c, s = math.cos(math.radians(hd)), math.sin(math.radians(hd))
                d = 1 if math.dist((x0, y0), (x1, y1)) < 6 else 0   # slow touch-down: keep the strip offset exact
                tv.append(f"{fm(x1 - hx - LIFE_LF * (k - 1) * c, d)} {fm(y1 - hy - LIFE_LF * (k - 1) * s, d)}")
                rv.append(str(hd))
            else:
                tv.append(f"{LIFE_LF if seq[f] == 'p' else 0} 0")
                rv.append("0")
        uses = (f'<use href="{psym}" x="{-LIFE_LF}"/><use href="{gsym}"/>'
                + "".join(f'<use href="{w}" x="{LIFE_LF * (j - 1)}"/>' for j, w in enumerate(BIRD_STRIP) if j > 1))
        anim.append(f'<g transform="translate({hx} {hy})"><g fill="{fill}">{life_anim(tv)}{life_anim(rv, kind="rotate")}{uses}</g></g>')
        still.append(f'<use href="{gsym}" transform="translate({hx} {hy})"/>')
        LIFE_TRACKS["birds"].append(dict(q=q, seq=seq, home=(hx, hy), toff=toff[i], land=land[i], phase=i % 4))
    return "\n".join(anim), "\n".join(still)


def bird_play(svg_birds):
    """Play the emitted pigeon sprites as the browser does: per bird and grid frame, which drawing is on the card,
    where it is and its heading."""
    out = []
    pat = (r'<g transform="translate\((-?[\d.]+) (-?[\d.]+)\)"><g fill="[^"]+"><animateTransform attributeName="transform" '
           r'type="translate" values="([^"]+)"(?: keyTimes="([^"]+)")? '
           r'dur="12s" calcMode="discrete" repeatCount="indefinite"/><animateTransform attributeName="transform" type="rotate" '
           r'values="([^"]+)"(?: keyTimes="([^"]+)")? dur="12s" calcMode="discrete" additive="sum" repeatCount="indefinite"/>'
           r'((?:<use href="[^"]+"(?: x="-?\d+")?/>)+)</g></g>')
    for m in re.finditer(pat, svg_birds):
        hx, hy = float(m.group(1)), float(m.group(2))
        T = life_expand(m.group(3), m.group(4))
        Rv = [(a, 0.0) for a, _ in life_expand(" 0;".join(m.group(5).split(";")) + " 0", m.group(6))]
        draws = [(href, float(x or 0)) for href, x in re.findall(r'<use href="([^"]+)"(?: x="(-?\d+)")?/>', m.group(7))]
        track = []
        for f in range(NF):
            (tx, ty), th = (hx + T[f][0], hy + T[f][1]), math.radians(Rv[f][0])
            on = []
            for href, ox in draws:
                x, y = tx + ox * math.cos(th), ty + ox * math.sin(th)
                if -60 < x < W + 60 and -60 < y < H + 60:
                    on.append((href, x, y))
            assert len(on) == 1, f"frame {f}: {len(on)} drawings on the card"
            track.append((on[0][1], on[0][2], Rv[f][0], on[0][0]))
        out.append(track)
    return out


def bird_positions_from_svg(svg_birds):
    """Every bird's position per frame from the emitted sprites (the drawing on the card)."""
    return [[(x, y) for x, y, _, _ in tr] for tr in bird_play(svg_birds)]


def bird_motion_ref(q):
    """What the old animateMotion showed for a flight polyline q (keyPoints 0.3 units before each vertex, rounded
    to 4 places, rotate="auto"): per flight frame, the position and heading."""
    cum = [0.0]
    for p0, p1 in zip(q, q[1:]):
        cum.append(cum[-1] + math.dist(p0, p1))
    total = cum[-1]
    out = []
    for n in range(1, len(q) - 1):
        s = float(fm(max(0.0, cum[n] - 0.3) / total, 4)) * total
        j = max(j for j in range(len(q) - 1) if cum[j] <= s + 1e-9 and cum[j + 1] > cum[j])
        u = (s - cum[j]) / (cum[j + 1] - cum[j])
        (x0, y0), (x1, y1) = q[j], q[j + 1]
        out.append((lerp(x0, x1, u), lerp(y0, y1, u), math.degrees(math.atan2(y1 - y0, x1 - x0))))
    return out


# ------------------------------------------------------------------ leaves (falling plate model)
def apw(I=1.1, a=0.1, th0=0.35, T=160.0, dt=0.004):
    """Andersen, Pesavento & Wang (2005) quasi-steady falling plate, nondimensional, RK4.
    Returns [(t, x, y, theta)], y up. Fluttering for 0.2 < I < ~1.3 with these coefficients."""
    CT, CR, Ac, Bc, mu1, mu2 = 1.2, math.pi, 1.4, 1.0, 0.2, 0.2
    J = 0.25 * (I * (1 + a * a) + 0.5 * (a * a - 1) ** 2)

    def f(s):
        x, y, th, u, v, w = s
        V = math.hypot(u, v) + 1e-12
        Gm = (2 / math.pi) * (-CT * u * v / V + CR * w)
        F = (1 / math.pi) * (Ac - Bc * (u * u - v * v) / (V * V)) * V
        du = ((I + 1) * v * w - Gm * v - math.sin(th) - F * u) / (I + a * a)
        dv = (-(I + a * a) * u * w + Gm * u - math.cos(th) - F * v) / (I + 1)
        dw = ((a * a - 1) * u * v - (mu1 + mu2 * abs(w)) * w) / J
        return [u * math.cos(th) - v * math.sin(th), u * math.sin(th) + v * math.cos(th), w, du, dv, dw]
    s = [0.0, 0.0, th0, 0.0, 0.0, 0.0]
    out = [(0.0, 0.0, 0.0, th0)]
    t = 0.0
    while t < T:
        k1 = f(s)
        k2 = f([p + dt / 2 * q for p, q in zip(s, k1)])
        k3 = f([p + dt / 2 * q for p, q in zip(s, k2)])
        k4 = f([p + dt * q for p, q in zip(s, k3)])
        s = [p + dt / 6 * (b + 2 * c + 2 * d_ + e) for p, b, c, d_, e in zip(s, k1, k2, k3, k4)]
        t += dt
        out.append((t, s[0], s[1], s[2]))
    return out


LEAVES = [dict(x0=1458, y0=118, start=10, I=1.08, th0=0.40, drift=-26, col=0, sc=1.15),
          dict(x0=1530, y0=96, start=92, I=1.16, th0=-0.3, drift=-34, col=2, sc=1.0),
          dict(x0=1496, y0=150, start=168, I=1.02, th0=0.25, drift=-20, col=1, sc=1.25)]


def leaf_tracks():
    out = []
    for L in LEAVES:
        tr = apw(I=L["I"], th0=L["th0"])
        late = [p for p in tr if p[0] > 30]
        xs = [p[1] for p in late]
        amp = (max(xs) - min(xs)) / 2
        vfall = -(late[-1][2] - late[0][2]) / (late[-1][0] - late[0][0])
        sigma = 44.0 / max(amp, 1e-6)             # flutter half-amplitude -> 44 units
        tau = sigma * vfall / 92.0                # mean fall speed -> 92 units/s
        t_off = 30.0                              # skip the release transient
        pts = []
        nfr = 0
        while True:
            tt = t_off + nfr / FPS / tau
            if tt > tr[-1][0]:
                break
            j = min(len(tr) - 1, int(tt / (tr[1][0] - tr[0][0])))
            _, x, y, th = tr[j]
            _, x0, y0, _ = tr[int(t_off / (tr[1][0] - tr[0][0]))]
            px = L["x0"] + sigma * (x - x0) + L["drift"] * nfr / FPS
            py = L["y0"] - sigma * (y - y0)
            pts.append((px, py, -math.degrees(th)))
            if py > 700:
                break
            nfr += 1
        out.append(dict(pts=pts, sigma=sigma, tau=tau, period=None, amp=amp, vfall=vfall))
    return out


LEAF_D = "M0 0C7.2 3 9.4 13 1 25C-2.2 20-9.4 12.6-6.4 4.4C-4.8 1.6-2.2 0 0 0Z"
LEAF_RIB = "M0 1.6C.6 9 .8 16 .9 23"


def xform_path(d, tx, ty, ang, sc):
    """Apply translate(tx ty) rotate(ang) scale(sc) to an absolute M/C/L/Z path."""
    c, s_ = math.cos(math.radians(ang)) * sc, math.sin(math.radians(ang)) * sc
    out = []
    for cmd, args in re.findall(r"([MCLZ])([^MCLZ]*)", d):
        nums = [float(v) for v in re.findall(r"-?\d*\.?\d+", args)]
        pts = [(tx + c * x - s_ * y, ty + s_ * x + c * y) for x, y in zip(nums[0::2], nums[1::2])]
        out.append(cmd + " ".join(pp(x, y) for x, y in pts))
    return "".join(out)


def leaves_svg(P, tracks):
    anim = []
    LIFE_TRACKS["leaves"] = []
    for L, tr in zip(LEAVES, tracks):
        pts = tr["pts"]
        n = len(pts)
        start = L["start"]
        q = [(round(x), round(y)) for x, y, _ in pts]       # the integer points the motion path used
        cum = [0.0]
        for a, b in zip(q, q[1:]):
            cum.append(cum[-1] + math.dist(a, b))
        tot = cum[-1]
        # per frame of the loop: index into the fall, or hold at the start / end
        idx = []
        for f in range(NF):
            k = (f - start) % NF
            idx.append(k if k < n else n - 1)
        hold_start = [(f - start) % NF >= n and (f - start) % NF > NF - 6 for f in range(NF)]
        kps, kts, rots, tvs = [], [], [], []
        prev = None
        for f in range(NF):
            k = 0 if hold_start[f] else idx[f]
            if k != prev:
                kps.append(fm(cum[k] / tot, 4))
                kts.append(fm(f / NF, 4))
                rots.append(fm(pts[k][2] + 8, 0))
                tvs.append(f"{q[k][0]} {q[k][1]}")
                prev = k
        LIFE_TRACKS["leaves"].append(dict(q=q, cum=cum, kps=kps, kts=kts))
        lc = P["leaf"][L["col"]]
        anim.append(f'<g><animateTransform attributeName="transform" type="translate" values="{";".join(tvs)}" '
                    f'keyTimes="{";".join(kts)}" dur="12s" calcMode="discrete" repeatCount="indefinite"/>'
                    f'<g transform="scale({fm(L["sc"], 2)})"><use href="#leaf" fill="{lc}">'
                    f'<animateTransform attributeName="transform" type="rotate" values="{";".join(rots)}" keyTimes="{";".join(kts)}" '
                    f'dur="12s" calcMode="discrete" repeatCount="indefinite"/></use></g></g>')
    return "\n".join(anim)


def branch_svg(P, rng):
    o = []
    twig = ("M1612 -6C1560 30 1500 60 1440 104C1420 118 1404 132 1392 150L1396 152C1410 136 1426 122 1446 110"
            "C1504 72 1562 42 1614 10Z"
            "M1520 50C1512 78 1500 104 1486 128L1490 130C1506 106 1518 80 1526 52Z"
            "M1466 92C1470 112 1468 134 1460 154L1464 155C1474 134 1476 112 1472 92Z")
    o.append(f'<path d="{twig}" fill="{P["twig"]}"/>')
    leaves = {}
    spots = [(1600, 6), (1584, 16), (1566, 26), (1548, 36), (1532, 46), (1514, 56), (1498, 66), (1480, 78),
             (1462, 90), (1446, 102), (1430, 114), (1414, 128), (1400, 142), (1520, 62), (1512, 84), (1502, 104),
             (1492, 124), (1470, 104), (1470, 126), (1464, 148), (1576, 30), (1556, 44), (1592, 22), (1540, 52)]
    for x, y in spots:
        for k in range(2):
            ang = rng.uniform(-60, 60) + (25 if k else -20)
            sc = rng.uniform(0.95, 1.35)
            col = P["leaf"][rng.choice((0, 0, 1, 1, 2, 2))]
            leaves.setdefault(col, []).append(xform_path(LEAF_D, x, y, ang, sc))
    for col, ds in leaves.items():
        o.append(f'<path d="{"".join(ds)}" fill="{col}"/>')
    return "\n".join(o)


# ------------------------------------------------------------------ life
# More life, frame-locked like the pigeons: each sprite is ONE discrete translate on the 20 fps grid that both
# moves it and picks its drawing from a strip of frames stored LIFE_LF units apart (off the card).
#   * a bubble busker east of the west lamp: the breeze blows a long tube out of the rope loop between two wands,
#     it pinches off into a giant soap bubble that drifts east, wobbles and pops. The drift is integrated (RK4)
#     from the Maxey-Riley equation in a gusty breeze with rows of eddies (incompressible, 12 s periodic): drag,
#     the air inside plus its added mass, and the weight of the soap film (a slow sink). Watching: a child
#     reaching up and an NYU student with a violet tote filming on a phone.
#   * two chess players at a stone table (the chess tables of the SW corner), one move each per loop.
#   * a squirrel that dashes, stops and flicks its tail (daytime only).
#   * night only: a few stars twinkle and the Empire State Building's beacon blinks.
LIFE_PAL = {
    "light": dict(
        bub_film="#FFF6E4", bub_rim="#FFFDF6", bub_a="#E27FBB", bub_b="#5EC3BF", bub_c="#F1C24F", bub_hi="#FFFFFF",
        busk="#2F7178", busk_dk="#245A60", beanie="#D4573A", wand="#5B4133", rope="#F6EBD8", bucket="#C4553C",
        bucket_rim="#E9D6B8",
        tbl="#D6C09F", tbl_top="#EBDCC1", tbl_dk="#B59D7F", sq_a="#4A3F3B", sq_b="#F3E8D2",
        chess=("#56606F", "#454E5B", "#3B2C2A", "#9A6A3E", "#7E552F", "#3F3B4D"),
        squ="#8F8781", squ_dk="#716A66", squ_lt="#DCD2C6",
        star="#E9E4D3", spark="#FFF6DE", beacon="#FF3B30",
        kid="#E2A33A", kid_dk="#C4862B", stu="#D9CDBA", stu_dk="#BCAE98", tote="#57068C", phone="#2A2A33",
    ),
    "dark": dict(
        bub_film="#CADCEB", bub_rim="#DCE7F0", bub_a="#C06AA2", bub_b="#55A9AE", bub_c="#E7BC6A", bub_hi="#FFE7B4",
        busk="#2A4E55", busk_dk="#203E44", beanie="#8A3B2C", wand="#2B2326", rope="#CFC4B2", bucket="#77392C",
        bucket_rim="#9C8F7E",
        tbl="#5A5961", tbl_top="#6E6C72", tbl_dk="#46454D", sq_a="#26232B", sq_b="#8D877B",
        chess=("#36404C", "#2B333D", "#1F1818", "#634A31", "#4E3A27", "#2A2834"),
        squ="#5F5A5C", squ_dk="#4A4649", squ_lt="#8E867C",
        star="#E9E4D3", spark="#FFF6DE", beacon="#FF3B30",
        kid="#8A6427", kid_dk="#6E5020", stu="#6E6760", stu_dk="#58524C", tote="#6A16A6", phone="#E9E4F2",
    ),
}
for _t in PAL:
    PAL[_t].update(LIFE_PAL[_t])

LIFE_LF = 2000                                       # frame spacing inside a life sprite (x), off the card
LIFE_TRACKS = {}                                     # filled while building, read by check_life


def life_k(y):
    """Figure scale at plaza depth y: k = 1 at y = 596 as in PEOPLE (about 25 units per metre)."""
    return 1.0 + (y - 596.0) * 0.0027


def life_anim(seq, dur=PERIOD, kind="translate"):
    """One discrete transform (translate "x y", or an additive rotate in degrees), values evenly spread over `dur`
    (one per grid frame, or one per 2 grid frames). Runs of equal values fold into keyTimes when that is shorter.
    Every change lands on the 20 fps grid."""
    n = len(seq)
    assert abs(dur * FPS / n - round(dur * FPS / n)) < 1e-9
    kv, kk = [], []
    for f, v in enumerate(seq):
        if f == 0 or v != seq[f - 1]:
            kv.append(v)
            kk.append(fm(f / n, 5))
    uni = f'values="{";".join(seq)}"'
    key = f'values="{";".join(kv)}" keyTimes="{";".join(kk)}"'
    add = ' additive="sum"' if kind == "rotate" else ""
    return (f'<animateTransform attributeName="transform" type="{kind}" {uni if len(uni) <= len(key) else key} '
            f'dur="{fm(dur, 3)}s" calcMode="discrete"{add} repeatCount="indefinite"/>')


def life_shadow(P, x, y, k, hgt, w=5.5):
    """Golden-hour shadow of a small figure, the same construction as people_svg."""
    L = hgt * 2.6
    dx, dy = SUN[0] * L, SUN[1] * L
    sh = poly([(x - w * k, y + 1), (x + dx - w * k * 0.3, y + dy - 2), (x + dx + w * k * 0.6, y + dy + 1.6), (x + w * k, y + 2.6)])
    return sh + ell(x + dx + 2, y + dy, 4.2 * k, 2.2 * k)


# ---- giant soap bubbles: physics
BUB_RHO_A, BUB_CD, BUB_FILM_H, BUB_RHO_W = 1.2, 0.47, 1.0e-6, 1000.0   # air, sphere drag, film thickness (m), water
BUB_U0 = 1.8                                         # mean breeze from the west, m/s
BUB_EDDY = ((0.30, 6.0, 2.0), (0.16, 4.0, 0.3))      # eddy rows: (w amplitude m/s, period s, phase)
BUB_EDDY_H = 7.0                                     # depth of the eddy layer over the plaza, m


def bub_breeze(t, X, Y):
    """The breeze (u east, w up) in m/s at time t, X m east of the loop, Y m above the plaza: a mean wind with
    uniform gusts, plus rows of eddies carried along by the mean wind. The eddies come from a stream function
    (A/k) sin(k(X - U0 t)) sin(pi Y/H), so the flow is incompressible and does not cross the plaza; at a fixed
    point every part repeats in 12 s."""
    tw = 2 * math.pi * t
    u = BUB_U0 * (1 + 0.18 * math.sin(tw / 12 + 0.6) + 0.10 * math.sin(tw / 4 + 2.1))
    w = 0.0
    sy, cy = math.sin(math.pi * Y / BUB_EDDY_H), math.cos(math.pi * Y / BUB_EDDY_H)
    for A, T, ph in BUB_EDDY:
        k = 2 * math.pi / (BUB_U0 * T)
        xi = k * (X - BUB_U0 * t) + ph
        u += A / k * math.pi / BUB_EDDY_H * math.sin(xi) * cy
        w -= A * math.cos(xi) * sy
    return u, w


def bub_breeze_dt(t, X, Y, h=1e-3):
    """Acceleration of the air itself, Du/Dt = du/dt + (u . grad) u, by central differences along the flow."""
    u, w = bub_breeze(t, X, Y)
    a = bub_breeze(t + h, X + u * h, Y + w * h)
    b = bub_breeze(t - h, X - u * h, Y - w * h)
    return (a[0] - b[0]) / (2 * h), (a[1] - b[1]) / (2 * h)


def bubble_coeffs(R, h=None):
    """For radius R: drag factor kd (1/m), film mass, displaced air mass, and the moving mass (air inside + film +
    added mass, half the displaced air)."""
    V = 4 / 3 * math.pi * R ** 3
    mf = BUB_RHO_A * V                                         # displaced air = the air inside (same density)
    mfilm = 4 * math.pi * R * R * (BUB_FILM_H if h is None else h) * BUB_RHO_W   # the only weight not floated
    m = 1.5 * mf + mfilm
    return 0.5 * BUB_RHO_A * BUB_CD * math.pi * R * R, mfilm, mf, m


def bubble_rhs(R, h=None):
    """Maxey-Riley without the history term: (m_p + mf/2) dv/dt = 1.5 mf Du/Dt + drag - m_film g, with the
    bubble's own mass m_p = mf + m_film. A nearly neutrally buoyant parcel of air rides the eddies, lags the
    gusts through its slip, and sinks slowly under the weight of its film."""
    cd, mfilm, mf, m = bubble_coeffs(R, h)

    def f(t, s):
        X, Y, vx, vy = s
        u, w = bub_breeze(t, X, Y)
        ax, ay = bub_breeze_dt(t, X, Y)
        rx, ry = u - vx, w - vy
        q = math.hypot(rx, ry)
        return (vx, vy, (1.5 * mf * ax + cd * q * rx) / m, (1.5 * mf * ay + cd * q * ry - mfilm * G) / m)
    return f


def life_rk4(f, t, s, dt):
    k1 = f(t, s)
    k2 = f(t + dt / 2, [a + dt / 2 * b for a, b in zip(s, k1)])
    k3 = f(t + dt / 2, [a + dt / 2 * b for a, b in zip(s, k2)])
    k4 = f(t + dt, [a + dt * b for a, b in zip(s, k3)])
    return [a + dt / 6 * (b + 2 * c + 2 * d_ + e) for a, b, c, d_, e in zip(s, k1, k2, k3, k4)]


def bubble_flight(R, t0, s0, nfr, sub=8, h=None):
    """Per-frame states (t, X, Y, vx, vy) of one bubble from its release, RK4 with `sub` steps per frame."""
    f = bubble_rhs(R, h)
    s, out = list(s0), [(t0, *s0)]
    dt = 1.0 / (FPS * sub)
    for i in range(1, nfr):
        for j in range(sub):
            s = life_rk4(f, t0 + ((i - 1) * sub + j) * dt, s, dt)
        out.append((t0 + i / FPS, *s))
    return out


# ---- giant soap bubbles: the strip of drawings (radius BUB_RB, slots scale it), one path per colour layer
BUB_RB = 15.0
BUB_KF = 6                                               # wobble frames
BUB_LAYERS = ("film", "tube", "c", "a", "b", "hi")


def _life_r1(v):
    return round(v * 10) / 10


def life_tchain(pts, closed=False):
    """Smooth curve through the midpoints of pts with the pts as quadratic control points (C1). Written as one q
    and then relative t segments: the reflected control point of each t is exactly the next point of pts, so only
    the on-curve midpoints are stored. Coordinates are rounded once (absolute), so nothing drifts but the implied
    control points, by well under a unit. Open: from pts[0] to pts[-1]. Returns a path starting with M."""
    P_ = [(_life_r1(x), _life_r1(y)) for x, y in pts]
    n = len(P_)
    if closed:
        mids = [(_life_r1((P_[i][0] + P_[(i + 1) % n][0]) / 2), _life_r1((P_[i][1] + P_[(i + 1) % n][1]) / 2)) for i in range(n)]
        start, ctrl, ends = mids[-1], P_[0], mids[:-1] + [mids[-1]]
    else:
        mids = [(_life_r1((P_[i][0] + P_[i + 1][0]) / 2), _life_r1((P_[i][1] + P_[i + 1][1]) / 2)) for i in range(1, n - 2)]
        start, ctrl, ends = P_[0], P_[1], mids + [P_[-1]]
    s = f"M{pp(*start)}q{pp(ctrl[0] - start[0], ctrl[1] - start[1])} {pp(ends[0][0] - start[0], ends[0][1] - start[1])}"
    cur = ends[0]
    for e in ends[1:]:
        s += f"t{pp(e[0] - cur[0], e[1] - cur[1])}"
        cur = e
    return s + ("Z" if closed else "")


def bub_frames():
    """Frames in strip order: wobble F0-F5, tube T0-T4 and pinch T5 (attached at the loop = origin), relax R0,
    pop P0-P1. Returns {layer: d} with frame j drawn at x offset -LIFE_LF*j, and the strip index of each frame."""
    lay = {k: [] for k in BUB_LAYERS}
    idx = {}
    r = math.radians

    def ellipse_pts(rx, ry, tau):
        c, s = math.cos(tau), math.sin(tau)
        return lambda th, d=0.0: ((rx - d) * math.cos(th) * c - (ry - d) * math.sin(th) * s,
                                  (rx - d) * math.cos(th) * s + (ry - d) * math.sin(th) * c)

    def arc(E, rx, ry, tau, a0, a1, d, ox):
        p0, p1 = E(a0, d), E(a1, d)
        return (f"M{pp(p0[0] + ox, p0[1])}a{fm(rx - d)} {fm(ry - d)} {fm(math.degrees(tau), 0)} 0 1 "
                f"{pp(p1[0] - p0[0], p1[1] - p0[1])}")

    def dot(x, y):
        return f"M{pp(x, y)}h.1"

    def bubble(j, rx, ry, tau, sw):
        ox = -LIFE_LF * j
        E = ellipse_pts(rx, ry, tau)
        p0, p1 = E(0), E(math.pi)
        rot = fm(math.degrees(tau), 0)
        lay["film"].append(f"M{pp(p0[0] + ox, p0[1])}a{fm(rx)} {fm(ry)} {rot} 0 1 {pp(p1[0] - p0[0], p1[1] - p0[1])}"
                           f"a{fm(rx)} {fm(ry)} {rot} 0 1 {pp(p0[0] - p1[0], p0[1] - p1[1])}")
        # thin-film colours: the film drains, so gold (thinnest) on top, magenta on the side, teal low; they sway
        for layer, a0, a1, d in (("c", 248, 302, 1.7), ("a", -32, 36, 1.5), ("b", 102, 156, 1.6)):
            lay[layer].append(arc(E, rx, ry, tau, r(a0) + sw - tau, r(a1) + sw - tau, d, ox))
        # the low sun (or the lamp) in the west: a window highlight up-left, fixed to the light, and a glint
        g = E(r(250) - tau, 3.7)
        lay["hi"].append(arc(E, rx, ry, tau, r(198) - tau, r(234) - tau, 2.5, ox) + dot(g[0] + ox, g[1]))

    j = 0
    for k in range(BUB_KF):
        ph = 2 * math.pi * k / BUB_KF
        a = 1 + 0.075 * math.sin(ph)
        bubble(j, BUB_RB * a, BUB_RB / a, r(28 + 12 * math.sin(ph + 1.1)), r(18 * math.sin(ph + 0.5)))
        idx[f"F{k}"] = j
        j += 1
    # the tube the breeze blows out of the loop: the centreline waves, the radius flares from the loop, round end
    rt = 8.2
    for t_, Lt in enumerate((12, 26, 40, 52, 62)):
        ox = -LIFE_LF * j

        def yc(s, t_=t_):
            return 2.4 * math.sin(2 * math.pi * s / 36 - 1.5 * t_) * min(1.0, s / 12)

        def rr(s):
            return rt * (0.72 + 0.28 * min(1.0, s / 9))
        e = Lt - rt
        ss = [e * i / 6 for i in range(7)]
        top = life_tchain([(s + ox, yc(s) - rr(s)) for s in ss])
        bot = life_tchain([(s + ox, yc(s) + rr(s)) for s in reversed(ss)])
        lay["tube"].append(f"{top}a{fm(rr(e))} {fm(rr(e))} 0 0 1 0 {fm(2 * rr(e))}L{bot[1:]}Z")

        def edge(s0, s1, side, ins):
            return life_tchain([(s + ox, yc(s) + side * (rr(s) - ins)) for s in (s0, (s0 + s1) / 2, s1)])
        lay["c"].append(edge(0.22 * e, 0.72 * e, -1, 1.6))
        lay["a"].append(edge(0.30 * e, 0.92 * e, 1, 1.5))
        q = rr(e) - 1.6
        lay["b"].append(f"M{pp(e + q + ox, yc(e))}a{fm(q)} {fm(q)} 0 0 1 {pp(-q * 0.7, q * 0.7)}")
        lay["hi"].append(edge(0.05 * e, 0.2 * e, -1, 2.4) + dot(0.3 * e + ox, yc(0.3 * e) - rr(0.3 * e) + 3.4))
        idx[f"T{t_}"] = j
        j += 1
    # pinch-off: the neck at the loop closes
    ox = -LIFE_LF * j
    Lt = 64
    pts = []
    for i in range(11):
        s = 3 + (Lt - 3) * i / 10
        w = rt * min(1.0, ((s - 3) / 16) ** 0.6) * (1.0 if s < Lt - rt else math.sqrt(max(0.0, 1 - ((s - (Lt - rt)) / rt) ** 2)))
        pts.append((s, w))
    top = [(s, -w + 1.2 * math.sin(s / 9)) for s, w in pts]
    bot = [(s, w + 1.2 * math.sin(s / 9)) for s, w in reversed(pts)]
    lay["tube"].append(life_tchain([(x + ox, y) for x, y in top + bot[1:-1]], closed=True))
    lay["c"].append("M" + "L".join(pp(x + ox, y + 1.6) for x, y in top[3:8:2]))
    lay["a"].append("M" + "L".join(pp(x + ox, y - 1.5) for x, y in bot[2:7:2]))
    lay["hi"].append("M" + "L".join(pp(x + ox, y + 2.4) for x, y in top[2:4]))
    idx["T5"] = j
    j += 1
    # relaxing into a sphere, centred on the bubble
    bubble(j, 1.35 * BUB_RB, 0.86 * BUB_RB, r(6), 0.0)
    idx["R0"] = j
    j += 1
    # pop: the film tears into arcs, droplets fly and fall
    for name, rad, fall, frag in (("P0", 1.1, 0.0, True), ("P1", 1.5, 3.0, False)):
        ox = -LIFE_LF * j
        for i in range(6 if frag else 0):
            a0 = r(20 + 60 * i + 9 * math.sin(i * 2.7))
            p0 = (rad * BUB_RB * math.cos(a0), rad * BUB_RB * math.sin(a0))
            p1 = (rad * BUB_RB * math.cos(a0 + r(24)), rad * BUB_RB * math.sin(a0 + r(24)))
            lay[("c", "a", "b")[i % 3]].append(f"M{pp(p0[0] + ox, p0[1])}a{fm(rad * BUB_RB)} {fm(rad * BUB_RB)} 0 0 1 {pp(p1[0] - p0[0], p1[1] - p0[1])}")
        for i in range(7):
            a0 = r(40 + 51 * i)
            rr_ = rad * BUB_RB * (1.15 + 0.12 * math.sin(i * 1.9))
            lay["hi"].append(dot(rr_ * math.cos(a0) + ox, rr_ * math.sin(a0) + fall))
        idx[name] = j
        j += 1
    return {k: "".join(v) for k, v in lay.items()}, idx


def bub_defs(P):
    lay, idx = bub_frames()
    st = {"film": f'fill="{P["bub_film"]}" fill-opacity="{".14" if not P["night"] else ".08"}" stroke="{P["bub_rim"]}" '
                  f'stroke-opacity="{".75" if not P["night"] else ".5"}" stroke-width=".9"',
          "tube": f'fill="{P["bub_film"]}" fill-opacity="{".1" if not P["night"] else ".06"}" stroke="{P["bub_rim"]}" '
                  f'stroke-opacity="{".5" if not P["night"] else ".36"}" stroke-width=".8"',
          "c": f'fill="none" stroke="{P["bub_c"]}" stroke-width="1.7" stroke-opacity=".85" stroke-linecap="round"',
          "a": f'fill="none" stroke="{P["bub_a"]}" stroke-width="1.6" stroke-opacity=".8" stroke-linecap="round"',
          "b": f'fill="none" stroke="{P["bub_b"]}" stroke-width="1.5" stroke-opacity=".8" stroke-linecap="round"',
          "hi": f'fill="none" stroke="{P["bub_hi"]}" stroke-width="2.3" stroke-opacity=".92" stroke-linecap="round"'}
    return f'<g id="bub">{"".join(f"<path d={chr(34)}{lay[k]}{chr(34)} {st[k]}/>" for k in BUB_LAYERS)}</g>', idx


# ---- the busker
BUSK = (356.0, 584.0)                                 # feet of the bubble busker, east of the west lamp
BUSK_LOOP = (28.6, -62.0)                             # centre of the rope loop in the busker's frame (x k)
BUB_EVERY = 48                                        # a bubble every 2.4 s; five per loop, in three slots
BUB_R = (0.84, 0.70, 0.92)                            # bubble radius per slot, m
BUB_SLIP = 0.9                                        # a new bubble leaves at this fraction of the local wind
BUB_LIST = [dict(rel=10 + BUB_EVERY * i, life=lf, R=BUB_R[i % 3], ph=ph)
           for i, (lf, ph) in enumerate(((112, 0), (104, 3), (120, 5), (72, 2), (70, 4)))]
BUSK_POSES = ("open", "close", "rest", "raise")


def busker_pose(P, x0, y0, k, pose, ox):
    """Arms, wands and rope for one pose, at x offset ox. Shoulder at (0.6, -31), all in units of k."""
    def Q(px, py):
        return x0 + ox + px * k, y0 + py * k
    hands, tips = {
        "open": (((9.6, -40.5), (6.4, -45.2)), ((33.2, -55.4), (24.4, -68.6))),
        "close": (((9.8, -41), (8.0, -43.6)), ((31.2, -62.6), (29.6, -64.2))),
        "rest": (((7.0, -22.5), (5.4, -23.6)), ((19.6, -5.0), (17.2, -3.8))),
        "raise": (((9.2, -36.5), (7.4, -38.6)), ((23.8, -63.4), (22.0, -64.4))),
    }[pose]
    sh = (0.6, -31.0)
    arms = "".join(f"M{pp(*Q(*sh))}L{pp(*Q(*h))}" for h in hands)
    wands = "".join(f"M{pp(*Q(*h))}L{pp(*Q(*t))}" for h, t in zip(hands, tips))
    (ax, ay), (bx, by) = tips
    if pose == "open":       # the loop, opened across the breeze: top string and the sagging bottom string
        rope = (f"M{pp(*Q(ax, ay))}Q{pp(*Q(ax + 8.5, ay + 4))} {pp(*Q(bx, by))}"
                f"Q{pp(*Q(bx - 9.5, by - 1))} {pp(*Q(ax, ay))}")
        film = rope + "Z"
    elif pose == "rest":     # dipped in the bucket
        rope = f"M{pp(*Q(ax, ay))}Q{pp(*Q(ax - 1, ay + 3))} {pp(*Q(bx, by))}"
        film = ""
    else:                    # loop closed: the strings hang together under the tips
        rope = f"M{pp(*Q(ax, ay))}Q{pp(*Q(ax + 3.5, ay + 15))} {pp(*Q(bx, by))}"
        film = ""
    handd = "".join(f"M{pp(*Q(*h))}h0" for h in hands)
    return arms, wands, rope, film, handd


def busker_svg(P):
    x0, y0 = BUSK
    k = life_k(y0)

    def Q(px, py):
        return x0 + px * k, y0 + py * k
    o = []
    if not P["night"]:
        o.append(f'<path d="{life_shadow(P, x0, y0, k, 40 * k)}{ell(*Q(19, 0.8), 5 * k, 1.6 * k)}" fill="{P["shadow"]}"/>')
    # bucket of bubble mix at the feet, legs, coat (lit west, shaded east), head and a beanie
    o.append(f'<path d="{poly([Q(13.2, -6.6), Q(21.0, -6.6), Q(20.2, 0), Q(14.0, 0)])}" fill="{P["bucket"]}"/>')
    o.append(f'<path d="{ell(*Q(17.1, -6.6), 3.9 * k, 1.1 * k)}" fill="{P["bucket_rim"]}"/>')
    legs = (poly([Q(-3.4, -14), Q(-0.8, -14), Q(-1.6, 0), Q(-4.4, 0)]) + poly([Q(0.6, -14), Q(3.4, -14), Q(4.8, 0), Q(2.0, 0)]))
    o.append(f'<path d="{legs}" fill="{P["hair"]}"/>')
    coat = (f"M{pp(*Q(-5.4, -31))}C{pp(*Q(-5.6, -34.5))} {pp(*Q(5.6, -34.5))} {pp(*Q(5.4, -31))}"
            f"L{pp(*Q(6.6, -12))}L{pp(*Q(-6.2, -12))}Z")
    o.append(f'<path d="{coat}" fill="{P["busk"]}"/>')
    o.append(f'<path d="{poly([Q(1.8, -33.6), Q(5.4, -31), Q(6.6, -12), Q(2.6, -12)])}" fill="{P["busk_dk"]}"/>')
    o.append(f'<path d="{circ(*Q(0.4, -38.4), 4.1 * k)}" fill="{P["skin"]}"/>')
    o.append(f'<path d="M{pp(*Q(-4.3, -38.2))}C{pp(*Q(-4.6, -44.6))} {pp(*Q(4.4, -44.8))} {pp(*Q(4.4, -38.6))}Z" fill="{P["beanie"]}"/>')
    body = "\n".join(o)
    # the four poses, one strip; arms over the coat
    layers = {"arm": [], "wand": [], "rope": [], "film": [], "hand": []}
    for j, pose in enumerate(BUSK_POSES):
        arms, wands, rope, film, handd = busker_pose(P, x0, y0, k, pose, LIFE_LF * j)
        layers["arm"].append(arms)
        layers["wand"].append(wands)
        layers["rope"].append(rope)
        layers["film"].append(film)
        layers["hand"].append(handd)
    strip = (f'<path d="{"".join(layers["film"])}" fill="{P["bub_film"]}" fill-opacity=".3"/>'
             f'<path d="{"".join(layers["arm"])}" fill="none" stroke="{P["busk"]}" stroke-width="{fm(2.7 * k)}" stroke-linecap="round"/>'
             f'<path d="{"".join(layers["hand"])}" stroke="{P["skin"]}" stroke-width="{fm(2.5 * k)}" stroke-linecap="round"/>'
             f'<path d="{"".join(layers["wand"])}" fill="none" stroke="{P["wand"]}" stroke-width="{fm(1.15 * k)}" stroke-linecap="round"/>'
             f'<path d="{"".join(layers["rope"])}" fill="none" stroke="{P["rope"]}" stroke-width="{fm(.75 * k)}"/>')
    # pose timeline: open while the tube grows, close to pinch it off, lower to dip, raise, open again
    seq = ["rest"] * NF
    for b in BUB_LIST:
        r = b["rel"]
        for f in range(r - 20, r + BUB_EVERY - 20):
            g = f % NF
            seq[g] = "open" if f < r else "close" if f < r + 6 else "rest" if f < r + BUB_EVERY - 26 else "raise"
    vals = [f"{-LIFE_LF * BUSK_POSES.index(p)} 0" for p in seq]
    body += f'<defs><g id="busk">{strip}</g></defs>'
    anim = f'<g>{life_anim(vals)}<use href="#busk"/></g>'
    still = '<use href="#busk"/>'                    # pose 0 of the strip: the loop open
    return body, anim, still


def bubbles_svg(P, data=None):
    """Two slots, two bubbles each; each slot is one translate that moves it and picks its frame."""
    defs, idx = bub_defs(P)
    x0, y0 = BUSK
    k = life_k(y0)
    S = 25.0 * k                                     # units per metre at the busker's depth
    lx, ly = x0 + BUSK_LOOP[0] * k, y0 + BUSK_LOOP[1] * k
    Yl = (y0 - ly) / S                               # loop height above the plaza, m
    slots = {}
    flights = []
    for bi, b in enumerate(BUB_LIST):
        sl = bi % 3
        sc = b["R"] * S / BUB_RB
        seq = slots.setdefault(sl, dict(sc=sc, frames=[None] * NF))
        assert abs(seq["sc"] - sc) < 1e-9
        fr = seq["frames"]
        r = b["rel"]
        busy = [f % NF for f in range(r - 20, r + b["life"])]
        assert all(fr[f] is None for f in busy), "two bubbles share a slot at once"
        for t_ in range(5):                          # the tube grows at the loop
            for f in range(r - 20 + 4 * t_, r - 16 + 4 * t_):
                fr[f % NF] = (lx, ly, idx[f"T{t_}"])
        for f in (r, r + 1):
            fr[f % NF] = (lx, ly, idx["T5"])
        X0 = 0.5 * 64 * sc / S                       # the pinched tube's centre, m east of the loop
        u0, w0 = bub_breeze((r + 2) / FPS, X0, Yl)       # the tube's air was blown out by the bub_breeze: it leaves
        st = bubble_flight(b["R"], (r + 2) / FPS, (X0, Yl, BUB_SLIP * u0, BUB_SLIP * w0), b["life"] - 2)
        flights.append(dict(R=b["R"], rel=r, states=st, sc=sc, slot=sl))
        for i, (t, X, Y, vx, vy) in enumerate(st):
            f = r + 2 + i
            if i < 4:
                name = "R0"
            elif i >= len(st) - 2:
                name = "P1"
            elif i >= len(st) - 4:
                name = "P0"
            else:
                name = f"F{(b['ph'] + (i - 4) // 4) % BUB_KF}"
            fr[f % NF] = (lx + S * X, y0 - S * Y, idx[name])
    o = [f"<defs>{defs}</defs>"]
    anim, still = [], []
    lx, ly = float(fm(lx)), float(fm(ly))            # what the SVG carries, so the drawn positions are exact
    for sl, s in sorted(slots.items()):
        s["sc"] = float(fm(s["sc"], 4))
        vals = []
        for v in s["frames"][::2]:
            if v is None:
                vals.append("0 -3000")
            else:
                x, y, j = v
                vals.append(f"{round(x - lx + LIFE_LF * j * s['sc'])} {round(y - ly)}")
        anim.append(f'<g transform="translate({pp(lx, ly)})"><g>{life_anim(vals)}<g transform="scale({fm(s["sc"], 4)})">'
                    f'<use href="#bub"/></g></g></g>')
        s["vals"] = vals
    # reduced motion: the scene at t = 2.6 s (a bubble drifting, the next tube growing)
    fs = round(2.6 * FPS)
    for sl, s in sorted(slots.items()):
        v = s["frames"][fs]
        if v:
            x, y, j = v
            still.append(f'<g transform="translate({pp(x + LIFE_LF * j * s["sc"], y)}) scale({fm(s["sc"], 4)})"><use href="#bub"/></g>')
    if data is not None:
        data.setdefault("life", {})["bubbles"] = dict(flights=flights, S=S, loop=(lx, ly), Yl=Yl, idx=idx,
                                                      sc={sl: s["sc"] for sl, s in slots.items()})
    return "".join(o), "\n".join(anim), "\n".join(still)


# ---- chess players at a stone table (the SW corner)
CHESS_AT = (100.0, 628.0)                                # foot of the table


def chess_figure(P, x0, y0, k, face, coat, coat_dk, hat, hat_kind, out):
    """A seated player on a stone stool, leaning in over the board; face = +1 looks east. Adds path data to `out`
    by colour so the two players share paths."""
    def Q(px, py):
        return x0 + face * px * k, y0 + py * k

    def add(col, d):
        out.setdefault(col, []).append(d)
    add(P["tbl_dk"], poly([Q(-3.2, -10.6), Q(3.2, -10.6), Q(2.6, 0), Q(-2.6, 0)]))
    add(P["tbl_top"], ell(*Q(0, -10.6), 3.2 * k, 0.9 * k))
    add(P["hair"], poly([Q(-2.4, -13.2), Q(7.4, -13.2), Q(8.4, 0), Q(6.0, 0), Q(5.4, -10.4), Q(-2.4, -10.4)]))
    add(coat, f"M{pp(*Q(-3.6, -27.2))}C{pp(*Q(-2.8, -30.8))} {pp(*Q(5.6, -31))} {pp(*Q(6.6, -27))}"
              f"L{pp(*Q(5.0, -11))}L{pp(*Q(-5.0, -10.6))}Z")
    add(coat_dk, poly([Q(-3.6, -27.2), Q(-1.2, -29.6), Q(-1.6, -10.8), Q(-5.0, -10.6)]))
    hx, hy = 4.6, -33.0
    add(P["skin"], circ(*Q(hx, hy), 3.9 * k))
    if hat_kind == "cap":
        add(hat, f"M{pp(*Q(hx - 4.1, hy - 0.2))}C{pp(*Q(hx - 4.0, hy - 5.6))} {pp(*Q(hx + 3.6, hy - 5.4))} {pp(*Q(hx + 4.0, hy - 1.6))}"
                 f"L{pp(*Q(hx + 6.4, hy - 0.8))}L{pp(*Q(hx + 3.8, hy - 0.4))}Z")
    else:
        add(hat, f"M{pp(*Q(hx - 4.0, hy))}C{pp(*Q(hx - 4.2, hy - 6.6))} {pp(*Q(hx + 4.2, hy - 6.6))} {pp(*Q(hx + 4.0, hy))}Z")


def chess_svg(P):
    x0, y0 = CHESS_AT
    k = life_k(y0)

    def Q(px, py):
        return x0 + px * k, y0 + py * k
    c = P["chess"]
    o = []
    if P["night"]:
        o.append(f'<ellipse cx="{fm(x0 - 8)}" cy="{fm(y0 + 2)}" rx="{fm(70 * k)}" ry="{fm(13 * k)}" fill="url(#pool)"/>')
    else:
        o.append(f'<path d="{life_shadow(P, x0 - 16 * k, y0, k, 30 * k)}{life_shadow(P, x0 + 16 * k, y0, k, 30 * k)}'
                 f'{life_shadow(P, x0, y0, k * 1.4, 19 * k)}" fill="{P["shadow"]}"/>')
    cols = {}
    chess_figure(P, x0 - 16 * k, y0, k, 1, c[0], c[1], c[2], "cap", cols)
    chess_figure(P, x0 + 16 * k, y0, k, -1, c[3], c[4], c[5], "beanie", cols)
    o += [f'<path d="{"".join(v)}" fill="{col}"/>' for col, v in cols.items()]
    # the table: pedestal, slab, the inlaid board seen at a low angle (two rows of squares), a few pieces
    o.append(f'<path d="{poly([Q(-2.4, -18), Q(2.4, -18), Q(3.2, 0), Q(-3.2, 0)])}" fill="{P["tbl"]}"/>')
    o.append(f'<path d="{poly([Q(-10.5, -19.6), Q(10.5, -19.6), Q(10.5, -17.4), Q(-10.5, -17.4)])}" fill="{P["tbl"]}"/>')
    o.append(f'<path d="{poly([Q(-9.6, -21.2), Q(9.6, -21.2), Q(10.5, -19.6), Q(-10.5, -19.6)])}" fill="{P["tbl_top"]}"/>')
    sq = fm(0.9 * k)
    a, b = Q(-5.4, -20.8), Q(5.4, -20.8)
    a2, b2 = Q(-5.4 + 0.9, -19.95), Q(5.4, -19.95)
    o.append(f'<path d="M{pp(*a)}H{fm(b[0])}M{pp(*a2)}H{fm(b2[0])}" stroke="{P["sq_a"]}" stroke-width="{fm(0.8 * k)}" '
             f'stroke-dasharray="{sq} {sq}"/>')
    pcs = "".join(f"M{pp(*Q(px, -21.6))}v{fm(-1.3 * k)}" for px in (-4.4, -2.6, 0.9))
    pcs2 = "".join(f"M{pp(*Q(px, -21.6))}v{fm(-1.3 * k)}" for px in (-0.6, 2.8, 4.2))
    o.append(f'<path d="{pcs}" stroke="{P["sq_b"]}" stroke-width="{fm(0.9 * k)}" stroke-linecap="round"/>')
    o.append(f'<path d="{pcs2}" stroke="{P["sq_a"]}" stroke-width="{fm(0.9 * k)}" stroke-linecap="round"/>')
    # arms: west player chin-on-hand / reaching, east player resting / reaching. One strip, one move each per loop
    def arm(face, kind, ox):
        sx = x0 - face * 16 * k
        def Q2(px, py):
            return sx + ox + face * px * k, y0 + py * k
        pts = {"chin": [(2.2, -25.6), (9.6, -20.8), (7.2, -29.4)], "rest": [(2.2, -25.6), (7.4, -18.6), (11.6, -20.4)],
               "reach": [(2.2, -25.6), (9.2, -24.6), (14.2, -22.6)]}[kind]
        d = "M" + "L".join(pp(*Q2(*p)) for p in pts)
        return d, f"M{pp(*Q2(*pts[-1]))}h0"
    states = [(("chin", "rest")), (("chin", "reach")), (("reach", "rest"))]
    arms = {0: [], 1: []}
    hands = []
    for j, (aw, ae) in enumerate(states):
        d, h = arm(1, aw, LIFE_LF * j)
        arms[0].append(d)
        hands.append(h)
        d, h = arm(-1, ae, LIFE_LF * j)
        arms[1].append(d)
        hands.append(h)
    strip = (f'<path d="{"".join(arms[0])}" fill="none" stroke="{c[0]}" stroke-width="{fm(2.6 * k)}" stroke-linecap="round" stroke-linejoin="round"/>'
             f'<path d="{"".join(arms[1])}" fill="none" stroke="{c[3]}" stroke-width="{fm(2.6 * k)}" stroke-linecap="round" stroke-linejoin="round"/>'
             f'<path d="{"".join(hands)}" stroke="{P["skin"]}" stroke-width="{fm(2.5 * k)}" stroke-linecap="round"/>')
    seq = ["0 0"] * NF
    for f in range(round(2.8 * FPS), round(3.9 * FPS)):
        seq[f] = f"{-LIFE_LF} 0"
    for f in range(round(8.6 * FPS), round(9.6 * FPS)):
        seq[f] = f"{-2 * LIFE_LF} 0"
    o.append(f'<defs><g id="chs">{strip}</g></defs>')
    anim = f'<g>{life_anim(seq)}<use href="#chs"/></g>'
    return "\n".join(o), anim, '<use href="#chs"/>'


# ---- a squirrel (daytime only: grey squirrels sleep at night)
SQ_A, SQ_B, SQ_C = (862.0, 633.0), (918.0, 626.0), (886.0, 638.0)


SQ_SHAPES = {   # facing east, feet at the origin; body, tail, chest (or None), eye
    "sit": ([(-2.2, 0), (-3.4, -1.8), (-3.2, -4.6), (-2.0, -7.0), (-1.0, -8.6), (-0.6, -10.2), (0.6, -11.2), (1.0, -12.6),
             (1.8, -11.0), (2.8, -10.6), (4.3, -9.4), (3.4, -8.4), (2.0, -8.2), (1.8, -6.8), (3.0, -6.2), (1.9, -5.2),
             (1.9, -2.8), (3.5, -0.9), (3.3, 0)],
            [(-2.6, -1.2), (-5.6, -1.8), (-8.4, -4.6), (-9.2, -8.6), (-7.8, -12.6), (-4.8, -14.6), (-1.8, -14.0),
             (-2.4, -12.0), (-4.2, -10.8), (-4.8, -8.4), (-4.4, -5.8), (-3.0, -3.6)],
            [(2.2, -8.0), (1.6, -6.6), (1.6, -3.0), (0.6, -3.2), (0.4, -6.8)], (2.9, -10.0)),
    "flick": (None,
              [(-2.6, -1.6), (-5.0, -3.0), (-6.4, -6.6), (-6.4, -11.0), (-5.0, -15.2), (-2.6, -17.0), (0.0, -16.4),
               (-0.6, -14.8), (-2.4, -13.6), (-2.8, -10.2), (-2.8, -6.4), (-2.2, -3.6)], None, None),
    "run0": ([(-4.6, -2.6), (-4.2, -4.8), (-1.0, -6.0), (2.4, -5.6), (3.6, -6.6), (5.0, -7.0), (5.4, -8.0), (5.9, -6.8),
              (7.2, -5.8), (5.8, -5.0), (4.6, -4.4), (6.6, -1.8), (6.4, -0.7), (3.6, -2.8), (-1.2, -2.8), (-4.4, -0.6),
              (-5.8, -0.3), (-5.7, -1.5)],
             [(-4.4, -3.4), (-7.8, -4.2), (-11.0, -6.4), (-13.4, -9.6), (-12.4, -12.0), (-9.6, -10.4), (-6.8, -8.4),
              (-4.0, -6.2)], None, (5.6, -6.4)),
    "run1": ([(-3.4, -2.4), (-3.6, -5.2), (-1.6, -7.4), (1.4, -7.4), (3.0, -6.6), (4.2, -7.6), (4.6, -8.6), (5.1, -7.4),
              (6.4, -6.2), (5.0, -5.4), (3.6, -5.2), (2.6, -2.8), (1.7, -0.3), (0.4, -0.3), (0.6, -2.6), (-0.8, -2.6),
              (-1.2, -0.2), (-2.7, -0.2)],
             [(-3.2, -4.4), (-6.6, -6.8), (-8.2, -11.0), (-7.0, -14.8), (-4.4, -15.0), (-4.4, -11.6), (-3.8, -8.6),
              (-2.4, -6.4)], None, (5.0, -6.8)),
}


def squirrel_frames(P):
    """Strip of side views facing east, feet at the origin: sit (tail curled), flick (tail snapped up), two bound
    phases. Facing west is the same strip mirrored. Returns the strip and its frame names."""
    k = life_k(632)
    names = ["sit", "flick", "run0", "run1"]
    lay = {"sh": [], "tail": [], "body": [], "chest": [], "eye": []}
    for j, n in enumerate(names):
        body, tail, chest, eye = SQ_SHAPES[n]
        if body is None:
            body, chest, eye = SQ_SHAPES["sit"][0], SQ_SHAPES["sit"][2], SQ_SHAPES["sit"][3]
        ox = -LIFE_LF * j

        def sc(pts):
            return [(ox + x * k, y * k) for x, y in pts]
        lay["sh"].append(f"M{pp(ox - 3 * k, 0.5)}h{fm((6 if n in ('sit', 'flick') else 9) * k)}")
        lay["tail"].append(life_tchain(sc(tail), True))
        lay["body"].append(life_tchain(sc(body), True))
        if chest:
            lay["chest"].append(life_tchain(sc(chest), True))
        lay["eye"].append(f"M{pp(ox + eye[0] * k, eye[1] * k)}h0")
    sh = (f'<path d="{"".join(lay["sh"])}" stroke="{P["shadow"]}" stroke-width="{fm(1.7 * k)}" stroke-linecap="round"/>'
          if not P["night"] else "")
    strip = (f'<g id="sqE">{sh}<path d="{"".join(lay["tail"])}" fill="{P["squ_dk"]}"/><path d="{"".join(lay["body"])}" '
             f'fill="{P["squ"]}"/><path d="{"".join(lay["chest"])}" fill="{P["squ_lt"]}"/><path d="{"".join(lay["eye"])}" '
             f'stroke="#2B2320" stroke-width="{fm(0.9 * k)}" stroke-linecap="round"/></g>')
    return strip, names


def squirrel_svg(P):
    if P["night"]:
        return "", "", ""
    strip, names = squirrel_frames(P)
    n = len(names)
    # facing west: the same strip mirrored; after the flip, frame j is stored at x = LIFE_LF * (2n - j)
    defs = f'<defs>{strip}</defs>'
    body = f'<use href="#sqE"/><use href="#sqE" transform="translate({2 * n * LIFE_LF} 0) scale(-1 1)"/>'

    def frame_off(name, face):
        j = names.index(name)
        return LIFE_LF * j if face > 0 else LIFE_LF * (2 * n - j)
    # (start frame, kind, from, to, face) segments over the loop; dashes are bounds 4 frames long
    plan = [(0, "sit", SQ_A, SQ_A, 1), (12, "flick", SQ_A, SQ_A, 1), (14, "sit", SQ_A, SQ_A, 1),
            (24, "dash", SQ_A, SQ_B, 1), (36, "sit", SQ_B, SQ_B, 1), (48, "flick", SQ_B, SQ_B, 1), (50, "sit", SQ_B, SQ_B, 1),
            (64, "flick", SQ_B, SQ_B, 1), (66, "sit", SQ_B, SQ_B, 1), (82, "dash", SQ_B, SQ_C, -1), (90, "sit", SQ_C, SQ_C, -1),
            (118, "flick", SQ_C, SQ_C, -1), (120, "sit", SQ_C, SQ_C, -1), (150, "flick", SQ_C, SQ_C, -1),
            (152, "sit", SQ_C, SQ_C, -1), (176, "dash", SQ_C, SQ_A, -1), (182, "sit", SQ_A, SQ_A, -1),
            (204, "flick", SQ_A, SQ_A, -1), (206, "sit", SQ_A, SQ_A, -1), (226, "turn", SQ_A, SQ_A, 1), (240, None, None, None, 1)]
    seq = [None] * NF
    track = []
    for (f0, kind, a, b, face), (f1, *_r) in zip(plan, plan[1:]):
        for f in range(f0, f1):
            if kind == "dash":
                u = (f - f0 + 1) / (f1 - f0)
                x, y = lerp(a[0], b[0], u), lerp(a[1], b[1], u)
                name = "run0" if ((f - f0) // 2) % 2 == 0 else "run1"
            else:
                x, y = a
                name = "flick" if kind == "flick" else "sit"
            seq[f] = f"{round(x - SQ_A[0] - frame_off(name, face))} {round(y - SQ_A[1])}"
            track.append((f, x, y, name, face))
    anim = f'<g transform="translate({pp(*SQ_A)})"><g>{life_anim(seq)}{body}</g></g>'
    still = f'<use href="#sqE" transform="translate({pp(*SQ_A)})"/>'
    LIFE_TRACKS["squirrel"] = track
    return defs, anim, still


# ---- the busker's audience: a child reaching for a bubble, an NYU student filming it (static)
KID_AT = (392.0, 610.0)
STUDENT_AT = (424.0, 630.0)


def audience_svg(P):
    o = []
    for (x0, y0), sc, kind in ((KID_AT, 0.66, "kid"), (STUDENT_AT, 1.0, "stu")):
        k = life_k(y0) * sc

        def Q(px, py):
            return x0 + px * k, y0 + py * k
        hgt = 42.5 * k
        if not P["night"]:
            o.append(f'<path d="{life_shadow(P, x0, y0, k, hgt)}" fill="{P["shadow"]}"/>')
        legs = poly([Q(-3.4, -14), Q(-0.9, -14), Q(-1.0, 0), Q(-3.6, 0)]) + poly([Q(0.9, -14), Q(3.4, -14), Q(3.8, 0), Q(1.2, 0)])
        coat = (f"M{pp(*Q(-5.4, -31))}C{pp(*Q(-5.6, -34.5))} {pp(*Q(5.6, -34.5))} {pp(*Q(5.4, -31))}"
                f"L{pp(*Q(6.2, -12))}L{pp(*Q(-6.2, -12))}Z")
        sh = poly([Q(1.6, -33.8), Q(5.4, -31), Q(6.2, -12), Q(2.4, -12)])
        col, dk = (P["kid"], P["kid_dk"]) if kind == "kid" else (P["stu"], P["stu_dk"])
        o.append(f'<path d="{legs}" fill="{P["hair"]}"/><path d="{coat}" fill="{col}"/><path d="{sh}" fill="{dk}"/>')
        hx = 0.8 if kind == "kid" else 1.0
        o.append(f'<path d="{circ(*Q(hx, -38.4), 4.1 * k)}" fill="{P["skin"]}"/>')
        o.append(f'<path d="M{pp(*Q(hx - 4.2, -38.6))}A{fm(4.2 * k)} {fm(4.2 * k)} 0 0 1 {pp(*Q(hx + 4.2, -38.6))}Z" fill="{P["hair"]}"/>')
        if kind == "kid":   # reaching up at the bubble going over, the other hand half up
            arms = f"M{pp(*Q(2.4, -30.4))}L{pp(*Q(7.0, -39.6))}L{pp(*Q(9.4, -49.6))}M{pp(*Q(-2.6, -30.4))}L{pp(*Q(-5.8, -23.4))}L{pp(*Q(-3.4, -17.8))}"
            o.append(f'<path d="{arms}" fill="none" stroke="{dk}" stroke-width="{fm(3.4 * k)}" stroke-linecap="round" stroke-linejoin="round"/>')
            o.append(f'<path d="M{pp(*Q(9.4, -49.6))}h0M{pp(*Q(-3.4, -17.8))}h0" stroke="{P["skin"]}" stroke-width="{fm(3.4 * k)}" stroke-linecap="round"/>')
        else:               # violet tote on the near shoulder, phone held up at the show
            o.append(f'<path d="M{pp(*Q(-2.2, -31))}L{pp(*Q(-4.6, -19))}M{pp(*Q(0.4, -31.6))}L{pp(*Q(-1.0, -19))}" stroke="{P["tote"]}" stroke-width="{fm(0.8 * k)}"/>')
            o.append(f'<path d="{poly([Q(-6.6, -19.6), Q(0.4, -19.6), Q(0.8, -9.4), Q(-7.0, -9.4)])}" fill="{P["tote"]}"/>')
            o.append(f'<path d="M{pp(*Q(2.6, -30))}L{pp(*Q(8.4, -33.6))}L{pp(*Q(9.4, -39.4))}" fill="none" stroke="{col}" '
                     f'stroke-width="{fm(2.6 * k)}" stroke-linecap="round" stroke-linejoin="round"/>')
            o.append(f'<path d="{poly([Q(8.6, -44.2), Q(11.0, -43.8), Q(10.4, -37.6), Q(8.0, -38.0)])}" fill="{P["phone"]}"/>')
    return "\n".join(o)


# ---- night sky: the stars (as before, drawn as round dots), a sparkle visiting five of them; the ESB beacon
STAR_TWINKLE = [(18, 2), (66, 12), (112, 31), (162, 33), (208, 0)]       # (grid frame, star index)


def life_sky_svg(P):
    """Insertion point (a), behind everything: night only."""
    if not P["stars"]:
        return ""
    srng = random.Random(7)
    by_r, stars = {}, []
    for _ in range(46):
        x, y = srng.uniform(20, 1580), srng.uniform(14, 300)
        if x < 1000 and 50 < y < 170:
            continue
        r = srng.choice((0.9, 1.1, 1.4))
        by_r.setdefault(r, []).append(f"M{pp(x, y)}h0")
        stars.append((x, y))
    o = [f'<path d="{"".join(v)}" stroke="{P["star"]}" stroke-width="{fm(2 * r)}" stroke-linecap="round" stroke-opacity=".7"/>'
         for r, v in sorted(by_r.items())]
    # the sparkle: a bright core with four short rays, then a smaller one (two frames of one strip)
    spark = (f'<path d="M0 0h0M{LIFE_LF} 0h0" stroke="{P["spark"]}" stroke-width="3.2" stroke-linecap="round"/>'
             f'<path d="M-4.6 0h9.2M0 -4.6v9.2M{LIFE_LF - 2.6} 0h5.2M{LIFE_LF} -2.6v5.2" stroke="{P["spark"]}" stroke-width=".7" '
             f'stroke-opacity=".8" stroke-linecap="round"/>')
    seq = ["0 -3000"] * NF
    for f0, si in STAR_TWINKLE:
        x, y = stars[si]
        for f in range(f0, f0 + 7):
            seq[f % NF] = f"{fm(x - (0 if f < f0 + 3 else LIFE_LF))} {fm(y)}"
    o.append(f'<g class="anim"><g>{life_anim(seq)}{spark}</g></g>')
    return "\n".join(o)


ESB_TIP = (-175.0, 1454.0, 6900.0)                   # vista_svg's Empire State Building: x, height, distance (ft)


def life_back_svg(P):
    """Insertion point (b), over the vista and the arch: night only, the beacon on the Empire State Building's mast
    flashes red, 0.6 s on in every 2 s (30 flashes a minute, as aviation beacons do)."""
    if not P["night"]:
        return ""
    bx, by = persp(*ESB_TIP)
    dot = f'<path d="M{pp(bx, by + 0.8)}h0" stroke="{P["beacon"]}" stroke-width="2.4" stroke-linecap="round"/>'
    return (f'<g class="anim"><g><animateTransform attributeName="transform" type="translate" values="0 0;0 -3000" '
            f'keyTimes="0;.3" dur="2s" calcMode="discrete" repeatCount="indefinite"/>{dot}</g></g><g class="still">{dot}</g>')


def life_front_svg(P, data=None):
    """Life in front: insertion point (c), after the front lamps."""
    o = []
    body, banim, bstill = busker_svg(P)
    bdefs, ganim, gstill = bubbles_svg(P, data)
    cbody, canim, cstill = chess_svg(P)
    sdefs, sanim, sstill = squirrel_svg(P)
    o += [bdefs, sdefs, cbody, body, audience_svg(P)]
    o.append(f'<g class="anim">{canim}{sanim}{banim}{ganim}</g><g class="still">{cstill}{sstill}{bstill}{gstill}</g>')
    return "\n".join(o)


# ------------------------------------------------------------------ assembly
def name_svg(P):
    fp = font("hubot-sans", 125, 800)
    d, w = text_path("Rohan Malhotra", fp, size=96, x=72, y=150, tracking=-0.02)
    return f'<path d="{d}" fill="{P["name"]}"/>', w


def build(theme, check_data=None):
    P = PAL[theme]
    rng = random.Random(1892)                        # the arch's year; same scene in both themes
    o = []
    o.append(f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" role="img" '
             f'aria-label="Rohan Malhotra. Washington Square Park and its arch, with the fountain, a flock of pigeons and giant soap bubbles.">')
    o.append("<title>Rohan Malhotra</title>")
    css = ("".join(f".d{k}{{fill:none;stroke:{P['drop']};stroke-width:{w};stroke-linecap:round}}"
                     f".j{k}{{fill:none;stroke:{P['jet']};stroke-width:{fm(w * 0.62, 2)};stroke-linecap:round;opacity:.42}}"
                     for k, w in enumerate((2.6, 3.0, 2.7))))
    o.append("<style>" + css + ".still{display:none}@media (prefers-reduced-motion:reduce){.anim{display:none}.still{display:inline}"
             "*{animation:none!important}}</style>")
    # defs
    sky = "".join(f'<stop offset="{o_}" stop-color="{c}"/>' for o_, c in P["sky"])
    defs = [f'<linearGradient id="sky" x1="0" y1="0" x2="1" y2=".25">{sky}</linearGradient>' if not P["night"] else
            f'<linearGradient id="sky" x1="0" y1="0" x2="0" y2="1">{sky}</linearGradient>',
            f'<linearGradient id="vsky" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="{P["v_sky"]}"/>'
            f'<stop offset="1" stop-color="{mix(P["v_sky"], P["v_lit"], 0.35)}"/></linearGradient>',
            '<clipPath id="card"><rect width="1600" height="640" rx="26"/></clipPath>',
            f'<path id="leaf" d="{LEAF_D}"/>']
    if P["night"]:
        defs.append('<radialGradient id="halo"><stop offset="0" stop-color="#FFD98C" stop-opacity=".55"/>'
                    '<stop offset=".35" stop-color="#FFC970" stop-opacity=".18"/><stop offset="1" stop-color="#FFC970" stop-opacity="0"/></radialGradient>')
        defs.append('<radialGradient id="pool"><stop offset="0" stop-color="#F7CF84" stop-opacity=".42"/>'
                    '<stop offset=".6" stop-color="#F7CF84" stop-opacity=".12"/><stop offset="1" stop-color="#F7CF84" stop-opacity="0"/></radialGradient>')
    defs.append(bird_sprites(P))
    o.append("<defs>" + "\n".join(defs) + "</defs>")
    o.append('<g clip-path="url(#card)">')
    o.append('<rect width="1600" height="640" fill="url(#sky)"/>')
    o.append(life_sky_svg(P))
    o.append(backdrop_svg(P, rng))
    o.append(plaza_svg(P, rng))
    o.append(vista_svg(P, rng))
    o.append(arch_svg(P, rng))
    if P["night"]:
        # floodlights at the arch's feet
        for x in (-25.0, 25.0):
            cx, cy = A(x, 0)
            o.append(f'<ellipse cx="{fm(cx)}" cy="{fm(cy + 2)}" rx="60" ry="9" fill="url(#pool)"/>')
    o.append(trees_svg(P, rng))
    o.append(nyu_flags_svg(P, check_data))
    o.append(lamps_svg(P, front=False))
    o.append(people_svg(P, which={0}))
    o.append(life_back_svg(P))
    # fountain
    streams = jets()
    ring = streams[0]
    assert len({st["pf"] for st in streams}) == 1      # every stream repeats on the same 6-frame pattern
    PF = ring["pf"]
    rip_fr, lands, rip_r = ripple_frames(ring)
    PH = max(ball(sj, sj[4] / G)[1] for sj in streams[1]["sub"]) - Y_WATER
    plume_fr, rad, rc = plume_core_frames(P, PH, streams)
    frng = random.Random(1872)                         # the fountain's own seeded stream
    refl, shim, rrows = f_reflection(P, frng, PH, rad, rc)
    o.append("<style>" + (".j0,.j1,.j2{opacity:.62}" if P["night"] else "") + f".fq{{fill:none;stroke:{P['f_ripple']};stroke-width:1.3}}</style>")
    o.append(fountain_static(P, "ground"))
    o.append(fountain_static(P, "basin"))
    o.append(f_water_shadow(P))
    o.append(f_wall_band(P))
    o.append(refl)
    o.append(f_night_lights(P, streams))
    o.append(f_splashes(P, lands))
    gl = f_glints(P, frng, lands)
    water = [r + s_ + g for r, s_, g in zip(rip_fr, shim, gl)]          # ripples, shimmer, glints: one short strip
    o.append(f'<g class="anim">{f_strip(water, F_TR, "fnw", 2)}</g><g class="still">{f_still("fnw", 2)}</g>')
    o.append(fountain_static(P, "coping"))
    all_tracks = []
    layers = {}
    for layer in ("far", "near"):
        statics, per_frame = [], [[] for _ in range(PF)]
        for si, st in enumerate(streams):
            sp = stream_paths(st)[layer]
            if sp:
                statics.append(f'<path d="{"".join(sp)}" class="j{si}"/>')
            fr, tracks = stream_frames(st, layer)
            all_tracks.extend(tracks)
            if fr[0]:
                for k in range(PF):
                    per_frame[k].append(f'<path d="{fr[k]}" class="d{si}"/>')
        layers[layer] = (statics, ["".join(x) for x in per_frame])
    dur = PF / FPS
    o.append("".join(layers["far"][0]))
    o.append(f'<g class="anim">{f_strip(layers["far"][1], dur, "fna", 2)}</g><g class="still">{f_still("fna", 2)}</g>')
    o.append(f_churn(P, frng, rc))
    o.append(f'<g class="anim">{f_strip(plume_fr, F_TB, "fnp", 1)}</g><g class="still">{f_still("fnp", 1)}</g>')
    o.append(f'<g class="anim">{f_strip(layers["near"][1], dur, "fnb", 2)}</g><g class="still">{f_still("fnb", 2)}</g>')
    o.append(f_sitters(P))
    if check_data is not None:
        check_data["fountain"] = dict(H=PH, rad=rad, rc=rc, rows=rrows, rip_r=rip_r,
                                      plume_fr=plume_fr, lands=lands)
    o.append("".join(layers["near"][0]))
    o.append(people_svg(P, which={1}))
    o.append(lamps_svg(P, front=True))
    o.append(life_front_svg(P, check_data))
    # pigeons
    brng = random.Random(77)
    homes = homes_layout(brng)
    frames, toff, land = simulate_flock(homes, brng)
    banim, bstill = birds_svg(P, homes, frames, toff, land, brng)
    o.append(f'<g class="anim">{banim}</g><g class="still">{bstill}</g>')
    # leaves, then the foreground branch they fall from
    lt = leaf_tracks()
    o.append(f'<g class="anim">{leaves_svg(P, lt)}</g>')
    still_leaves = []
    for L, tr in zip(LEAVES[:2], lt[:2]):
        x, y, a = tr["pts"][len(tr["pts"]) // 3]
        still_leaves.append(f'<use href="#leaf" fill="{P["leaf"][L["col"]]}" transform="translate({pp(x, y)}) scale({fm(L["sc"], 2)}) rotate({fm(a + 8, 0)})"/>')
    o.append(f'<g class="still">{"".join(still_leaves)}</g>')
    o.append(branch_svg(P, random.Random(5)))
    nm, nw = name_svg(P)
    o.append(nm)
    o.append("</g></svg>")
    svg = "\n".join(o)
    if check_data is not None:
        check_data.update(dict(tracks=all_tracks, streams=streams, homes=homes, frames=frames, toff=toff, land=land,
                               banim=banim, leaf_tracks=lt, lands=lands, name_w=nw))
    return svg


# ------------------------------------------------------------------ checks
def check(out_dir, data):
    print("== droplets vs gravity")
    by = {}
    for name, si, age, x, y in data["tracks"]:
        by.setdefault((name, si), {})[round(age * FPS)] = (age, x, y)
    worst_g, worst_res, n = 0.0, 0.0, 0
    for key, pts in by.items():
        ts = sorted(pts.values())
        # least squares y = a + b t + c t^2 and x = p + q t
        S = [[0.0] * 3 for _ in range(3)]
        rhs = [0.0] * 3
        for t, x, y in ts:
            v = [1, t, t * t]
            for i in range(3):
                rhs[i] += v[i] * y
                for j in range(3):
                    S[i][j] += v[i] * v[j]
        c = solve3(S, rhs)
        g_fit = 2 * c[2]
        res = max(abs(y - (c[0] + c[1] * t + c[2] * t * t)) for t, x, y in ts)
        # x linear
        tm = sum(t for t, _, _ in ts) / len(ts)
        xm = sum(x for _, x, _ in ts) / len(ts)
        q = sum((t - tm) * (x - xm) for t, x, _ in ts) / sum((t - tm) ** 2 for t, _, _ in ts)
        xres = max(abs(x - (xm + q * (t - tm))) for t, x, _ in ts)
        worst_g = max(worst_g, abs(g_fit - G_SCREEN) / G_SCREEN)
        worst_res = max(worst_res, res, xres)
        n += 1
    print(f"  {n} streams, {len(data['tracks'])} drop samples (every frame of every flight)")
    print(f"  screen gravity g*s*cos(el) = {G_SCREEN:.2f} units/s^2  (g = {G} m/s^2, s = {SF} units/m, el = 11 deg)")
    print(f"  fitted parabola: worst |g_fit - g|/g = {worst_g:.2e}, worst residual {worst_res:.3f} units (coords rounded to 0.1)")
    for s in data["streams"]:
        v = s["sub"][0]
        apex = v[1] + v[4] ** 2 / (2 * G)
        print(f"  {s['name']}: T = {s['T']} s, {s['K']} drops per jet, apex {apex:.2f} m, pattern repeats every {s['pf']} frames")
    print("== flock")
    tracks = bird_positions_from_svg(data["banim"])
    homes = data["homes"]
    for i, tr in enumerate(tracks):
        for f in range(NF):
            if tr[f][1] >= OFFCARD - 1e-6:
                tr[f] = (float(homes[i][0]), float(homes[i][1]))
    flying = [[not (math.dist(tracks[i][f], homes[i][:2]) < 1e-6) for f in range(NF)] for i in range(len(tracks))]
    mind_air, wa = 1e9, None
    mind_mix, wm = 1e9, None
    for f in range(NF):
        for i in range(len(tracks)):
            for j in range(i + 1, len(tracks)):
                d = math.dist(tracks[i][f], tracks[j][f])
                if flying[i][f] and flying[j][f] and d < mind_air:
                    mind_air, wa = d, f
                elif flying[i][f] != flying[j][f] and d < mind_mix:
                    mind_mix, wm = d, f
    seam = max(math.dist(tr[0], tr[-1]) for tr in tracks)
    homeerr = max(math.dist(tracks[i][0], homes[i][:2]) for i in range(len(tracks)))
    print(f"  {len(tracks)} pigeons, take-off frames {min(data['toff'])}-{max(data['toff'])}, touch-down frames "
          f"{min(data['land'])}-{max(data['land'])} (of {NF})")
    print(f"  minimum separation between two flying pigeons {mind_air:.1f} units at frame {wa} (wingspan 34, body 25)")
    print(f"  closest pass of a flying pigeon over one still on the ground {mind_mix:.1f} units at frame {wm} (take-off)")
    print(f"  t=0 position vs home: {homeerr:.3f} units; t=0 vs last frame: {seam:.3f} units")
    print("== leaves")
    for L, tr in zip(LEAVES, data["leaf_tracks"]):
        ths = [p[2] for p in tr["pts"]]
        print(f"  I={L['I']}: {len(tr['pts'])} frames ({len(tr['pts']) / FPS:.1f} s), plate angle {min(ths):.0f}..{max(ths):.0f} deg, "
              f"scale {tr['sigma']:.1f} units/half-chord")
    print("== loop seam and timing")
    for theme in ("light", "dark"):
        svg = open(os.path.join(out_dir, f"hero-{theme}.svg")).read()
        durs = set(re.findall(r'dur="([\d.]+)s"', svg))
        ok = all(abs(PERIOD / float(x) - round(PERIOD / float(x))) < 1e-9 for x in durs)
        kts = [float(v) for m in re.findall(r'keyTimes="([^"]+)"', svg) for v in m.split(";")]
        grid = max(abs(v * NF - round(v * NF)) for v in kts) / FPS
        calc = set(re.findall(r'calcMode="(\w+)"', svg))
        print(f"  {theme}: {len(svg) / 1024:.1f} KB, durations {sorted(durs, key=float)} all divide {PERIOD} s: {ok}; "
              f"keyTimes off the 20 fps grid by <= {grid * 1000:.2f} ms; calcModes {sorted(calc)}")
    check_fountain(out_dir, data)
    check_life(out_dir, data)
    check_scenery(out_dir, data)


def life_expand(vals, kts=None):
    """Per grid frame (x, y) of a discrete translate as the browser plays it (uniform, or with keyTimes)."""
    v = [tuple(float(q) for q in p.split()) for p in vals.split(";")]
    if kts:
        k = [float(q) for q in kts.split(";")]
        return [v[max(i for i in range(len(k)) if k[i] <= (f + 0.5) / NF)] for f in range(NF)]
    step = NF // len(v)
    return [v[f // step] for f in range(NF)]


def check_life(out_dir, data):
    """Proofs for the life section, re-derived from the emitted light SVG where it matters."""
    L = data["life"]["bubbles"]
    svg = open(os.path.join(out_dir, "hero-light.svg")).read()
    print("== life: pigeons and leaves without animateMotion (one translate + one additive rotate per sprite)")
    played = bird_play(data["banim"])
    dp = dh = 0.0
    same_draw = same_ground = True
    for tr, ref in zip(played, LIFE_TRACKS["birds"]):
        old = bird_motion_ref(ref["q"])
        for f in range(NF):
            x, y, hd, href = tr[f]
            if ref["seq"][f] == "a":
                ox, oy, oh = old[f - ref["toff"] - 1]
                dp = max(dp, math.hypot(x - ox, y - oy))
                dh = max(dh, abs((hd - oh + 180) % 360 - 180))
                same_draw &= href == BIRD_STRIP[2 + (f + ref["phase"]) % 4]
            else:
                same_ground &= (x, y) == ref["home"] and href.endswith("p") == (ref["seq"][f] == "p")
    ds = max(math.dist(tr[f][:2], ref["q"][f - ref["toff"]]) for tr, ref in zip(played, LIFE_TRACKS["birds"])
             for f in range(NF) if ref["seq"][f] == "a")
    n_anim = len(re.findall(r"<animate", data["banim"]))
    print(f"  {len(played)} pigeons, {n_anim} animation elements (was 39 with animateMotion): vs what animateMotion showed, "
          f"position within {dp:.2f} units (it sat 0.3 before each simulated point; now on it, within {ds:.2f}), "
          f"heading within {dh:.2f} deg, same flap drawing every frame: {same_draw}, same stand/peck on the ground: {same_ground}")
    lv = re.findall(r'<g><animateTransform attributeName="transform" type="translate" values="([^"]+)" keyTimes="([^"]+)" '
                    r'dur="12s" calcMode="discrete" repeatCount="indefinite"/><g transform="scale\([\d.]+\)"><use href="#leaf"', svg)
    dl = 0.0
    for (vals, kts), ref in zip(lv, LIFE_TRACKS["leaves"]):
        new_pos = life_expand(vals, kts)
        q, cum, tot = ref["q"], ref["cum"], ref["cum"][-1]
        old_v = []
        for kp in ref["kps"]:
            s = float(kp) * tot
            j = max(j for j in range(len(q) - 1) if cum[j] <= s + 1e-9 and cum[j + 1] > cum[j]) if s < tot else len(q) - 2
            u = min(1.0, (s - cum[j]) / (cum[j + 1] - cum[j]))
            old_v.append(f"{lerp(q[j][0], q[j + 1][0], u)} {lerp(q[j][1], q[j + 1][1], u)}")
        old_pos = life_expand(";".join(old_v), ";".join(ref["kts"]))
        dl = max(dl, max(math.dist(a, b) for a, b in zip(new_pos, old_pos)))
    print(f"  {len(lv)} leaves: translate on the old keyTimes, within {dl:.2f} units of the old motion path every frame")
    print("== life: giant soap bubbles")
    R0 = BUB_R[0]
    cd, mfilm, mf, m = bubble_coeffs(R0)
    wt = math.sqrt(8 * BUB_FILM_H * BUB_RHO_W * G / (BUB_RHO_A * BUB_CD))
    s, t = [0.0, 2.0, 0.0, 0.0], 0.0
    still = lambda t, s, R=R0: (lambda c: (s[2], s[3], -c[0] * math.hypot(s[2], s[3]) * s[2] / c[3],
                                           (-c[0] * math.hypot(s[2], s[3]) * s[3] - c[1] * G) / c[3]))(bubble_coeffs(R))
    for _ in range(int(120 / 0.01)):
        s = life_rk4(still, t, s, 0.01)
        t += 0.01
    print(f"  film {BUB_FILM_H * 1e6:.1f} um: film weight {mfilm * 1e3:.1f} g carried by {m:.2f} kg of moving mass (R = {R0} m); "
          f"terminal sink sqrt(8 h rho_w g / (rho_a Cd)) = {wt:.3f} m/s, still-air simulation {-s[3]:.3f} m/s")
    # the breeze: incompressible, tangent to the plaza, 12 s periodic at a fixed point
    rng = random.Random(4)
    div = per = 0.0
    for _ in range(300):
        tt, X, Y = rng.uniform(0, 12), rng.uniform(-2, 14), rng.uniform(0.2, 6)
        h = 1e-4
        du = (bub_breeze(tt, X + h, Y)[0] - bub_breeze(tt, X - h, Y)[0]) / (2 * h)
        dw = (bub_breeze(tt, X, Y + h)[1] - bub_breeze(tt, X, Y - h)[1]) / (2 * h)
        div = max(div, abs(du + dw))
        a, b = bub_breeze(tt, X, Y), bub_breeze(tt + PERIOD, X, Y)
        per = max(per, abs(a[0] - b[0]), abs(a[1] - b[1]))
    wg = max(abs(bub_breeze(rng.uniform(0, 12), rng.uniform(-2, 14), 0.0)[1]) for _ in range(300))
    print(f"  breeze: mean {BUB_U0} m/s with gusts, eddy rows carried at the mean wind; max |div| {div:.1e} 1/s, "
          f"max |w| at the plaza {wg:.1e} m/s, max |u(t+12 s) - u(t)| {per:.1e} m/s")
    # positions as drawn: parse every slot's translate values, undo the frame offset, compare with a fresh ODE solve
    slots = re.findall(r'<g transform="translate\((-?[\d.]+) (-?[\d.]+)\)"><g><animateTransform attributeName="transform" '
                       r'type="translate" values="([^"]+)"(?: keyTimes="([^"]+)")? dur="12s" calcMode="discrete" '
                       r'repeatCount="indefinite"/><g transform="scale\(([\d.]+)\)"><use href="#bub"/>', svg)
    assert len(slots) == len(L["sc"]), "bubble slots not found"
    drawn = []
    for ox_, oy_, vals, kts, sc in slots:
        v = life_expand(vals, kts)
        sp = LIFE_LF * float(sc)
        dr = {}
        for f, (x, y) in enumerate(v):
            if y > -1000:
                x, y = x + float(ox_), y + float(oy_)
                j = round((x - 550) / sp)
                dr[f] = (x - sp * j, y, j)
        drawn.append(dr)
    S, (lx, _), Yl = L["S"], L["loop"], L["Yl"]
    worst, nfr, clear, ground, top = 0.0, 0, 1e9, 1e9, 1e9
    tracks = []
    for fl in L["flights"]:
        r, R = fl["rel"], fl["R"]
        st0 = fl["states"][0]
        ref = bubble_flight(R, st0[0], st0[1:], len(fl["states"]), sub=32)
        dr = drawn[fl["slot"]]
        tr = {}
        for i, (tt, X, Y, vx, vy) in enumerate(ref):
            f = (r + 2 + i) % NF
            if f % 2:
                continue                              # slots step at 10 fps: even frames carry the values
            x, y, j = dr[f]
            worst = max(worst, math.hypot(x - (lx + S * X), y - (BUSK[1] - S * Y)))
            nfr += 1
            tr[f] = (lx + S * X, BUSK[1] - S * Y, R * S)
            ground = min(ground, Y - R)
            top = min(top, BUSK[1] - S * Y - R * S)
        tracks.append(tr)
        light_ = bubble_flight(R, st0[0], st0[1:], len(fl["states"]), sub=32, h=0.0)   # a weightless film
        film_sink = light_[-1][2] - ref[-1][2]
        dx = ref[-1][1] - ref[0][1]
        dt_ = ref[-1][0] - ref[0][0]
        um = sum(bub_breeze(tt, X, Y)[0] for tt, X, Y, *_ in ref) / len(ref)
        sink = Yl - min(Y for _, X, Y, *_ in ref)
        rise = max(Y for _, X, Y, *_ in ref) - Yl
        print(f"  bubble {len(tracks)}: R {R} m, released t={(r + 2) / FPS:.1f} s at {BUB_SLIP:.0%} of the local wind, "
              f"lives {dt_ + 0.1:.1f} s, drifts {dx:.1f} m at {dx / dt_:.2f} m/s (wind there {um:.2f}), "
              f"rides the eddies +{max(0.0, rise):.2f} / -{max(0.0, sink):.2f} m; the film's weight alone lowers it "
              f"{film_sink * 100:.0f} cm by the pop")
    for a in range(len(tracks)):
        for b in range(a + 1, len(tracks)):
            for f in set(tracks[a]) & set(tracks[b]):
                p, q = tracks[a][f], tracks[b][f]
                clear = min(clear, math.hypot(p[0] - q[0], p[1] - q[1]) - p[2] - q[2])
    print(f"  drawn vs a fresh RK4 solve (4x finer): worst {worst:.2f} units over {nfr} drawn positions (values rounded to 1)")
    print(f"  closest rims of two bubbles {clear:.1f} units; lowest bubble {ground:.2f} m above the plaza; "
          f"highest top y = {top:.0f} (name baseline y = 150)")
    print("== life: squirrel, chess, night")
    sq = LIFE_TRACKS.get("squirrel", [])
    dashes, cur = [], None
    for f, x, y, name, face in sq:
        if name.startswith("run"):
            if cur is None or f != cur[-1][0] + 1:
                cur = []
                dashes.append(cur)
            cur.append((f, x, y))
    for d_ in dashes:
        dist = math.dist(d_[0][1:], d_[-1][1:]) * len(d_) / max(1, len(d_) - 1)
        print(f"  squirrel dash at t={d_[0][0] / FPS:.2f} s: {dist:.0f} units in {len(d_) / FPS:.2f} s "
              f"= {dist / (len(d_) / FPS) / (25 * life_k(632)):.1f} m/s")
    flicks = sum(1 for i, (f, x, y, n, fc) in enumerate(sq) if n == "flick" and (i == 0 or sq[i - 1][3] != "flick"))
    print(f"  squirrel: {len(dashes)} dashes, {flicks} tail flicks, back on its first spot at the loop seam; daytime only")
    print("  chess: each player makes one move per loop (t = 2.8 s and 8.6 s)")
    print(f"  night: {len(STAR_TWINKLE)} stars twinkle (one sparkle at a time); the ESB beacon flashes 0.6 s in every 2 s")


def solve3(A_, b):
    M = [row[:] + [b[i]] for i, row in enumerate(A_)]
    for c in range(3):
        p = max(range(c, 3), key=lambda r: abs(M[r][c]))
        M[c], M[p] = M[p], M[c]
        for r in range(3):
            if r != c:
                k = M[r][c] / M[c][c]
                M[r] = [x - k * y for x, y in zip(M[r], M[c])]
    return [M[i][3] / M[i][i] for i in range(3)]


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.dirname(HERE))
    ap.add_argument("--check", action="store_true")
    a = ap.parse_args()
    data = {}
    for theme in ("light", "dark"):
        svg = build(theme, data if theme == "light" else None)
        path = os.path.join(a.out, f"hero-{theme}.svg")
        with open(path, "w") as fh:
            fh.write(svg)
        print(f"wrote {path} ({len(svg) / 1024:.1f} KB)")
    if a.check:
        check(a.out, data)


if __name__ == "__main__":
    main()
