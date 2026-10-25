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
    (flight times 1.5 / 2.4 / 1.8 s with 5 / 8 / 6 drops per jet all repeat every 0.3 s). Drops land on
    the water and ripple rings start at the landing point at the landing time.
  * the pigeons: a boids flock (separation, alignment, cohesion, a guide loop, arrive-and-land) sampled at
    20 fps. Each bird rides its own path with animateMotion (keyPoints are arc-length fractions of the sim
    samples, rotate="auto") with a 4-drawing flapping flipbook; on the ground a stand/peck flipbook. They
    take off in a wave, wheel round once and land back on their own spots.
  * falling leaves: the Andersen-Pesavento-Wang quasi-steady falling-plate model (fluttering regime),
    integrated with RK4; the leaf rides the computed path and rocks with the computed plate angle.

Frame-locked: every animation is discrete and changes only on a shared 20 fps grid. Every flipbook is a
filmstrip (frames stored 2000 units apart, off the card, stepped by one discrete translate): measured in
Chrome, discrete transforms and motion are skipped when unchanged, but discrete `d` and `href` animations
repaint the whole image every tick, which tripled the CPU. Every duration divides the 12 s period, so
t=0 and t=12 s are the same frame.

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
    o.append(f'<path d="{"".join(bands)}" fill="{P["band"]}"/>')
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
    o.append(f'<path d="{"".join(strips)}" fill="{P["band"]}"/>')
    o.append(f'<path d="{poly(key)}" fill="{P["stone_hi"]}" stroke="{P["line"]}" stroke-width="1.2"/>')
    ks = [A(1.9, 44.4), A(2.5, 51.0), A(3.1, 50.6), A(2.3, 44.4)]
    o.append(f'<path d="{poly(ks)}" fill="{P["band"]}"/>')
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
    return "\n".join(o)


# ------------------------------------------------------------------ the vista up Fifth Avenue
def vista_svg(P, rng):
    o = []
    clip = opening_path(back_fn)
    o.append(f'<clipPath id="vclip"><path d="{clip}"/></clipPath><g clip-path="url(#vclip)">')
    top = back_fn(0, CROWN)[1] - 4
    bot = back_fn(0, 0)[1] + 2
    xl, xr = back_fn(-OPEN_HW, 0)[0] - 2, back_fn(OPEN_HW, 0)[0] + 2
    vp = A(VPX, VPY)
    o.append(f'<rect x="{fm(xl)}" y="{fm(top)}" width="{fm(xr - xl)}" height="{fm(bot - top)}" fill="url(#vsky)"/>')
    # ground: cross street, then the avenue converging
    o.append(f'<path d="M{pp(xl, vp[1])}H{fm(xr)}V{fm(bot)}H{fm(xl)}Z" fill="{P["v_side"]}"/>')
    road = [persp(-35, 0, 30), persp(35, 0, 30), persp(35, 0, 60000), persp(-35, 0, 60000)]
    o.append(f'<path d="{poly(road)}" fill="{P["v_street"]}"/>')
    cross = [persp(-400, 0, 26), persp(400, 0, 26), persp(400, 0, 96), persp(-400, 0, 96)]
    o.append(f'<path d="{poly(cross)}" fill="{P["v_street"]}"/>')
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
    # facades along both sides: quads on the planes x = +-50 ft never overlap, so merge them by colour
    for side in (-1, 1):
        z = 330.0
        by_col, lines = {}, []
        while z < 9000:
            ln = rng.uniform(110, 260) * (1 + z / 3000)
            h = rng.choice([70, 85, 100, 120, 140, 160, 190, 230]) * rng.uniform(0.9, 1.1)
            z0, z1 = z, z + ln
            haze = round(min(0.8, (z0 / 9000.0) ** 0.9) * 6) / 6
            cf = mix(P["v_lit"] if side > 0 else P["v_sh"], P["v_sky"], haze)
            xb = 50.0 * side
            q = [persp(xb, 0, z0), persp(xb, h, z0), persp(xb, h, z1), persp(xb, 0, z1)]
            by_col.setdefault(cf, []).append(poly(q))
            if z0 < 2600:
                for yy in range(14, int(h) - 6, 12):
                    a, b = persp(xb, yy, z0), persp(xb, yy, z1)
                    lines.append(f"M{pp(*a)}L{pp(*b)}")
            z = z1
        for col, ds in by_col.items():
            o.append(f'<path d="{"".join(ds)}" fill="{col}"/>')
        col = P["v_line"] if (side > 0 or P["night"]) else P["v_line2"]
        if P["night"]:
            o.append(f'<path d="{"".join(lines)}" stroke="{col}" stroke-width=".9" stroke-dasharray="1.6 2.4" opacity=".85"/>')
        else:
            o.append(f'<path d="{"".join(lines)}" stroke="{col}" stroke-width=".7" opacity=".7"/>')
    o.append("</g>")
    return "\n".join(o)


# ------------------------------------------------------------------ backdrop: towers, the Row, trees
def backdrop_svg(P, rng):
    o = []
    # hazy towers behind the Row (2 Fifth Ave on the west, One Fifth Ave on the east)
    o.append(f'<path d="M-10 452V272H70V250H190V262H232V236H330V452Z" fill="{P["haze"]}"/>')
    one5 = [(1392, 452), (1392, 206), (1404, 206), (1404, 170), (1418, 170), (1418, 140), (1432, 140), (1432, 112),
            (1446, 112), (1446, 96), (1474, 96), (1474, 112), (1488, 112), (1488, 140), (1502, 140), (1502, 170),
            (1516, 170), (1516, 206), (1528, 206), (1528, 452)]
    o.append(f'<path d="{poly(one5)}" fill="{P["haze2"]}"/>')
    lit = [(1392, 452), (1392, 206), (1404, 206), (1404, 170), (1418, 170), (1418, 140), (1432, 140), (1432, 112),
           (1446, 112), (1446, 96), (1452, 96), (1452, 452)]
    o.append(f'<path d="{poly(lit)}" fill="{P["haze_lit"]}"/>')
    if P["night"]:
        wl = []
        for y in range(120, 440, 9):
            for x in range(1452, 1520, 9):
                if rng.random() < 0.32 and (y > 210 or 1438 < x < 1482):
                    wl.append(f"M{x} {y}h3.2v4.2h-3.2Z")
        o.append(f'<path d="{"".join(wl)}" fill="#E7B865" opacity=".75"/>')
    # the Row: Greek Revival brick houses on Washington Square North, frontal, beyond the arch
    yg, ytop = 434.0, 284.0
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
    bricks, stones, trims, wins, glints, lits, chims = [], [], [], [], [], [], []
    for i, (x0, x1, yt) in enumerate(houses):
        (stones if rng.random() < 0.18 else bricks).append(f"M{pp(x0, yt, 0)}H{fm(x1, 0)}V{fm(yg, 0)}H{fm(x0, 0)}Z")
        trims.append(f"M{pp(x0 - 1, yt - 6)}H{fm(x1 + 1)}V{fm(yt)}H{fm(x0 - 1)}Z")
        if rng.random() < 0.6:
            cx = rng.uniform(x0 + 8, x1 - 16)
            chims.append(f"M{pp(cx, yt - 6)}V{fm(yt - 22)}h9V{fm(yt - 6)}Z")
        bw = (x1 - x0) / 3
        for fl in range(4):
            wy = yt + 16 + fl * 34
            if wy + 20 > yg:
                break
            for b in range(3):
                wx = x0 + b * bw + bw / 2 - 5.4
                wins.append(f"M{pp(wx, wy, 0)}h11v20h-11Z")
                trims.append(f"M{pp(wx - 1.5, wy - 3, 0)}h14v3h-14Z")
                r = rng.random()
                if not P["night"] and r < 0.16:
                    glints.append(f"M{pp(wx, wy, 0)}h11v9h-11Z")
                if P["night"] and r < 0.42:
                    lits.append(f"M{pp(wx, wy, 0)}h11v20h-11Z")
    o.append(f'<path d="{"".join(chims)}" fill="{P["brick_dk"]}"/>')
    o.append(f'<path d="{"".join(bricks)}" fill="{P["brick"]}"/>')
    o.append(f'<path d="{"".join(stones)}" fill="{P["lime"]}"/>')
    o.append(f'<path d="{"".join(trims)}" fill="{P["trim"]}"/>')
    o.append(f'<path d="{"".join(wins)}" fill="{P["win"]}"/>')
    if glints:
        o.append(f'<path d="{"".join(glints)}" fill="{P["glint"]}"/>')
    if lits:
        o.append(f'<path d="{"".join(lits)}" fill="#F1C470"/>')
    return "\n".join(o)


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


TREES_L = [(52, 462, 330, 112, 92, 0), (214, 466, 344, 96, 84, 2), (356, 460, 318, 104, 96, 1),
           (516, 465, 340, 94, 82, 3), (660, 460, 326, 106, 92, 0), (808, 464, 344, 92, 80, 4),
           (944, 462, 352, 72, 72, 2)]
TREES_R = [(1452, 462, 344, 84, 86, 3), (1566, 466, 322, 98, 102, 1)]


def trees_svg(P, rng):
    o = []
    trunks, trunk_hi, twigs = [], [], []
    for x, yb, cy, rx, ry, fi in TREES_L + TREES_R:
        top = cy + ry * 0.35
        w0, w1 = 8.5, 4.6
        trunks.append(poly([(x - w0 / 2, yb), (x - w1 / 2, top), (x - 30, cy - 4), (x - 26, cy - 8), (x + w1 / 2 - 1, top - 14),
                            (x + 24, cy - 10), (x + 28, cy - 5), (x + w1 / 2, top), (x + w0 / 2, yb)]))
        trunk_hi.append(poly([(x - w0 / 2, yb), (x - w1 / 2, top), (x - w1 / 2 + 1.8, top), (x - w0 / 2 + 2.6, yb)]))
        twigs.append(f"M{pp(x, top, 0)}Q{pp(x - rx * 0.2, cy, 0)} {pp(x - rx * 0.55, cy - ry * 0.55, 0)}"
                     f"M{pp(x, top, 0)}Q{pp(x + rx * 0.15, cy - ry * 0.2, 0)} {pp(x + rx * 0.5, cy - ry * 0.6, 0)}"
                     f"M{pp(x, top - 10, 0)}L{pp(x + rx * 0.05, cy - ry * 0.75, 0)}")
    o.append(f'<path d="{"".join(trunks)}" fill="{P["trunk"]}"/>')
    o.append(f'<path d="{"".join(trunk_hi)}" fill="{P["trunk_hi"]}"/>')
    crowns_at = len(o)
    ox, oy = P["fol_off"]
    by_col = {}
    for x, yb, cy, rx, ry, fi in TREES_L + TREES_R:
        cs = crown(rng, x, cy, rx, ry, 34)
        side = (lambda c: c[0] - x < rx * 0.35 and c[1] - cy < ry * 0.45) if oy < 0 else (lambda c: c[1] - cy > -ry * 0.1)
        hi = [(cx_ + ox * r, cy_ + oy * r, r * 0.72) for cx_, cy_, r in cs if side((cx_, cy_))]
        lit, sh = P["fol"][fi]
        by_col.setdefault(sh, []).append(cpath(cs, 0))
        by_col.setdefault(lit, []).append(cpath(hi, 0))
    # draw shade masses first, then lit (keeps one path per colour)
    shades = {P["fol"][i][1] for i in range(len(P["fol"]))}
    for col, ds in by_col.items():
        if col in shades:
            o.append(f'<path d="{"".join(ds)}" fill="{col}"/>')
    for col, ds in by_col.items():
        if col not in shades:
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


def plaza_svg(P, rng):
    o = []
    o.append(f'<path d="M-10 446H1610V650H-10Z" fill="{P["plaza"]}"/>')
    rings = []
    for r in (12.4, 15.6, 19.5, 24.5, 30.5, 38.0):
        rings.append(ell(FX, FY, SF * r, SF * r * SE))
    o.append(f'<path d="{"".join(rings)}" fill="none" stroke="{P["ring"]}" stroke-width="2.2"/>')
    # lawn strips and the hoop fence along the far edge of the plaza
    o.append(f'<path d="M-10 446H1030V468H-10ZM1366 446H1610V468H1366Z" fill="{P["lawn"]}"/>')
    o.append(f'<path d="M-10 462H1030V468H-10ZM1366 462H1610V468H1366Z" fill="{P["lawn_dk"]}"/>')
    hoops = []
    for x0, x1 in ((-10, 1030), (1366, 1610)):
        s = f"M{x0} 469"
        n = int((x1 - x0) / 14)
        for _ in range(n):
            s += "q7-9 14 0"
        hoops.append(s)
    o.append(f'<path d="{"".join(hoops)}" fill="none" stroke="{P["fence"]}" stroke-width="1.6"/>')
    if not P["night"]:
        # long shadows of the elms that stand west of the frame
        bands = []
        for (y0, th, x1) in ((512, 22, 600), (566, 26, 760), (622, 34, 880)):
            top, bottom = [], []
            n = 18
            for i in range(n + 1):
                x = -20 + (x1 + 20) * i / n
                yc = y0 + SUN[1] * (x + 20)
                wob = 2.2 * math.sin(i * 0.9 + y0) + 1.2 * math.sin(i * 2.3)
                taper = 1.0 if i < n - 3 else (n - i + 0.6) / 3.6
                top.append((x, yc - th * taper / 2 + wob))
                bottom.append((x, yc + th * taper / 2 - wob * 0.6))
            bands.append(poly(top + list(reversed(bottom))))
        o.append(f'<path d="{"".join(bands)}" fill="{P["shadow"]}"/>')
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
    o = []
    for x, y, s, banner in LAMPS:
        if (y > 560) != front:
            continue
        body, globe, gc, hgt = lamp_shape(x, y, s)
        if not P["night"]:
            L = hgt * 1.55
            dx, dy = SUN[0] * L, SUN[1] * L
            sh = poly([(x - 2.5, y + 0.5), (x + dx, y + dy - 2.2), (x + dx + 2, y + dy + 2.2), (x + 2.5, y + 2.5)])
            sh += ell(x + dx + 9 * s / 30, y + dy + 1, 9 * s / 30, 3.2 * s / 30)
            sh += ell(x + 4, y + 1.2, 8 * s / 30, 2.4 * s / 30)
            o.append(f'<path d="{sh}" fill="{P["shadow"]}"/>')
        else:
            o.append(f'<ellipse cx="{fm(x + 6)}" cy="{fm(y + 3)}" rx="{fm(s * 4.6)}" ry="{fm(s * 1.0)}" fill="url(#pool)"/>')
            o.append(f'<circle cx="{fm(gc[0])}" cy="{fm(gc[1])}" r="{fm(s * 1.9)}" fill="url(#halo)"/>')
        o.append(f'<path d="{body}" fill="{P["lamp"]}"/>')
        o.append(f'<path d="{globe}" fill="{P["globe"]}"/>')
        if banner:
            k = s / 30.0
            bx, by = x + 1.5 * k, y - 84 * k
            o.append(f'<path d="M{pp(bx, by - 2 * k)}h{fm(18 * k)}" stroke="{P["lamp"]}" stroke-width="{fm(1.6 * k)}"/>')
            o.append(f'<path d="M{pp(bx + 3 * k, by)}h{fm(14 * k)}v{fm(30 * k)}l{fm(-7 * k)} {fm(-4 * k)}l{fm(-7 * k)} {fm(4 * k)}Z" fill="{P["banner"]}"/>')
            tx, ty = bx + 10 * k, by + 8 * k
            torch = (f"M{pp(tx - 1.3 * k, ty + 6 * k)}h{fm(2.6 * k)}l{fm(1.4 * k)} {fm(-4.6 * k)}h{fm(-5.4 * k)}Z"
                     f"M{pp(tx, ty - 5.6 * k)}c{fm(2.8 * k)} {fm(2 * k)} {fm(2.6 * k)} {fm(4.4 * k)} {fm(0.4 * k)} {fm(5.6 * k)}"
                     f"c{fm(-2.6 * k)} {fm(-0.8 * k)} {fm(-2.6 * k)} {fm(-3.8 * k)} {fm(-0.4 * k)} {fm(-5.6 * k)}Z")
            o.append(f'<path d="{torch}" fill="{P["torch"]}"/>')
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


PEOPLE = [(150, 616, 1.08, 2, "walk"), (962, 586, 0.98, 0, "sitread"), (1018, 596, 1.0, 1, "sit"),
          (1446, 630, 1.1, 3, "stand")]


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
R_OUT, R_IN, Y_RIM, Y_WATER = 10.6, 10.0, 0.45, 0.25


def jets():
    """Return stream definitions: list of dict(name, T, K, period_frames, subjets=[(x0,y0,z0,vx,vy,vz)], layer)."""
    out = []
    ring = []
    for j in range(10):
        a = 2 * math.pi * j / 10 + math.radians(9)
        r0, r1, T, y0 = 1.3, 6.2, 1.5, 0.4
        vr = (r1 - r0) / T
        vy = (Y_WATER - y0 + 0.5 * G * T * T) / T
        ring.append((r0 * math.cos(a), y0, r0 * math.sin(a), vr * math.cos(a), vy, vr * math.sin(a)))
    out.append(dict(name="ring", T=1.5, K=5, sub=ring, width=2.6))
    plA = []
    for j in range(7):
        a = 2 * math.pi * j / 7 + 0.4
        vr = 0.22 + 0.5 * ((j * 3) % 7) / 6
        T, y0 = 2.4, 0.4
        vy = (Y_WATER - y0 + 0.5 * G * T * T) / T
        plA.append((0.15 * math.cos(a), y0, 0.15 * math.sin(a), vr * math.cos(a), vy, vr * math.sin(a)))
    out.append(dict(name="plA", T=2.4, K=8, sub=plA, width=3.0))
    plB = []
    for j in range(8):
        a = 2 * math.pi * j / 8 + 0.1
        vr = 0.95 + 0.6 * ((j * 5) % 8) / 7
        T, y0 = 1.8, 0.4
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
    """Discrete d values (one per frame of the pattern) for one stream group and depth layer."""
    frames = []
    tracks = []
    for f in range(s["pf"]):
        d = []
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
                d.append(f"M{pp(x, y)}l{tx} {ty}")
                tracks.append((s["name"], si, age, float(fm(x)), float(fm(y))))    # as emitted
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


def ripple_frames(s, cls_n=3):
    """Ring jets land every T/K s at a fixed point; a ring of class c is c*T/K..(c+1)*T/K old."""
    T, K, pf = s["T"], s["K"], s["pf"]
    lands = []
    for sj in s["sub"]:
        X, Y, Z = ball(sj, T)
        lands.append((X, Z))
    classes = []
    for c in range(cls_n):
        fr = []
        for f in range(pf):
            age = (c * pf + f) / FPS
            r = 0.2 + 1.6 * age
            d = []
            for X, Z in lands:
                cx, cy = proj(X, Y_WATER, Z)
                d.append(ell(cx, cy, SF * r, SF * r * SE))
            fr.append("".join(d))
        classes.append(fr)
    return classes, lands


def plume_core_frames(P):
    fr = []
    base = proj(0, Y_WATER, 0)
    for f in range(6):
        ph = 2 * math.pi * f / 6
        pts_l, pts_r = [], []
        for i in range(9):
            h = 5.6 * i / 8
            w = 0.24 + 0.16 * (i / 8) + 0.05 * math.sin(ph + i * 1.3)
            x, y = proj(0, Y_WATER + h, 0)
            pts_r.append((x + SF * w, y))
            pts_l.append((x - SF * (w + 0.04 * math.cos(ph + i)), y))
        top = proj(0, Y_WATER + 5.9 + 0.12 * math.sin(ph), 0)
        d = poly([pts_l[0]] + pts_l[1:] + [top] + list(reversed(pts_r)))
        fr.append(d)
    foam = []
    for i in range(7):
        a = 2 * math.pi * i / 7
        cx, cy = proj(0.95 * math.cos(a), Y_WATER, 0.95 * math.sin(a))
        foam.append(ell(cx, cy, 15, 4.2))
    foam.append(ell(base[0], base[1] - 3, 30, 7.5))
    return fr, "".join(foam)


def fountain_static(P, part):
    o = []
    if part == "back":
        if not P["night"]:
            # the coping's long shadow on the plaza, east side
            pts = []
            for i in range(25):
                a = math.radians(-70 + 140 * i / 24)
                x, y = proj(R_OUT * math.cos(a), 0, R_OUT * math.sin(a))
                pts.append((x, y))
            far = [(x + 70 * math.cos(math.radians(-70 + 140 * i / 24)) ** 2, y - 6) for i, (x, y) in enumerate(pts)]
            o.append(f'<path d="{poly(pts + list(reversed(far)))}" fill="{P["shadow"]}"/>')
        # outer wall (front half), coping top
        bot = [proj(R_OUT * math.cos(math.radians(a)), 0, -R_OUT * math.sin(math.radians(a))) for a in range(0, 181, 6)]
        top = [proj(R_OUT * math.cos(math.radians(a)), Y_RIM, -R_OUT * math.sin(math.radians(a))) for a in range(180, -1, -6)]
        o.append(f'<path d="{poly(bot + top)}" fill="{P["rim_out"]}"/>')
        bot2 = [proj(R_OUT * math.cos(math.radians(a)), 0, -R_OUT * math.sin(math.radians(a))) for a in range(0, 61, 6)]
        top2 = [proj(R_OUT * math.cos(math.radians(a)), Y_RIM, -R_OUT * math.sin(math.radians(a))) for a in range(60, -1, -6)]
        o.append(f'<path d="{poly(bot2 + top2)}" fill="{P["rim_sh"]}"/>')
        cx, cy = proj(0, Y_RIM, 0)
        o.append(f'<path d="{ell(cx, cy, SF * R_IN, SF * R_IN * SE)}" fill="{P["wall_in"]}"/>')
        cx, cy = proj(0, Y_WATER, 0)
        o.append(f'<path d="{ell(cx, cy, SF * R_IN, SF * R_IN * SE)}" fill="{P["water"]}"/>')
        rr = []
        for r in (3.0, 4.6, 8.0):
            rr.append(ell(cx, cy, SF * r, SF * r * SE))
        o.append(f'<path d="{"".join(rr)}" fill="none" stroke="{P["water_dk"]}" stroke-width="1.4"/>')
        hi = []
        for (x0, y0, w) in ((-7.6, 1.6, 2.6), (-4.2, 3.4, 3.4), (3.6, 2.4, 2.2), (6.1, -2.8, 1.8), (-6.5, -3.3, 2.0)):
            a, b = proj(x0, Y_WATER, y0), proj(x0 + w, Y_WATER, y0)
            hi.append(f"M{pp(*a)}H{fm(b[0])}")
        o.append(f'<path d="{"".join(hi)}" stroke="{P["water_hi"]}" stroke-width="2" stroke-linecap="round"/>')
    elif part == "coping":
        cx, cy = proj(0, Y_RIM, 0)
        o.append(f'<path d="{ell(cx, cy, SF * R_OUT, SF * R_OUT * SE)}{ell(cx, cy, SF * R_IN, SF * R_IN * SE)}" '
                 f'fill="{P["rim_top"]}" fill-rule="evenodd"/>')
    return "\n".join(o)


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


def birds_svg(P, homes, frames, toff, land, rng):
    anim, still = [], []
    for i, (hx, hy, face) in enumerate(homes):
        fr = frames[i]
        white = i in (3, 10)
        fill = P["white_fill"] if white else P["bird_fill"]
        gsym = "#gR" if face > 0 else "#gL"
        psym = "#gRp" if face > 0 else "#gLp"
        hx, hy = round(hx), round(hy)
        homes[i] = (hx, hy, face)
        # flying sprite: waits below the card, rides the sampled flight, goes back below the card
        q = [(hx, OFFCARD)]
        d = f"M{hx} {fm(OFFCARD, 0)}"
        first = True
        for f in range(toff[i] + 1, land[i]):
            nx, ny = round(fr[f][0]), round(fr[f][1])
            d += f"L{nx} {ny}" if first else f"l{nx - q[-1][0]} {ny - q[-1][1]}"
            first = False
            q.append((nx, ny))
        d += f"L{hx} {fm(OFFCARD, 0)}"
        q.append((hx, OFFCARD))
        cum = [0.0]
        for a, b in zip(q, q[1:]):
            cum.append(cum[-1] + math.dist(a, b))
        total = cum[-1]
        kps, kts = ["0"], ["0"]
        for idx, f in enumerate(range(toff[i] + 1, land[i])):
            L = max(0.0, cum[idx + 1] - 0.3)            # just before the vertex: heading = last frame's motion
            kps.append(fm(L / total, 4))
            kts.append(fm(f / NF, 4))
        kps.append("1")
        kts.append(fm(land[i] / NF, 4))
        flap = filmstrip(['<use href="#w1"/>', '<use href="#w0"/>', '<use href="#w2"/>', '<use href="#w3"/>'], 0.2,
                         begin=(i % 4) * 0.05)
        anim.append(f'<g fill="{fill}"><animateMotion path="{d}" keyPoints="{";".join(kps)}" keyTimes="{";".join(kts)}" '
                    f'dur="12s" calcMode="discrete" rotate="auto" repeatCount="indefinite"/>{flap}</g>')
        # ground sprite: stand (0), peck (2000 away), or away while flying
        seq = ["s"] * NF
        for f in range(toff[i] + 1, land[i]):
            seq[f] = "a"
        ground = [f for f in range(NF) if seq[f] == "s" and (f < toff[i] - 4 or f > land[i] + 3)]
        for _ in range(3):
            f0 = rng.choice(ground)
            for f in range(f0, f0 + 4):
                if f in ground:
                    seq[f] = "p"
        OFF = {"s": "0 0", "p": "0 -2000", "a": "0 5000"}
        vals, keys = [], []
        for f in range(NF):
            if f == 0 or seq[f] != seq[f - 1]:
                vals.append(OFF[seq[f]])
                keys.append(fm(f / NF, 4))
        anim.append(f'<g transform="translate({hx} {hy})"><g><animateTransform attributeName="transform" type="translate" '
                    f'values="{";".join(vals)}" keyTimes="{";".join(keys)}" dur="12s" calcMode="discrete" repeatCount="indefinite"/>'
                    f'<use href="{gsym}"/><use href="{psym}" y="2000"/></g></g>')
        still.append(f'<use href="{gsym}" transform="translate({hx} {hy})"/>')
    return "\n".join(anim), "\n".join(still)


def bird_positions_from_svg(svg_birds):
    """Re-derive every bird's position per frame from the emitted path/keyPoints/keyTimes (as the browser does)."""
    out = []
    for m in re.finditer(r'<animateMotion path="([^"]+)" keyPoints="([^"]+)" keyTimes="([^"]+)"', svg_birds):
        d, kp, ktm = m.group(1), [float(v) for v in m.group(2).split(";")], [float(v) for v in m.group(3).split(";")]
        toks = re.findall(r"[MLl]|-?\d*\.?\d+", d)
        pts, i, cur, cmd = [], 0, (0.0, 0.0), None
        while i < len(toks):
            if toks[i] in "MLl":
                cmd = toks[i]
                i += 1
            x, y = float(toks[i]), float(toks[i + 1])
            i += 2
            cur = (cur[0] + x, cur[1] + y) if cmd == "l" else (x, y)
            pts.append(cur)
        cum = [0.0]
        for a, b in zip(pts, pts[1:]):
            cum.append(cum[-1] + math.dist(a, b))
        tot = cum[-1]

        def at(frac):
            L = frac * tot
            for j in range(1, len(cum)):
                if cum[j] >= L - 1e-9:
                    s = 0 if cum[j] == cum[j - 1] else (L - cum[j - 1]) / (cum[j] - cum[j - 1])
                    return (lerp(pts[j - 1][0], pts[j][0], s), lerp(pts[j - 1][1], pts[j][1], s))
            return pts[-1]
        track = []
        for f in range(NF):
            tt = (f + 0.5) / NF
            k = max(j for j in range(len(ktm)) if ktm[j] <= tt)
            track.append(at(kp[k]))
        out.append(track)
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
    for L, tr in zip(LEAVES, tracks):
        pts = tr["pts"]
        n = len(pts)
        start = L["start"]
        d = f"M{pp(pts[0][0], pts[0][1])}"
        q = [(round(pts[0][0]), round(pts[0][1]))]
        d = f"M{q[0][0]} {q[0][1]}"
        for x, y, _ in pts[1:]:
            nx, ny = round(x), round(y)
            d += f"l{nx - q[-1][0]} {ny - q[-1][1]}"
            q.append((nx, ny))
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
        kps, kts, rots, rkts = [], [], [], []
        prev = None
        for f in range(NF):
            k = 0 if hold_start[f] else idx[f]
            if k != prev:
                kps.append(fm(cum[k] / tot, 4))
                kts.append(fm(f / NF, 4))
                rots.append(fm(pts[k][2] + 8, 0))
                prev = k
        lc = P["leaf"][L["col"]]
        anim.append(f'<g><animateMotion path="{d}" keyPoints="{";".join(kps)}" keyTimes="{";".join(kts)}" dur="12s" '
                    f'calcMode="discrete" repeatCount="indefinite"/>'
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
            col = P["leaf"][rng.choice((0, 0, 1, 1, 2, 3))]
            leaves.setdefault(col, []).append(xform_path(LEAF_D, x, y, ang, sc))
    for col, ds in leaves.items():
        o.append(f'<path d="{"".join(ds)}" fill="{col}"/>')
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
             f'aria-label="Rohan Malhotra. Washington Square Park and its arch, with the fountain and a flock of pigeons.">')
    o.append("<title>Rohan Malhotra</title>")
    css = (f".r0,.r1{{fill:none;stroke:{P['ripple']};stroke-width:1.3}}.r0{{opacity:.8}}.r1{{opacity:.38}}"
           f".cf{{fill:{P['foam']};opacity:.9}}"
           + "".join(f".d{k}{{fill:none;stroke:{P['drop']};stroke-width:{w};stroke-linecap:round}}"
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
    if P["stars"]:
        srng = random.Random(7)
        st = []
        for _ in range(46):
            x, y = srng.uniform(20, 1580), srng.uniform(14, 300)
            if x < 1000 and 50 < y < 170:
                continue
            st.append(circ(x, y, srng.choice((0.9, 1.1, 1.4))))
        o.append(f'<path d="{"".join(st)}" fill="#E9E4D3" opacity=".7"/>')
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
    o.append(lamps_svg(P, front=False))
    o.append(people_svg(P, which={0}))
    # fountain
    o.append(fountain_static(P, "back"))
    streams = jets()
    ring = streams[0]
    assert len({st["pf"] for st in streams}) == 1      # every stream repeats on the same 6-frame pattern
    PF = ring["pf"]
    rip, lands = ripple_frames(ring, 2)
    o.append(fountain_static(P, "coping"))
    all_tracks = []
    core_fr, foam = plume_core_frames(P)
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
        layers[layer] = (statics, per_frame)
    far_frames = [f'<g><path d="{rip[0][k]}" class="r0"/><path d="{rip[1][k]}" class="r1"/>{"".join(layers["far"][1][k])}</g>'
                  for k in range(PF)]
    near_frames = [f'<g><path d="{core_fr[k]}" class="cf"/>{"".join(layers["near"][1][k])}</g>' for k in range(PF)]
    dur = PF / FPS
    o.append("".join(layers["far"][0]))
    o.append(f'<g class="anim">{filmstrip(far_frames, dur)}</g><g class="still"><path d="{rip[0][2]}" class="r0"/></g>')
    o.append(f'<path d="{foam}" fill="{P["foam"]}"/>')
    o.append(f'<g class="anim">{filmstrip(near_frames, dur)}</g><g class="still">{near_frames[2]}</g>')
    o.append("".join(layers["near"][0]))
    o.append(people_svg(P, which={1, 2, 3}))
    o.append(lamps_svg(P, front=True))
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
