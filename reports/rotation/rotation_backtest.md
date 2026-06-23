# Backtest rotazione H1 - calibrazione + edge prezzo

Fonte: OANDA H1 | barre: 3999 | split train/test @ 1999 | tol match: 6 | pivot: swing 6, |ext|>=1.5

offset = barre tra segnale e punto vero (0 = centrato, + = ritardo, - = anticipo). Metriche TEST = out-of-sample.

## Configurazione consigliata (miglior score out-of-sample)
- ext_min=1.5, k_window=12, conf_bars=1, method=slope_both
- TEST: precision 0.964, recall 0.894, f1 0.928, offset mediano 1, medio 0.78

## Follow-through del PREZZO dopo la rotazione (config consigliata)
Ritorno medio/mediano nella direzione segnalata e hit rate, a +N barre H1.

| orizzonte (barre H1) | n | ritorno medio % | mediano % | hit rate |
|---|---|---|---|---|
| +4 | 6432 | -0.0003 | 0.005 | 0.515 |
| +12 | 6421 | -0.0049 | -0.0 | 0.5 |
| +24 | 6393 | 0.0086 | 0.0 | 0.499 |

## Edge per FORZA della rotazione (|estremo| dello spread)
Le rotazioni piu' forti hanno piu' follow-through? hit rate per orizzonte.

| fascia estremo | n(+12) | hit +4 | hit +12 | hit +24 | medio % +24 |
|---|---|---|---|---|---|
| 1.5-2.0 | 1788 | 0.499 | 0.501 | 0.49 | 0.0067 |
| 2.0-2.5 | 1378 | 0.513 | 0.497 | 0.499 | 0.0007 |
| 2.5-3.0 | 982 | 0.505 | 0.509 | 0.496 | 0.0101 |
| 3.0-3.5 | 786 | 0.534 | 0.508 | 0.492 | 0.0044 |
| 3.5+ | 1487 | 0.534 | 0.492 | 0.515 | 0.0196 |

## Top 10 (per score out-of-sample)

| # | method | ext | K | conf | prec | rec | f1 | off.med | score |
|---|--------|-----|---|------|------|-----|----|---------|-------|
| 1 | slope_both | 1.5 | 12 | 1 | 0.964 | 0.894 | 0.928 | 1 | 0.878 |
| 2 | slope_both | 1.5 | 8 | 1 | 0.89 | 0.95 | 0.919 | 1 | 0.869 |
| 3 | ema_cross | 1.5 | 8 | 1 | 0.952 | 0.924 | 0.938 | 2.0 | 0.838 |
| 4 | ema_cross | 1.5 | 8 | 2 | 0.952 | 0.924 | 0.938 | 2.0 | 0.838 |
| 5 | ema_cross | 1.5 | 8 | 3 | 0.952 | 0.924 | 0.938 | 2.0 | 0.838 |
| 6 | slope_both | 1.5 | 18 | 1 | 0.963 | 0.78 | 0.862 | 1 | 0.812 |
| 7 | ema_cross | 1.5 | 12 | 1 | 0.981 | 0.841 | 0.906 | 2 | 0.806 |
| 8 | ema_cross | 1.5 | 12 | 2 | 0.981 | 0.841 | 0.906 | 2 | 0.806 |
| 9 | ema_cross | 1.5 | 12 | 3 | 0.981 | 0.841 | 0.906 | 2 | 0.806 |
| 10 | slope_both | 1.5 | 12 | 2 | 0.979 | 0.838 | 0.903 | 2 | 0.803 |

