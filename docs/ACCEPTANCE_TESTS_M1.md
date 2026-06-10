# M1 Acceptance Tests

M1 is accepted only when the Python engine matches the validated Pine behavior.

## Mandatory Cases

1. `EUR_USD`
   - `2026-03-31`: LONG must remain.
   - `2026-04-13`: LONG must remain.
   - `2026-04-17` / `2026-04-21`: weak SHORT must remain hidden unless true takeover.
   - `2026-04-22`: SHORT true takeover must be accepted.
   - `2026-04-28`: follow-up same-direction SHORT may remain as display duplicate; it is not a core regression.

2. `USD_CHF`
   - Strong opposite case around `2026-06-07`: USD+ / CHF-, score near 100, spread around 3.38 must show LONG/RESUME after v1.1 strong-opposite bypass.

3. `CHF_JPY`
   - Strong opposite case around `2026-06-07`: JPY+ / CHF-, score near 100, spread around 4.25 must show SHORT/RESUME after v1.1 strong-opposite bypass.

4. `EUR_NZD`
   - Early June LONG/RESUME must remain reactive and coherent.

5. Flat / non-actionable negatives
   - `GBP_JPY`: spread about 0.12 and no bias is correct.
   - `AUD_CAD`: old flat case with spread about 0.34 and no bias was correct; later AUDCAD movement is not a flat regression.
   - `NZD_CHF`: old spread about 0.17 and no bias was correct.

## Required Comparison Mode

- Use OANDA H4 complete candles only.
- Align bars in UTC.
- Compare signal state, not tiny decimal differences.
- Any threshold change is a failure unless Leonardo explicitly approves it before implementation.

## Golden Test Output

Each golden test should expose:

- pair;
- bar timestamp UTC;
- bias;
- type;
- state;
- score;
- strong currency;
- weak currency;
- spread;
- note;
- accepted/hidden reason where relevant.
