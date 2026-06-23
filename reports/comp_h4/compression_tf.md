# Compressione + espansione H4 - walk-forward

Fonte: OANDA H4 | granularita': H4 | barre: 19970 | fold: 6 (train 6000, test 2000)
Orizzonti in barre H4: [4, 12, 24] (su H4 = piu' tempo per barra). Entrata a CHIUSURA barra. edge = compressione - breakout liscio.

## Strategia selezionata (walk-forward, out-of-sample)
| set | n(+12) | hit +4 | hit +12 | hit +24 | medio% +12 |
|---|---|---|---|---|---|
| compressione | 9295 | 0.496 | 0.486 | 0.49 | -0.0256 |
| breakout liscio | 26070 | 0.49 | 0.483 | 0.487 | -0.0274 |

**Edge hit +12 (compressione vs breakout): 0.003**

## Profili fissi sul TEST
| profilo | n(+12) | hit +12 | medio% +12 | edge +12 |
|---|---|---|---|---|
| w12_p20 | 10858 | 0.488 | -0.0186 | 0.003 |
| w12_p30 | 14421 | 0.485 | -0.0217 | 0.0 |
| w18_p20 | 8607 | 0.486 | -0.0201 | 0.001 |
| w18_p30 | 11362 | 0.487 | -0.0222 | 0.002 |
| w24_p20 | 7141 | 0.486 | -0.023 | 0.004 |
| w24_p30 | 9435 | 0.486 | -0.0267 | 0.004 |

