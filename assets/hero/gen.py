#!/usr/bin/env python3
"""
The hero image at the top of github.com/rohanmalhotra0.

A Spot-style quadruped trots on a scrolling ruler, carrying a dog toy in its gripper.

Everything moving is computed here, then baked into CSS @keyframes (no JavaScript, no SMIL):
  * a trot gait: diagonal pairs in phase, duty factor 0.6, cycloidal swing trajectories
    (zero foot velocity relative to the ground at lift-off and touch-down);
  * closed-form 2-link inverse kinematics for every leg at every sample (knees point aft);
  * body bob (2x gait frequency) and a slight pitch;
  * arm IK that holds the gripper fixed in space while the body moves under it;
  * a ruler that scrolls at exactly the stance-foot speed, so planted feet never slide.

The SVG geometry itself is the standing pose, and the keyframes rotate each joint away from it
(static translate on a parent <g>, CSS rotate about the local origin on the child). With animations
off (prefers-reduced-motion, or a renderer that ignores CSS animation) the robot simply stands,
holding the toy. Every animation has the gait period, so the loop is seamless.

All text is converted to outlines (Hubot Sans Wide ExtraBold, Mona Sans) by textpath.py.
No fonts, scripts, SMIL, filters or external references.

usage: pip install -r requirements.txt && python3 gen.py [--out DIR] [--check] [--palette overrides.json]
Writes hero-dark.svg and hero-light.svg into assets/ by default.
"""
import argparse
import json
import math
import os

from fontTools.pens.boundsPen import BoundsPen
from fontTools.svgLib.path import parse_path

from textpath import font, text_path

HERE = os.path.dirname(os.path.abspath(__file__))

# ---------------------------------------------------------------- palette (his site, v2)
PALETTES = {
    "light": dict(card="#f3f2ee", edge=None, ink="#141414", muted="#55554f", strong="#c4c3bc",
                  tick="#b4b3ac", far="#a6a59f", cut="#f3f2ee", accent="#ff5b14", page="#ffffff"),
    "dark": dict(card="#0e0e0d", edge="#262624", ink="#ecebe6", muted="#a3a29b", strong="#4a4a46",
                 tick="#4a4a46", far="#62615c", cut="#0e0e0d", accent="#ff6a2b", page="#0d1117"),
}

# ---------------------------------------------------------------- layout (viewBox units)
W, H = 1600, 600
LAYOUT = dict(
    margin_x=104,
    name_size=132, name_lead=0.955, name_track=-0.025,
    tag_gap=70,              # baseline of "Malhotra" to baseline of the tagline
    ground_y=432,            # robot stands on the baseline of "Malhotra"
    robot_right=1528,        # right edge of the robot over the whole gait (aligns with the ruler end)
    ruler_gap=92, ruler_margin=72,
    facing=-1,               # -1: robot faces left (towards the name), +1: faces right
    tagline="Applied AI, quantitative systems, and robotics.",
)

# ---------------------------------------------------------------- robot, in metres (his site's model)
R = dict(
    S=352.0,                 # units per metre
    h0=0.53,                 # hip height at rest
    L1=0.32, L2=0.335,       # upper / lower leg
    hip_x=0.372,             # hips at +-hip_x from body centre
    rf=0.030,                # foot radius
    body_len=1.10,
    arm_L1=0.33, arm_L2=0.36,
)
GAIT = dict(
    T=1.30,                  # gait cycle, seconds
    N=50,                    # samples per cycle (2% keyframe steps)
    duty=0.60,               # stance fraction
    stride=0.27,             # stance stroke, m
    lift=0.068,              # swing apex, m
    bob=0.012,               # body bob amplitude, m
    pitch=0.5,               # body pitch amplitude, deg
)
# legs: (name, front?, near side?, phase offset). Trot: FL+RR together, FR+RL together.
LEGS = [("fl", True, False, 0.0), ("rl", False, False, 0.5), ("fr", True, True, 0.5), ("rr", False, True, 0.0)]
# rest (standing) foot x offsets from the hip, m: far legs slightly staggered for depth
REST_DX = {"fl": -0.09, "rl": 0.09, "fr": 0.0, "rr": 0.0}
# body section relative to the hip line (y down): hips sit low in the body, like Spot's
BODY = dict(top=-0.150, bot=0.072)
# arm rest pose (body frame, deg; SVG angles: 0 = forward, +90 = down)
ARM = dict(sx=0.31, sy=-0.196, a1=-42.0, a2=38.0, g=34.0)


def fnum(v, nd=2):
    s = f"{v:.{nd}f}".rstrip("0").rstrip(".")
    return "0" if s in ("-0", "", "-") else s


# ---------------------------------------------------------------- kinematics
def ik2(hx, hy, fx, fy, L1, L2, bend):
    """Planar 2-link IK. Angles are SVG angles (y down). bend=+1 rotates the first link
    clockwise from the target line (knee aft for a leg facing +x), -1 counter-clockwise."""
    dx, dy = fx - hx, fy - hy
    d = min(math.hypot(dx, dy), (L1 + L2) * 0.9999)
    phi = math.atan2(dy, dx)
    a = math.acos(max(-1.0, min(1.0, (L1 * L1 + d * d - L2 * L2) / (2 * L1 * d))))
    t1 = phi + bend * a
    kx, ky = hx + L1 * math.cos(t1), hy + L1 * math.sin(t1)
    t2 = math.atan2(fy - ky, fx - kx)
    return t1, t2


def foot_track(phi):
    """Foot centre relative to its neutral point, camera frame (moves with the body).
    Returns (dx, height) in metres. Stance: straight line at constant speed.
    Swing: cycloid in the world frame, so foot speed relative to ground is 0 at both ends."""
    D, b, h = GAIT["stride"], GAIT["duty"], GAIT["lift"]
    if phi < b:
        return D / 2 - D * (phi / b), 0.0
    s = (phi - b) / (1 - b)
    x = -D / 2 + D * s - (D / b) * math.sin(2 * math.pi * s) / (2 * math.pi)
    return x, h * (1 - math.cos(2 * math.pi * s)) / 2


def body_motion(u):
    """u: cycle fraction. Body highest at mid-stance of each diagonal pair (u = 0.3, 0.8)."""
    w = 2 * math.pi * 2 * (u - 0.30)
    return -GAIT["bob"] * math.cos(w), GAIT["pitch"] * math.sin(w)   # (dy m, y down), deg


def rot(x, y, deg):
    c, s = math.cos(math.radians(deg)), math.sin(math.radians(deg))
    return c * x - s * y, s * x + c * y


def cam_to_body(x, y, dy, p):
    """Camera frame (origin on the ground under the body centre) -> body-centre frame."""
    return rot(x, y - (-R["h0"] + dy), -p)


def rest_pose():
    rp = {}
    for name, front, near, off in LEGS:
        hx = R["hip_x"] * (1 if front else -1)
        fx, fy = hx + REST_DX[name], R["h0"] - R["rf"]
        t1, t2 = ik2(hx, 0.0, fx, fy, R["L1"], R["L2"], +1)
        rp[name] = (hx, t1, t2)
    a1, a2 = math.radians(ARM["a1"]), math.radians(ARM["a2"])
    ex, ey = ARM["sx"] + R["arm_L1"] * math.cos(a1), ARM["sy"] + R["arm_L1"] * math.sin(a1)
    wx, wy = ex + R["arm_L2"] * math.cos(a2), ey + R["arm_L2"] * math.sin(a2)
    rp["arm"] = dict(a1=a1, a2=a2, e=(ex, ey), w=(wx, wy), g=math.radians(ARM["g"]))
    return rp


def solve(rp):
    """Sample the gait. Returns dict of per-joint keyframe values (deg deltas from rest)."""
    N = GAIT["N"]
    out = {k: [] for k in ["bd"] + [f"{n}{j}" for n, *_ in LEGS for j in "hk"] + ["a1", "a2", "a3"]}
    arm = rp["arm"]
    w_cam = (arm["w"][0], arm["w"][1] - R["h0"])          # wrist target, fixed in camera frame
    for k in range(N + 1):
        u = (k % N) / N
        dy, p = body_motion(u)
        out["bd"].append((dy * R["S"], p))
        for name, front, near, off in LEGS:
            hx, t1r, t2r = rp[name]
            ddx, hgt = foot_track((u + off) % 1.0)
            fxb, fyb = cam_to_body(hx + ddx, -(R["rf"] + hgt), dy, p)
            t1, t2 = ik2(hx, 0.0, fxb, fyb, R["L1"], R["L2"], +1)
            out[name + "h"].append(math.degrees(t1 - t1r))
            out[name + "k"].append(math.degrees((t2 - t1) - (t2r - t1r)))
        wxb, wyb = cam_to_body(w_cam[0], w_cam[1], dy, p)
        b1, b2 = ik2(ARM["sx"], ARM["sy"], wxb, wyb, R["arm_L1"], R["arm_L2"], -1)
        gb = arm["g"] - math.radians(p)                    # gripper keeps its world angle
        out["a1"].append(math.degrees(b1 - arm["a1"]))
        out["a2"].append(math.degrees((b2 - b1) - (arm["a2"] - arm["a1"])))
        out["a3"].append(math.degrees((gb - b2) - (arm["g"] - arm["a2"])))
    return out


# ---------------------------------------------------------------- self-check (simulates CSS linear interpolation)
def check(rp, kf):
    S, N, T = R["S"], GAIT["N"], GAIT["T"]
    v = GAIT["stride"] / GAIT["duty"] * S          # units per cycle
    rnd = lambda a: [float(fnum(x)) for x in a]
    tracks = {k: rnd(vals) for k, vals in kf.items() if k != "bd"}
    bdy = [(float(fnum(a)), float(fnum(b))) for a, b in kf["bd"]]

    def interp(arr, u):
        x = u * N
        i = min(int(x), N - 1)
        f = x - i
        return arr[i] + (arr[i + 1] - arr[i]) * f

    def fk(name, u):
        hx, t1r, t2r = rp[name]
        kxr, kyr = R["L1"] * math.cos(t1r), R["L1"] * math.sin(t1r)
        fxr, fyr = R["L2"] * math.cos(t2r), R["L2"] * math.sin(t2r)
        dh, dk = interp(tracks[name + "h"], u), interp(tracks[name + "k"], u)
        lx, ly = rot(fxr, fyr, dk)
        lx, ly = rot(kxr + lx, kyr + ly, dh)
        bx, by = hx * S + lx * S, 0 + ly * S
        dyu = interp([b[0] for b in bdy], u)
        pp = interp([b[1] for b in bdy], u)
        cx, cy = rot(bx, by, pp)
        return cx, cy + (-R["h0"] * S + dyu)

    worst_x = worst_y = 0.0
    for name, front, near, off in LEGS:
        # touchdown at leg phase 0, i.e. cycle u0 = -off
        u0 = (-off) % 1.0
        x0, _ = fk(name, u0)
        M = 400
        for j in range(M + 1):
            ph = GAIT["duty"] * j / M
            u = (u0 + ph) % 1.0
            x, y = fk(name, u)
            want = x0 - v * ph
            worst_x = max(worst_x, abs(x - want))
            worst_y = max(worst_y, abs(y - (-R["rf"] * S)))
    # wrist / toy stillness
    arm = rp["arm"]
    wx_r, wy_r = arm["w"][0] * S, (arm["w"][1] - R["h0"]) * S
    worst_w = 0.0
    for j in range(401):
        u = j / 400
        a1 = arm["a1"] + math.radians(interp(tracks["a1"], u))
        a2 = arm["a2"] + math.radians(interp(tracks["a1"], u) + interp(tracks["a2"], u))
        ex, ey = ARM["sx"] * S + R["arm_L1"] * S * math.cos(a1), ARM["sy"] * S + R["arm_L1"] * S * math.sin(a1)
        wx, wy = ex + R["arm_L2"] * S * math.cos(a2), ey + R["arm_L2"] * S * math.sin(a2)
        dyu = interp([b[0] for b in bdy], u)
        pp = interp([b[1] for b in bdy], u)
        cx, cy = rot(wx, wy, pp)
        worst_w = max(worst_w, math.hypot(cx - wx_r, cy - R["h0"] * S + dyu - wy_r))
    px = 830 / W
    print(f"stance slip  max |dx| {worst_x:.4f} u ({worst_x * px:.4f} px @830)  max |dy| {worst_y:.4f} u")
    print(f"wrist drift  max {worst_w:.4f} u ({worst_w * px:.4f} px @830)")
    print(f"ground speed {v / T:.2f} u/s ({v / T * px:.1f} px/s @830), {GAIT['stride'] / GAIT['duty'] / T:.3f} m/s")


# ---------------------------------------------------------------- drawing helpers (metres in, units out)
def U(v):
    return v * R["S"]


def P(x, y):
    return f"{fnum(U(x))} {fnum(U(y))}"


def hull(c1, r1, c2, r2):
    """Outer tangent hull of two circles: a tapered link."""
    (x1, y1), (x2, y2) = c1, c2
    dx, dy = x2 - x1, y2 - y1
    d = math.hypot(dx, dy)
    ux, uy = dx / d, dy / d
    px_, py_ = -uy, ux
    cpsi = (r1 - r2) / d
    spsi = math.sqrt(max(0.0, 1 - cpsi * cpsi))
    n1 = (cpsi * ux + spsi * px_, cpsi * uy + spsi * py_)
    n2 = (cpsi * ux - spsi * px_, cpsi * uy - spsi * py_)
    a = (x1 + r1 * n1[0], y1 + r1 * n1[1])
    b = (x2 + r2 * n1[0], y2 + r2 * n1[1])
    c = (x2 + r2 * n2[0], y2 + r2 * n2[1])
    e = (x1 + r1 * n2[0], y1 + r1 * n2[1])
    return (f"M{P(*a)}L{P(*b)}A{fnum(U(r2))} {fnum(U(r2))} 0 0 0 {P(*c)}"
            f"L{P(*e)}A{fnum(U(r1))} {fnum(U(r1))} 0 1 0 {P(*a)}Z")


def circ(cx, cy, r):
    """Circle as a path (two arcs) so it can join other subpaths."""
    return (f"M{P(cx - r, cy)}A{fnum(U(r))} {fnum(U(r))} 0 1 0 {P(cx + r, cy)}"
            f"A{fnum(U(r))} {fnum(U(r))} 0 1 0 {P(cx - r, cy)}Z")


def rounded(points, radii):
    """Closed polygon with rounded corners (quadratic fillets)."""
    n = len(points)
    segs = []
    for i in range(n):
        p0, p1, p2 = points[i - 1], points[i], points[(i + 1) % n]
        r = radii[i] if isinstance(radii, (list, tuple)) else radii
        v1 = (p0[0] - p1[0], p0[1] - p1[1])
        v2 = (p2[0] - p1[0], p2[1] - p1[1])
        l1, l2 = math.hypot(*v1), math.hypot(*v2)
        r1, r2 = min(r, l1 / 2), min(r, l2 / 2)
        a = (p1[0] + v1[0] / l1 * r1, p1[1] + v1[1] / l1 * r1)
        b = (p1[0] + v2[0] / l2 * r2, p1[1] + v2[1] / l2 * r2)
        segs.append((a, p1, b))
    d = f"M{P(*segs[0][2])}"
    for i in range(1, n + 1):
        a, c, b = segs[i % n]
        d += f"L{P(*a)}Q{P(*c)} {P(*b)}"
    return d + "Z"


def line(x1, y1, x2, y2):
    return f"M{P(x1, y1)}L{P(x2, y2)}"


# ---------------------------------------------------------------- robot drawing
def draw_leg(name, rp, near, c):
    hx, t1r, t2r = rp[name]
    kx, ky = R["L1"] * math.cos(t1r), R["L1"] * math.sin(t1r)          # knee rel. hip
    fx, fy = R["L2"] * math.cos(t2r), R["L2"] * math.sin(t2r)          # foot rel. knee
    fill = c["ink"] if near else c["far"]
    lower = hull((0, 0), 0.030, (fx, fy), 0.019) + circ(fx, fy, R["rf"])
    upper = hull((0, 0), 0.060, (kx, ky), 0.040) + circ(0, 0, 0.064) + circ(kx, ky, 0.041)
    halo = f' stroke="{c["cut"]}" stroke-width="5" paint-order="stroke" stroke-linejoin="round"' if near else ""
    det = ""
    if near:
        det = (f'<path d="{circ(0, 0, 0.030)}{circ(kx, ky, 0.014)}" fill="none" stroke="{c["cut"]}" '
               f'stroke-width="1.5"/>')
    return (f'<g transform="translate({fnum(U(hx))},0)"><g class="j {name}h">'
            f'<g transform="translate({fnum(U(kx))},{fnum(U(ky))})"><g class="j {name}k">'
            f'<path d="{lower}" fill="{fill}"/></g></g>'
            f'<path d="{upper}" fill="{fill}"{halo}/>{det}</g></g>')


def draw_body(c):
    L = R["body_len"] / 2
    top, bot = BODY["top"], BODY["bot"]
    pts = [(-L + 0.035, top), (L - 0.06, top), (L + 0.008, top + 0.064), (L - 0.035, bot - 0.004),
           (-L + 0.05, bot), (-L - 0.004, bot - 0.065), (-L - 0.004, top + 0.03)]
    body = rounded(pts, [0.03, 0.045, 0.03, 0.03, 0.035, 0.02, 0.03])
    # hairline details: shell seam, front face panel, rear face panel
    seam = top + 0.082
    det = (line(-L + 0.07, seam, L - 0.10, seam)
           + line(-L + 0.04, bot - 0.05, -L + 0.034, top + 0.05))
    # front camera window on the sloped face
    det += rounded([(L - 0.018, top + 0.078), (L - 0.050, bot - 0.022), (L - 0.074, bot - 0.026), (L - 0.044, top + 0.074)], 0.008)
    return (f'<path d="{body}" fill="{c["ink"]}"/>'
            f'<path d="{det}" fill="none" stroke="{c["cut"]}" stroke-width="1.5" stroke-linecap="round"/>')


def grip_geom(rp):
    """Gripper frame helpers: s along the gripper axis, n across it (wrist-relative, metres)."""
    g = rp["arm"]["g"]
    ug = (math.cos(g), math.sin(g))
    ng = (-ug[1], ug[0])
    return lambda s_, n_: (ug[0] * s_ + ng[0] * n_, ug[1] * s_ + ng[1] * n_)


BALL_R = 0.042
BALL_S = 0.158            # ball centre along the gripper axis, from the wrist


def draw_arm(rp, c):
    arm = rp["arm"]
    sx, sy = ARM["sx"], ARM["sy"]
    ex, ey = arm["e"][0] - sx, arm["e"][1] - sy                       # elbow rel. shoulder
    wx, wy = arm["w"][0] - arm["e"][0], arm["w"][1] - arm["e"][1]     # wrist rel. elbow
    at = grip_geom(rp)
    t = BODY["top"]
    base = rounded([(sx - 0.10, t + 0.008), (sx - 0.068, sy - 0.006), (sx + 0.068, sy - 0.006), (sx + 0.10, t + 0.008)], 0.022)
    upper = hull((0, 0), 0.043, (ex, ey), 0.034)
    fore = hull((0, 0), 0.032, (wx, wy), 0.027)
    # gripper: a short block, two tapered fingers tangent to the toy
    grip = hull((0, 0), 0.034, at(0.084, 0), 0.031)
    for sg in (1, -1):
        b0, m0, t0 = at(0.096, sg * 0.036), at(BALL_S, sg * 0.0505), at(BALL_S + 0.046, sg * 0.033)
        grip += hull(b0, 0.0125, m0, 0.0095) + hull(m0, 0.0095, t0, 0.0072)
    bc = at(BALL_S, 0.0)
    halo = f' stroke="{c["cut"]}" stroke-width="5" paint-order="stroke" stroke-linejoin="round"'
    ring = lambda r: f'<path d="{circ(0, 0, r)}" fill="none" stroke="{c["cut"]}" stroke-width="1.5"/>'
    joint = lambda x, y, r, ri: (f'<g transform="translate({fnum(U(x))},{fnum(U(y))})">'
                                 f'<path d="{circ(0, 0, r)}" fill="{c["ink"]}"{halo}/>{ring(ri)}</g>')
    return (f'<path d="{base}" fill="{c["ink"]}"/>'
            f'<g transform="translate({fnum(U(sx))},{fnum(U(sy))})"><g class="j a1">'
            f'<g transform="translate({fnum(U(ex))},{fnum(U(ey))})"><g class="j a2">'
            f'<g transform="translate({fnum(U(wx))},{fnum(U(wy))})"><g class="j a3">'
            f'<circle cx="{fnum(U(bc[0]))}" cy="{fnum(U(bc[1]))}" r="{fnum(U(BALL_R))}" fill="{c["accent"]}"/>'
            f'<path d="{grip}" fill="{c["ink"]}"/>'
            f'</g></g>'
            f'<path d="{fore}" fill="{c["ink"]}"{halo}/>'
            f'{joint(wx, wy, 0.035, 0.013)}'
            f'</g></g>'
            f'<path d="{upper}" fill="{c["ink"]}"{halo}/>'
            f'{joint(ex, ey, 0.040, 0.016)}'
            f'</g></g>'
            f'{joint(sx, sy, 0.050, 0.021)}')


def draw_ground(c, x0, x1):
    """Ruler in the robot frame (forward = +x). Ticks scroll one period per gait cycle."""
    period = GAIT["stride"] / GAIT["duty"]           # metres travelled per cycle
    n_per = 5
    step = period / n_per
    ticks = ""
    i0 = int(math.floor(x0 / step)) - 1
    i1 = int(math.ceil((x1 + period) / step)) + 1
    for i in range(i0, i1 + 1):
        major = (i % n_per == 0)
        ticks += f"M{fnum(U(i * step))} 5V{15 if major else 10}"
    clip = f'<clipPath id="gc"><rect x="{fnum(U(x0))}" y="0" width="{fnum(U(x1 - x0))}" height="24"/></clipPath>'
    return clip, (f'<g clip-path="url(#gc)"><g class="j gr"><path d="{ticks}" stroke="{c["tick"]}" stroke-width="1.5"/></g></g>'
                  f'<path d="M{fnum(U(x0))} 0H{fnum(U(x1))}" stroke="{c["strong"]}" stroke-width="1.5"/>')


def robot_extent(rp):
    """(rear, front) x extents of the robot in metres over the whole gait cycle (and at rest)."""
    xs = [-R["body_len"] / 2 - 0.01, R["body_len"] / 2 + 0.01]
    for name, front, near, off in LEGS:
        hx, t1r, t2r = rp[name]
        xs += [hx + R["L1"] * math.cos(t1r) - 0.041, hx + R["L1"] * math.cos(t1r) + 0.041]
        for k in range(GAIT["N"]):
            ddx, hgt = foot_track((k / GAIT["N"] + off) % 1.0)
            t1, _ = ik2(hx, 0.0, hx + ddx, R["h0"] - R["rf"] - hgt, R["L1"], R["L2"], +1)
            kx = hx + R["L1"] * math.cos(t1)
            xs += [kx - 0.041, kx + 0.041, hx + ddx - R["rf"], hx + ddx + R["rf"]]
    at = grip_geom(rp)
    bc = at(BALL_S, 0.0)
    xs.append(rp["arm"]["w"][0] + bc[0] + BALL_R)
    xs.append(rp["arm"]["e"][0] + 0.048)
    return min(xs), max(xs)


def draw_robot(rp, c):
    legs_far = "".join(draw_leg(n, rp, False, c) for n, f, near, o in LEGS if not near)
    legs_near = "".join(draw_leg(n, rp, True, c) for n, f, near, o in LEGS if near)
    return (f'<g transform="translate(0,{fnum(-U(R["h0"]))})"><g class="j bd">'
            f'{legs_far}{draw_body(c)}{draw_arm(rp, c)}{legs_near}</g></g>')


# ---------------------------------------------------------------- type
def ink_bounds(d):
    """Exact ink bounds of SVG path data (xmin, ymin, xmax, ymax)."""
    bp = BoundsPen(None)
    parse_path(d, bp)
    return bp.bounds


def set_line(text, font, size, x_ink, y, tracking=0.0):
    """Outline `text` with its left ink edge exactly at x_ink. Returns (d, ink_bounds)."""
    d0, _ = text_path(text, font, size, 0, y, tracking)
    x0 = ink_bounds(d0)[0]
    d, _ = text_path(text, font, size, x_ink - x0, y, tracking)
    return d, ink_bounds(d)


def draw_type(c):
    L = LAYOUT
    s = L["name_size"]
    y2 = L["ground_y"]
    y1 = y2 - s * L["name_lead"]
    x = L["margin_x"]
    name_font, text_font = font("hubot-sans", 125, 800), font("mona-sans", 100, 400)
    d1, _ = set_line("Rohan", name_font, s, x, y1, L["name_track"])
    d2, b2 = set_line("Malhotra", name_font, s, x, y2, L["name_track"])
    # the tagline is set to the measure of the surname: same left and right ink edges
    _, bt = set_line(L["tagline"], text_font, 100, x, 0)
    ts = 100 * (b2[2] - b2[0]) / (bt[2] - bt[0])
    d3, _ = set_line(L["tagline"], text_font, ts, x, y2 + L["tag_gap"])
    return (f'<path d="{d1}{d2}" fill="{c["ink"]}"/>'
            f'<path d="{d3}" fill="{c["muted"]}"/>'), b2[2]


# ---------------------------------------------------------------- css
def keyframes(name, vals, fmt):
    N = len(vals) - 1
    body = "".join(f"{fnum(100 * k / N, 3)}%{{transform:{fmt(v)}}}" for k, v in enumerate(vals))
    return f"@keyframes {name}{{{body}}}"


def css(kf):
    T = GAIT["T"]
    rules = [f".j{{transform-box:view-box;transform-origin:0 0;animation:{fnum(T, 3)}s linear infinite}}"]
    frames = []
    for key, vals in kf.items():
        if key == "bd":
            fmt = lambda v: f"translate(0,{fnum(v[0])}px) rotate({fnum(v[1])}deg)"
        else:
            fmt = lambda v: f"rotate({fnum(v)}deg)"
        rules.append(f".{key}{{animation-name:{key}}}")
        frames.append(keyframes(key, vals, fmt))
    period_u = U(GAIT["stride"] / GAIT["duty"])
    rules.append(".gr{animation-name:gr}")
    frames.append(f"@keyframes gr{{0%{{transform:translate(0,0)}}100%{{transform:translate({fnum(-period_u)}px,0)}}}}")
    rules.append("@media (prefers-reduced-motion:reduce){*{animation:none!important}}")
    return "".join(rules) + "".join(frames)


# ---------------------------------------------------------------- assemble
def build(theme, rp, kf):
    c = PALETTES[theme]
    L = LAYOUT
    type_svg, name_right = draw_type(c)
    rear, front = robot_extent(rp)
    f = L["facing"]
    ox = L["robot_right"] + U(rear) if f < 0 else L["robot_right"] - U(front)
    sx0, sx1 = name_right + L["ruler_gap"], W - L["ruler_margin"]      # ruler window, screen x
    lx0, lx1 = sorted(((sx0 - ox) * f / R["S"], (sx1 - ox) * f / R["S"]))
    clip, ground = draw_ground(c, lx0, lx1)
    mirror = " scale(-1,1)" if f < 0 else ""
    edge = ""
    if c["edge"]:
        edge = f' stroke="{c["edge"]}" stroke-width="2"'
    svg = (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="{W}" height="{H}" '
           f'role="img" aria-labelledby="t"><title id="t">Rohan Malhotra</title>'
           f'<desc>A Spot-style robot trots along a ruler, carrying an orange ball in its gripper.</desc>'
           f'<style>{css(kf)}</style><defs>{clip}</defs>'
           f'<rect x="1" y="1" width="{W - 2}" height="{H - 2}" rx="16" fill="{c["card"]}"{edge}/>'
           f'{type_svg}'
           f'<g transform="translate({fnum(ox)},{fnum(L["ground_y"])}){mirror}">{ground}{draw_robot(rp, c)}</g>'
           f'</svg>')
    return svg, name_right, ox


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default=os.path.dirname(HERE))
    ap.add_argument("--check", action="store_true", help="print planting / stabilisation error of the baked keyframes")
    ap.add_argument("--palette", help='JSON file overriding colours, e.g. {"light": {"accent": "#0a66c2"}}')
    a = ap.parse_args()
    if a.palette:
        with open(a.palette) as fh:
            for theme, over in json.load(fh).items():
                PALETTES[theme].update(over)
    rp = rest_pose()
    kf = solve(rp)
    if a.check:
        check(rp, kf)
    for theme in ("dark", "light"):
        svg, nr, ox = build(theme, rp, kf)
        p = os.path.join(a.out, f"hero-{theme}.svg")
        with open(p, "w") as fh:
            fh.write(svg)
        print(p, len(svg.encode()), "bytes", f"name right edge {nr:.0f}, robot origin x {ox:.0f}")


if __name__ == "__main__":
    main()
