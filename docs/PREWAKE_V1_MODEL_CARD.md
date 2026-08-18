# Model card — PAIR_PREWAKE_V1

```text
Status:
RESEARCH CANDIDATE / PROSPECTIVE VALIDATION

Not:
validated trading strategy
```

---

## Identità

| Campo | Valore |
|---|---|
| `model_name` | `PAIR_PREWAKE_V1` |
| `model_version` | `pair-prewake-v1` |
| Frozen fingerprint | `6c767bcbc66f9719d9c4e47ff2756dc789901568f587772f1a27180f8872bd17` |
| Artifact | `prewake/models/pair_prewake_v1.json`, hash verificato a ogni load |
| Research source | `research/prewake-phase2` @ `bfadfc98b2bed21377287d16b2eab5745f0fe8c3` |
| Tuning | `FROZEN` |

## Ricerca storica

Phase 1 (audit PAIR pre-wake) + Phase 2 (change detection, compression-expansion,
common vs residual, dual-leg, robustezza, multiple testing).

**`No independent untouched final holdout available.`**
Il final holdout precedente (`2025-01-06T23:00` → `2026-08-17T11:00` UTC) è
`PREVIOUSLY SEEN FINAL HOLDOUT`: era già stato osservato quando la Phase 2 è
stata eseguita. Serve per decomposizione forense, non come validazione nuova.

Dataset congelato: 50.105 H1 comuni × 28 croci, `2018-07-25T13:00` →
`2026-08-17T11:00` UTC, OANDA H1 MID, sole barre complete.

## Caratteristiche storiche principali

```text
precision ~61-64% a seconda della fetta di valutazione
lead mediano ~3 H1
coverage bassa
circa 2-3 alert/giorno nella ricerca storica
```

Numeri esatti sul campione holdout (modello congelato unico):

| Metrica | Valore |
|---|---|
| Alert | `1.104` |
| Con rottura grezza fresca stessa direzione in `+1…+12` H1 | `702` |
| Precision `+1…+12` | `63,586957%` |
| CI 95% | `59,88% – 67,03%` |
| Lead mediano | `3` H1 |
| Lead medio | `3,95` H1 |
| Alert/giorno | `2,19` |
| Eventi same-bar (lead 0, diagnostici) | `4` |
| Alert con `fx_bias_same == 1` | `0` |
| Eventi `NEW_WAKE` | `0` — tutti `REAWAKENING` |

Precision al variare del lead minimo richiesto: `>=1H` 63,6% · `>=2H` 47,1% ·
`>=3H` 37,0% · `>=4H` 29,3% · `>=6H` 22,1%. La precisione cala rapidamente
quando si pretende più anticipo.

## Come funziona, in una riga

Per ogni H1 chiusa e ogni coppia: la direzione è il segno dell'EWMA (half-life 4)
dello z-robusto a 240 barre del gap cross-currency leave-one-pair-out; otto
feature pair-level vengono standardizzate e passate a una logistica congelata;
se la probabilità supera `0.5965942096795052` e il lifecycle è armato, viene
emesso un evento.

## Limiti dichiarati

- **Nessun holdout indipendente non toccato.** Qualunque metrica qui riportata è
  su dati già visti dalla ricerca. Non è una validazione fuori campione pulita.
- **Coverage bassa.** Il modello copre ~2,5% delle rotture a 12 H1. Non è un
  rilevatore esaustivo: tace molto più spesso di quanto parli.
- **Non ha detto EURNZD.** Sul case study congelato il massimo è stato
  `0.585555` contro soglia `0.596594`. È il comportamento corretto e non va
  "sistemato".
- **`fx_bias_same` è un soppressore, non un contributore.** Coefficiente
  `-1.8776`, attivo in 0 alert su 1.104. Il modello per costruzione non parla
  quando la rottura è già avvenuta.
- **Le feature dei ritorni contano pochissimo.** I coefficienti di
  `dir_ret1…dir_ret24` sono tra `+0,052` e `-0,037` su scala standardizzata: il
  peso reale sta in `abs_pair_z` (`-0,342`), `compression_ratio` (`-0,127`) e
  `fx_bias_same`.
- **Il lifecycle dipende dalla storia.** `NEW_WAKE` significa "primo in assoluto
  per quella coppia e direzione": dopo il seeding storico non comparirà quasi
  mai in live.
- **Regime.** Tutta la ricerca è su 2018-2026. Nessuna evidenza fuori da questo
  periodo.

## Soglia di decisione per la validazione prospettica

Non si dichiara un edge validato prima di **entrambe**:

```text
6 mesi di raccolta prospettica
E
300 alert prospettici
```

Fino ad allora PREWAKE è uno **strumento di osservazione**. Si può guardare, si
può usare per decidere dove aprire un grafico, ma non si può affermare che
funzioni.

## Cosa raccogliere durante il periodo prospettico

Totale alert e alert/giorno; rottura grezza a `+1, +2, +3, +4, +6, +8, +12, +24`;
precision, coverage, lead; directional return, MFE, MAE; eventi same-bar;
comparsa successiva di FX Bias e `time_to_fx_bias`; diagnostica dual-leg.
Nessun calcolo futuro può alterare gli eventi originali.

## Coorti da costruire dopo

`PREWAKE ONLY` · `FX BIAS ONLY` · `PREWAKE → FX BIAS` · `FX BIAS contemporaneo a
PREWAKE`. Nessuna assunzione a priori su quale sia migliore.

---

```text
Do not interpret as guaranteed future performance.
```

Questo modello non è un consiglio finanziario, non è una strategia validata, e
non produce raccomandazioni operative. È un candidato di ricerca in osservazione.
