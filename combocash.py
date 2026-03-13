import io
import os
import random
import re
from collections import Counter
from itertools import combinations
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import fitz  # PyMuPDF
import numpy as np
import pandas as pd
import streamlit as st


# =========================================================
# APP CONFIG
# =========================================================
APP_TITLE = "⚽ EuroVictory — Eurojackpot 5/50 + 2/12"
PDF_MAIN_FILENAME = "wyniki1ej.pdf"
PDF_EURO_FILENAME = "wyniki2ej.pdf"

MAIN_MIN = 1
MAIN_MAX = 50
MAIN_PICK_COUNT = 5

EURO_MIN = 1
EURO_MAX = 12
EURO_PICK_COUNT = 2

HYBRID_HOT_P = 0.70
HYBRID_COLD_P = 0.20
HYBRID_MIX_P = 0.10


# =========================================================
# UI STYLE
# =========================================================
APP_CSS = """
<style>
:root{
  --bg0:#eef8ef;
  --bg1:#ffffff;
  --card:#ffffff;
  --card2:#f8fff8;
  --txt:#000000;
  --mut:#111827;
  --green:#1f8b4c;
  --green2:#31b36c;
  --gold:#d8b84b;
  --blue:#2d77d1;
  --border: rgba(31,139,76,0.22);
  --shadow: 0 10px 28px rgba(0,0,0,.08);
}

.stApp{
  background-color: var(--bg0) !important;
  background-image:
    radial-gradient(1200px 800px at 12% 10%, rgba(49,179,108,0.10), transparent 58%),
    radial-gradient(950px 650px at 92% 18%, rgba(45,119,209,0.08), transparent 55%),
    linear-gradient(180deg, var(--bg0), var(--bg1)) !important;
  color: var(--txt) !important;
}

[data-testid="stAppViewContainer"],
[data-testid="stAppViewContainer"] *{
  color: var(--txt) !important;
}

[data-testid="stAppViewContainer"] h1,
[data-testid="stAppViewContainer"] h2,
[data-testid="stAppViewContainer"] h3,
[data-testid="stAppViewContainer"] h4{
  color: var(--txt) !important;
  letter-spacing: .30px;
}

[data-testid="stAppViewContainer"] h1{
  font-family: ui-serif, Georgia, "Times New Roman", serif;
  text-transform: uppercase;
}

.v-card{
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  border-radius: 18px;
  padding: 16px 16px 12px 16px;
}

.v-row{
  background: rgba(31,139,76,0.06);
  border: 1px solid rgba(31,139,76,0.18);
  border-radius: 14px;
  padding: 10px 12px;
  margin: 8px 0;
  color: #000000 !important;
}

.v-row-premium{
  background: rgba(216,184,75,0.12);
  border: 1px solid rgba(216,184,75,0.30);
  border-radius: 14px;
  padding: 10px 12px;
  margin: 8px 0;
  color: #000000 !important;
}

.v-pill{
  display:inline-block;
  padding: 6px 10px;
  margin: 3px 4px 0 0;
  border-radius: 999px;
  border: 1px solid rgba(31,139,76,0.28);
  background: rgba(31,139,76,0.10);
  font-weight: 900;
  color: #000000 !important;
}

.v-pill-premium{
  display:inline-block;
  padding: 6px 10px;
  margin: 3px 4px 0 0;
  border-radius: 999px;
  border: 1px solid rgba(216,184,75,0.40);
  background: rgba(216,184,75,0.14);
  font-weight: 900;
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
  border: 1px solid rgba(31,139,76,0.22) !important;
}

div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div{
  border-radius: 14px !important;
}

div.stButton > button[kind="primary"]{
  background: linear-gradient(90deg, var(--green) 0%, var(--green2) 100%) !important;
  color: #000000 !important;
  border: 0 !important;
  border-radius: 14px !important;
  padding: 0.80rem 1.10rem !important;
  font-weight: 1000 !important;
  letter-spacing: .6px !important;
  box-shadow: 0 10px 22px rgba(31,139,76,0.18) !important;
}

div.stButton > button[kind="primary"]:hover{
  filter: brightness(1.03);
  transform: translateY(-1px);
}

button[kind="header"]{
  opacity: 1 !important;
  visibility: visible !important;
}

@media (max-width: 780px){
  div.stButton > button[kind="primary"]{ width: 100% !important; }
}
</style>
"""


# =========================================================
# HELPERS
# =========================================================
LINE_DRAWNO = re.compile(r"^\d{4}$")
NUM_TOKEN_RE = re.compile(r"^\d{1,2}$")


def sanitize_txt_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        name = "wyniki.txt"
    name = name.replace("\\", "_").replace("/", "_").replace("..", "_")
    if not name.lower().endswith(".txt"):
        name += ".txt"
    return name


def even_odd_split(nums: List[int]) -> Tuple[int, int]:
    ev = sum(1 for n in nums if n % 2 == 0)
    od = len(nums) - ev
    return ev, od


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


def pick_unique(pool: List[int], k: int) -> List[int]:
    pool = list(dict.fromkeys(pool))
    if len(pool) < k:
        raise ValueError("Za mało liczb w puli.")
    return sorted(random.sample(pool, k))


# =========================================================
# PDF PARSER — GRID / WORD POSITION PARSER
# =========================================================
def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    if not pdf_bytes.startswith(b"%PDF"):
        head = pdf_bytes[:240].decode("utf-8", errors="replace")
        raise ValueError(
            "Plik nie wygląda jak prawdziwy PDF (brak nagłówka %PDF).\n"
            f"Początek pliku:\n{head}"
        )


def _read_pdf_pages_words(pdf_bytes: bytes) -> List[List[Tuple]]:
    _validate_pdf_bytes(pdf_bytes)
    doc = fitz.open(stream=pdf_bytes, filetype="pdf")
    pages_words = []
    for page in doc:
        pages_words.append(page.get_text("words") or [])
    doc.close()
    return pages_words


def _group_words_into_rows(words: List[Tuple], y_tolerance: float = 2.2) -> List[List[Tuple]]:
    if not words:
        return []

    words_sorted = sorted(words, key=lambda w: (round(w[1], 1), w[0]))
    rows = []
    current_row = []
    current_y = None

    for w in words_sorted:
        y = float(w[1])
        if current_y is None:
            current_row = [w]
            current_y = y
            continue

        if abs(y - current_y) <= y_tolerance:
            current_row.append(w)
            current_y = (current_y + y) / 2.0
        else:
            rows.append(sorted(current_row, key=lambda z: z[0]))
            current_row = [w]
            current_y = y

    if current_row:
        rows.append(sorted(current_row, key=lambda z: z[0]))

    return rows


def _is_footer_or_noise_row(texts: List[str]) -> bool:
    joined = " ".join(texts).lower()
    if "multipasko" in joined:
        return True
    if "www." in joined:
        return True
    if "mapy" in joined:
        return True
    if "liczbowe" in joined:
        return True
    if "lotto" in joined and "eurojackpot" not in joined:
        return True
    if "©" in joined:
        return True
    return False


def _extract_records_from_grid_words(
    pages_words: List[List[Tuple]],
    num_min: int,
    num_max: int,
    pick_count: int,
    title_fragment: str
) -> List[Dict]:
    records = []

    for page_words in pages_words:
        rows = _group_words_into_rows(page_words, y_tolerance=2.2)

        for row in rows:
            texts = [str(w[4]).strip() for w in row if str(w[4]).strip()]
            if not texts:
                continue

            joined = " ".join(texts).lower()
            if title_fragment.lower() in joined:
                continue
            if _is_footer_or_noise_row(texts):
                continue

            row_sorted = sorted(row, key=lambda z: z[0])
            row_texts = [str(w[4]).strip() for w in row_sorted if str(w[4]).strip()]

            first = row_texts[0]
            if not LINE_DRAWNO.match(first):
                continue

            draw_no = int(first)
            nums = []

            for token in row_texts[1:]:
                if not NUM_TOKEN_RE.match(token):
                    continue
                val = int(token)
                if num_min <= val <= num_max:
                    nums.append(val)

            nums = sorted(nums)

            if len(nums) == pick_count and len(set(nums)) == pick_count:
                records.append({
                    "draw_no": draw_no,
                    "nums": nums
                })

    dedup = {}
    ordered_drawnos = []
    for r in records:
        dno = r["draw_no"]
        if dno not in dedup:
            dedup[dno] = r["nums"]
            ordered_drawnos.append(dno)

    final_records = [{"draw_no": dno, "nums": dedup[dno]} for dno in ordered_drawnos]
    final_records.sort(key=lambda r: r["draw_no"], reverse=True)
    return final_records


@st.cache_data(show_spinner=False)
def load_eurojackpot_records_cached(pdf_main_bytes: bytes, pdf_euro_bytes: bytes) -> List[Dict]:
    main_pages_words = _read_pdf_pages_words(pdf_main_bytes)
    euro_pages_words = _read_pdf_pages_words(pdf_euro_bytes)

    main_records_raw = _extract_records_from_grid_words(
        pages_words=main_pages_words,
        num_min=MAIN_MIN,
        num_max=MAIN_MAX,
        pick_count=MAIN_PICK_COUNT,
        title_fragment="Eurojackpot 5/50"
    )

    euro_records_raw = _extract_records_from_grid_words(
        pages_words=euro_pages_words,
        num_min=EURO_MIN,
        num_max=EURO_MAX,
        pick_count=EURO_PICK_COUNT,
        title_fragment="Eurojackpot 2/12"
    )

    if not main_records_raw:
        raise RuntimeError("Nie udało się wyciągnąć wyników 5/50 z pliku `wyniki1ej.pdf`.")
    if not euro_records_raw:
        raise RuntimeError("Nie udało się wyciągnąć wyników 2/12 z pliku `wyniki2ej.pdf`.")

    main_map = {r["draw_no"]: r["nums"] for r in main_records_raw}
    euro_map = {r["draw_no"]: r["nums"] for r in euro_records_raw}

    common_drawnos = sorted(set(main_map.keys()) & set(euro_map.keys()), reverse=True)

    records = []
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
def compute_presence_percent_df_cached(draws: List[List[int]], nmin: int, nmax: int) -> pd.DataFrame:
    total_draws = len(draws)
    presence_counter = Counter()

    for draw in draws:
        for n in set(draw):
            presence_counter[n] += 1

    rows = []
    for n in range(nmin, nmax + 1):
        hits = presence_counter.get(n, 0)
        pct = (hits / total_draws * 100.0) if total_draws > 0 else 0.0
        rows.append({
            "Liczba": n,
            "Liczba_losowan_z_wystapieniem": hits,
            "Procent_losowan": pct
        })

    df = pd.DataFrame(rows).sort_values(
        ["Procent_losowan", "Liczba_losowan_z_wystapieniem", "Liczba"],
        ascending=[False, False, True]
    ).reset_index(drop=True)
    return df


def build_groups_from_percent(percent_df: pd.DataFrame, hot_size: int, cold_size: int, nmin: int, nmax: int) -> Tuple[List[int], List[int], List[int]]:
    hot = percent_df.head(hot_size)["Liczba"].tolist()
    cold = percent_df.tail(cold_size)["Liczba"].tolist()
    neutral = [n for n in range(nmin, nmax + 1) if n not in hot and n not in cold]
    return hot, cold, neutral


def build_hot_master_set(percent_df: pd.DataFrame, pick_count: int) -> List[int]:
    return sorted(percent_df.head(pick_count)["Liczba"].tolist())


@st.cache_data(show_spinner=False)
def compute_pair_triple_stats_main_cached(draws: List[List[int]]) -> Tuple[Counter, Counter]:
    pair_counter = Counter()
    triple_counter = Counter()

    for draw in draws:
        sdraw = sorted(draw)
        for pair in combinations(sdraw, 2):
            pair_counter[pair] += 1
        for triple in combinations(sdraw, 3):
            triple_counter[triple] += 1

    return pair_counter, triple_counter


@st.cache_data(show_spinner=False)
def compute_pair_stats_euro_cached(draws: List[List[int]]) -> Counter:
    pair_counter = Counter()
    for draw in draws:
        sdraw = sorted(draw)
        if len(sdraw) == 2:
            pair_counter[tuple(sdraw)] += 1
    return pair_counter


def build_target_profile(draws: List[List[int]], threshold: int) -> Dict:
    spreads = [(max(d) - min(d)) for d in draws if d]
    pair_counts = [count_adjacent_pairs(sorted(d)) for d in draws if d]

    even_odd_counter = Counter()
    low_high_counter = Counter()

    for d in draws:
        s = sorted(d)
        ev, od = even_odd_split(s)
        even_odd_counter[(ev, od)] += 1

        low = sum(1 for x in s if x <= threshold)
        high = len(s) - low
        low_high_counter[(low, high)] += 1

    target_even_odd = even_odd_counter.most_common(1)[0][0] if even_odd_counter else (len(draws[0]) // 2, len(draws[0]) - len(draws[0]) // 2)
    target_low_high = low_high_counter.most_common(1)[0][0] if low_high_counter else (len(draws[0]) // 2, len(draws[0]) - len(draws[0]) // 2)
    target_spread = sum(spreads) / len(spreads) if spreads else 0.0
    target_pairs = sum(pair_counts) / len(pair_counts) if pair_counts else 0.0

    return {
        "target_even_odd": target_even_odd,
        "target_low_high": target_low_high,
        "target_spread": target_spread,
        "target_pairs": target_pairs,
    }


# =========================================================
# HEATMAPS
# =========================================================
def build_heatmap_df(percent_df: pd.DataFrame, nmin: int, nmax: int, columns_per_row: int) -> pd.DataFrame:
    values = dict(zip(percent_df["Liczba"], percent_df["Procent_losowan"]))
    rows = []
    current = []
    for n in range(nmin, nmax + 1):
        current.append(f"{n:02d}\n{values.get(n, 0.0):.2f}%")
        if len(current) == columns_per_row:
            rows.append(current)
            current = []
    if current:
        while len(current) < columns_per_row:
            current.append("")
        rows.append(current)

    col_names = [f"C{i+1}" for i in range(columns_per_row)]
    return pd.DataFrame(rows, columns=col_names)


# =========================================================
# GENERATORS
# =========================================================
def gen_side_ticket(mode: str, hot: List[int], cold: List[int], pick_count: int, mix_hot_count: int, nmin: int, nmax: int) -> List[int]:
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
    if mode == "random":
        return pick_unique(list(range(nmin, nmax + 1)), pick_count)
    raise ValueError("Nieznany tryb losowania.")


# =========================================================
# SMART MODE
# =========================================================
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
    out = []
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
# POSITIONAL DIFFERENCE ANALYSIS
# =========================================================
def _choose_candidate_from_diffs(base_value: int, diff_counter: Counter, used: set, nmin: int, nmax: int) -> Optional[int]:
    for diff, _count in diff_counter.most_common():
        candidate = base_value + diff
        if nmin <= candidate <= nmax and candidate not in used:
            return candidate
    return None


def build_positional_difference_set(draws: List[List[int]], window: int, pick_count: int, nmin: int, nmax: int) -> Dict:
    if not draws:
        return {"set": [], "details": [], "window_used": 0}

    latest = sorted(draws[0])
    subset = draws[:max(2, min(window, len(draws)))]
    previous_draws = [sorted(d) for d in subset[1:]]

    used = set()
    result = []
    details = []

    for pos in range(pick_count):
        latest_val = latest[pos]
        diffs = []

        for prev in previous_draws:
            if len(prev) != pick_count:
                continue
            diff = prev[pos] - latest_val
            diffs.append(diff)

        diff_counter = Counter(diffs)
        chosen = _choose_candidate_from_diffs(latest_val, diff_counter, used, nmin, nmax)

        if chosen is None:
            fallback = latest_val
            if fallback in used:
                for candidate in range(nmin, nmax + 1):
                    if candidate not in used:
                        fallback = candidate
                        break
            chosen = fallback

        used.add(chosen)
        result.append(chosen)

        most_common_diff = None
        most_common_count = 0
        if diff_counter:
            most_common_diff, most_common_count = diff_counter.most_common(1)[0]

        details.append({
            "Pozycja": pos + 1,
            "Najnowsza liczba": latest_val,
            "Najczęstsza różnica": most_common_diff if most_common_diff is not None else 0,
            "Ile razy": most_common_count,
            "Wybrana liczba": chosen
        })

    result = sorted(result)

    if len(set(result)) < pick_count:
        fixed = []
        used2 = set()
        for n in result:
            if n not in used2:
                fixed.append(n)
                used2.add(n)
            else:
                for c in range(nmin, nmax + 1):
                    if c not in used2:
                        fixed.append(c)
                        used2.add(c)
                        break
        result = sorted(fixed[:pick_count])

    return {
        "set": result,
        "details": details,
        "window_used": len(subset)
    }


# =========================================================
# HOT MAX
# =========================================================
def build_hot_max_set(percent_df: pd.DataFrame, pick_count: int) -> Tuple[List[int], pd.DataFrame]:
    top = percent_df.head(pick_count).copy()
    result_set = sorted(top["Liczba"].tolist())
    return result_set, top


# =========================================================
# TURBO SCORE
# =========================================================
def similarity_to_recent(ticket: List[int], recent_draws: List[List[int]]) -> int:
    tset = set(ticket)
    if not recent_draws:
        return 0
    return max(len(tset.intersection(set(d))) for d in recent_draws)


def score_main_ticket(
    ticket: List[int],
    percent_map: Dict[int, float],
    pair_counter: Counter,
    triple_counter: Counter,
    target_profile: Dict,
    recent_draws: List[List[int]]
) -> Dict:
    sticket = sorted(ticket)

    number_score = sum(percent_map.get(n, 0.0) for n in sticket)
    pair_score_raw = sum(pair_counter.get(tuple(pair), 0) for pair in combinations(sticket, 2))
    triple_score_raw = sum(triple_counter.get(tuple(triple), 0) for triple in combinations(sticket, 3))

    ev, od = even_odd_split(sticket)
    target_ev, target_od = target_profile["target_even_odd"]
    even_odd_penalty = abs(ev - target_ev) + abs(od - target_od)

    low = sum(1 for x in sticket if x <= 25)
    high = len(sticket) - low
    target_low, target_high = target_profile["target_low_high"]
    low_high_penalty = abs(low - target_low) + abs(high - target_high)

    spread = sticket[-1] - sticket[0]
    spread_penalty = abs(spread - target_profile["target_spread"])

    adj_pairs = count_adjacent_pairs(sticket)
    pair_shape_penalty = abs(adj_pairs - target_profile["target_pairs"])

    recent_similarity = similarity_to_recent(sticket, recent_draws)

    final_score = (
        number_score * 3.0
        + pair_score_raw * 0.55
        + triple_score_raw * 1.10
        - even_odd_penalty * 2.0
        - low_high_penalty * 2.0
        - spread_penalty * 0.10
        - pair_shape_penalty * 1.30
        - recent_similarity * 4.0
    )

    return {
        "ticket": sticket,
        "number_score": number_score,
        "pair_score_raw": pair_score_raw,
        "triple_score_raw": triple_score_raw,
        "evens": ev,
        "odds": od,
        "low": low,
        "high": high,
        "spread": spread,
        "adj_pairs": adj_pairs,
        "recent_similarity": recent_similarity,
        "final_score": final_score,
    }


def score_euro_ticket(
    ticket: List[int],
    percent_map: Dict[int, float],
    pair_counter: Counter,
    target_profile: Dict,
    recent_draws: List[List[int]]
) -> Dict:
    sticket = sorted(ticket)

    number_score = sum(percent_map.get(n, 0.0) for n in sticket)
    pair_score_raw = pair_counter.get(tuple(sticket), 0)

    ev, od = even_odd_split(sticket)
    target_ev, target_od = target_profile["target_even_odd"]
    even_odd_penalty = abs(ev - target_ev) + abs(od - target_od)

    low = sum(1 for x in sticket if x <= 6)
    high = len(sticket) - low
    target_low, target_high = target_profile["target_low_high"]
    low_high_penalty = abs(low - target_low) + abs(high - target_high)

    spread = sticket[-1] - sticket[0]
    spread_penalty = abs(spread - target_profile["target_spread"])

    recent_similarity = similarity_to_recent(sticket, recent_draws)

    final_score = (
        number_score * 3.2
        + pair_score_raw * 1.30
        - even_odd_penalty * 1.8
        - low_high_penalty * 1.8
        - spread_penalty * 0.15
        - recent_similarity * 2.8
    )

    return {
        "ticket": sticket,
        "number_score": number_score,
        "pair_score_raw": pair_score_raw,
        "evens": ev,
        "odds": od,
        "low": low,
        "high": high,
        "spread": spread,
        "recent_similarity": recent_similarity,
        "final_score": final_score,
    }


def generate_candidate_records(
    count_candidates: int,
    base_mode_kind: str,
    hot_main: List[int],
    cold_main: List[int],
    hot_euro: List[int],
    cold_euro: List[int],
    mix_main_hot_count: int,
    mix_euro_hot_count: int
) -> List[Tuple[List[int], List[int]]]:
    candidates = []

    for _ in range(count_candidates):
        if base_mode_kind == "hybrid":
            chosen = random.choices(["hot", "cold", "mix"], weights=[HYBRID_HOT_P, HYBRID_COLD_P, HYBRID_MIX_P], k=1)[0]
            main = gen_side_ticket(chosen, hot_main, cold_main, MAIN_PICK_COUNT, mix_main_hot_count, MAIN_MIN, MAIN_MAX)
            euro = gen_side_ticket(chosen, hot_euro, cold_euro, EURO_PICK_COUNT, mix_euro_hot_count, EURO_MIN, EURO_MAX)
        elif base_mode_kind == "hot":
            main = gen_side_ticket("hot", hot_main, cold_main, MAIN_PICK_COUNT, mix_main_hot_count, MAIN_MIN, MAIN_MAX)
            euro = gen_side_ticket("hot", hot_euro, cold_euro, EURO_PICK_COUNT, mix_euro_hot_count, EURO_MIN, EURO_MAX)
        elif base_mode_kind == "cold":
            main = gen_side_ticket("cold", hot_main, cold_main, MAIN_PICK_COUNT, mix_main_hot_count, MAIN_MIN, MAIN_MAX)
            euro = gen_side_ticket("cold", hot_euro, cold_euro, EURO_PICK_COUNT, mix_euro_hot_count, EURO_MIN, EURO_MAX)
        else:
            main = gen_side_ticket("mix", hot_main, cold_main, MAIN_PICK_COUNT, mix_main_hot_count, MAIN_MIN, MAIN_MAX)
            euro = gen_side_ticket("mix", hot_euro, cold_euro, EURO_PICK_COUNT, mix_euro_hot_count, EURO_MIN, EURO_MAX)

        candidates.append((main, euro))

    uniq = []
    seen = set()
    for main, euro in candidates:
        key = (tuple(main), tuple(euro))
        if key not in seen:
            seen.add(key)
            uniq.append((main, euro))

    return uniq


def build_turbo_score_ranking(
    main_draws: List[List[int]],
    euro_draws: List[List[int]],
    hot_main: List[int],
    cold_main: List[int],
    hot_euro: List[int],
    cold_euro: List[int],
    base_mode_kind: str,
    mix_main_hot_count: int,
    mix_euro_hot_count: int,
    candidate_count: int,
    top_n: int
) -> Dict:
    main_percent_df = compute_presence_percent_df_cached(main_draws, MAIN_MIN, MAIN_MAX)
    euro_percent_df = compute_presence_percent_df_cached(euro_draws, EURO_MIN, EURO_MAX)

    main_percent_map = dict(zip(main_percent_df["Liczba"], main_percent_df["Procent_losowan"]))
    euro_percent_map = dict(zip(euro_percent_df["Liczba"], euro_percent_df["Procent_losowan"]))

    main_pair_counter, main_triple_counter = compute_pair_triple_stats_main_cached(main_draws)
    euro_pair_counter = compute_pair_stats_euro_cached(euro_draws)

    main_target_profile = build_target_profile(main_draws, threshold=25)
    euro_target_profile = build_target_profile(euro_draws, threshold=6)

    recent_main = main_draws[:10]
    recent_euro = euro_draws[:10]

    candidates = generate_candidate_records(
        count_candidates=candidate_count,
        base_mode_kind=base_mode_kind,
        hot_main=hot_main,
        cold_main=cold_main,
        hot_euro=hot_euro,
        cold_euro=cold_euro,
        mix_main_hot_count=mix_main_hot_count,
        mix_euro_hot_count=mix_euro_hot_count
    )

    scored = []
    for main_ticket, euro_ticket in candidates:
        main_score = score_main_ticket(
            ticket=main_ticket,
            percent_map=main_percent_map,
            pair_counter=main_pair_counter,
            triple_counter=main_triple_counter,
            target_profile=main_target_profile,
            recent_draws=recent_main
        )
        euro_score = score_euro_ticket(
            ticket=euro_ticket,
            percent_map=euro_percent_map,
            pair_counter=euro_pair_counter,
            target_profile=euro_target_profile,
            recent_draws=recent_euro
        )

        final_score = main_score["final_score"] + euro_score["final_score"]

        scored.append({
            "main_ticket": main_ticket,
            "euro_ticket": euro_ticket,
            "main_score": main_score,
            "euro_score": euro_score,
            "final_score": final_score,
        })

    scored.sort(key=lambda x: x["final_score"], reverse=True)
    best = scored[:top_n]

    rows = []
    for i, item in enumerate(best, start=1):
        rows.append({
            "Ranking": i,
            "Main 5/50": " ".join(f"{x:02d}" for x in item["main_ticket"]),
            "Euro 2/12": " ".join(f"{x:02d}" for x in item["euro_ticket"]),
            "Score": round(item["final_score"], 2),
            "Main Score": round(item["main_score"]["final_score"], 2),
            "Euro Score": round(item["euro_score"]["final_score"], 2),
            "Main P/N": f"{item['main_score']['evens']}/{item['main_score']['odds']}",
            "Euro P/N": f"{item['euro_score']['evens']}/{item['euro_score']['odds']}",
            "Main rozstrzał": item["main_score"]["spread"],
            "Euro rozstrzał": item["euro_score"]["spread"],
            "Podobieństwo main": item["main_score"]["recent_similarity"],
            "Podobieństwo euro": item["euro_score"]["recent_similarity"],
        })

    return {
        "rows": rows,
        "candidate_count_used": len(candidates),
        "main_target_profile": main_target_profile,
        "euro_target_profile": euro_target_profile,
    }


# =========================================================
# PREMIUM MODE
# =========================================================
def mutate_ticket(ticket: List[int], source_pool: List[int], replace_count: int, pick_count: int) -> List[int]:
    base = set(ticket)
    replace_count = min(replace_count, len(base))
    to_remove = set(random.sample(list(base), replace_count))
    kept = [x for x in base if x not in to_remove]
    available = [x for x in source_pool if x not in kept]
    need = pick_count - len(kept)

    if len(available) < need:
        available = [x for x in source_pool if x not in kept]

    added = random.sample(available, need)
    return sorted(kept + added)


def build_premium_ranking(
    main_draws: List[List[int]],
    euro_draws: List[List[int]],
    hot_main: List[int],
    cold_main: List[int],
    hot_euro: List[int],
    cold_euro: List[int],
    mix_main_hot_count: int,
    mix_euro_hot_count: int,
    candidate_count: int,
    top_n: int
) -> Dict:
    main_percent_df = compute_presence_percent_df_cached(main_draws, MAIN_MIN, MAIN_MAX)
    euro_percent_df = compute_presence_percent_df_cached(euro_draws, EURO_MIN, EURO_MAX)

    hot_max_main_set, hot_max_main_table = build_hot_max_set(main_percent_df, MAIN_PICK_COUNT)
    hot_max_euro_set, hot_max_euro_table = build_hot_max_set(euro_percent_df, EURO_PICK_COUNT)

    diff_main = build_positional_difference_set(main_draws, min(999, len(main_draws)), MAIN_PICK_COUNT, MAIN_MIN, MAIN_MAX)
    diff_euro = build_positional_difference_set(euro_draws, min(999, len(euro_draws)), EURO_PICK_COUNT, EURO_MIN, EURO_MAX)

    turbo_seed = build_turbo_score_ranking(
        main_draws=main_draws,
        euro_draws=euro_draws,
        hot_main=hot_main,
        cold_main=cold_main,
        hot_euro=hot_euro,
        cold_euro=cold_euro,
        base_mode_kind="hybrid",
        mix_main_hot_count=mix_main_hot_count,
        mix_euro_hot_count=mix_euro_hot_count,
        candidate_count=max(150, candidate_count // 2),
        top_n=min(12, max(5, top_n * 2))
    )

    seed_candidates = []
    seed_candidates.append((sorted(hot_max_main_set), sorted(hot_max_euro_set)))
    seed_candidates.append((sorted(diff_main["set"]), sorted(diff_euro["set"])))

    for row in turbo_seed["rows"]:
        seed_candidates.append((
            sorted([int(x) for x in row["Main 5/50"].split()]),
            sorted([int(x) for x in row["Euro 2/12"].split()])
        ))

    ordinary_candidates = generate_candidate_records(
        count_candidates=max(candidate_count, 250),
        base_mode_kind="hybrid",
        hot_main=hot_main,
        cold_main=cold_main,
        hot_euro=hot_euro,
        cold_euro=cold_euro,
        mix_main_hot_count=mix_main_hot_count,
        mix_euro_hot_count=mix_euro_hot_count
    )

    seed_candidates.extend(ordinary_candidates)

    source_pool_main = list(dict.fromkeys(hot_main + hot_max_main_set + diff_main["set"] + list(range(MAIN_MIN, MAIN_MAX + 1))))
    source_pool_euro = list(dict.fromkeys(hot_euro + hot_max_euro_set + diff_euro["set"] + list(range(EURO_MIN, EURO_MAX + 1))))

    mutated = []
    for main_ticket, euro_ticket in seed_candidates[:min(len(seed_candidates), candidate_count)]:
        mutated.append((sorted(main_ticket), sorted(euro_ticket)))
        mutated.append((
            mutate_ticket(main_ticket, source_pool_main, 1, MAIN_PICK_COUNT),
            mutate_ticket(euro_ticket, source_pool_euro, 1, EURO_PICK_COUNT),
        ))
        mutated.append((
            mutate_ticket(main_ticket, source_pool_main, 2, MAIN_PICK_COUNT),
            mutate_ticket(euro_ticket, source_pool_euro, 1, EURO_PICK_COUNT),
        ))

    all_candidates = seed_candidates + mutated

    uniq = []
    seen = set()
    for main_ticket, euro_ticket in all_candidates:
        key = (tuple(sorted(main_ticket)), tuple(sorted(euro_ticket)))
        if len(key[0]) == MAIN_PICK_COUNT and len(key[1]) == EURO_PICK_COUNT and key not in seen:
            seen.add(key)
            uniq.append((sorted(main_ticket), sorted(euro_ticket)))

    turbo_full = build_turbo_score_ranking(
        main_draws=main_draws,
        euro_draws=euro_draws,
        hot_main=hot_main,
        cold_main=cold_main,
        hot_euro=hot_euro,
        cold_euro=cold_euro,
        base_mode_kind="hybrid",
        mix_main_hot_count=mix_main_hot_count,
        mix_euro_hot_count=mix_euro_hot_count,
        candidate_count=max(100, len(uniq)),
        top_n=max(10, top_n)
    )

    main_percent_map = dict(zip(main_percent_df["Liczba"], main_percent_df["Procent_losowan"]))
    euro_percent_map = dict(zip(euro_percent_df["Liczba"], euro_percent_df["Procent_losowan"]))
    main_pair_counter, main_triple_counter = compute_pair_triple_stats_main_cached(main_draws)
    euro_pair_counter = compute_pair_stats_euro_cached(euro_draws)
    main_target_profile = build_target_profile(main_draws, threshold=25)
    euro_target_profile = build_target_profile(euro_draws, threshold=6)
    recent_main = main_draws[:10]
    recent_euro = euro_draws[:10]

    hot_max_main_ref = set(hot_max_main_set)
    hot_max_euro_ref = set(hot_max_euro_set)
    diff_main_ref = set(diff_main["set"])
    diff_euro_ref = set(diff_euro["set"])
    hot_main_ref = set(hot_main)
    hot_euro_ref = set(hot_euro)

    premium_scored = []

    for main_ticket, euro_ticket in uniq:
        main_score = score_main_ticket(
            main_ticket,
            main_percent_map,
            main_pair_counter,
            main_triple_counter,
            main_target_profile,
            recent_main
        )
        euro_score = score_euro_ticket(
            euro_ticket,
            euro_percent_map,
            euro_pair_counter,
            euro_target_profile,
            recent_euro
        )

        overlap_hot_max_main = len(set(main_ticket).intersection(hot_max_main_ref))
        overlap_hot_max_euro = len(set(euro_ticket).intersection(hot_max_euro_ref))
        overlap_diff_main = len(set(main_ticket).intersection(diff_main_ref))
        overlap_diff_euro = len(set(euro_ticket).intersection(diff_euro_ref))
        overlap_hot_main = len(set(main_ticket).intersection(hot_main_ref))
        overlap_hot_euro = len(set(euro_ticket).intersection(hot_euro_ref))

        premium_bonus = (
            overlap_hot_max_main * 4.2
            + overlap_hot_max_euro * 4.8
            + overlap_diff_main * 2.6
            + overlap_diff_euro * 3.0
            + overlap_hot_main * 1.1
            + overlap_hot_euro * 1.4
        )

        premium_final_score = main_score["final_score"] + euro_score["final_score"] + premium_bonus

        premium_scored.append({
            "main_ticket": main_ticket,
            "euro_ticket": euro_ticket,
            "main_score": main_score,
            "euro_score": euro_score,
            "premium_bonus": premium_bonus,
            "premium_final_score": premium_final_score,
            "overlap_hot_max_main": overlap_hot_max_main,
            "overlap_hot_max_euro": overlap_hot_max_euro,
            "overlap_diff_main": overlap_diff_main,
            "overlap_diff_euro": overlap_diff_euro,
            "overlap_hot_main": overlap_hot_main,
            "overlap_hot_euro": overlap_hot_euro,
        })

    premium_scored.sort(key=lambda x: x["premium_final_score"], reverse=True)
    best = premium_scored[:top_n]

    rows = []
    for i, item in enumerate(best, start=1):
        rows.append({
            "Ranking": i,
            "Main 5/50": " ".join(f"{x:02d}" for x in item["main_ticket"]),
            "Euro 2/12": " ".join(f"{x:02d}" for x in item["euro_ticket"]),
            "Premium Score": round(item["premium_final_score"], 2),
            "Bazowy Score Main": round(item["main_score"]["final_score"], 2),
            "Bazowy Score Euro": round(item["euro_score"]["final_score"], 2),
            "Bonus Premium": round(item["premium_bonus"], 2),
            "HOT MAX main": item["overlap_hot_max_main"],
            "HOT MAX euro": item["overlap_hot_max_euro"],
            "Różnice main": item["overlap_diff_main"],
            "Różnice euro": item["overlap_diff_euro"],
            "Hot main": item["overlap_hot_main"],
            "Hot euro": item["overlap_hot_euro"],
        })

    return {
        "rows": rows,
        "candidate_count_used": len(uniq),
        "hot_max_main_set": hot_max_main_set,
        "hot_max_euro_set": hot_max_euro_set,
        "hot_max_main_table": hot_max_main_table,
        "hot_max_euro_table": hot_max_euro_table,
        "diff_main": diff_main,
        "diff_euro": diff_euro,
        "main_target_profile": main_target_profile,
        "euro_target_profile": euro_target_profile,
    }


# =========================================================
# AI SIMULATION
# =========================================================
def weighted_sample_without_replacement(population: np.ndarray, weights: np.ndarray, k: int, rng: np.random.Generator) -> List[int]:
    probs = weights / weights.sum()
    chosen = rng.choice(population, size=k, replace=False, p=probs)
    return sorted(chosen.tolist())


@st.cache_data(show_spinner=False)
def run_ai_simulation_cached(
    main_percent_df: pd.DataFrame,
    euro_percent_df: pd.DataFrame,
    n_sims: int
) -> Dict:
    rng = np.random.default_rng(12345)

    main_population = np.array(main_percent_df["Liczba"].tolist(), dtype=int)
    euro_population = np.array(euro_percent_df["Liczba"].tolist(), dtype=int)

    main_weights = np.array(main_percent_df["Procent_losowan"].tolist(), dtype=float) + 0.01
    euro_weights = np.array(euro_percent_df["Procent_losowan"].tolist(), dtype=float) + 0.01

    main_occ = Counter()
    euro_occ = Counter()
    main_pair_occ = Counter()
    euro_pair_occ = Counter()

    for _ in range(n_sims):
        main_draw = weighted_sample_without_replacement(main_population, main_weights, MAIN_PICK_COUNT, rng)
        euro_draw = weighted_sample_without_replacement(euro_population, euro_weights, EURO_PICK_COUNT, rng)

        for n in main_draw:
            main_occ[n] += 1
        for n in euro_draw:
            euro_occ[n] += 1

        for pair in combinations(main_draw, 2):
            main_pair_occ[pair] += 1
        for pair in combinations(euro_draw, 2):
            euro_pair_occ[pair] += 1

    main_df = pd.DataFrame(
        [{"Liczba": n, "Symulacje_wystapien": main_occ.get(n, 0)} for n in range(MAIN_MIN, MAIN_MAX + 1)]
    ).sort_values(["Symulacje_wystapien", "Liczba"], ascending=[False, True]).reset_index(drop=True)

    euro_df = pd.DataFrame(
        [{"Liczba": n, "Symulacje_wystapien": euro_occ.get(n, 0)} for n in range(EURO_MIN, EURO_MAX + 1)]
    ).sort_values(["Symulacje_wystapien", "Liczba"], ascending=[False, True]).reset_index(drop=True)

    sim_main_set = sorted(main_df.head(MAIN_PICK_COUNT)["Liczba"].tolist())
    sim_euro_set = sorted(euro_df.head(EURO_PICK_COUNT)["Liczba"].tolist())

    top_main_pairs = pd.DataFrame(
        [{"Para": f"{a:02d}-{b:02d}", "Wystąpienia": c} for (a, b), c in main_pair_occ.most_common(10)]
    )
    top_euro_pairs = pd.DataFrame(
        [{"Para": f"{a:02d}-{b:02d}", "Wystąpienia": c} for (a, b), c in euro_pair_occ.most_common(10)]
    )

    return {
        "main_df": main_df,
        "euro_df": euro_df,
        "sim_main_set": sim_main_set,
        "sim_euro_set": sim_euro_set,
        "top_main_pairs": top_main_pairs,
        "top_euro_pairs": top_euro_pairs,
        "n_sims": n_sims
    }


# =========================================================
# CYCLE DETECTION
# =========================================================
@st.cache_data(show_spinner=False)
def detect_cycles_cached(draws: List[List[int]], nmin: int, nmax: int) -> pd.DataFrame:
    chronological = list(reversed(draws))
    total = len(chronological)

    rows = []

    for num in range(nmin, nmax + 1):
        positions = []
        for idx, draw in enumerate(chronological):
            if num in draw:
                positions.append(idx)

        occurrences = len(positions)

        if occurrences >= 2:
            gaps = [b - a for a, b in zip(positions[:-1], positions[1:])]
            avg_gap = float(sum(gaps) / len(gaps))
            last_gap = float((total - 1) - positions[-1])
            cycle_ratio = (last_gap / avg_gap) if avg_gap > 0 else 0.0
        elif occurrences == 1:
            avg_gap = 0.0
            last_gap = float((total - 1) - positions[-1])
            cycle_ratio = 0.0
        else:
            avg_gap = 0.0
            last_gap = float(total)
            cycle_ratio = 0.0

        rows.append({
            "Liczba": num,
            "Wystąpienia": occurrences,
            "Średni_cykl": round(avg_gap, 2),
            "Aktualna_przerwa": round(last_gap, 2),
            "Cycle_Ratio": round(cycle_ratio, 3)
        })

    df = pd.DataFrame(rows).sort_values(
        ["Cycle_Ratio", "Wystąpienia", "Liczba"],
        ascending=[False, False, True]
    ).reset_index(drop=True)

    return df


# =========================================================
# TXT EXPORTS
# =========================================================
def make_txt_for_results(records: List[Dict]) -> bytes:
    lines = []
    for r in records:
        draw_str = str(r["draw_no"]) if r["draw_no"] is not None else "—"
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


def make_txt_for_hot_set(main_set: List[int], euro_set: List[int], history_window: int) -> bytes:
    main_str = " ".join(f"{x:02d}" for x in main_set)
    euro_str = " ".join(f"{x:02d}" for x in euro_set)
    text = (
        "Eurojackpot HOT 6/2\n"
        f"Analizowana historia: ostatnie {history_window} losowań\n"
        f"Main 5/50: {main_str}\n"
        f"Euro 2/12: {euro_str}\n"
    )
    return text.encode("utf-8")


def make_txt_for_difference_set(main_diff: Dict, euro_diff: Dict, selected_window: int) -> bytes:
    main_str = " ".join(f"{x:02d}" for x in main_diff["set"])
    euro_str = " ".join(f"{x:02d}" for x in euro_diff["set"])
    lines = [
        "Eurojackpot — zestaw różnic pozycyjnych",
        f"Wybrany zakres użytkownika: {selected_window}",
        f"Main 5/50: {main_str}",
        f"Euro 2/12: {euro_str}",
        "",
        "Szczegóły MAIN:"
    ]
    for d in main_diff["details"]:
        lines.append(
            f"Pozycja {d['Pozycja']}: najnowsza={d['Najnowsza liczba']}, "
            f"najczęstsza różnica={d['Najczęstsza różnica']}, ile razy={d['Ile razy']}, wybrana={d['Wybrana liczba']}"
        )
    lines.append("")
    lines.append("Szczegóły EURO:")
    for d in euro_diff["details"]:
        lines.append(
            f"Pozycja {d['Pozycja']}: najnowsza={d['Najnowsza liczba']}, "
            f"najczęstsza różnica={d['Najczęstsza różnica']}, ile razy={d['Ile razy']}, wybrana={d['Wybrana liczba']}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_turbo_score(rows: List[Dict], candidate_count_used: int) -> bytes:
    lines = [
        "Eurojackpot Turbo Score — ranking kuponów",
        f"Liczba ocenionych kandydatów: {candidate_count_used}",
        ""
    ]
    for row in rows:
        lines.append(
            f"#{row['Ranking']} | Main={row['Main 5/50']} | Euro={row['Euro 2/12']} | "
            f"Score={row['Score']} | MainScore={row['Main Score']} | EuroScore={row['Euro Score']}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_premium(rows: List[Dict], candidate_count_used: int) -> bytes:
    lines = [
        "Eurojackpot Premium — ranking kuponów",
        f"Liczba ocenionych kandydatów: {candidate_count_used}",
        ""
    ]
    for row in rows:
        lines.append(
            f"#{row['Ranking']} | Main={row['Main 5/50']} | Euro={row['Euro 2/12']} | "
            f"PremiumScore={row['Premium Score']} | Bonus={row['Bonus Premium']}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_simulation(sim: Dict) -> bytes:
    main_str = " ".join(f"{x:02d}" for x in sim["sim_main_set"])
    euro_str = " ".join(f"{x:02d}" for x in sim["sim_euro_set"])
    lines = [
        f"AI symulacja Eurojackpot — liczba symulacji: {sim['n_sims']}",
        f"Sugerowany Main 5/50: {main_str}",
        f"Sugerowany Euro 2/12: {euro_str}",
        "",
        "TOP pary MAIN:"
    ]
    if not sim["top_main_pairs"].empty:
        for _, row in sim["top_main_pairs"].iterrows():
            lines.append(f"{row['Para']} -> {row['Wystąpienia']}")
    lines.append("")
    lines.append("TOP pary EURO:")
    if not sim["top_euro_pairs"].empty:
        for _, row in sim["top_euro_pairs"].iterrows():
            lines.append(f"{row['Para']} -> {row['Wystąpienia']}")
    return ("\n".join(lines) + "\n").encode("utf-8")


def make_txt_for_cycles(main_cycle_df: pd.DataFrame, euro_cycle_df: pd.DataFrame, main_set: List[int], euro_set: List[int]) -> bytes:
    main_str = " ".join(f"{x:02d}" for x in main_set)
    euro_str = " ".join(f"{x:02d}" for x in euro_set)

    lines = [
        "Eurojackpot — analiza cykli liczb",
        f"Sugerowany Main 5/50: {main_str}",
        f"Sugerowany Euro 2/12: {euro_str}",
        "",
        "TOP MAIN:"
    ]
    for _, row in main_cycle_df.head(10).iterrows():
        lines.append(
            f"Liczba {int(row['Liczba']):02d} | Wystąpienia={int(row['Wystąpienia'])} | "
            f"Średni cykl={row['Średni_cykl']} | Aktualna przerwa={row['Aktualna_przerwa']} | "
            f"Cycle ratio={row['Cycle_Ratio']}"
        )
    lines.append("")
    lines.append("TOP EURO:")
    for _, row in euro_cycle_df.head(10).iterrows():
        lines.append(
            f"Liczba {int(row['Liczba']):02d} | Wystąpienia={int(row['Wystąpienia'])} | "
            f"Średni cykl={row['Średni_cykl']} | Aktualna przerwa={row['Aktualna_przerwa']} | "
            f"Cycle ratio={row['Cycle_Ratio']}"
        )
    return ("\n".join(lines) + "\n").encode("utf-8")


# =========================================================
# FEATURE DESCRIPTIONS
# =========================================================
def render_feature_descriptions():
    with st.expander("📘 Opisy funkcji aplikacji", expanded=False):
        st.markdown("""
**⚽ Generuj kupony**  
Tworzy kupony zgodnie z wybranym trybem: hybryda, gorące, zimne, mix albo premium.

**🌿 Cyfry dnia**  
Buduje zestaw dnia na podstawie ostatnich wyników, trendu parzyste/nieparzyste, niskie/wysokie i rozstrzału.

**📋 Pokaż wyniki**  
Pokazuje ostatnie wyniki Eurojackpot odczytane z `wyniki1ej.pdf` i `wyniki2ej.pdf`.

**🔥 HOT SET**  
Pokazuje najczęściej występujące liczby według procentu wystąpień w losowaniach.

**📐 Zestaw różnic**  
Analizuje różnice pozycji między najnowszym losowaniem a wcześniejszymi i buduje nowy zestaw.

**🔥 HOT MAX**  
Buduje pełny zestaw z liczb o najwyższym procencie wystąpień.

**⭐ Turbo Score**  
Generuje wielu kandydatów i ocenia ich na podstawie:
- procentu wystąpień,
- par,
- trójek (dla 5/50),
- balansu parzyste/nieparzyste,
- balansu niskie/wysokie,
- rozstrzału,
- podobieństwa do ostatnich wyników.

**👑 Premium**  
Łączy jednocześnie:
- HOT/COLD,
- HOT MAX,
- zestaw różnic,
- Turbo Score,
- mutacje kandydatów.  
Na końcu wybiera topowe kupony premium.

**🟦 Heatmapa**  
Pokazuje mapę liczb 1–50 i 1–12 wraz z procentem wystąpień.

**🤖 AI symulacja**  
Uruchamia ważone symulacje losowań na podstawie historycznych procentów i pokazuje sugerowany zestaw.

**🔄 Cykle liczb**  
Wyszukuje liczby, które historycznie miały pewien rytm pojawiania się i sprawdza, czy są „blisko swojego cyklu”.

**🧠 Tryb inteligentny**  
Dodatkowe filtry ograniczające mało pożądane układy.
        """)


# =========================================================
# SETTINGS PANEL
# =========================================================
def settings_panel(defaults: Dict) -> Dict:
    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("⚙️ Ustawienia")

    mode_ui = st.selectbox(
        "Tryb typowania",
        [
            "Hybryda 70/20/10 (hot/cold/mix)",
            "Tylko 🔥 gorące",
            "Tylko ❄️ zimne",
            "Tylko ⚗️ mix (hot+zimne)",
            "Premium 👑",
        ],
        index=defaults.get("mode_index", 0),
        help="Premium łączy kilka algorytmów jednocześnie."
    )

    history_window = st.selectbox(
        "Ile ostatnich losowań brać do analizy HOT/COLD?",
        [50, 100, 250, 500, 750, 999],
        index=defaults.get("hist_index", 5)
    )

    difference_window = st.selectbox(
        "Analiza różnic pozycyjnych — zakres losowań",
        [50, 100, 250, 500, 750, 999],
        index=defaults.get("diff_hist_index", 5)
    )

    c1, c2 = st.columns(2)
    with c1:
        n_tickets = st.slider("Liczba kuponów", 1, 300, defaults.get("n_tickets", 30), 1)
        hot_main_size = st.slider("Ile liczb w grupie Gorących (Main 5/50)", 5, 30, defaults.get("hot_main_size", 20), 1)
        hot_euro_size = st.slider("Ile liczb w grupie Gorących (Euro 2/12)", 2, 10, defaults.get("hot_euro_size", 6), 1)
    with c2:
        preview_limit = st.slider("Ile kuponów pokazać w podglądzie", 5, 100, defaults.get("preview_limit", 30), 5)
        cold_main_size = st.slider("Ile liczb w grupie Zimnych (Main 5/50)", 5, 30, defaults.get("cold_main_size", 20), 1)
        cold_euro_size = st.slider("Ile liczb w grupie Zimnych (Euro 2/12)", 2, 10, defaults.get("cold_euro_size", 4), 1)

    mix_main_hot_count = st.slider("MIX: ile liczb z gorących dla Main 5/50?", 1, 4, defaults.get("mix_main_hot_count", 3), 1)
    mix_euro_hot_count = st.slider("MIX: ile liczb z gorących dla Euro 2/12?", 0, 2, defaults.get("mix_euro_hot_count", 1), 1)

    st.markdown("---")
    st.subheader("🔥 HOT MAX")
    hot_max_enabled = st.checkbox(
        "Włącz HOT MAX (działa przy trybie: Tylko gorące)",
        value=defaults.get("hot_max_enabled", False)
    )
    hot_max_main_count = st.selectbox("Ile liczb z HOT MAX dla Main?", [1, 2, 3, 4, 5], index=defaults.get("hot_max_main_idx", 4))
    hot_max_euro_count = st.selectbox("Ile liczb z HOT MAX dla Euro?", [0, 1, 2], index=defaults.get("hot_max_euro_idx", 2))

    st.markdown("---")
    st.subheader("⭐ Turbo Score")
    turbo_candidate_count = st.selectbox(
        "Ile kandydatów ma ocenić Turbo Score?",
        [100, 200, 300, 500, 750, 1000],
        index=defaults.get("turbo_candidate_idx", 3)
    )
    turbo_top_n = st.selectbox(
        "Ile najlepszych kuponów pokazać?",
        [3, 5, 10, 15, 20],
        index=defaults.get("turbo_top_idx", 2)
    )

    st.markdown("---")
    st.subheader("👑 Premium")
    premium_candidate_count = st.selectbox(
        "Premium: ile kandydatów ma zbudować silnik premium?",
        [200, 300, 500, 750, 1000, 1500],
        index=defaults.get("premium_candidate_idx", 2)
    )
    premium_top_n = st.selectbox(
        "Premium: ile finalnych kuponów pokazać?",
        [3, 5, 10, 15, 20],
        index=defaults.get("premium_top_idx", 2)
    )

    st.markdown("---")
    st.subheader("🤖 AI symulacja")
    ai_sim_count = st.selectbox(
        "Ile losowań ma zasymulować AI?",
        [5000, 10000, 25000, 50000, 100000],
        index=defaults.get("ai_sim_idx", 4)
    )

    st.markdown("---")
    st.subheader("🧠 Tryb inteligentny")
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
        "difference_window": int(difference_window),
        "n_tickets": int(n_tickets),
        "hot_main_size": int(hot_main_size),
        "cold_main_size": int(cold_main_size),
        "hot_euro_size": int(hot_euro_size),
        "cold_euro_size": int(cold_euro_size),
        "mix_main_hot_count": int(mix_main_hot_count),
        "mix_euro_hot_count": int(mix_euro_hot_count),
        "preview_limit": int(preview_limit),
        "hot_max_enabled": bool(hot_max_enabled),
        "hot_max_main_count": int(hot_max_main_count),
        "hot_max_euro_count": int(hot_max_euro_count),
        "turbo_candidate_count": int(turbo_candidate_count),
        "turbo_top_n": int(turbo_top_n),
        "premium_candidate_count": int(premium_candidate_count),
        "premium_top_n": int(premium_top_n),
        "ai_sim_count": int(ai_sim_count),
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
    st.markdown(APP_CSS, unsafe_allow_html=True)

    st.title(APP_TITLE)
    st.write("Generator typowań Eurojackpot na bazie prawdziwych wyników z dwóch plików PDF: 5/50 i 2/12.")
    st.caption("Wersja rozszerzona: Hot/Cold, Hot Max, Turbo Score, Premium, Heatmapy, AI symulacja i analiza cykli.")

    if "last_records" not in st.session_state:
        st.session_state["last_records"] = []
    if "last_daily" not in st.session_state:
        st.session_state["last_daily"] = None
    if "show_results" not in st.session_state:
        st.session_state["show_results"] = False
    if "hot_set" not in st.session_state:
        st.session_state["hot_set"] = None
    if "difference_set" not in st.session_state:
        st.session_state["difference_set"] = None
    if "hot_max_set" not in st.session_state:
        st.session_state["hot_max_set"] = None
    if "turbo_score_result" not in st.session_state:
        st.session_state["turbo_score_result"] = None
    if "premium_result" not in st.session_state:
        st.session_state["premium_result"] = None
    if "ai_sim_result" not in st.session_state:
        st.session_state["ai_sim_result"] = None
    if "cycle_result" not in st.session_state:
        st.session_state["cycle_result"] = None

    pdf_main_path = Path(os.getcwd()) / PDF_MAIN_FILENAME
    pdf_euro_path = Path(os.getcwd()) / PDF_EURO_FILENAME

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("📄 Dane wejściowe")
    st.write(f"Plik główny 5/50: `{pdf_main_path}`")
    st.write(f"Plik dodatkowy 2/12: `{pdf_euro_path}`")
    st.markdown('<div class="v-muted">Aplikacja łączy oba PDF-y po numerze losowania.</div>', unsafe_allow_html=True)
    st.markdown("</div>", unsafe_allow_html=True)

    render_feature_descriptions()

    if not pdf_main_path.exists():
        st.error(f"❌ Nie znaleziono `{PDF_MAIN_FILENAME}`.")
        st.stop()

    if not pdf_euro_path.exists():
        st.error(f"❌ Nie znaleziono `{PDF_EURO_FILENAME}`.")
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
        "hist_index": 5,
        "diff_hist_index": 5,
        "n_tickets": 30,
        "hot_main_size": 20,
        "cold_main_size": 20,
        "hot_euro_size": 6,
        "cold_euro_size": 4,
        "mix_main_hot_count": 3,
        "mix_euro_hot_count": 1,
        "preview_limit": 30,
        "hot_max_enabled": False,
        "hot_max_main_idx": 4,
        "hot_max_euro_idx": 2,
        "turbo_candidate_idx": 3,
        "turbo_top_idx": 2,
        "premium_candidate_idx": 2,
        "premium_top_idx": 2,
        "ai_sim_idx": 4,
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

    with st.expander("⚙️ Ustawienia", expanded=True):
        cfg = settings_panel(defaults)

    history_window_used = min(cfg["history_window"], len(result_records_all))
    result_records = result_records_all[:history_window_used]

    main_draws = [r["main_nums"] for r in result_records]
    euro_draws = [r["euro_nums"] for r in result_records]

    main_percent_df = compute_presence_percent_df_cached(main_draws, MAIN_MIN, MAIN_MAX)
    euro_percent_df = compute_presence_percent_df_cached(euro_draws, EURO_MIN, EURO_MAX)

    hot_main, cold_main, _ = build_groups_from_percent(main_percent_df, cfg["hot_main_size"], cfg["cold_main_size"], MAIN_MIN, MAIN_MAX)
    hot_euro, cold_euro, _ = build_groups_from_percent(euro_percent_df, cfg["hot_euro_size"], cfg["cold_euro_size"], EURO_MIN, EURO_MAX)

    hot_main_set = build_hot_master_set(main_percent_df, MAIN_PICK_COUNT)
    hot_euro_set = build_hot_master_set(euro_percent_df, EURO_PICK_COUNT)

    left, right = st.columns([1.2, 0.8], gap="large")

    with left:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("📊 Statystyka procentowa — Main 5/50")
        st.success(f"✅ Analizowane losowania: **{len(result_records)}**")
        main_df_display = main_percent_df.copy()
        main_df_display["Procent_losowan"] = main_df_display["Procent_losowan"].map(lambda x: f"{x:.2f}%")
        st.dataframe(main_df_display, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("📊 Statystyka procentowa — Euro 2/12")
        euro_df_display = euro_percent_df.copy()
        euro_df_display["Procent_losowan"] = euro_df_display["Procent_losowan"].map(lambda x: f"{x:.2f}%")
        st.dataframe(euro_df_display, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    with right:
        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🔥 Gorące / ❄️ Zimne — Main 5/50")
        st.markdown("**Gorące**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(hot_main)]), unsafe_allow_html=True)
        st.markdown("**Zimne**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(cold_main)]), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🔥 Gorące / ❄️ Zimne — Euro 2/12")
        st.markdown("**Gorące**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(hot_euro)]), unsafe_allow_html=True)
        st.markdown("**Zimne**")
        st.markdown(" ".join([f'<span class="v-pill">{n:02d}</span>' for n in sorted(cold_euro)]), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="v-card">', unsafe_allow_html=True)
        st.subheader("🎛️ Wybrany tryb")
        st.write(f"**Tryb:** {cfg['mode_ui']}")
        st.write(f"**Analiza HOT/COLD:** ostatnie **{history_window_used}** losowań")
        st.write(f"**AI symulacja:** {cfg['ai_sim_count']} losowań")
        st.write(f"**Tryb inteligentny:** {'TAK' if cfg['smart_enabled'] else 'NIE'}")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    st.markdown('<div class="v-card">', unsafe_allow_html=True)
    st.subheader("🎟️ Narzędzia")

    c1, c2, c3, c4 = st.columns(4, gap="large")
    with c1:
        generate = st.button("⚽ GENERUJ KUPONY", type="primary", use_container_width=True)
        daily = st.button("🌿 CYFRY DNIA", type="primary", use_container_width=True)
    with c2:
        show_res = st.button("📋 POKAŻ WYNIKI", type="primary", use_container_width=True)
        show_hot = st.button("🔥 HOT SET", type="primary", use_container_width=True)
    with c3:
        build_diff = st.button("📐 ZESTAW RÓŻNIC", type="primary", use_container_width=True)
        build_turbo = st.button("⭐ TURBO SCORE", type="primary", use_container_width=True)
    with c4:
        build_premium = st.button("👑 PREMIUM", type="primary", use_container_width=True)
        build_ai_sim = st.button("🤖 AI SYMULACJA", type="primary", use_container_width=True)

    c5, c6 = st.columns(2, gap="large")
    with c5:
        build_heatmap = st.button("🟦 HEATMAPY", type="primary", use_container_width=True)
    with c6:
        build_cycles = st.button("🔄 CYKLE LICZB", type="primary", use_container_width=True)

    if show_res:
        st.session_state["show_results"] = not st.session_state["show_results"]

    if show_hot:
        st.session_state["hot_set"] = {"main": hot_main_set, "euro": hot_euro_set}

    if build_diff:
        st.session_state["difference_set"] = {
            "main": build_positional_difference_set(main_draws, cfg["difference_window"], MAIN_PICK_COUNT, MAIN_MIN, MAIN_MAX),
            "euro": build_positional_difference_set(euro_draws, cfg["difference_window"], EURO_PICK_COUNT, EURO_MIN, EURO_MAX)
        }

    if build_turbo:
        base_mode_kind = "hybrid"
        if cfg["mode_ui"] == "Tylko 🔥 gorące":
            base_mode_kind = "hot"
        elif cfg["mode_ui"] == "Tylko ❄️ zimne":
            base_mode_kind = "cold"
        elif cfg["mode_ui"] == "Tylko ⚗️ mix (hot+zimne)":
            base_mode_kind = "mix"

        st.session_state["turbo_score_result"] = build_turbo_score_ranking(
            main_draws=main_draws,
            euro_draws=euro_draws,
            hot_main=hot_main,
            cold_main=cold_main,
            hot_euro=hot_euro,
            cold_euro=cold_euro,
            base_mode_kind=base_mode_kind,
            mix_main_hot_count=cfg["mix_main_hot_count"],
            mix_euro_hot_count=cfg["mix_euro_hot_count"],
            candidate_count=cfg["turbo_candidate_count"],
            top_n=cfg["turbo_top_n"]
        )

    if build_premium or cfg["mode_ui"] == "Premium 👑":
        st.session_state["premium_result"] = build_premium_ranking(
            main_draws=main_draws,
            euro_draws=euro_draws,
            hot_main=hot_main,
            cold_main=cold_main,
            hot_euro=hot_euro,
            cold_euro=cold_euro,
            mix_main_hot_count=cfg["mix_main_hot_count"],
            mix_euro_hot_count=cfg["mix_euro_hot_count"],
            candidate_count=cfg["premium_candidate_count"],
            top_n=cfg["premium_top_n"]
        )

    if build_ai_sim:
        st.session_state["ai_sim_result"] = run_ai_simulation_cached(
            main_percent_df=main_percent_df,
            euro_percent_df=euro_percent_df,
            n_sims=cfg["ai_sim_count"]
        )

    if build_cycles:
        main_cycle_df = detect_cycles_cached(main_draws, MAIN_MIN, MAIN_MAX)
        euro_cycle_df = detect_cycles_cached(euro_draws, EURO_MIN, EURO_MAX)
        st.session_state["cycle_result"] = {
            "main_df": main_cycle_df,
            "euro_df": euro_cycle_df,
            "main_set": sorted(main_cycle_df.head(MAIN_PICK_COUNT)["Liczba"].tolist()),
            "euro_set": sorted(euro_cycle_df.head(EURO_PICK_COUNT)["Liczba"].tolist())
        }

    if build_heatmap:
        st.session_state["heatmap_main"] = build_heatmap_df(main_percent_df, MAIN_MIN, MAIN_MAX, 10)
        st.session_state["heatmap_euro"] = build_heatmap_df(euro_percent_df, EURO_MIN, EURO_MAX, 4)

    mode_ui = cfg["mode_ui"]
    if mode_ui == "Hybryda 70/20/10 (hot/cold/mix)":
        base_mode_kind = "hybrid"
    elif mode_ui == "Tylko 🔥 gorące":
        base_mode_kind = "hot"
    elif mode_ui == "Tylko ❄️ zimne":
        base_mode_kind = "cold"
    elif mode_ui == "Premium 👑":
        base_mode_kind = "premium"
    else:
        base_mode_kind = "mix"

    hot_max_mode_active = (
        base_mode_kind == "hot"
        and cfg["hot_max_enabled"]
        and cfg["hot_max_main_count"] == 5
        and cfg["hot_max_euro_count"] == 2
    )

    def gen_one_record() -> Dict:
        if base_mode_kind == "premium":
            premium_result_local = build_premium_ranking(
                main_draws=main_draws,
                euro_draws=euro_draws,
                hot_main=hot_main,
                cold_main=cold_main,
                hot_euro=hot_euro,
                cold_euro=cold_euro,
                mix_main_hot_count=cfg["mix_main_hot_count"],
                mix_euro_hot_count=cfg["mix_euro_hot_count"],
                candidate_count=cfg["premium_candidate_count"],
                top_n=max(3, min(cfg["premium_top_n"], 10))
            )
            best_row = premium_result_local["rows"][0]
            return {
                "Typ": "premium",
                "Main": [int(x) for x in best_row["Main 5/50"].split()],
                "Euro": [int(x) for x in best_row["Euro 2/12"].split()]
            }

        if hot_max_mode_active:
            hot_max_main_set, hot_max_main_table = build_hot_max_set(main_percent_df, MAIN_PICK_COUNT)
            hot_max_euro_set, hot_max_euro_table = build_hot_max_set(euro_percent_df, EURO_PICK_COUNT)
            return {
                "Typ": "hot_max",
                "Main": hot_max_main_set,
                "Euro": hot_max_euro_set,
                "HotMaxMainTable": hot_max_main_table,
                "HotMaxEuroTable": hot_max_euro_table
            }

        if base_mode_kind == "hybrid":
            chosen = random.choices(["hot", "cold", "mix"], weights=[HYBRID_HOT_P, HYBRID_COLD_P, HYBRID_MIX_P], k=1)[0]
            return {
                "Typ": chosen,
                "Main": gen_side_ticket(chosen, hot_main, cold_main, MAIN_PICK_COUNT, cfg["mix_main_hot_count"], MAIN_MIN, MAIN_MAX),
                "Euro": gen_side_ticket(chosen, hot_euro, cold_euro, EURO_PICK_COUNT, cfg["mix_euro_hot_count"], EURO_MIN, EURO_MAX)
            }
        if base_mode_kind == "hot":
            return {
                "Typ": "hot",
                "Main": gen_side_ticket("hot", hot_main, cold_main, MAIN_PICK_COUNT, cfg["mix_main_hot_count"], MAIN_MIN, MAIN_MAX),
                "Euro": gen_side_ticket("hot", hot_euro, cold_euro, EURO_PICK_COUNT, cfg["mix_euro_hot_count"], EURO_MIN, EURO_MAX)
            }
        if base_mode_kind == "cold":
            return {
                "Typ": "cold",
                "Main": gen_side_ticket("cold", hot_main, cold_main, MAIN_PICK_COUNT, cfg["mix_main_hot_count"], MAIN_MIN, MAIN_MAX),
                "Euro": gen_side_ticket("cold", hot_euro, cold_euro, EURO_PICK_COUNT, cfg["mix_euro_hot_count"], EURO_MIN, EURO_MAX)
            }

        return {
            "Typ": "mix",
            "Main": gen_side_ticket("mix", hot_main, cold_main, MAIN_PICK_COUNT, cfg["mix_main_hot_count"], MAIN_MIN, MAIN_MAX),
            "Euro": gen_side_ticket("mix", hot_euro, cold_euro, EURO_PICK_COUNT, cfg["mix_euro_hot_count"], EURO_MIN, EURO_MAX)
        }

    if generate:
        progress = st.progress(0)
        status = st.empty()

        with st.spinner("Generuję kupony Eurojackpot..."):
            if base_mode_kind == "premium":
                premium_result_local = build_premium_ranking(
                    main_draws=main_draws,
                    euro_draws=euro_draws,
                    hot_main=hot_main,
                    cold_main=cold_main,
                    hot_euro=hot_euro,
                    cold_euro=cold_euro,
                    mix_main_hot_count=cfg["mix_main_hot_count"],
                    mix_euro_hot_count=cfg["mix_euro_hot_count"],
                    candidate_count=cfg["premium_candidate_count"],
                    top_n=cfg["premium_top_n"]
                )
                st.session_state["premium_result"] = premium_result_local
                premium_rows = premium_result_local["rows"]

                recs = []
                total = min(int(cfg["n_tickets"]), len(premium_rows))
                for i in range(total):
                    recs.append({
                        "Typ": "premium",
                        "Main": [int(x) for x in premium_rows[i]["Main 5/50"].split()],
                        "Euro": [int(x) for x in premium_rows[i]["Euro 2/12"].split()],
                    })
                    progress.progress(int((i + 1) / total * 100))
                    status.write(f"Postęp: {i+1}/{total}")

            elif hot_max_mode_active:
                hot_max_main_set, hot_max_main_table = build_hot_max_set(main_percent_df, MAIN_PICK_COUNT)
                hot_max_euro_set, hot_max_euro_table = build_hot_max_set(euro_percent_df, EURO_PICK_COUNT)

                recs = []
                total = int(cfg["n_tickets"])
                for i in range(total):
                    recs.append({
                        "Typ": "hot_max",
                        "Main": hot_max_main_set,
                        "Euro": hot_max_euro_set,
                        "HotMaxMainTable": hot_max_main_table,
                        "HotMaxEuroTable": hot_max_euro_table
                    })
                    if (i + 1) % 10 == 0 or (i + 1) == total:
                        progress.progress(int((i + 1) / total * 100))
                        status.write(f"Postęp: {i+1}/{total}")

                st.session_state["hot_max_set"] = {
                    "main_set": hot_max_main_set,
                    "euro_set": hot_max_euro_set,
                    "main_table": hot_max_main_table,
                    "euro_table": hot_max_euro_table,
                    "window": history_window_used
                }

            else:
                if not cfg["smart_enabled"]:
                    recs = []
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
        st.session_state["last_records"] = recs

    if daily:
        main_daily = pick_daily_set_from_hot(
            hot=hot_main,
            pick_count=MAIN_PICK_COUNT,
            nmin=MAIN_MIN,
            nmax=MAIN_MAX,
            prefer_parity=parity_bias_from_last_n(main_draws, 10),
            prefer_level=high_low_bias_from_last_two(main_draws, threshold=25),
            threshold=25,
            target_spread=avg_spread_last_n(main_draws, 10),
            max_attempts=650
        )
        euro_daily = pick_daily_set_from_hot(
            hot=hot_euro,
            pick_count=EURO_PICK_COUNT,
            nmin=EURO_MIN,
            nmax=EURO_MAX,
            prefer_parity=parity_bias_from_last_n(euro_draws, 10),
            prefer_level=high_low_bias_from_last_two(euro_draws, threshold=6),
            threshold=6,
            target_spread=avg_spread_last_n(euro_draws, 10),
            max_attempts=300
        )

        st.session_state["last_daily"] = {
            "main": main_daily,
            "euro": euro_daily
        }

    # =========================================================
    # OUTPUT SECTIONS
    # =========================================================
    if st.session_state["show_results"]:
        st.markdown("### 📋 Ostatnie wyniki Eurojackpot")
        count_choice = st.selectbox("Ile ostatnich wyników pokazać?", [10, 50, 100], index=0)

        slice_records = result_records_all[:int(count_choice)]
        df_results = pd.DataFrame({
            "Numer losowania": [f"{r['draw_no']:04d}" if r["draw_no"] is not None else "—" for r in slice_records],
            "Main 5/50": [" ".join(f"{x:02d}" for x in r["main_nums"]) for r in slice_records],
            "Euro 2/12": [" ".join(f"{x:02d}" for x in r["euro_nums"]) for r in slice_records],
        })
        st.dataframe(df_results, use_container_width=True, hide_index=True)

        results_name = sanitize_txt_filename(st.text_input("Nazwa pliku wyników .txt", value="euro_wyniki.txt"))
        st.download_button(
            "⬇️ Pobierz wyniki jako TXT",
            data=make_txt_for_results(slice_records),
            file_name=results_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("hot_set") is not None:
        hs = st.session_state["hot_set"]
        main_str = " ".join(f"{x:02d}" for x in hs["main"])
        euro_str = " ".join(f"{x:02d}" for x in hs["euro"])
        st.markdown("### 🔥 HOT SET")
        st.markdown(f'<div class="v-row"><b>Main 5/50</b> — {main_str}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="v-row"><b>Euro 2/12</b> — {euro_str}</div>', unsafe_allow_html=True)

        hot_name = sanitize_txt_filename(st.text_input("Nazwa pliku HOT .txt", value="euro_hot_set.txt"))
        st.download_button(
            "⬇️ Pobierz HOT SET jako TXT",
            data=make_txt_for_hot_set(hs["main"], hs["euro"], history_window_used),
            file_name=hot_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("difference_set") is not None:
        ds = st.session_state["difference_set"]
        main_str = " ".join(f"{x:02d}" for x in ds["main"]["set"])
        euro_str = " ".join(f"{x:02d}" for x in ds["euro"]["set"])
        st.markdown("### 📐 Zestaw różnic")
        st.markdown(f'<div class="v-row"><b>Main 5/50</b> — {main_str}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="v-row"><b>Euro 2/12</b> — {euro_str}</div>', unsafe_allow_html=True)

        st.markdown("#### Szczegóły MAIN")
        st.dataframe(pd.DataFrame(ds["main"]["details"]), use_container_width=True, hide_index=True)
        st.markdown("#### Szczegóły EURO")
        st.dataframe(pd.DataFrame(ds["euro"]["details"]), use_container_width=True, hide_index=True)

        diff_name = sanitize_txt_filename(st.text_input("Nazwa pliku różnic .txt", value="euro_roznice.txt"))
        st.download_button(
            "⬇️ Pobierz zestaw różnic jako TXT",
            data=make_txt_for_difference_set(ds["main"], ds["euro"], cfg["difference_window"]),
            file_name=diff_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("hot_max_set") is not None:
        hm = st.session_state["hot_max_set"]
        main_str = " ".join(f"{x:02d}" for x in hm["main_set"])
        euro_str = " ".join(f"{x:02d}" for x in hm["euro_set"])
        st.markdown("### 🔥 HOT MAX")
        st.markdown(f'<div class="v-row"><b>Main 5/50</b> — {main_str}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="v-row"><b>Euro 2/12</b> — {euro_str}</div>', unsafe_allow_html=True)

        st.markdown("#### TOP MAIN")
        main_table_display = hm["main_table"].copy()
        main_table_display["Procent_losowan"] = main_table_display["Procent_losowan"].map(lambda x: f"{x:.2f}%")
        st.dataframe(main_table_display, use_container_width=True, hide_index=True)

        st.markdown("#### TOP EURO")
        euro_table_display = hm["euro_table"].copy()
        euro_table_display["Procent_losowan"] = euro_table_display["Procent_losowan"].map(lambda x: f"{x:.2f}%")
        st.dataframe(euro_table_display, use_container_width=True, hide_index=True)

    if st.session_state.get("turbo_score_result") is not None:
        turbo = st.session_state["turbo_score_result"]
        turbo_df = pd.DataFrame(turbo["rows"])
        st.markdown("### ⭐ Turbo Score")
        st.markdown(
            f'<div class="v-row"><b>Turbo Score</b> — oceniono {turbo["candidate_count_used"]} kandydatów i wybrano TOP {len(turbo["rows"])}</div>',
            unsafe_allow_html=True
        )
        st.dataframe(turbo_df, use_container_width=True, hide_index=True)

        turbo_name = sanitize_txt_filename(st.text_input("Nazwa pliku Turbo Score .txt", value="euro_turbo_score.txt"))
        st.download_button(
            "⬇️ Pobierz ranking Turbo Score jako TXT",
            data=make_txt_for_turbo_score(turbo["rows"], turbo["candidate_count_used"]),
            file_name=turbo_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("premium_result") is not None:
        premium = st.session_state["premium_result"]
        premium_df = pd.DataFrame(premium["rows"])
        st.markdown("### 👑 Premium")
        st.markdown(
            f'<div class="v-row-premium"><b>Premium Mode</b> — oceniono {premium["candidate_count_used"]} kandydatów i wybrano TOP {len(premium["rows"])}</div>',
            unsafe_allow_html=True
        )
        st.dataframe(premium_df, use_container_width=True, hide_index=True)

        main_hotmax_str = " ".join(f"{x:02d}" for x in premium["hot_max_main_set"])
        euro_hotmax_str = " ".join(f"{x:02d}" for x in premium["hot_max_euro_set"])
        main_diff_str = " ".join(f"{x:02d}" for x in premium["diff_main"]["set"])
        euro_diff_str = " ".join(f"{x:02d}" for x in premium["diff_euro"]["set"])

        st.markdown(
            f"""
<div class="v-row-premium">
<b>Źródła premium:</b><br>
HOT MAX Main: {main_hotmax_str}<br>
HOT MAX Euro: {euro_hotmax_str}<br>
Różnice Main: {main_diff_str}<br>
Różnice Euro: {euro_diff_str}
</div>
            """,
            unsafe_allow_html=True
        )

        premium_name = sanitize_txt_filename(st.text_input("Nazwa pliku Premium .txt", value="euro_premium.txt"))
        st.download_button(
            "⬇️ Pobierz ranking Premium jako TXT",
            data=make_txt_for_premium(premium["rows"], premium["candidate_count_used"]),
            file_name=premium_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("ai_sim_result") is not None:
        sim = st.session_state["ai_sim_result"]
        main_str = " ".join(f"{x:02d}" for x in sim["sim_main_set"])
        euro_str = " ".join(f"{x:02d}" for x in sim["sim_euro_set"])

        st.markdown("### 🤖 AI symulacja")
        st.markdown(
            f'<div class="v-row"><b>Symulacje:</b> {sim["n_sims"]} | <b>Sugerowany Main:</b> {main_str} | <b>Sugerowany Euro:</b> {euro_str}</div>',
            unsafe_allow_html=True
        )

        st.markdown("#### Wyniki symulacji — Main")
        st.dataframe(sim["main_df"].head(15), use_container_width=True, hide_index=True)

        st.markdown("#### Wyniki symulacji — Euro")
        st.dataframe(sim["euro_df"].head(12), use_container_width=True, hide_index=True)

        if not sim["top_main_pairs"].empty:
            st.markdown("#### Najczęstsze pary MAIN w symulacji")
            st.dataframe(sim["top_main_pairs"], use_container_width=True, hide_index=True)

        if not sim["top_euro_pairs"].empty:
            st.markdown("#### Najczęstsze pary EURO w symulacji")
            st.dataframe(sim["top_euro_pairs"], use_container_width=True, hide_index=True)

        sim_name = sanitize_txt_filename(st.text_input("Nazwa pliku AI symulacji .txt", value="euro_ai_symulacja.txt"))
        st.download_button(
            "⬇️ Pobierz wynik AI symulacji jako TXT",
            data=make_txt_for_simulation(sim),
            file_name=sim_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("cycle_result") is not None:
        cyc = st.session_state["cycle_result"]
        main_str = " ".join(f"{x:02d}" for x in cyc["main_set"])
        euro_str = " ".join(f"{x:02d}" for x in cyc["euro_set"])

        st.markdown("### 🔄 Cykle liczb")
        st.markdown(
            f'<div class="v-row"><b>Sugerowany Main:</b> {main_str} | <b>Sugerowany Euro:</b> {euro_str}</div>',
            unsafe_allow_html=True
        )

        st.markdown("#### TOP cykle — Main")
        st.dataframe(cyc["main_df"].head(15), use_container_width=True, hide_index=True)

        st.markdown("#### TOP cykle — Euro")
        st.dataframe(cyc["euro_df"].head(12), use_container_width=True, hide_index=True)

        cycle_name = sanitize_txt_filename(st.text_input("Nazwa pliku cykli .txt", value="euro_cykle.txt"))
        st.download_button(
            "⬇️ Pobierz analizę cykli jako TXT",
            data=make_txt_for_cycles(cyc["main_df"], cyc["euro_df"], cyc["main_set"], cyc["euro_set"]),
            file_name=cycle_name,
            mime="text/plain",
            use_container_width=True
        )

    if st.session_state.get("heatmap_main") is not None and st.session_state.get("heatmap_euro") is not None:
        st.markdown("### 🟦 Heatmapy")
        st.markdown("#### Main 1–50")
        st.dataframe(st.session_state["heatmap_main"], use_container_width=True, hide_index=True)
        st.markdown("#### Euro 1–12")
        st.dataframe(st.session_state["heatmap_euro"], use_container_width=True, hide_index=True)

    if st.session_state.get("last_daily") is not None:
        d = st.session_state["last_daily"]
        main_str = " ".join(f"{x:02d}" for x in d["main"])
        euro_str = " ".join(f"{x:02d}" for x in d["euro"])

        st.markdown("### 🌿 Cyfry dnia")
        st.markdown(f'<div class="v-row"><b>Main 5/50</b> — {main_str}</div>', unsafe_allow_html=True)
        st.markdown(f'<div class="v-row"><b>Euro 2/12</b> — {euro_str}</div>', unsafe_allow_html=True)

    records = st.session_state.get("last_records", [])
    if records:
        st.markdown("### 🎯 Wygenerowane kupony")
        df_out = pd.DataFrame({
            "Typ": [r["Typ"] for r in records],
            "Main 5/50": [" ".join(f"{x:02d}" for x in r["Main"]) for r in records],
            "Euro 2/12": [" ".join(f"{x:02d}" for x in r["Euro"]) for r in records],
        })

        preview_n = min(cfg["preview_limit"], len(records))
        for i in range(preview_n):
            row_class = "v-row-premium" if df_out.iloc[i]["Typ"] == "premium" else "v-row"
            st.markdown(
                f'<div class="{row_class}"><b>Kupon #{i+1:03d}</b> '
                f'<span class="v-muted">[{df_out.iloc[i]["Typ"]}]</span> — '
                f'Main: {df_out.iloc[i]["Main 5/50"]} | Euro: {df_out.iloc[i]["Euro 2/12"]}</div>',
                unsafe_allow_html=True
            )

        st.dataframe(df_out, use_container_width=True, hide_index=True)

        tickets_name = sanitize_txt_filename(st.text_input("Nazwa pliku kuponów .txt", value="euro_kupony.txt"))
        st.download_button(
            "⬇️ Pobierz kupony jako TXT",
            data=make_txt_for_tickets(records),
            file_name=tickets_name,
            mime="text/plain",
            use_container_width=True
        )

    with st.expander("✅ Kontrola parsera (pierwsze 5 rekordów)"):
        for i, r in enumerate(result_records_all[:5], start=1):
            st.write(
                f"{i}. Losowanie: {r['draw_no']:04d} | "
                f"Main: {' '.join(f'{x:02d}' for x in r['main_nums'])} | "
                f"Euro: {' '.join(f'{x:02d}' for x in r['euro_nums'])}"
            )


if __name__ == "__main__":
    main()
