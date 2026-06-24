# Backtest compressione allineata multi-timeframe

Fonte: OANDA H1/H4/D/W
Richieste: H1=20000 H4=5000 D1=1500 W=800
Split walk-forward semplice: train 60%, test 40%.
No lookahead: ogni evento usa solo timeframe superiori gia' chiusi al momento dell'ingresso.

## Cosa viene confrontato
- Baseline: rottura H1 semplice allineata a Daily + Weekly, cioe' il motore `allineate` attuale.
- Test 1: rottura da compressione H4 allineata a Daily + Weekly.
- Test 2: rottura da compressione H1 allineata a H4 + Daily.

## TEST out-of-sample
| coorte | n(+12h) | hit +4h | hit +12h | hit +24h | hit +48h | medio% +12h | edge hit vs baseline | edge medio vs baseline |
|---|---:|---:|---:|---:|---:|---:|---:|---:|
| Baseline H1 breakout + D + W | 814 | 0.485 | 0.482 | 0.491 | 0.461 | 0.0203 | 0.0 | 0.0 |
| H4 compressione + D + W | 40 | 0.65 | 0.525 | 0.525 | 0.425 | 0.053 | 0.043 | 0.0327 |
| H1 compressione + H4 + D | 193 | 0.456 | 0.435 | 0.453 | 0.448 | -0.0065 | -0.047 | -0.0268 |
| H1 breakout tutti | 21844 | 0.475 | 0.486 | 0.484 | 0.482 | -0.0016 | 0.004 | -0.0219 |
| H4 compressioni tutte | 1886 | 0.487 | 0.482 | 0.464 | 0.468 | -0.0037 | 0.0 | -0.024 |
| H1 compressioni tutte | 7794 | 0.483 | 0.501 | 0.49 | 0.488 | 0.0033 | 0.019 | -0.017 |

## TRAIN sample
| coorte | n(+12h) | hit +12h | medio% +12h |
|---|---:|---:|---:|
| Baseline H1 breakout + D + W | 1117 | 0.524 | 0.0014 |
| H4 compressione + D + W | 80 | 0.5 | 0.0062 |
| H1 compressione + H4 + D | 354 | 0.511 | 0.0336 |
| H1 breakout tutti | 33561 | 0.498 | 0.0015 |
| H4 compressioni tutte | 2647 | 0.487 | -0.0113 |
| H1 compressioni tutte | 11741 | 0.506 | 0.005 |

## Decisione provvisoria
Solo H4 compressione + D + W migliora la baseline H1+D+W.

## Numeri chiave +12h
- Baseline H1+D+W: hit 0.482 | medio% 0.0203
- H4 compressione+D+W: hit 0.525 | medio% 0.053
- H1 compressione+H4+D: hit 0.435 | medio% -0.0065

## Nota per Sonnet
Se entrambe le coorti restano sotto la baseline H1+D+W, il dato supporta l'ipotesi di rimuovere dal sito il motore H4 come guida direzionale e lasciare solo il filtro daily+weekly piu' selettivo.
