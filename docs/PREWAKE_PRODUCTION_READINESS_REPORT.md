# PREWAKE PRODUCTION READINESS REPORT

**Data:** 2026-08-17, Europe/Rome
**Motore:** `PAIR_PREWAKE_V1` / `pair-prewake-v1`
**Esito:** `READY FOR STEP A` — codice installabile con entrambi i flag OFF.
**NON ancora READY per le email:** manca l'osservazione shadow su barre live reali (STEP B/C) e il seed dello stato nel repo di produzione.

---

## 1. Git

| Voce | Valore |
|---|---|
| Production branch | `main` |
| Production parent | `60b841fff2f3977a6144fe876ae3610a0ce50c8b` (2026-08-17 18:53:27 UTC) |
| Implementation branch | `feature/pair-prewake-v1-live` |
| Implementation commits | `c998d01` (engine core), `774a7de` (integrazione) |
| Push | **non eseguito** — in attesa di autorizzazione |
| Worktree di ricerca | **non alterati** |

---

## 2. Provenienza e fingerprint

| Voce | Valore | Esito |
|---|---|---|
| Research source commit | `bfadfc98b2bed21377287d16b2eab5745f0fe8c3` | verificato in locale |
| Research parent | `5ef88c454eb8bd89f8fab37623ab94c21cb41f1c` | verificato |
| Research fingerprint | `6c767bcbc66f9719d9c4e47ff2756dc789901568f587772f1a27180f8872bd17` | **ricalcolato, MATCH** |
| Componenti del fingerprint | 4 SHA-256 su file su disco | **tutti MATCH** |
| Production artifact hash | `sha256:c90c95fca01a7028880ce28fbea4a49976bbc33564dd6fbc447794ff410f7b94` | verificato a ogni load |

---

## 3. Parità storica

`scripts/prewake_parity.py`, motore di produzione contro ledger congelato Phase 1.

```
production events : 1104
research events   : 1104
matched = 1104     only_production = 0     only_research = 0
```

| Test | Atteso | Ottenuto | Esito |
|---|---|---|---|
| Event parity | 1.104, zero differenze | 1.104, zero differenze | ✅ |
| Score parity | `abs(diff) <= 1e-12` | **max `4,441e-16`**, 1104/1104 entro soglia | ✅ |
| Feature parity | — | max `6,3e-16` (`abs_pair_z`); `0,0` su `compression_ratio` e `fx_bias_same` | ✅ |
| Lifecycle transition | identiche | incrementale vs batch: 0 differenze | ✅ |
| §54 event count | `1.104` | 1.104 | ✅ |
| §54 breakout `+1…+12` | `702` | 702 → precision `63,586957%` | ✅ |
| §55 EURNZD | `NO ALERT`, max `0,585555` | max `0,585555` < `0,596594`, 0 eventi | ✅ |
| §56 lead-0 | 4 eventi same-bar | 4, gli stessi del forensic audit | ✅ |

**`ZERO DIFFERENCES`.**

---

## 4. Regressione FX Bias

| Misura | Prima dell'integrazione | Dopo |
|---|---|---|
| Test FX Bias | 75, verdi | **75, verdi** |
| File FX Bias modificati | — | **nessuno** |

File toccati fuori da `prewake/`: solo `vercel.json`, con due righe additive
(header cache per le due pagine nuove, function `api/prewake.py`). Nessuna
modifica a `fx_bias_radar/`, `scripts/run_pre_rottura.py`, `scripts/send_digest.py`,
`.github/workflows/pre_rottura.yml`, `api/pre_rottura.py`, `public/pre_rottura.js`.

Nessun test esistente è stato rimosso, saltato o indebolito.

---

## 5. Test

| Suite | Test |
|---|---|
| FX Bias esistente | 75 |
| PREWAKE nuovi | **55** |
| Totale | **130, tutti verdi** |

Copertura §57: orientamento coppie, OLS-LOPO (incluso il vincolo
leave-one-pair-out e la ricostruzione esatta di un set coerente), EWMA4 batch vs
incrementale, ordine feature, trasformazioni, score del modello, confronto con
la soglia, `fx_bias_same` (semantica e assenza di lookahead per troncamento del
futuro), dati mancanti, completezza H1, lifecycle `NEW_WAKE`/`REAWAKENING`,
reset per cambio direzione, reset a quattro barre sotto il 70%, nessun evento
duplicato, backfill senza email, email live una sola volta, timestamp
prospettico, linking FX Bias, maturazione outcome, timezone,
idempotenza su restart/replay, rifiuto di artifact manomesso, rifiuto di
override del modello via environment.

Copertura §58, casi A–K: A nessun alert · B superamento soglia → evento ·
C cinque barre sopra soglia → una sola emissione · D reset dopo quattro H1 sotto
il 70% · E riattivazione · F cambio direzione · G FX Bias 3 H1 dopo ·
H email fallita e ritentata senza duplicare l'evento · I stesso H1 processato
due volte · J barra cross-currency assente → `SKIPPED_INCOMPLETE_INPUT` ·
K restart e ricostruzione lifecycle.

---

## 6. Shadow (offline)

`scripts/prewake_shadow_replay.py` — 240 run orarie simulate attraverso il
percorso reale di produzione (stato persistito → JSON → ricaricato → avanzato →
append idempotente), confrontate con un unico replay completo.

```
full-replay events over the window : 29
shadow incremental events          : 29
second passes correctly skipped    : 240/240
only_full_replay = 0   only_shadow = 0   duplicates = 0
SHADOW RESULT: IDENTICAL TO OFFLINE REPLAY
```

**H1 live processate: 0.** Questo è shadow *offline*. STEP B e STEP C su barre
reali non sono ancora stati fatti.

---

## 7. Performance

`evaluate()` su finestra di 400 barre × 28 coppie: **~360 ms** (min 332, max 392).
A 300 barre ~223 ms, a 600 barre ~631 ms.

Il job gira in un workflow separato, quindi non aggiunge nulla al ciclo FX Bias.
Ogni run registra `model_eval_ms` e `total_prewake_ms` in `prewake_runs.jsonl`.

---

## 8. Persistenza

Nessuna migration di database, perché **non esiste un database**: FX Bias
persiste su file committati e serviti in lettura da Vercel. PREWAKE usa lo
stesso substrato, con file **nuovi** sotto `reports/prewake/`.

Tabelle aggiunte: nessuna. File aggiunti:

```
prewake_events.jsonl        append-only, immutabile      (SS29, SS41)
prewake_runs.jsonl          append-only                  (SS28)
prewake_email.jsonl         append-only, latest-per-event(SS34)
prewake_outcomes.jsonl      append-only                  (SS38-SS40)
prewake_fx_bias_links.jsonl append-only                  (SS36, SS37)
prewake_corrections.jsonl   append-only, auditato        (SS41)
prewake_state.json          unico file mutabile
prewake_latest.json         derivato
prewake_health.json         derivato
```

**Rollback testato:** il rollback è la disabilitazione dei due flag e/o del
workflow. Nessuna tabella FX Bias è stata modificata, nessuno schema esistente è
stato toccato, quindi non esiste alcuno stato da annullare. I file PREWAKE
restano come dati di ricerca.

Stato attuale del ledger locale: **169 eventi di backfill**
(`2026-05-18` → `2026-08-13`), tutti `is_backfill=true`, `is_prospective=false`,
email `SUPPRESSED_BACKFILL`. Zero eventi prospettici.

---

## 9. Email

| Voce | Valore |
|---|---|
| Infrastruttura | SMTP Gmail esistente di FX Bias, nessun secondo sistema |
| Template | `[PREWAKE] {PAIR} {LONG/SHORT} — {HH:MM}`, corpo minimale in Europe/Rome |
| Linguaggio | vietati BUY/SELL/ENTRY/STOP/TARGET — verificato da test |
| Idempotency key | `prewake:{model_version}:{event_id}` |
| Retry | stato `RETRY` nel log append-only, ritentato al run successivo, mai duplica l'evento |
| Backfill | mai inviate (`SUPPRESSED_BACKFILL`) |
| Sicurezza | nessun token, credenziale o stack trace nel corpo o nei file (§62) |
| Email FX Bias | **non modificate** |
| Dry-run eseguito | sì, in test (`deliver(..., dry_run=True)` e mock SMTP) |

---

## 10. Deployment e flag

```
PREWAKE_ENGINE_ENABLED = false
PREWAKE_EMAIL_ENABLED  = false
```

Da impostare come **repository variables** su GitHub (non secrets: non sono
segreti). Il workflow `prewake-h1` legge `vars.PREWAKE_ENGINE_ENABLED` e
`vars.PREWAKE_EMAIL_ENABLED`. Con i flag assenti o `false` il job non fa nulla e
registra `DISABLED`.

Parametri del modello in environment: **rifiutati attivamente**
(`config.assert_no_model_overrides()` solleva un errore all'avvio).

---

## 11. Prospective start

`prospective_start_at = null`.

Verrà valorizzato **soltanto** nel momento in cui `PREWAKE_EMAIL_ENABLED` viene
messo a `true` (STEP D). Il freeze della ricerca del 17/08/2026 non viene usato
retroattivamente.

---

## 12. Cosa manca prima delle email

1. **Push del branch** e apertura PR (non fatto: serve la tua autorizzazione).
2. **Seed dello stato nel repo di produzione.** Va eseguito
   `scripts/prewake_seed.py --from-frozen` sulla tua macchina, dove stanno i
   pickle congelati, e committato `reports/prewake/prewake_state.json` (~7 KB).
   Senza seed il run orario si ferma con `NOT_SEEDED` per costruzione.
3. **STEP A** — deploy con entrambi i flag OFF; verificare import, test, FX Bias
   invariato.
4. **STEP B** — `PREWAKE_ENGINE_ENABLED=true`, email OFF. Osservare almeno un
   ciclo H1 completo: score, timing, assenza di duplicati, lifecycle,
   performance, errori.
5. **STEP C** — confrontare alcune barre live con l'esecuzione offline dello
   stesso motore. Devono coincidere.
6. **STEP D** — abilitare le email e registrare `prospective_start_at`.

---

## 13. Verdetto

```
Historical parity ........ ZERO DIFFERENCES
Score parity ............. 4,441e-16  (richiesto <= 1e-12)
Event parity ............. 1104 / 1104
Golden tests ............. 4/4
FX Bias regression ....... 0 differenze, 75/75 verdi
Tests .................... 130/130 verdi
DB migration ............. nessuna (nessun DB); solo file nuovi
Rollback ................. due flag, nessun impatto su FX Bias
Shadow offline ........... identico al replay
Shadow live H1 ........... 0 barre  <-- da fare
Email dry-run ............ ok (test)
Prospective start ........ non fissato, corretto

READY:      STEP A (deploy con flag OFF)
NOT READY:  abilitazione email
```
