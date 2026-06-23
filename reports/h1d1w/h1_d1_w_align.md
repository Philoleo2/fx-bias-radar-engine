# Confluenza H1 + D1 + W

Fonte: OANDA H1+D1+W | H1 ~20000 | D1 ~1500 | W ~800
H1 window=12; D1 attivo=10 giorni; W attivo=8 settimane.
No lookahead: H1 usa solo D1/W strettamente precedenti alla sua data.

## TEST out-of-sample
| coorte | n(+12) | hit +4 | hit +12 | hit +24 | hit +48 | medio% +12 |
|---|---|---|---|---|---|---|
| all | 21832 | 0.474 | 0.486 | 0.484 | 0.481 | -0.0022 |
| aligned_d1 | 4483 | 0.51 | 0.503 | 0.495 | 0.485 | 0.0273 |
| aligned_w | 3785 | 0.502 | 0.511 | 0.524 | 0.509 | 0.0292 |
| aligned_d1w | 1053 | 0.531 | 0.528 | 0.551 | 0.518 | 0.0615 |
| d1_aligned_w_missing | 3041 | 0.501 | 0.496 | 0.472 | 0.474 | 0.0162 |
| d1_aligned_w_counter | 389 | 0.519 | 0.496 | 0.521 | 0.477 | 0.0215 |
| context_none | 8976 | 0.46 | 0.477 | 0.475 | 0.469 | -0.0123 |

## Confronto chiave +12 H1
- Edge hit aligned_d1w vs all: 0.042
- Edge hit aligned_d1w vs aligned_d1: 0.025
- Edge medio% aligned_d1w vs all: 0.0637
- Edge medio% aligned_d1w vs aligned_d1: 0.0342

aligned_d1w medio% +12: 0.0615% | aligned_d1: 0.0273% | all: -0.0022%
