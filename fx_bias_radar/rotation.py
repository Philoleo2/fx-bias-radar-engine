"""M4 - Rilevatore di ROTAZIONE della forza valutaria (display/selezione, H1).

Obiettivo (richiesta di Leonardo): segnalare quando la valuta FORTE e la valuta
DEBOLE di una coppia iniziano a ruotare l'una verso l'altra (la forte molla, la
debole recupera) = inversione da estremo dello spread di forza H1. Timing
CENTRATO: ne' troppo presto ne' troppo tardi. La campana sul prezzo e l'ingresso
li decide Leonardo sul grafico. NON tocca il motore H4 ne' le sue soglie.

Spread di forza di una coppia: sp = z_base - z_quote (sulle chiusure H1).
- sp molto positivo  -> base forte, quote debole (coppia in alto)
- sp molto negativo  -> base debole, quote forte (coppia in basso)
Rotazione SHORT = sp gira giu' da un estremo positivo (base molla + quote recupera).
Rotazione LONG  = sp gira su  da un estremo negativo.

Due funzioni:
- label_pivots(): verita' a POSTERIORI (swing high/low confermati) per il backtest.
- detect_at()/detect_rotations(): regola CAUSALE (solo barre passate), parametrica,
  usata sia nel backtest sia live (segnale sull'ultima barra chiusa).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional

Num = Optional[float]


def _val(x: Num) -> Optional[float]:
    return x if isinstance(x, (int, float)) else None


def slope(series: List[Num], t: int, n: int) -> Optional[float]:
    """Pendenza semplice sulle ultime n barre fino a t: (s[t]-s[t-n])/n."""
    if t - n < 0:
        return None
    a, b = _val(series[t - n]), _val(series[t])
    if a is None or b is None:
        return None
    return (b - a) / n


def ema_at(series: List[Num], t: int, n: int) -> Optional[float]:
    """EMA causale di lunghezza n calcolata fino alla barra t."""
    if t < 0:
        return None
    k = 2.0 / (n + 1.0)
    e: Optional[float] = None
    start = max(0, t - 4 * n)
    for i in range(start, t + 1):
        v = _val(series[i])
        if v is None:
            continue
        e = v if e is None else (v * k + e * (1 - k))
    return e


@dataclass
class RotParams:
    ext_min: float = 2.0        # magnitudine minima dell'estremo |spread|
    k_window: int = 12          # finestra per individuare il picco recente
    recent: int = 4             # il picco deve essere entro queste barre da t
    conf_bars: int = 2          # barre di conferma del giro
    method: str = "slope_both"  # "slope_both" | "ema_cross" | "drop"
    drop_min: float = 0.5       # method "drop": calo minimo dal picco
    ema_len: int = 6            # method "ema_cross"
    cooldown: int = 6           # barre minime tra due segnali sulla stessa coppia


def _peak_recent(sp: List[Num], t: int, k: int, recent: int, sign: int):
    """Restituisce (peak_value, peak_idx) del max(sign=+1)/min(sign=-1) su [t-k+1..t]
    se il picco e' entro 'recent' barre da t, altrimenti (None, None)."""
    lo = max(0, t - k + 1)
    best_v = None
    best_i = None
    for i in range(lo, t + 1):
        v = _val(sp[i])
        if v is None:
            continue
        if best_v is None or (sign > 0 and v > best_v) or (sign < 0 and v < best_v):
            best_v, best_i = v, i
    if best_i is None or (t - best_i) > recent:
        return None, None
    return best_v, best_i


def detect_at(sp: List[Num], zb: List[Num], zq: List[Num], t: int,
              p: RotParams) -> Optional[str]:
    """Segnale di rotazione CAUSALE alla barra t: 'SHORT', 'LONG' o None.

    sp = serie spread (z_base - z_quote); zb,zq = serie z di base e quote.
    """
    if t < max(p.conf_bars, p.ema_len, 2):
        return None
    cur = _val(sp[t])
    prev = _val(sp[t - 1])
    if cur is None or prev is None:
        return None

    # --- TOP -> SHORT ---
    peak, _pi = _peak_recent(sp, t, p.k_window, p.recent, sign=+1)
    if peak is not None and peak >= p.ext_min and cur < prev:
        if _turn_confirmed(sp, zb, zq, t, p, peak, sign=+1):
            return "SHORT"

    # --- BOTTOM -> LONG ---
    trough, _ti = _peak_recent(sp, t, p.k_window, p.recent, sign=-1)
    if trough is not None and trough <= -p.ext_min and cur > prev:
        if _turn_confirmed(sp, zb, zq, t, p, trough, sign=-1):
            return "LONG"
    return None


def _turn_confirmed(sp, zb, zq, t, p: RotParams, pivot: float, sign: int) -> bool:
    """sign=+1 top (cerco giro giu'), sign=-1 bottom (giro su')."""
    if p.method == "drop":
        return (pivot - _val(sp[t])) * sign >= p.drop_min if _val(sp[t]) is not None else False
    if p.method == "ema_cross":
        e_now = ema_at(sp, t, p.ema_len)
        e_prev = ema_at(sp, t - 1, p.ema_len)
        c_now, c_prev = _val(sp[t]), _val(sp[t - 1])
        if None in (e_now, e_prev, c_now, c_prev):
            return False
        # cross sotto la EMA per un top, sopra per un bottom
        return (c_now - e_now) * sign < 0 and (c_prev - e_prev) * sign >= 0
    # default: "slope_both" - i DUE lati ruotano insieme sulle ultime conf_bars
    sb = slope(zb, t, p.conf_bars)
    sq = slope(zq, t, p.conf_bars)
    if sb is None or sq is None:
        return False
    # top (sign +1): base molla (sb<0) e quote recupera (sq>0). bottom: inverso.
    return (sb * sign < 0) and (sq * sign > 0)


def detect_rotations(sp: List[Num], zb: List[Num], zq: List[Num],
                     p: RotParams) -> List[dict]:
    """Scansione causale su tutta la serie con debounce (cooldown)."""
    out: List[dict] = []
    last_bar = {"SHORT": -10**9, "LONG": -10**9}
    n = len(sp)
    for t in range(n):
        d = detect_at(sp, zb, zq, t, p)
        if d is None:
            continue
        if t - last_bar[d] < p.cooldown:
            continue
        last_bar[d] = t
        sign = 1 if d == "SHORT" else -1
        peak, _pk = _peak_recent(sp, t, p.k_window, p.recent, sign)
        out.append({"bar": t, "dir": d, "spread": _val(sp[t]), "peak": peak})
    return out


def label_pivots(sp: List[Num], *, swing: int = 6, ext_min: float = 2.0) -> List[dict]:
    """Verita' a POSTERIORI: swing high/low confermati (max/min su +/-swing) con
    |spread| >= ext_min. Usato SOLO nel backtest come riferimento del 'punto vero'."""
    out: List[dict] = []
    n = len(sp)
    for t in range(swing, n - swing):
        v = _val(sp[t])
        if v is None:
            continue
        window = [_val(sp[i]) for i in range(t - swing, t + swing + 1)]
        if any(w is None for w in window):
            continue
        if v == max(window) and v >= ext_min:
            out.append({"bar": t, "dir": "SHORT", "spread": v})
        elif v == min(window) and v <= -ext_min:
            out.append({"bar": t, "dir": "LONG", "spread": v})
    return out


# --- Integrazione col layer di forza H1 (display/selezione) ---
# Parametri scelti dal backtest out-of-sample (precision 0.965, recall 0.894,
# offset mediano +1 barra): rotazione centrata, ne' presto ne' tardi.
DEFAULT_ROT_PARAMS = RotParams(method="slope_both", ext_min=1.5,
                               k_window=12, conf_bars=1)


def rotations_from_strength(h1_payload: dict,
                            params: RotParams = DEFAULT_ROT_PARAMS,
                            cluster_cap: int = 2) -> List[dict]:
    """Dalle 8 serie z H1 (compute_strength) alle ROTAZIONI sull'ultima barra
    chiusa. Una riga per coppia che ruota: forte (ex-forte che molla), debole
    (ex-debole che recupera), direzione nuova, spread H1. Dedup per valuta."""
    from . import pairs as P
    z = {c["ccy"]: c.get("series") for c in h1_payload.get("currencies", [])}
    rows: List[dict] = []
    for pair in P.PAIRS:
        base, quote = P.base_quote(pair)
        zb, zq = z.get(base), z.get(quote)
        if not zb or not zq or len(zb) != len(zq) or len(zb) < 14:
            continue
        sp = [(zb[i] - zq[i]) if (zb[i] is not None and zq[i] is not None) else None
              for i in range(len(zb))]
        t = len(sp) - 1
        d = detect_at(sp, zb, zq, t, params)
        if d is None:
            continue
        forte, debole = (base, quote) if d == "SHORT" else (quote, base)
        rows.append({
            "pair": pair, "dir": d, "base": base, "quote": quote,
            "forte": forte, "debole": debole,
            "spread_h1": round(sp[t], 4) if sp[t] is not None else None,
        })
    rows.sort(key=lambda r: -abs(r["spread_h1"] or 0.0))
    out: List[dict] = []
    cnt: dict = {}
    for r in rows:
        b, q = r["base"], r["quote"]
        if cnt.get(b, 0) >= cluster_cap or cnt.get(q, 0) >= cluster_cap:
            continue
        cnt[b] = cnt.get(b, 0) + 1
        cnt[q] = cnt.get(q, 0) + 1
        out.append(r)
    return out


def detect_crossovers(sp: List[Num], cooldown: int = 6) -> List[dict]:
    """Incroci dello spread di forza attraverso lo ZERO (cambio di leadership).
    LONG = sp passa da <=0 a >0 (base supera quote); SHORT = viceversa.
    'slope' = |variazione| al cross = quanto e' deciso l'incrocio."""
    out: List[dict] = []
    last = -10 ** 9
    for t in range(1, len(sp)):
        a, b = _val(sp[t - 1]), _val(sp[t])
        if a is None or b is None:
            continue
        d = None
        if a <= 0 and b > 0:
            d = "LONG"
        elif a >= 0 and b < 0:
            d = "SHORT"
        if d and (t - last) >= cooldown:
            out.append({"bar": t, "dir": d, "slope": abs(b - a), "spread": b})
            last = t
    return out
