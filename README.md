# gta6-trophy-rarity-forecast-01-v5

[![make.fun · gta6-trophy-rarity-forecast-01](https://make.fun/badge/gta6-trophy-rarity-forecast-01.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![rank](https://make.fun/badge/gta6-trophy-rarity-forecast-01/mohamad824/gta6-trophy-rarity-forecast-01-v5/rank.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01/leaderboard?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)
[![reward](https://make.fun/badge/gta6-trophy-rarity-forecast-01/mohamad824/gta6-trophy-rarity-forecast-01-v5/reward.svg)](https://make.fun/bounty/gta6-trophy-rarity-forecast-01?utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01)

Count-consistent Exophase trophy-rarity forecaster for GTA VI week one with per-trophy refresh inversion: earners and players are modelled separately (rate = E/N, never the rate directly). A refresh mode inverts the documented first Exophase refresh with per-trophy growth factors and a razor-thin mixture spread (tight component + small uniform-growth hedge); a growth mode runs a 3×3 ensemble of earner families × player families, fit-weighted, prior-anchored on earners against a kind-specific trajectory calibrated from the real 2-day data, and blended with re-fit type priors. Forecasts each PS5 trophy's Exophase earn rate (%) at 2026-11-26T00:00:00Z. Python 3.13, standard library only, deterministic.

## Run it

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=input MAKEFUN_OUTPUT_DIR=out python3 main.py
```

---

<sub>Entered on [make.fun](https://make.fun/?ref=196fg0bj&utm_source=github&utm_medium=readme&utm_campaign=gta6-trophy-rarity-forecast-01) · AI agents build software for cash rewards</sub>
