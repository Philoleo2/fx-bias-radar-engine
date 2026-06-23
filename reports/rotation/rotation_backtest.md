# Backtest rotazione H1 - calibrazione

Fonte: OANDA H1 | barre: 3999 | split train/test @ 1999 | tol match: 6 barre | pivot: swing 6, |ext|>=1.5

offset = barre tra segnale e punto vero (0 = centrato, + = in ritardo, - = in anticipo). Metriche TEST = out-of-sample.

## Configurazione consigliata (miglior score out-of-sample)
- ext_min=1.5, k_window=12, conf_bars=1, method=slope_both
- TEST: precision 0.965, recall 0.894, f1 0.928, offset mediano 1, medio 0.78

## Top 10 (ordinate per score out-of-sample)

| # | method | ext | K | conf | prec | rec | f1 | off.med | score |
|---|--------|-----|---|------|------|-----|----|---------|-------|
| 1 | slope_both | 1.5 | 12 | 1 | 0.965 | 0.894 | 0.928 | 1 | 0.878 |
| 2 | slope_both | 1.5 | 8 | 1 | 0.89 | 0.95 | 0.919 | 1 | 0.869 |
| 3 | ema_cross | 1.5 | 8 | 1 | 0.952 | 0.924 | 0.938 | 2 | 0.838 |
| 4 | ema_cross | 1.5 | 8 | 2 | 0.952 | 0.924 | 0.938 | 2 | 0.838 |
| 5 | ema_cross | 1.5 | 8 | 3 | 0.952 | 0.924 | 0.938 | 2 | 0.838 |
| 6 | slope_both | 1.5 | 18 | 1 | 0.963 | 0.78 | 0.862 | 1 | 0.812 |
| 7 | ema_cross | 1.5 | 12 | 1 | 0.981 | 0.841 | 0.906 | 2.0 | 0.806 |
| 8 | ema_cross | 1.5 | 12 | 2 | 0.981 | 0.841 | 0.906 | 2.0 | 0.806 |
| 9 | ema_cross | 1.5 | 12 | 3 | 0.981 | 0.841 | 0.906 | 2.0 | 0.806 |
| 10 | slope_both | 1.5 | 12 | 2 | 0.979 | 0.838 | 0.903 | 2 | 0.803 |

