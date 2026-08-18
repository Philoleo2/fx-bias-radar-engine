#!/usr/bin/env bash
# Vercel Ignored Build Step — salta il deploy per i commit di soli dati.
#
# Contesto: Vercel e' Git-linked su main con production branch main. Il cron
# orario di FX Bias committa su main soltanto i propri report, e ogni push
# ritriggerava un deploy production completo: ~24 build al giorno per file che
# le function leggono a runtime da GitHub raw, non dal bundle.
#
# SEMANTICA VERCEL (non invertire):
#   exit 0 -> IGNORA il build
#   exit 1 -> ESEGUI il build
#
# Criterio: confronto dei FILE modificati, non il testo del messaggio di commit.
# "[skip ci]" e' troppo fragile: un commit di codice con quel marcatore nel
# messaggio non verrebbe deployato.
#
# FAIL-SAFE: qualunque dubbio -> BUILD. Ogni percorso di errore (range git non
# determinabile, commit irraggiungibile in un clone shallow, diff vuoto,
# percorso sconosciuto) esce 1. Un deploy di troppo costa qualche minuto; un
# deploy mancato lascia la produzione indietro rispetto al codice.
#
# Uso in test: passare i percorsi come argomenti salta la parte git e classifica
# soltanto quella lista.
#   bash scripts/vercel_ignore_build.sh reports/prerottura/fase4_log.csv

set -u

# --- percorsi considerati SOLO DATI -----------------------------------------
# Volutamente stretti. reports/prewake/ su main e' seed-support: il ledger vero
# vive sul branch prewake-data. Nota: api/prewake.py include reports/prewake/**
# nel proprio bundle come fallback, quindi saltare il build lascia quel fallback
# indietro finche' non arriva un build successivo. Accettabile perche' il
# percorso primario della function e' la lettura da GitHub raw su prewake-data.
DATA_ONLY_PREFIXES=(
  "reports/prerottura/"
  "reports/prewake/"
)

is_data_only_path() {
  local path="$1"
  case "$path" in
    *..*) return 1 ;;                      # path traversal: mai fidarsi
  esac
  local prefix
  for prefix in "${DATA_ONLY_PREFIXES[@]}"; do
    case "$path" in
      "$prefix"*) return 0 ;;
    esac
  done
  return 1
}

decide() {
  local files="$1"
  if [ -z "$files" ]; then
    echo "BUILD: nessun file rilevato nel diff (fail-safe)"
    return 1
  fi
  local path
  while IFS= read -r path; do
    [ -z "$path" ] && continue
    if ! is_data_only_path "$path"; then
      echo "BUILD: modificato un file non-dati -> $path"
      return 1
    fi
  done <<< "$files"
  echo "IGNORE: solo file dati/report"
  while IFS= read -r path; do
    [ -n "$path" ] && echo "  - $path"
  done <<< "$files"
  return 0
}

# --- modalita' test: percorsi espliciti come argomenti -----------------------
if [ "$#" -gt 0 ]; then
  if decide "$(printf '%s\n' "$@")"; then exit 0; else exit 1; fi
fi

# --- modalita' Vercel: ricava i file dal range git ---------------------------
have_commit() { git cat-file -e "${1}^{commit}" 2>/dev/null; }

BASE=""
HEAD_SHA="${VERCEL_GIT_COMMIT_SHA:-HEAD}"

if ! have_commit "$HEAD_SHA"; then
  echo "BUILD: commit corrente non raggiungibile ($HEAD_SHA) (fail-safe)"
  exit 1
fi

# VERCEL_GIT_PREVIOUS_SHA = ultimo deployment andato a buon fine. E' il
# confronto corretto: se una serie di commit dati viene saltata, il successivo
# commit di codice viene comunque confrontato con cio' che e' realmente in
# produzione, non solo con il commit precedente.
if [ -n "${VERCEL_GIT_PREVIOUS_SHA:-}" ] && have_commit "$VERCEL_GIT_PREVIOUS_SHA"; then
  BASE="$VERCEL_GIT_PREVIOUS_SHA"
  echo "range: ultimo deployment $BASE -> $HEAD_SHA"
elif have_commit "${HEAD_SHA}^"; then
  BASE="${HEAD_SHA}^"
  echo "range: commit precedente $BASE -> $HEAD_SHA (VERCEL_GIT_PREVIOUS_SHA non utilizzabile)"
else
  echo "BUILD: impossibile determinare un commit di confronto (clone shallow?) (fail-safe)"
  exit 1
fi

if ! FILES="$(git diff --name-only "$BASE" "$HEAD_SHA" 2>/dev/null)"; then
  echo "BUILD: git diff fallito (fail-safe)"
  exit 1
fi

if decide "$FILES"; then exit 0; else exit 1; fi
