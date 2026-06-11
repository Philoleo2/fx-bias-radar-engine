# RUNBOOK M2C - Deploy Vercel (per Codex: solo esecuzione)

Data: 2026-06-11
Autore: Claude (Sonnet), supervisione FR035
Branch: codex/vercel-dashboard
Stato review: APPROVATO. Motore verificato identico al canonico M1
(engine/currency_index/pine_series/candles/focus/report byte-per-byte;
pairs.py solo additivo). 41/41 test verdi.

Unica modifica della supervisione (gia' nel working tree, da committare):
- `fx_bias_radar/scan_service.py`: `latest_report_path()` risolve i path
  relativi anche contro il root del repo -> il fallback sui report Actions
  funziona quando la cwd della function Vercel non e' il root (bug reale,
  verificato: prima falliva da cwd esterna, ora passa).
- `tests/test_scan_service_dashboard.py`: nuovo test del fallback
  cwd-indipendente.
- questo runbook in `docs/`.

## Step 0 - Commit della supervisione (PowerShell, dal root del repo)

```powershell
python -m unittest discover -s tests      # atteso: 41 OK
git add fx_bias_radar/scan_service.py tests/test_scan_service_dashboard.py docs/RUNBOOK_M2C_VERCEL_DEPLOY.md
git commit -m "M2 supervision Sonnet: cwd-independent Actions fallback + deploy runbook"
git push origin codex/vercel-dashboard
```

## Step 1 - Progetto Vercel

1. vercel.com -> Add New Project -> Import `Philoleo2/fx-bias-radar-engine`.
2. Framework Preset: **Other**. Nessun build command. Output: default
   (Vercel serve `public/` come static root e `api/*.py` come functions).
3. NON impostare il Production Branch su codex/vercel-dashboard: lasciare
   main; il branch genera automaticamente un PREVIEW deployment.
4. Verificare che Fluid Compute sia attivo (default sui progetti nuovi):
   serve per `maxDuration: 60` di `api/scan.py` sul piano Hobby.

## Step 2 - Environment Variables (Settings -> Environment Variables)

Scope: Production + Preview. MAI nel codice/repo.

```text
OANDA_ENV=practice
OANDA_ACCESS_TOKEN=<token OANDA di Leonardo>
DASHBOARD_TOKEN=<token privato scelto da Leonardo, lungo e non riusato>
CACHE_SECONDS=60
```

## Step 3 - Smoke test sul PREVIEW (URL del deployment di branch)

```text
GET /api/health            -> 200, has_oanda_token=true, has_dashboard_token=true
GET /api/scan (senza auth) -> 401 {"ok":false,"error":"unauthorized"}
GET /api/scan con header Authorization: Bearer <DASHBOARD_TOKEN>
                           -> 200 JSON: focus, 28 pairs, last_closed_h4_utc
```

Controlli aggiuntivi:
- tempo di risposta del primo /api/scan < 60s (atteso 5-20s col fetch concorrente);
- secondo refresh entro 60s -> `cache.hit: true`;
- DevTools -> Network: il token OANDA NON appare in nessuna risposta/header;
- header `Cache-Control: no-store` presente sulle risposte API.

Test del fallback (opzionale ma raccomandato, ora che il path e' fixato):
rimuovere temporaneamente `OANDA_ACCESS_TOKEN` dal Preview -> /api/scan deve
rispondere con `source: "GitHub Actions latest committed report"` + warning.
Poi RIPRISTINARE il token.

## Step 4 - Test di Leonardo da telefono (accettazione)

1. Aprire l'URL preview; inserire il DASHBOARD_TOKEN una volta.
2. Refresh -> focus cards leggibili, tabella 28 coppie, filtri.
3. Download JSON / CSV / Markdown funzionanti.
4. Disclaimer "Radar di attenzione: decisione sulle linee manuali" visibile.
5. Confronto a campione con pannello Pine v1.3 sulla stessa barra chiusa
   (vale anche come run di parita' live M1).

## Step 5 - Merge e chiusura

- Solo dopo accettazione Leonardo: merge `codex/vercel-dashboard` -> `main`
  (la produzione Vercel si aggiorna dal main).
- Lo schedule di `.github/workflows/scan.yml` resta COMMENTATO finche' la
  parita' live M1 non e' chiusa (target ~lun 15/06).
- M2D Telegram dopo il pass della parita', sullo stesso `scan_service`.

## Invarianti

Motore e soglie INTOCCABILI. Niente ordini/alert dal deploy. Il radar dice
dove guardare; la decisione resta sulle linee manuali.
