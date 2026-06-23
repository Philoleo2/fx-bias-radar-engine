# Compressione + espansione H1 - edge prezzo

Fonte: OANDA H1 | barre H1: 3999 | split train/test: 2399/1600
Compressione = range delle ultime N barre <= percentile storico su 120 finestre precedenti.
Espansione = nuova chiusura fuori dal range delle ultime N barre. hit 0.50 = caso.

Profilo migliore su TRAIN per edge hit +12: **w12_p20**.

## Profilo scelto train/test

| profilo | set | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 | edge hit +12 vs baseline |
|---|---|---|---|---|---|---|---|
| w12_p20 train | compression_expansion | 2149 | 0.455 | 0.499 | 0.496 | 0.0048 | 0.009 |
| w12_p20 train | breakout_only | 6155 | 0.457 | 0.49 | 0.494 | 0.0002 | 0.009 |
| w12_p20 test | compression_expansion | 1558 | 0.495 | 0.489 | 0.483 | -0.0072 | 0.0 |
| w12_p20 test | breakout_only | 4287 | 0.484 | 0.489 | 0.476 | -0.0106 | 0.0 |
| w12_p20 all | compression_expansion | 3707 | 0.472 | 0.495 | 0.49 | -0.0003 | 0.005 |
| w12_p20 all | breakout_only | 10442 | 0.468 | 0.49 | 0.487 | -0.0042 | 0.005 |

## Tutti i profili - TEST out-of-sample

| profilo | set | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 | edge hit +12 vs baseline |
|---|---|---|---|---|---|---|---|
| w12_p20 | compression_expansion | 1558 | 0.495 | 0.489 | 0.483 | -0.0072 | 0.0 |
| w12_p20 | breakout_only | 4287 | 0.484 | 0.489 | 0.476 | -0.0106 | 0.0 |
| w12_p30 | compression_expansion | 2032 | 0.494 | 0.495 | 0.486 | -0.0099 | 0.006 |
| w12_p30 | breakout_only | 4287 | 0.484 | 0.489 | 0.476 | -0.0106 | 0.006 |
| w18_p20 | compression_expansion | 1172 | 0.478 | 0.516 | 0.511 | 0.0017 | 0.023 |
| w18_p20 | breakout_only | 3435 | 0.481 | 0.493 | 0.479 | -0.01 | 0.023 |
| w18_p30 | compression_expansion | 1541 | 0.471 | 0.506 | 0.503 | 0.003 | 0.013 |
| w18_p30 | breakout_only | 3435 | 0.481 | 0.493 | 0.479 | -0.01 | 0.013 |
| w24_p20 | compression_expansion | 928 | 0.45 | 0.519 | 0.502 | 0.0187 | 0.024 |
| w24_p20 | breakout_only | 2887 | 0.478 | 0.495 | 0.473 | -0.0098 | 0.024 |
| w24_p30 | compression_expansion | 1219 | 0.476 | 0.523 | 0.493 | 0.018 | 0.028 |
| w24_p30 | breakout_only | 2887 | 0.478 | 0.495 | 0.473 | -0.0098 | 0.028 |

