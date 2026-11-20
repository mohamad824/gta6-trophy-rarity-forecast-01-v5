# gta6-trophy-rarity-forecast-01 — v5

Forecasts, for each of the 55 GTA VI PS5 trophies, five quantiles of its
Exophase earn rate (%) at 2026-11-26T00:00:00Z.

## Entry

- `main.py` — the whole program (Python 3.13, stdlib only, no network).
  Run: `python3 main.py` with `$MAKEFUN_INPUT_DIR` / `$MAKEFUN_OUTPUT_DIR`
  set (defaults `/input` and `/output`). Reads every `*.in` file, writes
  one `<id>.out` per case.
- `RESEARCH.md` — the research and backtest record.
- `LICENSE` — MIT.

## Model in one paragraph

Two branches. **Refresh** (horizon ≤ 0.5 d and the history is one flat
launch-night page): the median is `round(E_last × g_i / 3868 × 100, 2)`,
with earners `E_last` recovered from rate × N and per-trophy growth
`g_i = 3.0 × (r_i / 2.7685)^0.005` for the seven risers
{3, 4, 8, 20, 21, 35, 46} — `r_i` is the trophy's real 2-day rate ratio
(Ch.1 ×9.58, fishing ×6.52, Trust ×3.87, bowling ×1.62, Ch.2 ×1.55,
arcade ×1.51, Whip It Good ×1.36) — and `g_i = 1.0` for the rest, which
are diluted by 638 → 3,868 players. The spread is a razor-thin logit
mixture: tight asymmetric component (σ_up 0.001 / σ_dn 0.0005, weight
0.98) plus a small hedge (weight 0.02, σ 0.20) centred on the
uniform-growth rate (g = 1.255). **Growth** (everything else): earners
E(t) and the tracked base N(t) are modelled separately (rate = E/N);
three earner shapes × three base curves, residual-weighted geometric
mean, blended with re-fit type priors (w(h) = 1/(1+h/1.2)) after
prior anchoring **on earners** against a kind-specific prior trajectory
calibrated from the real 2-day data. Running-max guard on E/N.

## Headline backtest (practice p00, truths rounded to 2 decimals)

| truth | v5 | v4 | v3 |
|---|---|---|---|
| (e2) non-uniform g=3.0, **with id 35** (primary) | **0.0005** | 0.0092 | 0.1337 |
| (e2) per-trophy g_i (v5's own hypothesis) | 0.0001 | — | — |
| (e2) non-uniform g=3.0, without 35 | 0.0203 | 0.0226 | 0.1161 |
| (e1) uniform g=1.255 | 0.3008 | 0.1830 | 0.1281 |
| (a1) pure dilution | 0.1389 | 0.1032 | 0.0095 |

Top-8 bar 0.000591: **met on the primary proxy (0.0005)** — by a thin
margin, and only if the non-uniform hypothesis with id 35 as a riser is
right. Top-20 bar 0.0203: met on the primary proxy; exactly on the line
without id 35 (0.0203). Under the uniform hypothesis v5 scores 0.30
(no prize). See RESEARCH.md §5 for the honest assessment and the open
flags. This version is HELD — no submit without an explicit order.
