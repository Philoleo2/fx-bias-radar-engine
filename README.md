# FX Bias Radar Engine

Python engine and dashboard for the FX Bias Radar / Metodo Garlando project.

This repository is the Phase 2 home for the all-pairs engine and operational dashboard:

- data source: OANDA REST v20 practice;
- universe: 28 FX pairs;
- timeframe: closed H4 candles only;
- current milestone: M1 merged, M2 dashboard in progress;
- objective: port the validated TradingView Pine engine `FX_Bias_Radar_Production_v1_1.pine` one-to-one into Python.

The radar is not an entry system and must not trade. It only identifies where Leonardo should look on manually drawn charts.

## Safety

Never commit secrets.

Local secrets belong in `.env`, which is ignored by Git:

```text
OANDA_ENV=practice
OANDA_BASE_URL=https://api-fxpractice.oanda.com
OANDA_ACCOUNT_ID=
OANDA_ACCESS_TOKEN=
DASHBOARD_TOKEN=
CACHE_SECONDS=60
```

For GitHub Actions, use repository secrets:

- `OANDA_ACCOUNT_ID`
- `OANDA_ACCESS_TOKEN`

For the Vercel dashboard, use project environment variables:

- `OANDA_ENV=practice`
- `OANDA_ACCESS_TOKEN`
- `DASHBOARD_TOKEN`
- `CACHE_SECONDS=60`

## M0 Check

Run locally:

```powershell
& 'C:\Users\leotr\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe' scripts\oanda_m0_check.py
```

Portable form:

```bash
python scripts/oanda_m0_check.py
```

Expected result: account summary plus complete H4 candles for `EUR_USD`, `USD_CHF`, `CHF_JPY`.

## Tests

```bash
python -m unittest discover -s tests -q
python -m compileall fx_bias_radar scripts tests
```

## Dashboard

Local fixture preview:

```bash
python scripts/dev_dashboard.py
```

Open `http://127.0.0.1:8765` and use token `dev` unless `DASHBOARD_TOKEN`
is set. The default local preview uses golden fixtures. To fetch live OANDA
data locally, set the OANDA environment variables and run:

```bash
python scripts/dev_dashboard.py --live
```

Vercel deployment uses:

- static UI in `public/`;
- `api/health.py`;
- `api/scan.py`;
- the shared `fx_bias_radar.scan_service` used by CLI, API, and future
  Telegram alerts.

Radar of attention only: the dashboard does not decide entries or place
orders. Leonardo still validates manual lines and timing in TradingView.

## Next Milestone

M1 must port the Pine v1.1 engine without changing thresholds or behavior. See:

- `docs/SONNET_BUILD_BRIEF_FASE2_FULL_SYSTEM_2026-06-10.md`
- `docs/ACCEPTANCE_TESTS_M1.md`
