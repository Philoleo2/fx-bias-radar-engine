# prewake-data — ledger di PAIR_PREWAKE_V1

Branch **dati**, non codice. Contiene esclusivamente lo stato e il ledger del
motore PREWAKE, scritti dal workflow `prewake-h1`.

Esiste separato da `main` per una ragione precisa: `pre_rottura.yml` scrive su
`main` ogni ora con un `git push` nudo, senza `pull` né retry. Due scrittori
sullo stesso ref significano, prima o poi, un push respinto e un report perso.
Con ref distinti la contesa è impossibile per costruzione, e il comportamento di
FX Bias resta esattamente quello di sempre.

Regole:

- qui non finisce mai codice, e mai nulla sotto `reports/prerottura/`;
- `prewake_events.jsonl` è append-only e immutabile: un evento non viene
  riscritto perché ha fallito o non è piaciuto;
- `prewake_state.json` è l'unico file mutabile (EWMA ricorsiva + lifecycle);
- nessun force-push, mai.

Stato iniziale: seed della storia congelata completa (50.105 H1,
2018-07-25 -> 2026-08-17), fingerprint del modello
`6c767bcbc66f9719d9c4e47ff2756dc789901568f587772f1a27180f8872bd17`.
