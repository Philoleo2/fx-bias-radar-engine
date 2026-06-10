# M1 Python port - note di merge per Codex

Data: 2026-06-10 (rev. 2 dopo review Codex)
Autore: Claude (Sonnet)
Sorgente del porting: `FX_Bias_Radar_Production_v1_1.pine` (715 righe), 1:1.
Stato: unit test PASS (0 fail); golden test pronti ma SKIP finche' mancano le
fixtures; smoke test end-to-end (28 coppie sintetiche -> report) PASS.

## Correzioni recepite dalla review Codex (2026-06-10)

- FINDING 1 RISOLTO: `scan.yml` ha lo schedule COMMENTATO; al merge non si
  attiva nessun cron. Resta solo `workflow_dispatch` per i run manuali di
  parita'. De-commentare lo schedule SOLO dopo il gate M1.
- FINDING 2 RISOLTO: `env_credentials()` ora risolve in ordine (1) variabili
  d'ambiente (i secrets di Actions vincono), (2) loader M0
  `fx_bias_radar.config.load_oanda_config()` se presente nel repo merged
  (duck-typing su dict/oggetto), (3) file `.env` in cwd/root repo. In locale
  basta il `.env` gia' compilato da Leonardo. Test dedicati in
  `tests/test_credentials.py` (si auto-skippano se il repo fornisce gia'
  credenziali reali).
- Cache `__pycache__` esclusa dal pacchetto zip (usare lo ZIP come sorgente
  del merge; se si copia la cartella, NON stagiare le cache - la .gitignore
  M0 le ignora gia').
- Golden flat: aggiunta la nota di ampiezza (giornata intera vs screenshot
  puntuale) nel docstring; in caso di fail con fixtures reali verificare
  prima l'ampiezza del test, poi il motore.

## Contenuto del drop

```text
fx_bias_radar/
  __init__.py
  pine_series.py     # primitive Pine-equivalenti (sma/stdev POP/ema/highest/cross/nz)
  pairs.py           # 28 coppie + formule indici simmetrici (P:226-265)
  candles.py         # modello candela, allineamento UTC, fixtures I/O (M1.1)
  currency_index.py  # momentum EMA20 -> 8 indici -> z/slope/vel/state/score/rank (M1.2)
  engine.py          # state machine v1.1 completa (M1.3) - riferimenti P:<riga>
  focus.py           # focus list dal motore VERO (cluster-cap 2, max 5, no pin)
  report.py          # report Markdown + JSON per run (M1.5)
  oanda_fetch.py     # client dati REST v20 (stdlib) - SOLO endpoint dati
scripts/
  run_h4_scan.py     # scan completo 28 coppie (fixtures o OANDA live)
  build_fixtures.py  # costruisce le fixtures golden (.env o env var, locale)
tests/
  helpers_synthetic.py      # generatore PairFrame sintetici
  test_pine_series.py       # primitive
  test_engine_mechanisms.py # 12 test: ogni meccanismo validato FR006..FR025
  test_credentials.py       # risoluzione credenziali (Finding 2)
  test_golden_cases.py      # casi-verita' ACCEPTANCE_TESTS_M1 (skip senza fixtures)
.github/workflows/scan.yml  # cron H4 COMMENTATO - attivare solo dopo gate M1
```

## Come fare il merge nel repo `fx-bias-radar-engine`

1. Sorgente canonica = `fx-bias-radar-engine-M1.zip` (niente cache dentro).
   Copiare le cartelle nel root del repo (accanto al package M0).
2. CONFLITTO ATTESO - client OANDA: esiste gia' il tuo modulo M0. Tenerne UNO:
   o si adatta `oanda_fetch.py` a usare il tuo client, o viceversa.
   L'interfaccia richiesta dal runner e': `fetch_all_pairs(token, env,
   count|from/to) -> dict[pair -> list[Candle]]` con coppie formato `EURUSD`.
   `env_credentials()` prova gia' il tuo `load_oanda_config()` se presente.
3. I test girano con il comando gia' in uso: `python -m unittest discover -s tests`
   (eseguito dal root del repo). CI esistente compatibile.
4. `tests/helpers_synthetic.py` non inizia per `test_` quindi non viene raccolto
   come test: e' un helper importato dai test dei meccanismi.

## Scelte di fedelta' (importanti per la review)

- Soglie INVARIATE, default identici al Pine: spreadMin 1.00, resumeScoreMin 55,
  neutralFloor 0.35, removeFloor 0.70, deadTakeoverMult 1.10,
  strongOppositeFloor 3.0, TTL 36, protective cap 120, resetBars 4,
  extensionMax 1.20, newBars 2, biasMemoryBars 36, dedup 20/1.15/+10.
- `ta.stdev` = deviazione standard di POPOLAZIONE (default Pine). Testato.
- `ta.ema` seed = primo valore valido; con fetch >= 400 barre la differenza
  dal calcolo full-history di TradingView e' trascurabile sulle barre recenti.
- Convenzione warmup: le finestre rolling restituiscono None finche' non hanno
  `length` valori validi -> i segnali partono dopo ~170 barre. RACCOMANDATO
  fetch 500 barre (default del runner); mai meno di 400.
- Ordine di esecuzione per barra identico al Pine: update regime vivo ->
  morte + salvataggio dead/protective peak -> stream eventi (anti-flip,
  post-death, strong-opposite) -> promozione/clear regime -> series memory ->
  display. Solo barre CHIUSE (confirmedBar implicito).
- Dead code v1.1 NON portato (non alimenta nulla): P:489 acceptedAge,
  P:493 dominantPeakActive, P:496 dominantExtended, P:519 postDeathDeadDirNum,
  P:520 acceptedSpreadPeak.
- Label dedup: portato come flag `label_shown` (display-only); il cap
  maxMarkerLabels (12) e' una questione di rendering TradingView, non di stato:
  non influisce su nessun output del motore.
- focus.py NON e' il porting dello scanner v1.3: e' la focus list calcolata
  dallo stato VERO del motore su tutte le coppie (la divergenza scanner
  sparisce). Ranking: stato (NUOVO>ATTIVO>ESTESO) -> score -> spread;
  cluster-cap 2 per valuta; max 5; nessun pin. Heuristics di display,
  da tarare con Leonardo nell'uso live (nota Codex: da validare in parita').

## Prossimi passi (gate M1)

1. Leonardo (locale, basta il .env): `python scripts/build_fixtures.py
   --start 2026-01-01 --out tests/fixtures/golden_2026H1`, poi commit fixtures.
2. Girano i golden test (ora SKIP): devono passare TUTTI. Se uno fallisce =
   HARD STOP (brief sez. 14): diagnosi insieme, nessun cambio al motore senza
   approvazione di Leonardo.
3. Parita' live 3-5 giorni: `python scripts/run_h4_scan.py --oanda` dopo le
   chiusure H4 e confronto a campione col pannello Pine v1.3 su TradingView.
   Divergenze decimali ok; divergenze di SEGNALE = bug.
4. Solo dopo il gate: de-commentare lo schedule in `scan.yml` e iniziare M2
   (Telegram).
