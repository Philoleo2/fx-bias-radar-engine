# Compressione + espansione H1 - storico lungo walk-forward

Fonte: OANDA H1 paginated | barre H1 allineate: 29953 | richieste: 30000 | page_size: 5000
Walk-forward: train 6000 barre, test 2000 barre, fold: 11.
Compressione = range ultime N barre <= percentile storico su 120 finestre precedenti.
Espansione = nuova chiusura fuori dal range. Baseline = breakout da solo.

## Strategia selezionata dal TRAIN di ogni fold

| strategia | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 | baseline hit +12 | baseline medio% +12 | edge hit +12 |
|---|---|---|---|---|---|---|---|---|
| walk-forward selected | 25434 | 0.485 | 0.502 | 0.499 | 0.0011 | 0.49 | -0.0049 | 0.012 |

## Profili fissi sul TEST walk-forward

| profilo | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 | baseline hit +12 | baseline medio% +12 | edge hit +12 |
|---|---|---|---|---|---|---|---|---|
| w12_p20 | 21613 | 0.483 | 0.502 | 0.499 | 0.0022 | 0.49 | -0.0049 | 0.012 |
| w12_p30 | 28553 | 0.484 | 0.501 | 0.498 | 0.0009 | 0.49 | -0.0049 | 0.011 |
| w18_p20 | 16818 | 0.483 | 0.495 | 0.494 | -0.0017 | 0.486 | -0.0074 | 0.009 |
| w18_p30 | 21849 | 0.481 | 0.491 | 0.494 | -0.0032 | 0.486 | -0.0074 | 0.005 |
| w24_p20 | 12326 | 0.48 | 0.481 | 0.494 | -0.012 | 0.483 | -0.0093 | -0.002 |
| w24_p30 | 16323 | 0.476 | 0.483 | 0.498 | -0.0115 | 0.483 | -0.0093 | 0.0 |

## Fold

| fold | train | test | profilo scelto | edge train +12 | n test +12 | hit test +12 | edge test +12 |
|---|---|---|---|---|---|---|---|
| 1 | 0-6000 | 6000-8000 | w12_p30 | 0.015 | 2627 | 0.491 | 0.019 |
| 2 | 2000-8000 | 8000-10000 | w12_p30 | 0.019 | 2560 | 0.508 | 0.019 |
| 3 | 4000-10000 | 10000-12000 | w12_p30 | 0.021 | 2711 | 0.515 | -0.008 |
| 4 | 6000-12000 | 12000-14000 | w12_p30 | 0.01 | 2706 | 0.5 | 0.022 |
| 5 | 8000-14000 | 14000-16000 | w12_p30 | 0.011 | 2549 | 0.482 | 0.004 |
| 6 | 10000-16000 | 16000-18000 | w12_p30 | 0.006 | 2560 | 0.504 | -0.003 |
| 7 | 12000-18000 | 18000-20000 | w12_p20 | 0.013 | 2003 | 0.543 | 0.025 |
| 8 | 14000-20000 | 20000-22000 | w12_p20 | 0.012 | 1898 | 0.488 | 0.01 |
| 9 | 16000-22000 | 22000-24000 | w12_p20 | 0.01 | 1962 | 0.513 | 0.03 |
| 10 | 18000-24000 | 24000-26000 | w12_p20 | 0.021 | 1974 | 0.499 | 0.019 |
| 11 | 20000-26000 | 26000-28000 | w12_p20 | 0.021 | 1884 | 0.481 | -0.002 |

