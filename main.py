#!/usr/bin/env python3
"""GTA VI trophy-rarity forecast, v5 (stdlib only).

Forecasts, for each of the 55 GTA VI PS5 trophies, five quantiles of its
Exophase earn rate (%) at the case target.

Two branches, chosen by horizon + history shape:

* Refresh branch (horizon <= 0.5 d and the history is one flat page):
  the launch-night page (638 players) is stale; Exophase refreshes it to
  3,868 players and earners grow by a per-trophy factor g_i over the
  90 minutes.  Median = round(E_last * g_i / 3868 * 100, 2), where
  E_last = round(last_rate / 100 * N_last) is the earner count recovered
  from rate x N (never from any parenthesised count).  Risers
  {3,4,8,20,21,35,46} get g_i = 3.0 * (r_i / 2.7685) ** 0.005, with r_i
  the trophy's 2-day rate ratio (Exophase live 20 Nov 23:02 UTC:
  Ch.1 x9.58, fishing x6.52, Trust x3.87, bowling x1.62, Ch.2 x1.55,
  arcade x1.51, Whip It Good x1.36); every other trophy g_i = 1.0 and
  is diluted by 638 -> 3,868.  Spread is a two-component logit mixture:
  a tight asymmetric component (sigma_up 0.001 / sigma_dn 0.0005,
  weight 0.98) plus a small hedge (weight 0.02, sigma 0.20) centred on
  the uniform-growth rate (g = 1.255).  The 100% intro trophy stays
  at 99.99.

* Growth branch (everything else): earners E(t) and the tracked base
  N(t) are modelled separately (rate = E / N).  Three earner shapes
  (logistic-power, saturating-exponential, persistence-flat) are fit
  per trophy to the running-max-guarded E(t) series by grid + linear
  least squares, residual-weighted; three tracked-base curves scale
  the N knot table (638 -> 3,868 -> 6,315 -> 8,200 at day 7) by
  {0.7, 1.0, 1.5}.  The 9 combinations are combined by a
  residual-weighted geometric mean, then blended with a type prior
  (re-fit from the real 2-day trajectory) with w(h) = 1 / (1 + h/1.2),
  h in days, after prior anchoring.  Spread is lognormal with
  sigma = 0.45 * sqrt(0.10^2 + (0.15*sqrt(h))^2 + sigma_type^2
  + resid^2 + between-family variance), clamped to [0.30, 1.80].

Deterministic (no randomness, no network, no wall-clock dependence),
absolute paths only, stdlib only.
"""

import json
import math
import os
import sys

# ---------------------------------------------------------------- constants

LEVELS = (0.05, 0.25, 0.5, 0.75, 0.95)
Z = (-1.6448536269514722, -0.6744897501960817, 0.0,
     0.6744897501960817, 1.6448536269514722)

# Refresh branch.
N_REFRESH = 3868            # players tracked after the launch-night refresh
N_LAUNCH = 638              # players tracked on the launch-night page
G_BASE = 3.0                # geometric mean of the risers' 90-min growth
G_UNIFORM = 1.255           # hedge centre: uniform-growth hypothesis
RISERS = (3, 4, 8, 20, 21, 35, 46)
# 2-day rate ratios (rate at 20 Nov 23:02 UTC / launch rate), Exophase.
RATE_RATIO_2D = {3: 9.58, 20: 6.52, 8: 3.87, 46: 1.62,
                 4: 1.55, 21: 1.51, 35: 1.36}
_RGEO = math.exp(sum(math.log(v) for v in RATE_RATIO_2D.values())
                 / len(RATE_RATIO_2D))
ALPHA = 0.005               # shrink of the 2-day ranking into 90-min g_i
SIGMA_UP = 0.001            # tight-component logit sigma above the median
SIGMA_DN = 0.0005           # tight-component logit sigma below the median
W_HEDGE = 0.02              # hedge weight in the refresh mixture
SIGMA_HEDGE = 0.20          # hedge logit sigma

# Growth branch.
# Day-7 (target) priors by trophy kind, re-fit from the real 2-day
# trajectory (Ch.1 55%, fishing 40%, Trust 18%, Ch.2 25%, arcade 8%,
# bowling 7%, 100 vehicles 8.5%, mission 3.5%, strand 1.5%, collect
# 0.5%, stunt 0.3%, easy 10%, activity 5%, final 1.2%,
# platinum / 100% gold 0.03%).  Ch.3/Ch.4 (11%/5%) interpolate the
# story decay between Ch.2 (25%) and the final mission (1.2%).
KIND_PRIOR = {
    "platinum": 0.03, "gold100": 0.03, "intro": 100.0,
    "ch1": 55.0, "ch2": 25.0, "ch3": 11.0, "ch4": 5.0, "final": 1.2,
    "trust": 18.0, "mission": 3.5, "strand": 1.5,
    "fishing": 40.0, "arcade": 8.0, "bowling": 7.0, "vehicles": 8.5,
    "collect": 0.5, "stunt": 0.3, "easy": 10.0, "activity": 5.0,
}
# Logit-sigma by kind family (Dahl design: story 0.15, easy/activity/
# collect/stunt 0.30, platinum/gold 0.08).
KIND_SIGMA = {
    "platinum": 0.08, "gold100": 0.08, "intro": 0.08,
    "ch1": 0.15, "ch2": 0.15, "ch3": 0.15, "ch4": 0.15, "final": 0.15,
    "trust": 0.15, "mission": 0.15, "strand": 0.15,
    "fishing": 0.15, "arcade": 0.30, "bowling": 0.30, "vehicles": 0.30,
    "collect": 0.30, "stunt": 0.30, "easy": 0.30, "activity": 0.30,
}
# Fraction of the day-7 prior reached by 48 h, per kind: kind-median of
# (2-day Exophase rate / R7), floored at 0.005.  The 2-day trajectory
# shows fast kinds at 0.07-0.33 of their ceiling by day 2 and slow
# kinds at ~0.005-0.03 -- a single shared progress curve would put the
# anchor systematically off for every kind, so the prior trajectory
# is kind-specific.  Platinum / 100% gold are floored (1 earner is noise).
KIND_F48 = {
    "platinum": 0.10, "gold100": 0.10, "intro": 1.0,
    "ch1": 0.218, "ch2": 0.068, "ch3": 0.005, "ch4": 0.005, "final": 0.017,
    "trust": 0.237, "mission": 0.006, "strand": 0.007,
    "fishing": 0.333, "arcade": 0.178, "bowling": 0.180, "vehicles": 0.200,
    "collect": 0.020, "stunt": 0.033, "easy": 0.005, "activity": 0.005,
}
KIND_BY_ID = {
    1: "platinum", 2: "intro", 3: "ch1", 4: "ch2", 5: "ch3", 6: "ch4",
    7: "final", 8: "trust", 9: "mission", 10: "mission", 11: "mission",
    12: "mission", 13: "mission", 14: "gold100", 15: "stunt",
    16: "activity", 17: "activity", 18: "activity", 19: "activity",
    20: "fishing", 21: "arcade", 22: "strand", 23: "strand",
    24: "strand", 25: "strand", 26: "strand", 27: "strand",
    28: "collect", 29: "collect", 30: "collect", 31: "collect",
    32: "collect", 33: "activity", 34: "easy", 35: "vehicles",
    36: "activity", 37: "easy", 38: "activity", 39: "easy",
    40: "mission", 41: "mission", 42: "collect", 43: "mission",
    44: "easy", 45: "easy", 46: "bowling", 47: "activity",
    48: "activity", 49: "activity", 50: "easy", 51: "activity",
    52: "collect", 53: "easy", 54: "collect", 55: "activity",
}
# Tracked-base knots, hours since the first read: (t, N).
# 638 -> 3,868 (first refresh, ~4.5 h) -> ~6,315 (day 2) -> ~8,200 (day 7).
N_KNOTS = ((0.0, 638.0), (4.5, 3868.0), (48.0, 6315.0), (168.0, 8200.0))
N_SCALES = (0.7, 1.0, 1.5)          # player families (slow/base/fast base)
N_WEIGHTS = (0.25, 0.50, 0.25)
SIGMA_SCALE = 0.45                  # growth-spread scale (v4 re-fit)
W_HORIZON_SCALE = 1.2               # w(h) = 1 / (1 + h / 1.2), h in days


# ---------------------------------------------------------------- helpers

def clamp(x, lo, hi):
    return lo if x < lo else hi if x > hi else x


def logit_pct(x):
    p = clamp(x, 0.01, 99.99) / 100.0
    return math.log(p / (1.0 - p))


def inv_logit_pct(lx):
    if lx >= 0.0:
        return 100.0 / (1.0 + math.exp(-lx))
    e = math.exp(lx)
    return 100.0 * e / (1.0 + e)


def norm_cdf(x):
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def linregress(xs, ys):
    """Least squares y ~ a + b*x. Returns (a, b) or None."""
    n = len(xs)
    if n < 2:
        return None
    mx = sum(xs) / n
    my = sum(ys) / n
    sxx = sum((x - mx) ** 2 for x in xs)
    if sxx <= 1e-12:
        return None
    sxy = sum((x - mx) * (y - my) for x, y in zip(xs, ys))
    b = sxy / sxx
    return (my - b * mx, b)


def parse_time(s):
    """ISO 8601 UTC -> hours since epoch (float). No datetime needed
    beyond a fixed day count; parse manually for determinism."""
    # "2026-11-19T03:00:00Z" (fractional seconds tolerated).
    date, _, clock = s.partition("T")
    y, mo, d = (int(v) for v in date.split("-"))
    clock = clock.rstrip("Z")
    hh, mm, rest = clock.split(":")
    ss = float(rest)
    # Days since 2026-01-01 (2026 is not a leap year).
    mdays = (0, 31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30)
    days = sum(mdays[:mo - 1]) + (d - 1)
    return (days * 24.0 + int(hh) + int(mm) / 60.0 + ss / 3600.0
            + (y - 2026) * 8760.0)


# ---------------------------------------------------------------- refresh

def growth_factor(tid):
    if tid in RATE_RATIO_2D:
        return G_BASE * (RATE_RATIO_2D[tid] / _RGEO) ** ALPHA
    return 1.0


def refresh_row(e_last, tid):
    """Five quantiles for one trophy under the refresh branch."""
    if tid == 2:
        return [99.99, 99.99, 99.99, 99.99, 99.99]
    med_t = round(e_last * growth_factor(tid) / N_REFRESH * 100.0, 2)
    med_h = round(e_last * G_UNIFORM / N_REFRESH * 100.0, 2)
    lt, lh = logit_pct(med_t), logit_pct(med_h)

    def cdf(lx):
        if lx < lt:
            pt = norm_cdf((lx - lt) / SIGMA_DN)
        else:
            pt = norm_cdf((lx - lt) / SIGMA_UP)
        ph = norm_cdf((lx - lh) / SIGMA_HEDGE)
        return (1.0 - W_HEDGE) * pt + W_HEDGE * ph

    lo, hi = lt - 2.0, lt + 2.0
    out = []
    for tau in LEVELS:
        a, b = lo, hi
        for _ in range(80):
            m = 0.5 * (a + b)
            if cdf(m) < tau:
                a = m
            else:
                b = m
        q = inv_logit_pct(0.5 * (a + b))
        out.append(round(clamp(q, 0.01, 99.99), 4))
    for i in range(1, 5):
        if out[i] < out[i - 1]:
            out[i] = out[i - 1]
    return out


# ---------------------------------------------------------------- growth

def n_table(t_hours, scale):
    """Tracked base at t (hours since first read) under one N family:
    log-linear interpolation on the knot table, with the day-7 knot
    scaled; flat beyond the last knot."""
    knots = []
    for t, n in N_KNOTS:
        if t >= 168.0:
            n = N_KNOTS[0][1] + (n - N_KNOTS[0][1]) * scale
        knots.append((t, n))
    if t_hours <= knots[0][0]:
        return knots[0][1]
    for (t0, n0), (t1, n1) in zip(knots, knots[1:]):
        if t_hours <= t1:
            f = (t_hours - t0) / (t1 - t0)
            # Interpolate in log space (base growth is multiplicative).
            return math.exp(math.log(n0) + f * (math.log(n1) - math.log(n0)))
    return knots[-1][1]


def fit_earner_family(shape, ts, es):
    """Fit one earner shape to (t_hours, E) by grid + linear LS.
    Returns (E_at_target_fn, rms_log_resid) or None."""
    pts = [(t, e) for t, e in zip(ts, es) if e > 0]
    if len(pts) < 3:
        return None
    best = None
    if shape == "logistic":
        # E = A / (1 + B exp(-C t)); 1/E linear in exp(-C t).
        for c in (1.0 / 6, 1.0 / 12, 1.0 / 24, 1.0 / 48, 1.0 / 96):
            xs = [math.exp(-c * t) for t, _ in pts]
            ys = [1.0 / e for _, e in pts]
            fit = linregress(xs, ys)
            if fit is None:
                continue
            a, b = fit
            if a <= 1e-9:
                continue
            a_big, b_big = 1.0 / a, b / a
            if b_big < -0.9:
                continue

            def pred(t, a_big=a_big, b_big=b_big, c=c):
                return a_big / (1.0 + b_big * math.exp(-c * t))
            best = _score_fit(best, pred, pts)
    elif shape == "saturating":
        # E = A (1 - exp(-t/tau)) + E0.
        for tau in (6.0, 12.0, 24.0, 48.0, 96.0, 192.0):
            xs = [1.0 - math.exp(-t / tau) for t, _ in pts]
            ys = [e for _, e in pts]
            fit = linregress(xs, ys)
            if fit is None:
                continue
            e0, a_big = fit

            def pred(t, e0=e0, a_big=a_big, tau=tau):
                return e0 + a_big * (1.0 - math.exp(-t / tau))
            best = _score_fit(best, pred, pts)
    elif shape == "flat":
        # E = A + B t exp(-t/tau).
        for tau in (12.0, 24.0, 48.0, 96.0):
            xs = [t * math.exp(-t / tau) for t, _ in pts]
            ys = [e for _, e in pts]
            fit = linregress(xs, ys)
            if fit is None:
                continue
            a_big, b_big = fit

            def pred(t, a_big=a_big, b_big=b_big, tau=tau):
                return a_big + b_big * t * math.exp(-t / tau)
            best = _score_fit(best, pred, pts)
    return best


def _score_fit(best, pred, pts):
    try:
        sq, n = 0.0, 0
        for t, e in pts:
            p = pred(t)
            if p <= 0:
                return best
            sq += (math.log(p / e)) ** 2
            n += 1
        rms = math.sqrt(sq / n) if n else 9.9
    except (ValueError, OverflowError, ZeroDivisionError):
        return best
    if best is None or rms < best[1]:
        return (pred, rms)
    return best


def growth_row(tid, ts, es, ns, t_target, h_days, last_rate):
    """Five quantiles for one trophy under the growth branch."""
    kind = KIND_BY_ID.get(tid, "activity")
    prior_r7 = KIND_PRIOR[kind]
    if last_rate >= 99.99 or kind == "intro":
        return [99.99, 99.99, 99.99, 99.99, 99.99]
    e_last = es[-1] if es else 0.0
    # --- earner-family fits -------------------------------------------
    fams = []
    for shape in ("logistic", "saturating", "flat"):
        got = fit_earner_family(shape, ts, es)
        if got is not None:
            fams.append(got)
    if not fams:
        # No fit possible (too few points): flat earners.
        e_preds = [(lambda t, e=e_last: e, 0.0)]
    else:
        e_preds = fams
    # Residual weights (floor 0.10), as in v2/v3.
    weights = []
    for _, resid in e_preds:
        weights.append(max(0.10, math.exp(-(resid ** 2) / (2 * 0.15 ** 2))))
    resid_mean = sum(w * r for w, (_, r) in zip(weights, e_preds)) / sum(weights)
    # --- 9 combinations ------------------------------------------------
    log_rates, combo_w = [], []
    for (pred, _), w_e in zip(e_preds, weights):
        try:
            e_t = pred(t_target)
        except (ValueError, OverflowError):
            continue
        e_t = max(e_t, e_last)  # earners never decrease (running-max)
        for scale, w_n in zip(N_SCALES, N_WEIGHTS):
            n_t = n_table(t_target, scale)
            if n_t <= 0:
                continue
            rate = clamp(e_t / n_t * 100.0, 0.01, 99.99)
            log_rates.append(math.log(rate))
            combo_w.append(w_e * w_n)
    if not log_rates:
        extrap = max(last_rate, 0.01)
        between_var = 0.0
    else:
        tot = sum(combo_w)
        mean_log = sum(w * v for w, v in zip(combo_w, log_rates)) / tot
        extrap = math.exp(mean_log)
        between_var = min(
            sum(w * (v - mean_log) ** 2 for w, v in zip(combo_w, log_rates)) / tot,
            0.25)
    # --- prior anchoring (earner space) -------------------------------
    # Compare the last observed earner count with the earners the prior
    # trajectory implies at the checkpoint.  Anchoring on earners (not
    # rates) keeps dilution out of the comparison: a rate can fall while
    # earners grow, and a low rate at 48 h mostly means players have
    # not reached the trophy yet, not that the day-7 ceiling is low.
    # u_kind(t): fraction of the day-7 prior reached by t; equals
    # KIND_F48 at 48 h, rises to 1 at 168 h, ~linear before 48 h.
    t_last = ts[-1] if ts else 0.0
    f48 = KIND_F48[kind]
    if t_last <= 48.0:
        u_last = max(f48 * (t_last / 48.0), 0.005)
    else:
        u_last = 1.0 - (1.0 - f48) * ((168.0 - t_last) / 120.0)
    u_last = clamp(u_last, 0.005, 1.0)
    n_last = ns[-1] if ns else N_LAUNCH
    e_prior_chk = prior_r7 * u_last / 100.0 * n_last
    if e_last >= 5 and e_prior_chk > 0:
        anchor = clamp((e_last / e_prior_chk) ** 0.5, 0.25, 4.0)
    else:
        anchor = 1.0
    anchored = clamp(prior_r7 * anchor, 0.01, 99.99)
    # --- blend ---------------------------------------------------------
    w = 1.0 / (1.0 + h_days / W_HORIZON_SCALE)
    median = math.exp(w * math.log(max(extrap, 0.01))
                      + (1.0 - w) * math.log(anchored))
    median = clamp(median, 0.01, 99.99)
    # --- spread --------------------------------------------------------
    sig = SIGMA_SCALE * math.sqrt(0.10 ** 2 + (0.15 * math.sqrt(h_days)) ** 2
                                  + KIND_SIGMA[kind] ** 2
                                  + resid_mean ** 2 + between_var)
    sig = clamp(sig, 0.30, 1.80)
    lm = logit_pct(median)
    out = []
    for z in Z:
        out.append(round(clamp(inv_logit_pct(lm + z * sig), 0.01, 99.99), 4))
    for i in range(1, 5):
        if out[i] < out[i - 1]:
            out[i] = out[i - 1]
    return out


# ---------------------------------------------------------------- driver

def forecast_case(case):
    trophies = case["trophies"]
    hist = case.get("history", [])
    horizon_min = float(case.get("horizon_minutes", 0))
    h_days = horizon_min / 1440.0
    target_h = parse_time(case["target"]) if case.get("target") else 0.0

    # History series: (t_hours since first read, N, [rates]).
    t0 = parse_time(hist[0]["at"]) if hist else 0.0
    series = []
    for read in hist:
        rates = read.get("rates") or []
        if len(rates) < len(trophies):
            continue
        n = read.get("players_tracked") or 0
        series.append((parse_time(read["at"]) - t0, n, rates))
    if not series:
        series = [(0.0, N_LAUNCH, [None] * len(trophies))]

    # Flat history? (every read identical rates and N)
    flat = True
    ref_rates, ref_n = series[0][2], series[0][1]
    for _, n, rates in series:
        if n != ref_n:
            flat = False
            break
        for a, b in zip(rates, ref_rates):
            if a is None or b is None or abs(a - b) > 1e-9:
                flat = False
                break
        if not flat:
            break

    rows = []
    if h_days <= 0.5 and flat:
        # Refresh branch.
        _, n_last, last_rates = series[-1]
        n_last = n_last or N_LAUNCH
        for tr, rate in zip(trophies, last_rates):
            tid = tr["id"]
            if rate is None:
                rate = 0.01
            if rate >= 99.99:
                e_last = n_last
            else:
                e_last = round(rate / 100.0 * n_last)
            rows.append({"id": tid, "q": refresh_row(e_last, tid)})
    else:
        # Growth branch: per-trophy E(t) series, running-max guarded.
        t_target = target_h - t0
        for idx, tr in enumerate(trophies):
            tid = tr["id"]
            ts, es, ns = [], [], []
            e_max, n_max = 0.0, 0.0
            for t, n, rates in series:
                r = rates[idx]
                if r is None or not n:
                    continue
                e = round(r / 100.0 * n)
                e_max = max(e_max, float(e))   # earners never decrease
                n_max = max(n_max, float(n))   # base never decreases
                ts.append(t)
                es.append(e_max)
                ns.append(n_max)
            if not ts:
                rows.append({"id": tid, "q": [0.01, 0.01, 0.01, 0.01, 0.01]})
                continue
            last_rate = series[-1][2][idx]
            if last_rate is None:
                last_rate = 0.01
            rows.append({"id": tid,
                         "q": growth_row(tid, ts, es, ns, t_target, h_days,
                                         float(last_rate))})
    return {"trophies": rows}


def main():
    in_dir = os.environ.get("MAKEFUN_INPUT_DIR", "/input")
    out_dir = os.environ.get("MAKEFUN_OUTPUT_DIR", "/output")
    os.makedirs(out_dir, exist_ok=True)
    names = sorted(fn for fn in os.listdir(in_dir) if fn.endswith(".in"))
    for fn in names:
        with open(os.path.join(in_dir, fn), "r", encoding="utf-8") as fh:
            case = json.load(fh)
        out = forecast_case(case)
        cid = fn[:-3]
        with open(os.path.join(out_dir, cid + ".out"), "w",
                  encoding="utf-8") as fh:
            json.dump(out, fh, separators=(",", ":"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
