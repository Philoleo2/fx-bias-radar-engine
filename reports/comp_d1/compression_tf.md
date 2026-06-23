# Compressione + espansione D - walk-forward

Fonte: OANDA D | granularita': D | barre: 3973 | fold: 4 (train 1500, test 500)
Orizzonti in barre D: [4, 12, 24] (su D = piu' tempo per barra). Entrata a CHIUSURA barra. edge = compressione - breakout liscio.

## Strategia selezionata (walk-forward, out-of-sample)
| set | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 |
|---|---|---|---|---|---|
| compressione | 1997 | 0.51 | 0.513 | 0.488 | 0.0525 |
| breakout liscio | 5785 | 0.491 | 0.48 | 0.466 | -0.0559 |

**Edge hit +12 (compressione vs breakout): 0.033**

## Profili fissi sul TEST
| profilo | n(+12) | hit +12 | medio% +12 | edge +12 |
|---|---|---|---|---|
| w12_p20 | 1997 | 0.513 | 0.0525 | 0.033 |
| w12_p30 | 2593 | 0.501 | 0.0161 | 0.021 |
| w18_p20 | 1523 | 0.491 | -0.0348 | 0.024 |
| w18_p30 | 1998 | 0.484 | -0.051 | 0.017 |
| w24_p20 | 1305 | 0.478 | -0.0643 | 0.02 |
| w24_p30 | 1711 | 0.479 | -0.0615 | 0.021 |

