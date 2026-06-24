# Backtest Ichimoku D1+W vs Compressione D1+W

Fonte: OANDA H1+D1+W. H1=20000, D=1500, W=800.
Walk-forward: train 6000 barre H1, test 2000 barre H1, fold: 7.
Evento H1: nuova rottura del range a 12 barre. Orizzonte primario: +12 H1.
No lookahead: ogni H1 usa solo D/W con data strettamente precedente; nuvola Ichimoku da t-26.

## Regola di decisione

Adottare Ichimoku solo se `ichimoku_d1w` batte `compr_d1w` su TEST in hit e ritorno medio,
con coerenza tra fold e almeno ~150 eventi utilizzabili. In caso contrario resta la compressione D1+W.

**Verdetto automatico:** NON ADOTTARE: Ichimoku D1+W non batte compr_d1w in modo coerente su hit e ritorno medio. Tenere la compressione D1+W attuale.

## TEST out-of-sample

| coorte | n +12 | hit +4 | hit +12 | hit +24 | hit +48 | medio% +12 | edge hit vs compr | edge medio% vs compr |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| all | 38436 | 0.48 | 0.493 | 0.492 | 0.493 | -0.0 | -0.07 | -0.0708 |
| compr_d1w | 1988 | 0.551 | 0.563 | 0.592 | 0.579 | 0.0708 | 0.0 | 0.0 |
| ichimoku_d1w | 8045 | 0.51 | 0.534 | 0.532 | 0.514 | 0.0295 | -0.029 | -0.0413 |
| ichimoku_d1_only | 14348 | 0.505 | 0.522 | 0.518 | 0.495 | 0.024 | -0.041 | -0.0468 |
| ichimoku_w_only | 14045 | 0.5 | 0.517 | 0.519 | 0.525 | 0.0166 | -0.046 | -0.0542 |
| kijun_d1w | 16660 | 0.524 | 0.549 | 0.55 | 0.542 | 0.0469 | -0.014 | -0.0239 |
| kijun_d1_only | 22917 | 0.515 | 0.54 | 0.531 | 0.513 | 0.0401 | -0.023 | -0.0307 |
| kijun_w_only | 21374 | 0.505 | 0.526 | 0.535 | 0.547 | 0.026 | -0.037 | -0.0448 |

## Fold: Ichimoku D1+W vs compr_d1w a +12 H1

| fold | test | n compr | hit compr | medio% compr | n ichi | hit ichi | medio% ichi | edge hit | edge medio% | vince entrambi |
|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| 1 | 6000-8000 | 553 | 0.58 | 0.043 | 1277 | 0.561 | 0.0093 | -0.019 | -0.0337 | False |
| 2 | 8000-10000 | 189 | 0.603 | 0.126 | 788 | 0.547 | 0.0444 | -0.056 | -0.0816 | False |
| 3 | 10000-12000 | 198 | 0.641 | 0.1343 | 1118 | 0.537 | 0.0206 | -0.104 | -0.1137 | False |
| 4 | 12000-14000 | 166 | 0.608 | 0.3317 | 1160 | 0.511 | 0.0868 | -0.097 | -0.2449 | False |
| 5 | 14000-16000 | 339 | 0.522 | 0.0057 | 1276 | 0.521 | 0.0156 | -0.001 | 0.0099 | False |
| 6 | 16000-18000 | 399 | 0.494 | 0.0194 | 1425 | 0.516 | 0.0086 | 0.022 | -0.0108 | False |
| 7 | 18000-20000 | 144 | 0.569 | 0.0137 | 1001 | 0.557 | 0.0346 | -0.012 | 0.0209 | False |

Fold comparabili: 7; Ichimoku vince hit+medio in 0 fold.

## Note

- `compr_d1w` e' la baseline live attuale: direzione compressione D1 e W attiva.
- `ichimoku_d1w` richiede prezzo fuori nuvola e Tenkan/Kijun concordi su D1 e W.
- `kijun_*` e' solo variante esplorativa close-vs-Kijun, non parte della decisione primaria.
- Il report e' research-only: non modifica scanner, dashboard o motore operativo.
