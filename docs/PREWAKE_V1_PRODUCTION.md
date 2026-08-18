# PAIR_PREWAKE_V1 — documentazione di produzione

Motore di attenzione precoce che gira in parallelo a FX Bias Radar, senza
modificarne il comportamento. Questo documento descrive cosa è stato portato in
produzione, da dove viene, e soprattutto **cosa non deve essere toccato**.

---

## 1. Scopo

PREWAKE osserva le 28 coppie a ogni H1 chiusa e segnala **quali coppie guardare
e in che direzione**, tipicamente qualche ora prima che compaia una rottura
grezza fresca. Non è un segnale operativo, non è un consiglio di trade, non
sostituisce FX Bias. È un radar di attenzione in **validazione prospettica**.

FX Bias continua a funzionare esattamente come prima. ValutaVision non è
integrato e non deve esserlo in questa fase.

---

## 2. Provenienza

| Voce | Valore |
|---|---|
| Branch di ricerca | `research/prewake-phase2` (mai pushata: vive solo nel worktree locale) |
| Commit finale | `bfadfc98b2bed21377287d16b2eab5745f0fe8c3` |
| Parent Phase 2 | `5ef88c454eb8bd89f8fab37623ab94c21cb41f1c` |
| Worktree | `C:\Users\leotr\Documents\Indicatore\fxbr-prewake-phase2` |
| Fingerprint semantico | `6c767bcbc66f9719d9c4e47ff2756dc789901568f587772f1a27180f8872bd17` |
| Branch di produzione | `feature/pair-prewake-v1-live`, parent `60b841fff2f3977a6144fe876ae3610a0ce50c8b` |

Componenti del fingerprint, verificati sui file **su disco** (attenzione: hanno
line ending CRLF; gli stessi blob dentro git sono normalizzati a LF e danno
hash diversi — usare i file checked-out, non `git show`):

| Artefatto | SHA-256 |
|---|---|
| `research/FROZEN_METHOD.json` | `b02ba527…82518f` |
| `research/fx_pressure_engine.py` | `b1a76be3…49bed6` |
| `research/fx_pressure_evaluation.py` | `58604fd2…fda329ab` |
| `scripts/run_pair_prewake_audit.py` | `71fab163…8f9854b7` |
| `research/pair_prewake_audit.py` | `80762b01…438a04d` |

Le copie sotto `Output\FX_Pressure_Definitive_2026-08-17\research\` sono di una
versione **precedente** e non corrispondono al fingerprint. Non usarle.

---

## 3. Il modello

Artefatto immutabile: `prewake/models/pair_prewake_v1.json`.
Contiene `model_name`, `model_version`, commit e fingerprint di ricerca,
training cutoff, ordine feature, trasformazioni, coefficienti, intercetta,
scaler, threshold, parametri EWMA/lifecycle/reset e `artifact_hash`.

`prewake/model.py` **ricalcola l'hash a ogni load** e rifiuta un artefatto
manomesso (`ArtifactError`). Non esiste alcuna funzione di fit nel modulo.

| Campo | Valore |
|---|---|
| Stimatore | logistic L2, `C=1.0`, `lbfgs`, `max_iter=400`, `random_state=20260817` |
| Intercetta | `-0.4159863092887988` |
| Threshold | `0.5965942096795052` (quantile OOS di sviluppo `0.996`) |
| Training cutoff | index `40084` = `2025-01-06T22:00:00+00:00`, purge/embargo 24 H1 |
| Refit | uno solo, su development fino a `dev_end-24`, con la `C` modale dei fold |

Ordine feature (immutabile):
`dir_ret1, dir_ret4, dir_ret12, dir_ret24, abs_pair_z, compression_ratio, pair_vol120, fx_bias_same`

Standardizzazione esplicita `(x - mean) / scale` con mean/scale congelati, poi
`logit = coef @ z + intercept`, clip a `[-40, 40]`, sigmoide.

**La produzione non addestra mai. Solo `predict` / `score`.**

### Perché esiste un solo artefatto

La ricerca ha due percorsi di scoring: `walk_forward_cube()` produce predizioni
**per-fold** (campione `DEVELOPMENT_WALK_FORWARD`, 1.185 eventi) e
`score_from_frozen_model()` usa **un solo modello serializzato**
(`FROZEN_METHOD.json → methods.LOGIT_BASE.model`, campione
`PREVIOUSLY_SEEN_FINAL_HOLDOUT`, 1.104 eventi). I numeri di riferimento
(1.104 alert, 702 breakout) vengono interamente dal secondo. L'artefatto
destinabile al live è quindi unico e non ambiguo.

---

## 4. Direzione e feature

```
direction = sign( EWMA_half_life_4( robust_z_prior_240( OLS_LOPO_gap_1H ) ) )
```

- `OLS_LOPO_gap` = rendimento 1H della coppia meno la sua ricostruzione
  cross-currency stimata **escludendo la coppia stessa** (leave-one-pair-out,
  vincolo a somma zero sugli 8 indici valutari).
- `robust_z_prior(·, 240)` = mediana/MAD sulle **240 barre precedenti**,
  scala `max(1.4826 · MAD, 1e-12)`.
- `EWMA` half-life 4, **ricorsiva, inizializzata alla prima osservazione finita
  della serie e mai resettata**.

Le otto feature sono costruite in `prewake/features.py` con le primitive
congelate di `prewake/primitives.py`, che sono port fedeli del motore di
ricerca.

---

## 5. `fx_bias_same` — audit forense

Questo è il punto su cui la specifica iniziale era sbagliata, quindi va detto
esplicitamente.

```
fx_bias      = where(compressed, fresh_breakout, 0)
compressed   = range(12 barre precedenti) <= quantile 0.20 dei 120 range precedenti
fresh_breakout = close[t] fuori dal max/min delle 12 barre PRECEDENTI,
                 e lo stato grezzo precedente non era già lo stesso
fx_bias_same = 1.0 se fx_bias[t] == sign(EWMA4[t]), altrimenti 0.0
```

**Semantica precisa:** rottura grezza *fresca*, sulla **barra corrente**, in
**regime di compressione**, nella **stessa direzione** del segno di EWMA4 del
gap OLS-LOPO.

**Dipendenza dal motore FX Bias: NESSUNA.** È una funzione pura del prezzo
calcolata dentro il motore congelato. Non legge `fx_bias_radar/engine.py`, non
legge ROT/RESUME, non legge il detector H4, non legge alcuno stato del prodotto.
L'unico import della ricerca da produzione è la lista delle 28 coppie.

Conseguenze pratiche:

- la firma del motore è `evaluate(bar_times, close, high, low, …)`: **non** riceve
  `fx_bias_state`, e passarglielo cambierebbe il modello;
- l'ordine nello scheduler è indifferente: PREWAKE può girare prima, dopo o in
  parallelo a FX Bias;
- **non** si può dire "il modello PREWAKE usa una feature FX Bias", ma **neanche**
  "due motori completamente indipendenti": consumano lo stesso feed OANDA H1 e
  `fx_bias_same` è concettualmente lo stesso fenomeno (rottura fresca in
  compressione) che FX Bias osserva, ricalcolato in modo autonomo.

**Verdetto no-lookahead: PASS.** Tutte le finestre usano `lag 1…N` o
`windows[:, :-1]`, quindi escludono il valore corrente dalla propria storia; il
solo dato della barra `t` usato è la sua chiusura, nota alla chiusura di `t`.

**Dato empirico:** su 1.104 alert storici, `fx_bias_same == 1` in **0 casi**.
Con coefficiente `-1.8776` la feature è di fatto un **soppressore**: il modello
non allerta mai su una barra che ha già la rottura fresca in compressione nella
stessa direzione. È esattamente la semantica "pre-wake". La feature **non va
rimossa**: toglierla produrrebbe un modello diverso.

---

## 6. Lifecycle

Eventi: `NEW_WAKE`, `REAWAKENING`.

Reset (uno qualsiasi):
- cambio di direzione;
- **quattro** H1 consecutive con score `< 0.70 × threshold`;
- score non finito.

Un segnale che resta sopra soglia per cinque ore genera **un solo** evento.

### Semantica di NEW_WAKE — leggere prima di modificare qualunque cosa

Nel motore congelato `NEW_WAKE` significa **primo start di lifecycle in assoluto
per quella (coppia, direzione) su tutta la serie scorata**, non "primo dopo
reset". Il flag viene consumato anche se lo start cade fuori dalla finestra di
emissione. Tutti i 1.104 eventi di holdout sono infatti `REAWAKENING`, zero
`NEW_WAKE`.

Conseguenze:
- dopo il seeding dalla storia completa, **56/56** slot (28 coppie × 2 direzioni)
  hanno già "sparato": ogni alert live sarà `REAWAKENING`;
- l'`event_type` dipende da dove inizia la storia scorata, quindi la parità
  richiede di fissare l'**origine** del warm-up, non solo la sua lunghezza;
- per questo email e UI usano un'unica etichetta neutra `PREWAKE`, mentre
  l'etichetta congelata resta nel ledger per audit e parità.

Due implementazioni devono sempre coincidere:
`batch_lifecycle_events` (port fedele, usato dal parity test) e `advance`
(incrementale, usato in produzione). Il test
`TestIncrementalEqualsBatch.test_random_scenarios_agree` le confronta su
scenari casuali.

---

## 7. Warm-up e stato

Vincoli di finestra: `robust_z` 240, compression 12+120 = 132, `pair_z`/`vol` 120,
`ret24` 24, breakout 12. **Score valido dalla barra 241.**

L'EWMA è ricorsiva e senza reset, quindi dipende dall'origine della serie.
La produzione risolve così:

1. `scripts/prewake_seed.py --from-frozen MID BA` replaya **una volta** l'intera
   storia congelata (50.105 H1, 2018-07-25 → 2026-08-17) e scrive
   `reports/prewake/prewake_state.json` (~7 KB): stato EWMA per coppia, stato
   lifecycle per (coppia, direzione), ultima barra processata;
2. ogni run orario carica lo stato, scarica una finestra di 400 H1, calcola le
   feature finestrate su tutta la finestra ma **avanza EWMA e lifecycle solo
   sulle barre nuove**, poi risalva lo stato.

Questo rende un run incrementale numericamente identico a un replay completo.
Verificato: 240 run orarie simulate = replay offline, zero differenze, zero
duplicati (`scripts/prewake_shadow_replay.py`).

⚠️ Le barre della finestra precedenti a quelle nuove sono **solo lookback**. Non
devono mai essere rifornite all'EWMA né al lifecycle una seconda volta.

---

## 8. Dati

- Fonte: pipeline OANDA già esistente di FX Bias
  (`fx_bias_radar.strength_h1.fetch_all_h1`). Nessun secondo downloader.
- Granularità **H1**, prezzo **M (MID)**, **solo barre `complete=true`**.
  Coincide con la convenzione della ricerca (il BID/ASK serviva solo per lo
  spread, che non entra in nessuna delle otto feature).
- Griglia = **intersezione dei timestamp di apertura barra su tutte le 28
  coppie** (policy della ricerca). Se la barra più recente non è presente per
  tutte, il run registra `SKIPPED_INCOMPLETE_INPUT` e il job successivo ritenta.
  Non si produce mai un segnale con dati parziali.
- Universo: `fx_bias_radar.pairs` — 28 coppie, 8 valute. La ricerca importa
  **lo stesso modulo**, quindi la parità di universo è strutturale.

Differenza documentata: la ricerca intersecava anche i timestamp BID/ASK. La
produzione interseca solo il MID. Lo spread non entra nel modello, ma il set di
barre ai margini può differire di pochissimo.

---

## 9. Timestamp

Internamente **UTC**, sempre timezone-aware. In UI ed email **Europe/Rome**.
L'alert si riferisce alla **chiusura** della H1, cioè un'ora dopo l'apertura
barra: una barra aperta 09:00 UTC chiude 10:00 UTC = 12:00 Europe/Rome in estate.

---

## 10. Scheduler

Workflow **separato**: `.github/workflows/prewake.yml`, cron `10 * * * *`
(HH:10, cinque minuti dopo il job FX Bias `pre_rottura`).

Motivo: isolamento totale (§48). Un errore PREWAKE non può toccare FX Bias
perché gira in un job diverso. È possibile perché PREWAKE non legge alcuno
stato FX Bias.

```
OANDA H1 fetch
  ↓ verifica griglia comune completa
  ↓ avanza stato congelato (EWMA + lifecycle)
  ↓ persiste run + eventi (append-only, idempotente)
  ↓ notifiche
  ↓ outcome tracking prospettico
  ↓ commit del ledger
```

---

## 11. Persistenza

FX Bias non ha database: lo stato è file committati su git e serviti in lettura
dalle function Vercel. PREWAKE usa lo stesso substrato.

| File | Natura |
|---|---|
| `reports/prewake/prewake_events.jsonl` | **append-only, immutabile** |
| `reports/prewake/prewake_runs.jsonl` | append-only |
| `reports/prewake/prewake_email.jsonl` | append-only, vince il record più recente per `event_id` |
| `reports/prewake/prewake_outcomes.jsonl` | append-only |
| `reports/prewake/prewake_fx_bias_links.jsonl` | append-only |
| `reports/prewake/prewake_corrections.jsonl` | append-only, per correzioni tecniche auditate |
| `reports/prewake/prewake_state.json` | **unico file mutabile** (EWMA + lifecycle) |
| `reports/prewake/prewake_latest.json` | derivato, rigenerato |
| `reports/prewake/prewake_health.json` | derivato, rigenerato |

Un evento **non viene mai riscritto** perché ha fallito, si è invertito, non è
stato tradato o ValutaVision era contrario. Tutto ciò che è mutabile
(consegna email, maturazione outcome, link a FX Bias) vive in un log laterale
proprio. Le correzioni tecniche sono append-only.

**Idempotenza:** `event_id = sha256(model_version | pair | bar_time_utc |
event_type | direction)[:32]`. Lo stesso H1 non può produrre due eventi identici.

---

## 12. Email

Riusa l'SMTP Gmail di FX Bias (`FXBR_GMAIL_USER`, `FXBR_GMAIL_APP_PASSWORD`,
`FXBR_DIGEST_TO`; opzionale `FXBR_PREWAKE_TO`). Nessun secondo sistema SMTP.
**Le email FX Bias non sono state toccate.**

Subject: `[PREWAKE] GBPCHF LONG — 10:00`

Vietati nel corpo: BUY, SELL, ENTRY, STOP, TARGET, qualunque raccomandazione
operativa. Vietato esporre token, credenziali, stack trace (§62): un errore
SMTP registra solo il tipo di eccezione.

**Idempotenza:** `prewake:{model_version}:{event_id}`. Se SMTP fallisce
l'evento resta nel ledger, lo stato email diventa `RETRY` e il run successivo
ritenta — senza mai duplicare l'evento.

**Nessun backfill email:** gli eventi storici sono `is_backfill=true`,
`is_prospective=false`, e il loro stato email è `SUPPRESSED_BACKFILL`. Non
possono essere inviati.

---

## 13. Prospective start

`prospective_start_at` è `null` finché le email non vengono realmente
abilitate. Solo gli eventi con `bar_time_utc >= prospective_start_at` sono
`PROSPECTIVE`; tutti gli altri sono `HISTORICAL/BACKFILL`.

Il freeze della ricerca (17/08/2026 20:19 Europe/Rome) **non** è lo start della
raccolta live.

---

## 14. Feature flag

Consentiti, e solo operativi:

```
PREWAKE_ENGINE_ENABLED
PREWAKE_EMAIL_ENABLED
PREWAKE_UI_ENABLED
```

Vietati, e attivamente rifiutati da `config.assert_no_model_overrides()` che
solleva un errore all'avvio:

```
PREWAKE_THRESHOLD  PREWAKE_EWMA  PREWAKE_RESET
PREWAKE_COEFFICIENTS  PREWAKE_INTERCEPT  PREWAKE_FEATURES
```

---

## 15. COSA NON DEVE ESSERE MODIFICATO

Il candidato è **FROZEN**. Modificarlo invalida la validazione prospettica in
corso e obbliga a una nuova `model_version`.

- threshold `0.5965942096795052`;
- i 9 numeri del modello (intercetta + 8 coefficienti) e mean/scale;
- l'ordine e la definizione delle 8 feature;
- `fx_bias_same` — **non rimuoverla**, anche se la dipendenza sembra poco
  elegante: farne a meno produce un modello diverso;
- EWMA half-life 4 e la sua natura ricorsiva senza reset;
- `robust_z_prior` finestra 240, `1.4826 · MAD`;
- compression 12 / 120 / q=0.20, breakout 12;
- lifecycle, reset 4 barre a 0.70 × threshold, semantica di `NEW_WAKE`;
- l'universo delle 28 coppie e delle 8 valute.

Non aggiungere: nuovi filtri, dual-leg come requisito, compression-expansion,
CUSUM, BOCPD, Shiryaev–Roberts. Non riaddestrare. Non "sistemare" il modello
perché non prende EURNZD: **non prenderlo è il comportamento corretto**.

`same_bar_raw_breakout` resta **solo diagnostica**: non sopprime mai il segnale.
Se il motore congelato avrebbe emesso quei quattro eventi lead-0, deve
continuare a emetterli.

Se un giorno nasce una V2, deve chiamarsi `pair-prewake-v2` e coesistere
storicamente con V1. Mai sovrascrivere `pair-prewake-v1`.

---

## 16. Parità storica

`scripts/prewake_parity.py` confronta il motore di produzione con il ledger
congelato della Phase 1, evento per evento.

```
production events : 1104
research events   : 1104
matched=1104  only_production=0  only_research=0
score parity : max|diff| = 4.441e-16   (tolleranza richiesta 1e-12)
feature parity: max 6.3e-16 su abs_pair_z, 0.0 su compression_ratio e fx_bias_same
GOLDEN §54 : 1104 alert, 702 breakout +1…+12
GOLDEN §55 : EURNZD max 0.585555 < 0.596594 → NO ALERT
GOLDEN §56 : 4 eventi same-bar riconosciuti
PARITY RESULT: ZERO DIFFERENCES
```

`scripts/prewake_shadow_replay.py` verifica che l'esecuzione incrementale
oraria coincida con il replay offline: 240 run simulate, zero differenze, zero
duplicati, ogni secondo passaggio sullo stesso H1 correttamente saltato.

---

## 17. Runbook

```bash
# seed una tantum (richiede i pickle congelati)
python scripts/prewake_seed.py --from-frozen <mid.pkl.gz> <ba.pkl.gz> --backfill-from 2026-05-17

# parità storica
python scripts/prewake_parity.py --mid <mid> --ba <ba> --golden pair_prewake_events.csv

# shadow offline
python scripts/prewake_shadow_replay.py --mid <mid> --ba <ba> --bars 240

# run orario (in CI)
python scripts/run_prewake.py --oanda

# outcome prospettici
python scripts/prewake_outcomes.py --oanda
```

---

## 18. Rollback

1. `PREWAKE_EMAIL_ENABLED=false` → smettono le email, gli eventi continuano;
2. `PREWAKE_ENGINE_ENABLED=false` → il motore non gira più.

Nessuno dei due tocca FX Bias. Non ci sono migration distruttive: PREWAKE
scrive solo file nuovi sotto `reports/prewake/`. Per un rollback completo basta
disabilitare il workflow `prewake-h1`; i file restano come dati di ricerca.
