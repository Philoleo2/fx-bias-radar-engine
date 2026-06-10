# Sonnet Build Brief - FX Bias Radar Phase 2 Python Engine

Data: 2026-06-10  
Owner: Leonardo  
Implementation target: Python repository `fx-bias-radar-engine`  
Current status: M0 OANDA live check confirmed by Leonardo.

## 1. Mission

Build the full off-Pine FX Bias Radar engine for the Metodo Garlando workflow.

The system must scan all 28 major FX crosses on closed H4 candles, using OANDA REST v20 data, and identify pairs worth opening on TradingView. It must remain a radar of attention, not an entry engine.

Leonardo manually draws chart lines and evaluates breaks/pullbacks. The system must never build trendlines, validate touches, decide entries, place orders, calculate targets, or manage trades.

Operational meaning:

> One currency strengthens and another weakens; look here.

## 2. Non-Negotiable Product Rules

- Do not change the validated engine thresholds during M1.
- Do not add trading/order endpoints.
- Do not implement line logic, break validation, touch counts, or entry logic.
- Use only closed H4 candles.
- Keep Pine v1.3 as the visual current-chart companion.
- Python becomes the all-pairs source of truth only after M1 parity is proven.
- Alerts are postponed until M2.

## 3. Validated Source Of Truth

Port the engine from:

```text
FX_Bias_Radar_Production_v1_1.pine
```

Do not port the lightweight v1.3 focus-list as the engine. v1.3 solved Pine scanner stability, but Python should run the real v1.1-style state machine across all pairs.

v1.1 includes the v0.17 / FR024 strong-opposite bypass and is accepted by Leonardo:

- EURUSD historical regression intact.
- USDCHF strong opposite LONG/RESUME visible.
- CHFJPY strong opposite SHORT/RESUME visible.

## 4. Engine Concepts To Preserve

The Python implementation must preserve the Pine mental model and naming as much as possible:

- `candidateEvent` separate from `acceptedEvent`;
- hidden opposite RESUME must not promote or corrupt the active regime;
- dead/protective peak memory protects strong prior regimes;
- post-death TTL about 36 H4 bars;
- protective cap about 120 H4 bars;
- takeover only if opposite spread is at least effective dead/protective peak * 1.10;
- ROT is always free;
- no global threshold increase;
- strong-opposite bypass floor = 3.0 from v1.1;
- display dedup must not mutate core state.

## 5. Thresholds To Preserve

Use the actual v1.1 Pine values as source. The known invariants are:

- `spreadMin = 1.00`
- `resumeScoreMin = 55`
- `neutralFloor = 0.35`
- `removeFloor = 0.70`
- `deadTakeoverMult = 1.10`
- `strongOppositeFloor = 3.0`
- post-death TTL around `36`
- protective cap around `120`

If a value is discovered under a different exact variable name in Pine, preserve the Pine value and document the mapping.

## 6. Architecture

Recommended modules:

```text
fx_bias_radar/
  config.py          # env/secrets loading
  oanda.py           # REST v20 data access
  pairs.py           # 28 pair universe
  candles.py         # candle models, closed-bar filtering, UTC alignment
  currency_index.py  # 28 pairs -> 8 currency strength series
  engine.py          # v1.1 state machine
  state.py           # per-pair/regime state dataclasses
  report.py          # markdown/json report output
  focus.py           # all-pairs focus ranking from real engine state
scripts/
  oanda_m0_check.py
  run_h4_scan.py
tests/
```

Design preference:

- reconstruct state from historical lookback on each run where feasible;
- use at least 150 H4 bars, preferably 180-220, to cover protective cap + TTL;
- saved state may be diagnostic/cache, not a single point of corruption.

## 7. Data Layer Requirements

OANDA:

- environment: practice;
- base URL: `https://api-fxpractice.oanda.com`;
- candles endpoint: `/v3/instruments/{instrument}/candles`;
- account endpoint only for sanity checks;
- use `price=M` midpoint candles unless Pine/OANDA visual comparison proves another choice is required;
- filter `complete=true`;
- use UTC timestamps.

M0 has already passed:

- account returned;
- account summary returned;
- H4 candles returned for `EUR_USD`, `USD_CHF`, `CHF_JPY`;
- Leonardo confirmed OHLC against TradingView/OANDA.

## 8. M1 Implementation Plan

### M1.1 Data parity

Implement historical fetch for all 28 pairs. Produce a report with latest complete H4 timestamp per pair and fail if pairs are misaligned.

### M1.2 Currency strength parity

Port the Pine data layer:

- 28 pair returns/normalization;
- 8 currency strength series;
- z-score / slope / velocity logic exactly as Pine.

Do not invent a new strength model.

### M1.3 Engine state machine

Port v1.1 function-for-function:

- score/spread;
- ROT;
- RESUME;
- NUOVO/ATTIVO/ESTESO;
- anti-flip;
- post-death hidden candidate behavior;
- protective/dead peak;
- takeover;
- strong-opposite bypass;
- accepted vs attention event.

### M1.4 Golden tests

Implement automated tests for the mandatory historical cases in `docs/ACCEPTANCE_TESTS_M1.md`.

### M1.5 Report mode

Before Telegram, output a Markdown/JSON report per run:

- focus list from real per-pair engine state;
- current events;
- active/extended regimes;
- hidden/blocked reasons for debugging;
- no trade instruction.

## 9. M2 Alert Plan

Only after M1 parity:

- Telegram bot token in GitHub Secrets;
- one grouped message per H4 run;
- alert only on new attention event;
- no alert on every persistent ATTIVO/ESTESO bar;
- anti-spam/dedup based on production display defaults;
- include final reminder: "Radar di attenzione: decisione sulle linee manuali."

Message shape:

```text
EURNZD LONG RESUME NUOVO 94 | EUR+ / NZD- | spread 1.21 | pullback
Radar di attenzione: decisione sulle linee manuali.
```

## 10. GitHub Actions Plan

CI:

- compile;
- unit tests;
- golden tests once M1 data fixtures exist.

Scheduled scan after M1:

- run after H4 close with small delay;
- suggested UTC schedule: `01:05`, `05:05`, `09:05`, `13:05`, `17:05`, `21:05`;
- handle DST by using UTC OANDA bars, not local time assumptions.

Secrets:

- `OANDA_ACCOUNT_ID`
- `OANDA_ACCESS_TOKEN`
- later `TELEGRAM_BOT_TOKEN`
- later `TELEGRAM_CHAT_ID`

## 11. Output Contract

Report rows should include:

- pair;
- bias: LONG / SHORT / `-`;
- type: ROT / RESUME / `-`;
- state: NUOVO / ATTIVO / ESTESO / NESSUNO;
- score;
- strong currency;
- weak currency;
- spread;
- note;
- event freshness;
- reason if hidden/blocked.

Focus list should prefer actionable quality, not raw spread alone:

- real active event/state;
- fresh or improving condition;
- cluster cap to avoid five rows all saying the same currency theme;
- current pair is not pinned artificially;
- panel/current chart remains separately judged in Pine.

## 12. Known User Workflow

Leonardo works like this:

1. Let radar choose 3-5 pairs to inspect.
2. Open those TradingView charts.
3. Draw/check manual Metodo Garlando lines.
4. Use screenshot review prompt/rulebook for timing judgment.
5. Enter only when his line/pullback method confirms.

The Python engine must support step 1 only.

## 13. Done Criteria For Full System

M1 done:

- M0 remains passing;
- all 28 pairs fetch;
- engine matches Pine v1.1 on golden cases;
- 3-5 day live parity with Pine v1.3/current chart has no signal divergence.

M2 done:

- Telegram alerts only on new attention events;
- one week live alert review coherent;
- no spam;
- no trade/entry language.

## 14. Hard Stop Conditions

Stop and ask Leonardo if:

- a Pine threshold seems wrong or missing;
- a golden case fails and the fix would change core behavior;
- OANDA feed differs materially from TradingView/OANDA;
- implementing alerts would require storing secrets outside GitHub Secrets/local `.env`;
- any code path would place or simulate orders.
