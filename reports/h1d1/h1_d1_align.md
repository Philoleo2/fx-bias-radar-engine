# Confluenza H1 + D1: rottura H1 allineata al daily

Fonte: OANDA H1+D1 | H1 barre/coppia ~20000 | D1 ~1500 | finestra attiva D1 = 10 giorni
Rottura H1 (window 12) classificata vs direzione attiva D1. Orizzonti in barre H1. Metriche su TEST (out-of-sample, ultima parte). edge = aligned - all.

## TEST out-of-sample
| classe | n(+12) | hit +4 | hit +12 | hit +24 | hit +48 | medio% +12 |
|---|---|---|---|---|---|---|
| aligned | 4481 | 0.51 | 0.503 | 0.495 | 0.485 | 0.0272 |
| counter | 3799 | 0.468 | 0.487 | 0.489 | 0.501 | -0.0113 |
| context_none | 13549 | 0.464 | 0.479 | 0.478 | 0.475 | -0.0094 |
| all | 21829 | 0.474 | 0.486 | 0.484 | 0.481 | -0.0022 |

**Edge hit +12 (aligned vs all): 0.017**  |  ritorno medio aligned +12: 0.0272% vs all -0.0022%

