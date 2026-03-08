import io
import os
import re
import random
from collections import Counter
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import pandas as pd
import streamlit as st

# =========================================================
# PDF ENGINES
# =========================================================
try:
    import fitz  # PyMuPDF
    HAS_PYMUPDF = True
except Exception:
    HAS_PYMUPDF = False

try:
    from pypdf import PdfReader
    from pypdf.errors import PdfReadError
    HAS_PYPDF = True
except Exception:
    HAS_PYPDF = False
    PdfReader = None
    PdfReadError = Exception


# =========================================================
# APP CONFIG
# =========================================================
APP_TITLE = "⚽ EuroVictory — Eurojackpot 5/50 + 2/12"
PDF_MAIN_FILENAME = "wyniki1ej.pdf"   # main numbers 5/50
PDF_EURO_FILENAME = "wyniki2ej.pdf"   # euro numbers 2/12

MAIN_MIN = 1
MAIN_MAX = 50
MAIN_PICK_COUNT = 5

EURO_MIN = 1
EURO_MAX = 12
EURO_PICK_COUNT = 2

DRAWNO_MIN = 1000

HYBRID_HOT_P = 0.70
HYBRID_COLD_P = 0.20
HYBRID_MIX_P = 0.10


# =========================================================
# UI STYLE — football pitch theme
# =========================================================
FOOTBALL_CSS = """
<style>
:root{
  --grass1:#2f9e44;
  --grass2:#2b8a3e;
  --grass3:#37b24d;
  --card:#ffffffee;
  --card2:#f8fff8f2;
  --txt:#000000;
  --mut:#1f2937;
  --shadow: 0 12px 28px rgba(0,0,0,.16);
}

.stApp{
  background:
    linear-gradient(90deg,
      rgba(255,255,255,0.18) 0%,
      rgba(255,255,255,0.18) 0.6%,
      transparent 0.6%,
      transparent 49.5%,
      rgba(255,255,255,0.22) 49.5%,
      rgba(255,255,255,0.22) 50.5%,
      transparent 50.5%,
      transparent 99.4%,
      rgba(255,255,255,0.18) 99.4%,
      rgba(255,255,255,0.18) 100%
    ),
    radial-gradient(circle at 50% 50%, transparent 0 64px, rgba(255,255,255,0.22) 64px 66px, transparent 66px),
    linear-gradient(180deg, var(--grass1) 0%, var(--grass2) 50%, var(--grass3) 100%) !important;
  color: var(--txt) !important;
  background-attachment: fixed !important;
}

[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] *{
  color: var(--txt) !important;
}

[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3,
[data-testid="stAppViewContainer"] h4{
  color: #ffffff !important;
  text-shadow: 0 2px 8px rgba(0,0,0,.25);
  letter-spacing: .35px;
}

[data-testid="stAppViewContainer"] h1{
  font-family: ui-serif, Georgia, "Times New Roman", serif;
  text-transform: uppercase;
}

.v-card{
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 2px solid rgba(255,255,255,0.35);
  box-shadow: var(--shadow);
  border-radius: 20px;
  padding: 16px 16px 12px 16px;
  backdrop-filter: blur(3px);
}

.v-pill{
  display:inline-block;
  padding: 6px 10px;
  margin: 3px 4px 0 0;
  border-radius: 999px;
  border: 1px solid rgba(47,158,68,0.25);
  background: rgba(47,158,68,0.14);
  font-weight: 900;
  color: #000000 !important;
}

.v-row{
  background: rgba(255,255,255,0.72);
  border: 1px solid rgba(47,158,68,0.18);
  border-radius: 14px;
  padding: 10px 12px;
  margin: 8px 0;
  color: #000000 !important;
}

.v-muted{
  opacity: .88;
  font-size: .92rem;
  color: var(--mut) !important;
}

[data-testid="stDataFrame"]{
  border-radius: 16px !important;
  overflow: hidden !important;
  border: 1px solid rgba(255,255,255,0.35) !important;
}

div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div{
  border-radius: 14px !important;
  background: rgba(255,255,255,0.96) !important;
}

div.stButton > button[kind="primary"]{
  background: linear-gradient(90deg, #ffffff 0%, #f1f3f5 100%) !important;
  color: #0b3d0b !important;
  border: 2px solid rgba(255,255,255,0.88) !important;
  border-radius: 14px !important;
  padding: 0.80rem 1.10rem !important;
  font-weight: 1000 !important;
  letter-spacing: .6px !important;
  box-shadow: 0 10px 22px rgba(0,0,0,0.15) !important;
}
div.stButton > button[kind="primary"]:hover{
  filter: brightness(1.03);
  transform: translateY(-1px);
}

button[kind="header"]{
  opacity: 1 !important;
  visibility: visible !important;
}

@media (max-width: 640px){
  div.stButton > button[kind="primary"]{ width: 100% !important; }
}
</style>
"""


# =========================================================
# GENERIC PDF HELPERS
# =========================================================
INT_RE = re.compile(r"\d+")

def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    if not pdf_bytes.startswith(b"%PDF"):
        head = pdf_bytes[:240].decode("utf-8", errors="replace")
        raise ValueError(
            "Plik nie wygląda jak prawdziwy PDF (brak nagłówka %PDF).\n"
            f"Początek pliku:\n{head}"
        )

def _read_pdf_pages_text_pymupdf(pdf_bytes: bytes) -> List[str]:
    if not HAS_PYMUPDF:
        raise RuntimeError("PyMuPDF not available")
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages = []
    for page in doc:
        pages.append(page.get_text("text") or "")
    doc.close()
    return pages

def _read_pdf_pages_text_pypdf(pdf_bytes: bytes) -> List[str]:
    if not HAS_PYPDF:
        raise RuntimeError("pypdf not available")
    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
    except Exception as e:
        raise PdfReadError(str(e))
    pages = []
    for page in reader.pages:
        try:
            pages.append(page.extract_text() or "")
        except Exception:
            pages.append("")
    return pages

def _read_pdf_pages_text(pdf_bytes: bytes) -> List[str]:
    _validate_pdf_bytes(pdf_bytes)

    last_err = None
    pages: List[str] = []

    if HAS_PYMUPDF:
        try:
            pages = _read_pdf_pages_text_pymupdf(pdf_bytes)
        except Exception as e:
            last_err = e
            pages = []

    if not pages and HAS_PYPDF:
        try:
            pages = _read_pdf_pages_text_pypdf(pdf_bytes)
        except Exception as e:
            last_err = e
            pages = []

    if not pages:
        if last_err:
            raise RuntimeError(f"Nie udało się odczytać PDF. Ostatni błąd: {last_err}")
        raise RuntimeError("Nie udało się odczytać PDF.")

    return pages


# =========================================================
# TOKEN PARSERS — ROBUST FOR YOUR PDF STRUCTURE
# =========================================================
def _extract_tokens_and_drawnos_main_from_pages(pages: List[str]) -> Tuple[List[int], List[int]]:
    """
    For 5/50:
    - collect all numbers 1..50 from top parts of pages
    - when page reaches draw numbers section (>=1000), collect draw numbers
    """
    tokens: List[int] = []
    drawnos: List[int] = []

    for page_text in pages:
        lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
        in_drawno_section = False

        for ln in lines:
            if "Eurojackpot" in ln and "5/50" in ln:
                continue

            ints = [int(x) for x in INT_RE.findall(ln)]
            if not ints:
                continue

            if any(x >= DRAWNO_MIN for x in ints):
                in_drawno_section = True

            if in_drawno_section:
                for x in ints:
                    if DRAWNO_MIN <= x < 100000:
                        drawnos.append(x)
            else:
                for x in ints:
                    if MAIN_MIN <= x <= MAIN_MAX:
                        tokens.append(x)

    return tokens, drawnos


def _extract_tokens_and_drawnos_euro_from_pages(pages: List[str]) -> Tuple[List[int], List[int]]:
    """
    For 2/12:
    - collect all numbers 1..12 from top parts of pages
    - when page reaches draw numbers section (>=1000), collect draw numbers
    """
    tokens: List[int] = []
    drawnos: List[int] = []

    for page_text in pages:
        lines = [ln.strip() for ln in page_text.splitlines() if ln.strip()]
        in_drawno_section = False

        for ln in lines:
            if "Eurojackpot" in ln and "2/12" in ln:
                continue

            ints = [int(x) for x in INT_RE.findall(ln)]
            if not ints:
                continue

            if any(x >= DRAWNO_MIN for x in ints):
                in_drawno_section = True

            if in_drawno_section:
                for x in ints:
                    if DRAWNO_MIN <= x < 100000:
                        drawnos.append(x)
            else:
                for x in ints:
                    if EURO_MIN <= x <= EURO_MAX:
                        tokens.append(x)

    return tokens, drawnos


def _chunk_tokens(tokens: List[int], pick_count: int, num_min: int, num_max: int) -> List[List[int]]:
    if len(tokens) < pick_count:
        return []

    if len(tokens) % pick_count == 0:
        draws = []
        for i in range(0, len(tokens), pick_count):
            d = tokens[i:i + pick_count]
            draws.append(sorted(d))
        return draws

    best = []
    best_valid = -1

    for offset in range(pick_count):
        t = tokens[offset:]
        if len(t) < pick_count:
            continue

        cut = (len(t) // pick_count) * pick_count
        t = t[:cut]

        draws = []
        valid = 0
        for i in range(0, len(t), pick_count):
            d = t[i:i + pick_count]
            if len(set(d)) == pick_count and all(num_min <= n <= num_max for n in d):
                valid += 1
            draws.append(sorted(d))

        if valid > best_valid:
            best_valid = valid
            best = draws

    return best


# =========================================================
# LOAD + JOIN BOTH PDFs
# =========================================================
@st.cache_data(show_spinner=False)
def load_eurojackpot_records_cached(pdf_main_bytes: bytes, pdf_euro_bytes: bytes) -> List[Dict]:
    main_pages = _read_pdf_pages_text(pdf_main_bytes)
    euro_pages = _read_pdf_pages_text(pdf_euro_bytes)

    main_tokens, main_drawnos = _extract_tokens_and_drawnos_main_from_pages(main_pages)
    euro_tokens, euro_drawnos = _extract_tokens_and_drawnos_euro_from_pages(euro_pages)

    main_draws = _chunk_tokens(main_tokens, MAIN_PICK_COUNT, MAIN_MIN, MAIN_MAX)
    euro_draws = _chunk_tokens(euro_tokens, EURO_PICK_COUNT, EURO_MIN, EURO_MAX)

    if not main_draws:
        raise RuntimeError("Nie udało się wyciągnąć wyników 5/50 z pliku głównego.")
    if not euro_draws:
        raise RuntimeError("Nie udało się wyciągnąć wyników 2/12 z pliku dodatkowego.")

    n_main = min(len(main_draws), len(main_drawnos))
    n_euro = min(len(euro_draws), len(euro_drawnos))

    main_records = [
        {"draw_no": main_drawnos[i], "main_nums": main_draws[i]}
        for i in range(n_main)
    ]
    euro_records = [
        {"draw_no": euro_drawnos[i], "euro_nums": euro_draws[i]}
        for i in range(n_euro)
    ]

    main_map = {r["draw_no"]: r["main_nums"] for r in main_records}
    euro_map = {r["draw_no"]: r["euro_nums"] for r in euro_records}

    common_drawnos = sorted(set(main_map.keys()) & set(euro_map.keys()), reverse=True)

    records: List[Dict] = []
    for dno in common_drawnos:
        records.append({
            "draw_no": dno,
            "date_str": "—",
            "main_nums": main_map[dno],
            "euro_nums": euro_map[dno],
        })

    if not records:
        raise RuntimeError("Nie udało się połączyć danych 5/50 i 2/12 po numerze losowania.")

    return records


# =========================================================
# STATS
# =========================================================
@st.cache_data(show_spinner=False)
def compute_freq_df_main_cached(draws: List[List[int]]) -> pd.DataFrame:
    flat = [n for d in draws for n in d]
    c = Counter(flat)
    rows = [{"Liczba": n, "Wystąpienia": c.get(n, 0)} for n in range(MAIN_MIN, MAIN_MAX + 1)]
    return pd.DataFrame(rows).sort_values(["Wystąpienia", "Liczba"], ascending=[False, True]).reset_index(drop=True)

@st.cache_data(show_spinner=False)
def compute_freq_df_euro_cached(draws: List[List[int]]) -> pd.DataFrame:
    flat = [n for d in draws for n in d]
    c = Counter(flat)
    rows = [{"Liczba": n, "Wystąpienia": c.get(n, 0)} for n in range(EURO_MIN, EURO_MAX + 1)]
    return pd.DataFrame(rows).sort_values(["Wystąpienia", "Liczba"], ascending=[False, True]).reset_index(drop=True)

def build_groups_from_freq(freq_df: pd.DataFrame, hot_size: int, cold_size: int, num_min: int, num_max: int) -> Tuple[List[int], List[int], List[int]]:
    hot = freq_df.head(hot_size)["Liczba"].tolist()
    cold = freq_df.tail(cold_size)["Liczba"].tolist()
    neutral = [n for n in range(num_min, num_max + 1) if n not in hot and n not in cold]
    return hot, cold, neutral

def build_hot_master_main(freq_df_main: pd.DataFrame) -> List[int]:
    return sorted(freq_df_main.head(MAIN_PICK_COUNT)["Liczba"].tolist())

def build_hot_master_euro(freq_df_euro: pd.DataFrame) -> List[int]:
    return sorted(freq_df_euro.head(EURO_PICK_COUNT)["Liczba"].tolist())


# =========================================================
# GENERATION
# =========================================================
def pick_unique(pool: List[int], k: int) -> List[int]:
    pool = list(dict.fromkeys(pool))
    if len(pool) < k:
        raise ValueError("Za mało liczb w puli, aby wylosować unikalny zestaw.")
    return sorted(random.sample(pool, k))

def gen_side_ticket(mode: str, hot: List[int], cold: List[int], pick_count: int, mix_hot_count: int) -> List[int]:
    if mode == "hot":
        return pick_unique(hot, pick_count)
    if mode == "cold":
        return pick_unique(cold, pick_count)
    if mode == "mix":
        if mix_hot_count >= pick_count:
            return pick_unique(hot, pick_count)
        if mix_hot_count <= 0:
            return pick_unique(cold, pick_count)
        h = pick_unique(hot, mix_hot_count)
        c = pick_unique([x for x in cold if x not in h], pick_count - mix_hot_count)
        return sorted(h + c)
    raise ValueError("Nieznany tryb losowania.")

def count_adjacent_pairs(nums_sorted: List[int]) -> int:
    return sum(1 for a, b in zip(nums_sorted, nums_sorted[1:]) if b == a + 1)

def has_run_length(nums_sorted: List[int], run_len: int) -> bool:
    if run_len <= 1:
        return True
    run = 1
    for a, b in zip(nums_sorted, nums_sorted[1:]):
        if b == a + 1:
            run += 1
            if run >= run_len:
                return True
        else:
            run = 1
    return False

def even_odd_split(nums: List[int]) -> Tuple[int, int]:
    ev = sum(1 for n in nums if n % 2 == 0)
    od = len(nums) - ev
    return ev, od

def smart_ok_main(
    ticket: List[int],
    block_run_2: bool,
    block_run_3: bool,
    max_adjacent_pairs: Optional[int],
    even_odd_choice: str
) -> bool:
    nums = sorted(ticket)

    if block_run_3 and has_run_length(nums, 3):
        return False
    if block_run_2 and has_run_length(nums, 2):
        return False

    pairs = count_adjacent_pairs(nums)
    if max_adjacent_pairs is not None and pairs > max_adjacent_pairs:
        return False

    ev, od = even_odd_split(nums)
    if even_odd_choice != "Dowolnie":
        try:
            ev_t, od_t = even_odd_choice.split("/")
            if not (ev == int(ev_t) and od == int(od_t)):
                return False
        except Exception:
            pass

    return True

def smart_ok_euro(
    ticket: List[int],
    euro_no_consecutive: bool,
    euro_even_odd_choice: str
) -> bool:
    nums = sorted(ticket)

    if euro_no_consecutive and len(nums) == 2 and nums[1] == nums[0] + 1:
        return False

    ev, od = even_odd_split(nums)
    if euro_even_odd_choice != "Dowolnie":
        try:
            ev_t, od_t = euro_even_odd_choice.split("/")
            if not (ev == int(ev_t) and od == int(od_t)):
                return False
        except Exception:
            pass

    return True

def generate_with_smart_filters(
    gen_func,
    n_tickets: int,
    max_attempts_per_ticket: int,
    smart_kwargs_main: Dict,
    smart_kwargs_euro: Dict
) -> List[Dict]:
    out: List[Dict] = []
    attempts = 0

    while len(out) < n_tickets:
        attempts += 1
        if attempts > n_tickets * max_attempts_per_ticket:
            break

        rec = gen_func()
        if smart_ok_main(rec["Main"], **smart_kwargs_main) and smart_ok_euro(rec["Euro"], **smart_kwargs_euro):
            out.append(rec)

    return out


# =========================================================
# DAILY NUMBERS
# =========================================================
def flatten_last_n(draws: List[List[int]], n: int) -> List[int]:
    return [x for d in draws[:n] for x in d]

def parity_bias_from_last_n(draws: List[List[int]], n: int) -> str:
    nums = flatten_last_n(draws, n)
    ev = sum(1 for x in nums if x % 2 == 0)
    od = len(nums) - ev
    if ev > od:
        return "ODD"
    if od > ev:
        return "EVEN"
    return "ANY"

def high_low_bias_from_last_two(draws: List[List[int]], threshold: int) -> str:
    if len(draws) < 2:
        return "ANY"
    last2 = draws[:2]
    all_nums = [x for d in last2 for x in d]
    low = sum(1 for x in all_nums if x <= threshold)
    high = len(all_nums) - low
    if low >= high + 2:
        return "HIGH"
    if high >= low + 2:
        return "LOW"
    return "ANY"

def avg_spread_last_n(draws: List[List[int]], n: int) -> float:
    spreads = [(max(d) - min(d)) for d in draws[:n] if d]
    return sum(spreads) / len(spreads) if spreads else 0.0

def pick_daily_set_from_hot(
    hot: List[int],
    pick_count: int,
    nmin: int,
    nmax: int,
    prefer_parity: str,
    prefer_level: str,
    threshold: int,
    target_spread: Optional[float] = None,
    max_attempts: int = 650
) -> List[int]:
    hot_unique = sorted(set([x for x in hot if nmin <= x <= nmax]))
    if len(hot_unique) < pick_count:
        hot_unique = hot_unique + [x for x in range(nmin, nmax + 1) if x not in hot_unique]

    pool = hot_unique[:]

    if prefer_level != "ANY":
        filtered = [x for x in pool if (x <= threshold)] if prefer_level == "LOW" else [x for x in pool if (x > threshold)]
        if len(filtered) >= pick_count:
            pool = filtered

    if prefer_parity != "ANY":
        filtered = [x for x in pool if (x % 2 == 0)] if prefer_parity == "EVEN" else [x for x in pool if (x % 2 == 1)]
        if len(filtered) >= pick_count:
            pool = filtered

    best = None
    best_score = -10**9

    for _ in range(max_attempts):
        cand = sorted(random.sample(pool, pick_count))
        spread = cand[-1] - cand[0]
        score = 0.0

        if target_spread is not None:
            score -= abs(spread - target_spread) * 0.25

        if prefer_parity != "ANY":
            ev, od = even_odd_split(cand)
            score += (ev * 0.35) if prefer_parity == "EVEN" else (od * 0.35)

        if prefer_level != "ANY":
            low = sum(1 for x in cand if x <= threshold)
            high = pick_count - low
            score += (high * 0.25) if prefer_level == "HIGH" else (low * 0.25)

        if score > best_score:
            best_score = score
            best = cand

    return best if best is not None else sorted(random.sample(range(nmin, nmax + 1), pick_count))


# =========================================================
# TXT EXPORT
# =========================================================
def sanitize_txt_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        name = "wyniki.txt"
    name = name.replace("\\", "_").replace("/", "_").replace("..", "_")
    if not name.lower().endswith(".txt"):
        name += ".txt"
    return name

def make_txt_for_results(result_records: List[Dict]) -> bytes:
    lines = []
    for r in result_records:
        draw_no = r.get("draw_no")
        draw_str = str(draw_no) if draw_no is not None else "—"
        main_str = " ".join(f"{x:02d}" for x in r["main_nums"])
        euro_str = " ".join(f"{x:02d}" for x in r["euro_nums"])
        lines.append(f"Losowanie: {draw_str} | Main: {main_str} | Euro: {euro_str}")
    return ("\n".join(lines) + "\n").encode("utf-8")

def make_txt_for_tickets(records: List[Dict]) -> bytes:
    lines = []
    for i, r in enumerate(records, start=1):
        main_str = " ".join(f"{x:02d}" for x in r["Main"])
        euro_str = " ".join(f"{x:02d}" for x in r["Euro"])
        lines.append(f"{i:03d}. [{r['Typ']}] Main: {main_str} | Euro: {euro_str}")
    return ("\n".join(lines) + "\n").encode("utf-8")

def make_txt_for_hot_master_set(main_set: List[int], euro_set: List[int], history_window: int) -> bytes:
    main_str = " ".join(f"{x:02d}" for x in main_set)
    euro_str = " ".join(f"{x:02d}" for x in euro_set)
    text = (
        f"Eurojackpot HOT MASTER SET\n"
        f"Analizowana historia: ostatnie {history_window} losowań\n"
        f"Main 5/50: {main_str}\n"
        f"Euro 2/12: {euro_str}\n"
    )
    return text.encode("utf-8")


# =========================================================
# SETTINGS PANEL
# =========================================================
def settings_panel(defaults: Dict) -> Dict:
    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("⚙️ Ustawienia (panel główny — działa na komputerze i telefonie)")

    mode_ui = st.selectbox(
        "Tryb typowania",
        [
            "Hybryda 70/20/10 (hot/cold/mix)",
            "Tylko 🔥 gorące",
            "Tylko ❄️ zimne",
            "Tylko ⚗️ mix (hot+zimne)",
        ],
        index=defaults.get("mode_index", 0)
    )

    history_window = st.selectbox(
        "Ile ostatnich losowań brać do analizy HOT/COLD?",
        [50, 100, 250, 500, 999],
        index=defaults.get("hist_index", 4)
    )

    c1, c2 = st.columns(2)
    with c1:
        n_tickets = st.slider("Liczba kuponów", 1, 500, defaults.get("n_tickets", 50), 1)
        hot_main_size = st.slider("Ile liczb w grupie Gorących (Main 5/50)", 5, 35, defaults.get("hot_main_size", 20), 1)
        hot_euro_size = st.slider("Ile liczb w grupie Gorących (Euro 2/12)", 2, 10, defaults.get("hot_euro_size", 6), 1)
    with c2:
        preview_limit = st.slider("Ile kuponów pokazać w podglądzie", 10, 200, defaults.get("preview_limit", 60), 10)
        cold_main_size = st.slider("Ile liczb w grupie Zimnych (Main 5/50)", 5, 35, defaults.get("cold_main_size", 20), 1)
        cold_euro_size = st.slider("Ile liczb w grupie Zimnych (Euro 2/12)", 2, 10, defaults.get("cold_euro_size", 4), 1)

    mix_main_hot_count = st.slider("MIX: ile liczb z gorących dla Main 5/50?", 1, 4, defaults.get("mix_main_hot_count", 3), 1)
    mix_euro_hot_count = st.slider("MIX: ile liczb z gorących dla Euro 2/12?", 0, 2, defaults.get("mix_euro_hot_count", 1), 1)

    st.markdown("---")
    st.subheader("🧠 Tryb inteligentny (opcjonalny)")

    smart_enabled = st.checkbox("Włącz tryb inteligentny", value=defaults.get("smart_enabled", False))

    if smart_enabled:
        block_run_2 = st.checkbox("Main: blokuj układy 1–2 (kolejne liczby)", value=defaults.get("block_run_2", True))
        block_run_3 = st.checkbox("Main: blokuj układy 1–3 (ciąg 3 kolejnych)", value=defaults.get("block_run_3", True))

        limit_pairs_on = st.checkbox("Main: włącz limit par (kolejne liczby)", value=defaults.get("limit_pairs_on", True))
        max_adj_pairs = None
        if limit_pairs_on:
            max_adj_pairs = st.slider("Main: maks. liczba par kolejnych", 0, 4, defaults.get("max_adj_pairs", 2), 1)

        even_odd_choice_main = st.radio(
            "Main 5/50 — parzyste / nieparzyste",
            ["Dowolnie", "3/2", "2/3", "4/1", "1/4", "5/0", "0/5"],
            index=defaults.get("even_odd_main_idx", 0)
        )

        euro_no_consecutive = st.checkbox("Euro 2/12: blokuj liczby kolejne", value=defaults.get("euro_no_consecutive", False))

        even_odd_choice_euro = st.radio(
            "Euro 2/12 — parzyste / nieparzyste",
            ["Dowolnie", "1/1", "2/0", "0/2"],
            index=defaults.get("even_odd_euro_idx", 0)
        )

        max_attempts_per_ticket = st.slider("Limit prób na kupon", 10, 500, defaults.get("max_attempts", 120), 10)
    else:
        block_run_2 = False
        block_run_3 = False
        max_adj_pairs = None
        even_odd_choice_main = "Dowolnie"
        euro_no_consecutive = False
        even_odd_choice_euro = "Dowolnie"
        max_attempts_per_ticket = 120

    st.markdown("</div>", unsafe_allow_html=True)

    return {
        "mode_ui": mode_ui,
        "history_window": int(history_window),
        "n_tickets": int(n_tickets),
        "hot_main_size": int(hot_main_size),
        "cold_main_size": int(cold_main_size),
        "hot_euro_size": int(hot_euro_size),
        "cold_euro_size": int(cold_euro_size),
        "mix_main_hot_count": int(mix_main_hot_count),
        "mix_euro_hot_count": int(mix_euro_hot_count),
        "preview_limit": int(preview_limit),
        "smart_enabled": bool(smart_enabled),
        "block_run_2": bool(block_run_2),
        "block_run_3": bool(block_run_3),
        "max_adj_pairs": max_adj_pairs,
        "even_odd_choice_main": even_odd_choice_main,
        "euro_no_consecutive": bool(euro_no_consecutive),
        "even_odd_choice_euro": even_odd_choice_euro,
        "max_attempts_per_ticket": int(max_attempts_per_ticket),
    }


# =========================================================
# MAIN APP
# =========================================================
def main():
    st.set_page_config(
        page_title="EuroVictory",
        page_icon="⚽",
        layout="wide",
        initial_sidebar_state="collapsed"
    )
    st.markdown(FOOTBALL_CSS, unsafe_allow_html=True)

    st.title(APP_TITLE)
    st.write("Generator typowań Eurojackpot na bazie prawdziwych wyników z dwóch plików PDF: 5/50 i 2/12.")
    st.caption("Parser poprawiony pod strukturę Twoich PDF-ów: tokeny są zbierane sekwencyjnie i dzielone odpowiednio co 5 i co 2, a potem łączone po numerze losowania.")

    if "last_records" not in st.session_state:
        st.session_state["last_records"] = []
    if "last_daily" not in st.session_state:
        st.session_state["last_daily"] = None
    if "show_results" not in st.session_state:
        st.session_state["show_results"] = False
    if "hot_master_set" not in st.session_state:
        st.session_state["hot_master_set"] = None

    pdf_main_path = Path(os.getcwd()) / PDF_MAIN_FILENAME
    pdf_euro_path = Path(os.getcwd()) / PDF_EURO_FILENAME

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("📄 Dane wejściowe")
    st.write(f"Plik główny 5/50: `{pdf_main_path}`")
    st.write(f"Plik dodatkowy 2/12: `{pdf_euro_path}`")
    st.write(f"Silnik PDF: **{'PyMuPDF (fitz)' if HAS_PYMUPDF else 'pypdf (fallback)'}**")
    st.markdown('<div class="v-muted">Dane są łączone po tym samym numerze losowania z obu plików.</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    if not pdf_main_path.exists():
        st.error(f"❌ Nie znaleziono `{PDF_MAIN_FILENAME}` obok `app.py`.")
        st.stop()

    if not pdf_euro_path.exists():
        st.error(f"❌ Nie znaleziono `{PDF_EURO_FILENAME}` obok `app.py`.")
        st.stop()

    try:
        pdf_main_bytes = pdf_main_path.read_bytes()
        pdf_euro_bytes = pdf_euro_path.read_bytes()
        result_records_all = load_eurojackpot_records_cached(pdf_main_bytes, pdf_euro_bytes)
    except Exception as e:
        st.error("❌ Aplikacja nie mogła wczytać PDF albo połączyć wyników Eurojackpot.")
        st.code(str(e))
        st.stop()

    defaults = {
        "mode_index": 0,
        "hist_index": 4,
        "n_tickets": 50,
        "hot_main_size": 20,
        "cold_main_size": 20,
        "hot_euro_size": 6,
        "cold_euro_size": 4,
        "mix_main_hot_count": 3,
        "mix_euro_hot_count": 1,
        "preview_limit": 60,
        "smart_enabled": False,
        "block_run_2": True,
        "block_run_3": True,
        "limit_pairs_on": True,
        "max_adj_pairs": 2,
        "even_odd_main_idx": 0,
        "euro_no_consecutive": False,
        "even_odd_euro_idx": 0,
        "max_attempts": 120
    }

    with st.expander("⚙️ Ustawienia (kliknij, aby rozwinąć)", expanded=True):
        cfg = settings_panel(defaults)

    result_records = result_records_all[:cfg["history_window"]]
    main_draws = [r["main_nums"] for r in result_records]
    euro_draws = [r["euro_nums"] for r in result_records]

    freq_df_main = compute_freq_df_main_cached(main_draws)
    freq_df_euro = compute_freq_df_euro_cached(euro_draws)

    hot_main, cold_main, _neutral_main = build_groups_from_freq(
        freq_df_main, cfg["hot_main_size"], cfg["cold_main_size"], MAIN_MIN, MAIN_MAX
    )
    hot_euro, cold_euro, _neutral_euro = build_groups_from_freq(
        freq_df_euro, cfg["hot_euro_size"], cfg["cold_euro_size"], EURO_MIN, EURO_MAX
    )

    hot_master_main = build_hot_master_main(freq_df_main)
    hot_master_euro = build_hot_master_euro(freq_df_euro)

    left, right = st.columns([1.2, 0.8], gap="large")

    with left:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("📊 Częstotliwość — Main 5/50")
        st.success(f"✅ Analizowane losowania: **{len(result_records)}** (z {len(result_records_all)} połączonych losowań)")
        st.dataframe(freq_df_main, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("📊 Częstotliwość — Euro 2/12")
        st.dataframe(freq_df_euro, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🔥 Gorące / ❄️ Zimne — Main 5/50")
        st.markdown("**Gorące (Hot)**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(hot_main)]), unsafe_allow_html=True)
        st.markdown("**Zimne (Cold)**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(cold_main)]), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🔥 Gorące / ❄️ Zimne — Euro 2/12")
        st.markdown("**Gorące (Hot)**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(hot_euro)]), unsafe_allow_html=True)
        st.markdown("**Zimne (Cold)**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(cold_euro)]), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🎛️ Podsumowanie trybu")
        st.write(f"**Tryb:** {cfg['mode_ui']}")
        st.write(f"**Analiza HOT/COLD:** ostatnie **{cfg['history_window']}** losowań")
        st.write(f"**Tryb inteligentny:** {'TAK' if cfg['smart_enabled'] else 'NIE'}")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("🎟️ Generator")

    col_btn1, col_btn2, col_btn3, col_btn4 = st.columns(4, gap="large")
    with col_btn1:
        generate = st.button("⚽ GENERUJ KUPONY", type="primary", use_container_width=True)
    with col_btn2:
        daily = st.button("🌿 CYFRY DNIA", type="primary", use_container_width=True)
    with col_btn3:
        show_res = st.button("📋 POKAŻ WYNIKI", type="primary", use_container_width=True)
    with col_btn4:
        show_hot_set = st.button("🔥 HOT SET", type="primary", use_container_width=True)

    if show_res:
        st.session_state["show_results"] = not st.session_state["show_results"]

    if show_hot_set:
        st.session_state["hot_master_set"] = {
            "main": hot_master_main,
            "euro": hot_master_euro
        }

    mode_ui = cfg["mode_ui"]
    if mode_ui == "Hybryda 70/20/10 (hot/cold/mix)":
        base_mode_kind = "hybrid"
    elif mode_ui == "Tylko 🔥 gorące":
        base_mode_kind = "hot"
    elif mode_ui == "Tylko ❄️ zimne":
        base_mode_kind = "cold"
    else:
        base_mode_kind = "mix"

    def gen_one_record() -> Dict:
        if base_mode_kind == "hybrid":
            chosen = random.choices(
                ["hot", "cold", "mix"],
                weights=[HYBRID_HOT_P, HYBRID_COLD_P, HYBRID_MIX_P],
                k=1
            )[0]
            return {
                "Typ": chosen,
                "Main": gen_side_ticket(chosen, hot_main, cold_main, MAIN_PICK_COUNT, cfg["mix_main_hot_count"]),
                "Euro": gen_side_ticket(chosen, hot_euro, cold_euro, EURO_PICK_COUNT, cfg["mix_euro_hot_count"])
            }

        if base_mode_kind == "hot":
            return {
                "Typ": "hot",
                "Main": gen_side_ticket("hot", hot_main, cold_main, MAIN_PICK_COUNT, cfg["mix_main_hot_count"]),
                "Euro": gen_side_ticket("hot", hot_euro, cold_euro, EURO_PICK_COUNT, cfg["mix_euro_hot_count"])
            }

        if base_mode_kind == "cold":
            return {
                "Typ": "cold",
                "Main": gen_side_ticket("cold", hot_main, cold_main, MAIN_PICK_COUNT, cfg["mix_main_hot_count"]),
                "Euro": gen_side_ticket("cold", hot_euro, cold_euro, EURO_PICK_COUNT, cfg["mix_euro_hot_count"])
            }

        return {
            "Typ": "mix",
            "Main": gen_side_ticket("mix", hot_main, cold_main, MAIN_PICK_COUNT, cfg["mix_main_hot_count"]),
            "Euro": gen_side_ticket("mix", hot_euro, cold_euro, EURO_PICK_COUNT, cfg["mix_euro_hot_count"])
        }

    if generate:
        progress = st.progress(0)
        status = st.empty()

        with st.spinner("Generuję kupony Eurojackpot..."):
            if not cfg["smart_enabled"]:
                recs: List[Dict] = []
                total = int(cfg["n_tickets"])
                for i in range(total):
                    recs.append(gen_one_record())
                    if (i + 1) % 10 == 0 or (i + 1) == total:
                        progress.progress(int((i + 1) / total * 100))
                        status.write(f"Postęp: {i+1}/{total}")
            else:
                smart_kwargs_main = {
                    "block_run_2": cfg["block_run_2"],
                    "block_run_3": cfg["block_run_3"],
                    "max_adjacent_pairs": cfg["max_adj_pairs"],
                    "even_odd_choice": cfg["even_odd_choice_main"]
                }
                smart_kwargs_euro = {
                    "euro_no_consecutive": cfg["euro_no_consecutive"],
                    "euro_even_odd_choice": cfg["even_odd_choice_euro"]
                }

                recs = generate_with_smart_filters(
                    gen_func=gen_one_record,
                    n_tickets=int(cfg["n_tickets"]),
                    max_attempts_per_ticket=int(cfg["max_attempts_per_ticket"]),
                    smart_kwargs_main=smart_kwargs_main,
                    smart_kwargs_euro=smart_kwargs_euro
                )
                progress.progress(100)
                status.write(f"Postęp: {len(recs)}/{int(cfg['n_tickets'])}")

        progress.empty()
        status.empty()

        if cfg["smart_enabled"] and len(recs) < int(cfg["n_tickets"]):
            st.warning(
                f"⚠️ Filtry są ostre: wygenerowano **{len(recs)}** / {int(cfg['n_tickets'])} kuponów. "
                "Poluzuj filtry albo zwiększ limit prób."
            )

        st.session_state["last_records"] = recs

    if daily:
        prefer_parity_main = parity_bias_from_last_n(main_draws, 10)
        prefer_level_main = high_low_bias_from_last_two(main_draws, threshold=25)
        target_spread_main = avg_spread_last_n(main_draws, 10)

        daily_main = pick_daily_set_from_hot(
            hot=hot_main,
            pick_count=MAIN_PICK_COUNT,
            nmin=MAIN_MIN,
            nmax=MAIN_MAX,
            prefer_parity=prefer_parity_main,
            prefer_level=prefer_level_main,
            threshold=25,
            target_spread=target_spread_main,
            max_attempts=650
        )

        prefer_parity_euro = parity_bias_from_last_n(euro_draws, 10)
        prefer_level_euro = high_low_bias_from_last_two(euro_draws, threshold=6)
        target_spread_euro = avg_spread_last_n(euro_draws, 10)

        daily_euro = pick_daily_set_from_hot(
            hot=hot_euro,
            pick_count=EURO_PICK_COUNT,
            nmin=EURO_MIN,
            nmax=EURO_MAX,
            prefer_parity=prefer_parity_euro,
            prefer_level=prefer_level_euro,
            threshold=6,
            target_spread=target_spread_euro,
            max_attempts=400
        )

        st.session_state["last_daily"] = {
            "main": daily_main,
            "euro": daily_euro
        }

    if st.session_state["show_results"]:
        st.markdown("### 📋 Ostatnie wyniki Eurojackpot")
        count_choice = st.selectbox("Ile ostatnich wyników pokazać?", [10, 50, 100], index=0)
        slice_records = result_records_all[:int(count_choice)]

        df_results = pd.DataFrame({
            "Numer losowania": [r["draw_no"] for r in slice_records],
            "Data": [r["date_str"] for r in slice_records],
            "Main 5/50": [" ".join(f"{x:02d}" for x in r["main_nums"]) for r in slice_records],
            "Euro 2/12": [" ".join(f"{x:02d}" for x in r["euro_nums"]) for r in slice_records],
        })
        st.dataframe(df_results, use_container_width=True, hide_index=True)

        st.markdown('<div class="v-muted">Zapis jest dostępny wyłącznie jako plik TXT (pobieranie → folder „Pobrane”).</div>', unsafe_allow_html=True)
        filename_input = st.text_input("Nazwa pliku wyników .txt (np. euro_wyniki.txt)", value="euro_wyniki.txt")
        safe_name = sanitize_txt_filename(filename_input)
        st.download_button(
            "⬇️ Pobierz wyniki jako TXT",
            data=make_txt_for_results(slice_records),
            file_name=safe_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("hot_master_set") is not None:
        hot_set = st.session_state["hot_master_set"]
        main_str = " ".join(f"{x:02d}" for x in hot_set["main"])
        euro_str = " ".join(f"{x:02d}" for x in hot_set["euro"])

        st.markdown("### 🔥 HOT MASTER SET — Eurojackpot")
        st.markdown(
            f'<div class="v-row"><b>Main 5/50</b> — {main_str} '
            f'<span class="v-muted"> | z ostatnich {cfg["history_window"]} losowań</span></div>',
            unsafe_allow_html=True
        )
        st.markdown(
            f'<div class="v-row"><b>Euro 2/12</b> — {euro_str} '
            f'<span class="v-muted"> | z ostatnich {cfg["history_window"]} losowań</span></div>',
            unsafe_allow_html=True
        )

        hot_set_filename_input = st.text_input("Nazwa pliku HOT SET .txt (np. euro_hot_set.txt)", value="euro_hot_set.txt")
        safe_hot_name = sanitize_txt_filename(hot_set_filename_input)
        st.download_button(
            "⬇️ Pobierz HOT SET jako TXT",
            data=make_txt_for_hot_master_set(hot_set["main"], hot_set["euro"], cfg["history_window"]),
            file_name=safe_hot_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("last_daily") is not None:
        info = st.session_state["last_daily"]
        main_str = " ".join(f"{x:02d}" for x in info["main"])
        euro_str = " ".join(f"{x:02d}" for x in info["euro"])

        st.markdown("### 🌿 Twoje cyfry dnia — Eurojackpot")
        st.markdown(
            f'<div class="v-row"><b>Main 5/50</b> — {main_str}</div>',
            unsafe_allow_html=True
        )
        st.markdown(
            f'<div class="v-row"><b>Euro 2/12</b> — {euro_str}</div>',
            unsafe_allow_html=True
        )

    records = st.session_state.get("last_records", [])
    if records:
        st.markdown("### 🎯 Wygenerowane kupony Eurojackpot")

        df_out = pd.DataFrame({
            "Typ": [r["Typ"] for r in records],
            "Main 5/50": [" ".join(f"{x:02d}" for x in r["Main"]) for r in records],
            "Euro 2/12": [" ".join(f"{x:02d}" for x in r["Euro"]) for r in records],
        })

        preview_n = min(int(cfg["preview_limit"]), len(records))
        st.caption(f"Podgląd pierwszych **{preview_n}** kuponów (pełna lista w tabeli).")

        for i in range(preview_n):
            main_str = df_out.iloc[i]["Main 5/50"]
            euro_str = df_out.iloc[i]["Euro 2/12"]
            typ = df_out.iloc[i]["Typ"]

            st.markdown(
                f'<div class="v-row"><b>Kupon #{i+1:03d}</b> '
                f'<span class="v-muted">[{typ}]</span> — Main: {main_str} | Euro: {euro_str}</div>',
                unsafe_allow_html=True
            )

        st.markdown("#### Pełna tabela")
        st.dataframe(df_out, use_container_width=True, hide_index=True)

        st.markdown('<div class="v-muted">Zapis kuponów jest dostępny wyłącznie jako plik TXT (pobieranie → „Pobrane”).</div>', unsafe_allow_html=True)
        ticket_filename_input = st.text_input("Nazwa pliku kuponów .txt (np. euro_kupony.txt)", value="euro_kupony.txt")
        safe_ticket_name = sanitize_txt_filename(ticket_filename_input)
        st.download_button(
            "⬇️ Pobierz kupony jako TXT",
            data=make_txt_for_tickets(records),
            file_name=safe_ticket_name,
            mime="text/plain",
            use_container_width=True
        )

    with st.expander("✅ Kontrola (pierwsze 3 rekordy — powinny być najnowsze)"):
        for i, r in enumerate(result_records_all[:3], start=1):
            st.write(
                f"{i}. Losowanie: {r['draw_no']} | "
                f"Main: {' '.join(f'{x:02d}' for x in r['main_nums'])} | "
                f"Euro: {' '.join(f'{x:02d}' for x in r['euro_nums'])}"
            )

    with st.expander("📌 Diagnostyka — TOP/LOW"):
        c1, c2 = st.columns(2)
        with c1:
            st.write("TOP 15 — Main 5/50")
            st.dataframe(freq_df_main.head(15), use_container_width=True, hide_index=True)
            st.write("LOW 15 — Main 5/50")
            st.dataframe(freq_df_main.tail(15).sort_values(["Wystąpienia", "Liczba"]), use_container_width=True, hide_index=True)
        with c2:
            st.write("TOP 12 — Euro 2/12")
            st.dataframe(freq_df_euro.head(12), use_container_width=True, hide_index=True)
            st.write("LOW 12 — Euro 2/12")
            st.dataframe(freq_df_euro.tail(12).sort_values(["Wystąpienia", "Liczba"]), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
