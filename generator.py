import io
import os
import re
import zipfile
import random
from collections import Counter
from pathlib import Path
from typing import List, Dict, Tuple, Optional

import pandas as pd
import streamlit as st
from pypdf import PdfReader
from pypdf.errors import PdfReadError


# =========================================================
# APP CONFIG
# =========================================================
APP_TITLE = "💶 Eurojackpot — Smart Tip Generator"
PDF_MAIN = "wyniki1.pdf"   # 5/50
PDF_EURO = "wyniki2.pdf"   # 2/12

MAIN_MIN, MAIN_MAX, MAIN_PICK = 1, 50, 5
EURO_MIN, EURO_MAX, EURO_PICK = 1, 12, 2


# =========================================================
# UI STYLE (dark + green accents)
# =========================================================
DARK_GREEN_CSS = """
<style>
:root{
  --bg0:#050507;
  --bg1:#0b0b10;
  --card: rgba(16,16,24,0.92);
  --card2: rgba(12,12,18,0.92);
  --txt:#f4f4f6;
  --mut:#b9b9c8;
  --green:#00ff99;
  --green2:#23ffb0;
  --border: rgba(0,255,153,0.22);
  --shadow: 0 14px 44px rgba(0,0,0,.65);
}

.stApp{
  background:
    radial-gradient(900px 600px at 10% 10%, rgba(0,255,153,0.12), transparent 55%),
    radial-gradient(900px 600px at 90% 15%, rgba(0,255,153,0.06), transparent 50%),
    linear-gradient(180deg, var(--bg0), var(--bg1));
  color: var(--txt) !important;
}

.block-container{ padding-top: 2.0rem; padding-bottom: 2.5rem; max-width: 1100px; }

h1,h2,h3,h4{ letter-spacing: .4px; }
h1{
  font-family: ui-serif, Georgia, "Times New Roman", serif;
  text-transform: uppercase;
}

.gg-card{
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  border-radius: 18px;
  padding: 16px 16px 12px 16px;
}

.gg-pill{
  display:inline-block;
  padding: 6px 10px;
  margin: 3px 4px 0 0;
  border-radius: 999px;
  border: 1px solid rgba(0,255,153,0.28);
  background: rgba(0,255,153,0.08);
  font-weight: 900;
  color: #dfffee;
}

.gg-muted{ opacity: .80; font-size: .92rem; }

section[data-testid="stSidebar"]{
  background: linear-gradient(180deg, rgba(0,255,153,0.10) 0%, rgba(0,0,0,0.20) 100%);
  border-right: 1px solid rgba(0,255,153,0.12);
}

div[data-baseweb="select"] > div,
div[data-baseweb="input"] > div,
div[data-baseweb="textarea"] > div{
  border-radius: 14px !important;
}

div.stButton > button[kind="primary"]{
  background: linear-gradient(90deg, #00ff99 0%, #23ffb0 100%) !important;
  color: #000000 !important;
  border: 0 !important;
  border-radius: 14px !important;
  padding: 0.80rem 1.10rem !important;
  font-weight: 1000 !important;
  letter-spacing: .6px !important;
  box-shadow: 0 12px 26px rgba(0,255,153,0.18) !important;
}
div.stButton > button[kind="primary"]:hover{
  filter: brightness(1.04);
  transform: translateY(-1px);
}

div.stButton > button{
  border-radius: 14px !important;
}

.gg-row{
  background: rgba(255,255,255,0.03);
  border: 1px solid rgba(0,255,153,0.18);
  border-radius: 14px;
  padding: 10px 12px;
  margin: 8px 0;
}

[data-testid="stDataFrame"]{
  border-radius: 16px !important;
  overflow: hidden !important;
  border: 1px solid rgba(0,255,153,0.22) !important;
}

@media (max-width: 640px){
  .block-container{ padding-left: 1rem; padding-right: 1rem; }
  div.stButton > button[kind="primary"]{ width: 100% !important; }
}
</style>
"""


# =========================================================
# PDF PARSING (robust)
# =========================================================
def _build_line_regex(k: int) -> re.Pattern:
    parts = [r"(\d{1,2})" for _ in range(k)]
    pattern = r"(?<!\d)" + r"\s+".join(parts) + r"(?!\d)"
    return re.compile(pattern)


def extract_draws_from_pdf(pdf_path: Path, k: int, nmin: int, nmax: int) -> List[List[int]]:
    pdf_bytes = pdf_path.read_bytes()

    if not pdf_bytes.startswith(b"%PDF"):
        head = pdf_bytes[:240].decode("utf-8", errors="replace")
        raise ValueError(
            f"Plik `{pdf_path.name}` NIE wygląda jak prawdziwy PDF (brak nagłówka %PDF).\n"
            "Najczęściej to wskaźnik Git LFS albo uszkodzony upload.\n\n"
            f"Pierwsze znaki pliku:\n{head}"
        )

    try:
        reader = PdfReader(io.BytesIO(pdf_bytes), strict=False)
    except PdfReadError as e:
        raise PdfReadError(f"PdfReadError: {e}\nPDF może być uszkodzony lub niekompletny.")

    line_re = _build_line_regex(k=k)
    draws: List[List[int]] = []

    for page in reader.pages:
        try:
            text = page.extract_text() or ""
        except Exception:
            text = ""

        for m in line_re.finditer(text):
            nums = [int(m.group(i)) for i in range(1, k + 1)]
            if all(nmin <= n <= nmax for n in nums) and len(set(nums)) == k:
                draws.append(sorted(nums))

    return draws


# =========================================================
# STATS + GROUPS
# =========================================================
def compute_freq(draws: List[List[int]], nmin: int, nmax: int) -> pd.DataFrame:
    flat = [n for d in draws for n in d]
    c = Counter(flat)
    rows = [{"Liczba": n, "Wystąpienia": c.get(n, 0)} for n in range(nmin, nmax + 1)]
    df = pd.DataFrame(rows).sort_values(["Wystąpienia", "Liczba"], ascending=[False, True]).reset_index(drop=True)
    return df


def build_groups(freq_df: pd.DataFrame, nmin: int, nmax: int, hot_size: int, cold_size: int) -> Tuple[List[int], List[int], List[int]]:
    hot = freq_df.head(hot_size)["Liczba"].tolist()
    cold = freq_df.tail(cold_size)["Liczba"].tolist()
    neutral = [n for n in range(nmin, nmax + 1) if n not in hot and n not in cold]
    return hot, cold, neutral


# =========================================================
# GENERATION
# =========================================================
def pick_unique(pool: List[int], k: int) -> List[int]:
    pool = list(dict.fromkeys(pool))
    if len(pool) < k:
        raise ValueError("Za mało liczb w puli, aby wylosować unikalny zestaw.")
    return sorted(random.sample(pool, k))


def gen_from_groups(mode: str, hot: List[int], cold: List[int], pick_count: int, mix_hot_count: int) -> List[int]:
    if mode == "hot":
        return pick_unique(hot, pick_count)
    if mode == "cold":
        return pick_unique(cold, pick_count)
    if mode == "mix":
        if mix_hot_count <= 0:
            return pick_unique(cold, pick_count)
        if mix_hot_count >= pick_count:
            return pick_unique(hot, pick_count)
        h = pick_unique(hot, mix_hot_count)
        c = pick_unique([x for x in cold if x not in h], pick_count - mix_hot_count)
        return sorted(h + c)
    raise ValueError("Nieznany tryb losowania.")


def draw_weighted_mode(w_hot: float = 0.70, w_cold: float = 0.20, w_mix: float = 0.10) -> str:
    return random.choices(["hot", "cold", "mix"], weights=[w_hot, w_cold, w_mix], k=1)[0]


# =========================================================
# SMART MODE (filters applied to MAIN 5/50 numbers)
# =========================================================
def count_adjacent_pairs(nums_sorted: List[int]) -> int:
    pairs = 0
    for a, b in zip(nums_sorted, nums_sorted[1:]):
        if b == a + 1:
            pairs += 1
    return pairs


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
    main_nums: List[int],
    block_run_2: bool,
    block_run_3: bool,
    max_adjacent_pairs: Optional[int],
    even_odd_choice: str
) -> bool:
    nums = sorted(main_nums)

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


def generate_tickets_with_smart(
    make_one_ticket_func,
    n_tickets: int,
    max_attempts_per_ticket: int,
    smart_kwargs: Dict
) -> List[Dict]:
    out: List[Dict] = []
    attempts = 0
    while len(out) < n_tickets:
        attempts += 1
        if attempts > n_tickets * max_attempts_per_ticket:
            break

        rec = make_one_ticket_func()
        if smart_ok_main(rec["Main"], **smart_kwargs):
            out.append(rec)

    return out


# =========================================================
# NEW: "Twoje cyfry dnia" logic
# =========================================================
def flatten_last_n(draws: List[List[int]], n: int) -> List[int]:
    return [x for d in draws[:n] for x in d]


def parity_bias_from_last_n(draws: List[List[int]], n: int) -> str:
    nums = flatten_last_n(draws, n)
    ev = sum(1 for x in nums if x % 2 == 0)
    od = len(nums) - ev
    if ev > od:
        return "ODD"   # dziś preferuj nieparzyste
    if od > ev:
        return "EVEN"  # dziś preferuj parzyste
    return "ANY"


def high_low_bias_from_last_two(draws: List[List[int]], threshold: int) -> str:
    """
    If last two draws are mostly low -> prefer HIGH today.
    If last two draws are mostly high -> prefer LOW today.
    Else ANY.
    """
    if len(draws) < 2:
        return "ANY"

    last2 = draws[:2]
    all_nums = [x for d in last2 for x in d]
    low = sum(1 for x in all_nums if x <= threshold)
    high = len(all_nums) - low

    # If clear majority low -> switch to high; vice versa
    if low >= high + 2:
        return "HIGH"
    if high >= low + 2:
        return "LOW"
    return "ANY"


def avg_spread_last_n(draws: List[List[int]], n: int) -> float:
    spreads = []
    for d in draws[:n]:
        if not d:
            continue
        spreads.append(max(d) - min(d))
    return sum(spreads) / len(spreads) if spreads else 0.0


def pick_daily_set_from_hot(
    hot: List[int],
    pick_count: int,
    nmin: int,
    nmax: int,
    prefer_parity: str,     # "EVEN" | "ODD" | "ANY"
    prefer_level: str,      # "LOW" | "HIGH" | "ANY"
    threshold: int,
    target_spread: Optional[float] = None,
    max_attempts: int = 400
) -> List[int]:
    """
    Picks numbers primarily from HOT, but filters by:
    - parity preference (if possible)
    - high/low preference (if possible)
    - tries to match a 'spread' feel (difference max-min) if target_spread given
    """
    hot_unique = sorted(set([x for x in hot if nmin <= x <= nmax]))
    if len(hot_unique) < pick_count:
        # fallback: extend pool with whole range
        hot_unique = hot_unique + [x for x in range(nmin, nmax + 1) if x not in hot_unique]

    # Build filtered pools
    pool = hot_unique[:]

    if prefer_level != "ANY":
        if prefer_level == "LOW":
            filtered = [x for x in pool if x <= threshold]
        else:
            filtered = [x for x in pool if x > threshold]
        if len(filtered) >= pick_count:
            pool = filtered

    # Parity preference should not kill the pool entirely; we apply softly
    if prefer_parity != "ANY":
        if prefer_parity == "EVEN":
            filtered = [x for x in pool if x % 2 == 0]
        else:
            filtered = [x for x in pool if x % 2 == 1]
        # if we can still pick enough, use it; else keep previous pool
        if len(filtered) >= pick_count:
            pool = filtered

    best = None
    best_score = -10**9

    for _ in range(max_attempts):
        candidate = sorted(random.sample(pool, pick_count))

        # Score: spread closeness + parity match + level match
        spread = (candidate[-1] - candidate[0]) if candidate else 0
        score = 0.0

        if target_spread is not None:
            score -= abs(spread - target_spread) * 0.25

        if prefer_parity != "ANY":
            ev, od = even_odd_split(candidate)
            if prefer_parity == "EVEN":
                score += ev * 0.35
            else:
                score += od * 0.35

        if prefer_level != "ANY":
            low = sum(1 for x in candidate if x <= threshold)
            high = pick_count - low
            if prefer_level == "LOW":
                score += low * 0.25
            else:
                score += high * 0.25

        if score > best_score:
            best_score = score
            best = candidate

        # If it strongly satisfies parity + level, we can accept early
        if prefer_parity != "ANY" and prefer_level != "ANY":
            # Accept if majority aligns
            ev, od = even_odd_split(candidate)
            low = sum(1 for x in candidate if x <= threshold)
            high = pick_count - low
            parity_ok = (ev > od) if prefer_parity == "EVEN" else (od > ev)
            level_ok = (high > low) if prefer_level == "HIGH" else (low > high)
            if parity_ok and level_ok:
                return candidate

    return best if best is not None else sorted(random.sample(range(nmin, nmax + 1), pick_count))


# =========================================================
# APP
# =========================================================
def main():
    st.set_page_config(
        page_title="Eurojackpot Generator",
        page_icon="💶",
        layout="wide",
        initial_sidebar_state="expanded"
    )
    st.markdown(DARK_GREEN_CSS, unsafe_allow_html=True)

    st.title(APP_TITLE)
    st.write("Generator typowań Eurojackpot na bazie historii losowań z dwóch plików PDF:")
    st.caption("• `wyniki1.pdf` → 5/50 (5 liczb 1–50) • `wyniki2.pdf` → 2/12 (2 liczby 1–12)")

    pdf_main_path = Path(os.getcwd()) / PDF_MAIN
    pdf_euro_path = Path(os.getcwd()) / PDF_EURO

    # SIDEBAR
    with st.sidebar:
        st.header("⚙️ Ustawienia")

        mode_ui = st.selectbox(
            "Tryb typowania (dotyczy 5/50 i 2/12 równocześnie)",
            [
                "Hybryda 70/20/10 (hot/cold/mix)",
                "Tylko 🔥 gorące",
                "Tylko ❄️ zimne",
                "Tylko ⚗️ mix (hot+zimne)",
            ],
            index=0
        )

        st.divider()
        n_tickets = st.slider("Liczba kuponów", 1, 500, 20, 1)

        st.divider()
        st.subheader("🔥/❄️ Wielkość grup (5/50)")
        hot_main_size = st.slider("Hot (5/50)", 5, 40, 20, 1)
        cold_main_size = st.slider("Cold (5/50)", 5, 40, 20, 1)

        st.subheader("🔥/❄️ Wielkość grup (2/12)")
        hot_euro_size = st.slider("Hot (2/12)", 2, 10, 6, 1)
        cold_euro_size = st.slider("Cold (2/12)", 2, 10, 6, 1)

        st.divider()
        st.subheader("⚗️ MIX — ustawienia")
        mix_hot_main_count = st.slider("MIX (5/50): ile z gorących?", 1, 4, 3, 1)
        mix_hot_euro_count = st.slider("MIX (2/12): ile z gorących?", 0, 2, 1, 1)

        st.divider()
        st.subheader("🧠 Tryb inteligentny (opcjonalny)")
        smart_enabled = st.checkbox("Włącz tryb inteligentny", value=False)

        if smart_enabled:
            st.caption("Filtry działają na części 5/50 (główne 5 liczb).")

            block_run_2 = st.checkbox("Blokuj układy 1–2 (kolejne liczby)", value=True)
            block_run_3 = st.checkbox("Blokuj układy 1–3 (ciąg 3 kolejnych)", value=True)

            limit_pairs_on = st.checkbox("Włącz limit par (kolejne liczby)", value=True)
            max_adj_pairs = None
            if limit_pairs_on:
                max_adj_pairs = st.slider("Maks. liczba par kolejnych", 0, 4, 2, 1)

            even_odd_choice = st.radio(
                "Parzyste / Nieparzyste (5 liczb)",
                ["Dowolnie", "3/2", "2/3", "4/1", "1/4", "5/0", "0/5"],
                index=1
            )

            max_attempts_per_ticket = st.slider("Limit prób na kupon", 10, 500, 120, 10)
        else:
            block_run_2 = False
            block_run_3 = False
            max_adj_pairs = None
            even_odd_choice = "Dowolnie"
            max_attempts_per_ticket = 120

    # LOAD DATA
    top_left, top_right = st.columns([1.2, 0.8], gap="large")

    with top_left:
        st.markdown('<div class="gg-card">', unsafe_allow_html=True)
        st.subheader("📄 Dane wejściowe (PDF)")
        st.write(f"5/50: `{pdf_main_path}`")
        st.write(f"2/12: `{pdf_euro_path}`")

        if not pdf_main_path.exists():
            st.error(f"❌ Brak `{PDF_MAIN}` w katalogu aplikacji (obok pliku .py).")
            st.stop()
        if not pdf_euro_path.exists():
            st.error(f"❌ Brak `{PDF_EURO}` w katalogu aplikacji (obok pliku .py).")
            st.stop()

        try:
            draws_main = extract_draws_from_pdf(pdf_main_path, k=MAIN_PICK, nmin=MAIN_MIN, nmax=MAIN_MAX)
            draws_euro = extract_draws_from_pdf(pdf_euro_path, k=EURO_PICK, nmin=EURO_MIN, nmax=EURO_MAX)
        except ValueError as e:
            st.error("❌ Problem z PDF (to nie jest prawdziwy PDF albo Git LFS pointer).")
            st.code(str(e))
            st.stop()
        except Exception as e:
            st.error("❌ Błąd czytania PDF (może być uszkodzony / niepełny).")
            st.code(str(e))
            st.stop()

        if len(draws_main) == 0:
            st.error("❌ Nie znaleziono losowań 5/50 (linii z 5 liczbami 1–50) w `wyniki1.pdf`.")
            st.stop()

        if len(draws_euro) == 0:
            st.error("❌ Nie znaleziono losowań 2/12 (linii z 2 liczbami 1–12) w `wyniki2.pdf`.")
            st.stop()

        st.success(f"✅ 5/50 losowań: **{len(draws_main)}** | ✅ 2/12 losowań: **{len(draws_euro)}**")
        st.markdown('<div class="gg-muted">Aplikacja analizuje wszystkie losowania i buduje grupy Hot/Cold dla obu pul.</div>', unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="gg-card">', unsafe_allow_html=True)
        st.subheader("📊 Częstotliwość 5/50 (1–50)")
        freq_main = compute_freq(draws_main, MAIN_MIN, MAIN_MAX)
        st.dataframe(freq_main, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="gg-card">', unsafe_allow_html=True)
        st.subheader("📊 Częstotliwość 2/12 (1–12)")
        freq_euro = compute_freq(draws_euro, EURO_MIN, EURO_MAX)
        st.dataframe(freq_euro, use_container_width=True, hide_index=True)
        st.markdown("</div>", unsafe_allow_html=True)

    # Groups
    hot_main, cold_main, _ = build_groups(freq_main, MAIN_MIN, MAIN_MAX, hot_main_size, cold_main_size)
    hot_euro, cold_euro, _ = build_groups(freq_euro, EURO_MIN, EURO_MAX, hot_euro_size, cold_euro_size)

    with top_right:
        st.markdown('<div class="gg-card">', unsafe_allow_html=True)
        st.subheader("🔥/❄️ Grupy (5/50)")
        st.markdown("**Gorące (Hot)**")
        st.markdown(" ".join([f'<span class="gg-pill">{n:02d}</span>' for n in sorted(hot_main)]), unsafe_allow_html=True)
        st.markdown("**Zimne (Cold)**")
        st.markdown(" ".join([f'<span class="gg-pill">{n:02d}</span>' for n in sorted(cold_main)]), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="gg-card">', unsafe_allow_html=True)
        st.subheader("🔥/❄️ Grupy (2/12)")
        st.markdown("**Gorące (Hot)**")
        st.markdown(" ".join([f'<span class="gg-pill">{n:02d}</span>' for n in sorted(hot_euro)]), unsafe_allow_html=True)
        st.markdown("**Zimne (Cold)**")
        st.markdown(" ".join([f'<span class="gg-pill">{n:02d}</span>' for n in sorted(cold_euro)]), unsafe_allow_html=True)
        st.markdown("</div>", unsafe_allow_html=True)

        st.markdown('<div class="gg-card">', unsafe_allow_html=True)
        st.subheader("🎛️ Wybrany tryb")
        st.write(f"**Tryb:** {mode_ui}")
        st.write(f"**Tryb inteligentny:** {'TAK' if smart_enabled else 'NIE'}")
        st.write(f"**MIX 5/50:** {mix_hot_main_count} hot + {MAIN_PICK - mix_hot_main_count} cold")
        st.write(f"**MIX 2/12:** {mix_hot_euro_count} hot + {EURO_PICK - mix_hot_euro_count} cold")
        st.markdown("</div>", unsafe_allow_html=True)

    st.divider()

    # =========================================================
    # BUTTONS: Generator + "Twoje cyfry dnia"
    # =========================================================
    st.markdown('<div class="gg-card">', unsafe_allow_html=True)
    st.subheader("🎟️ Eurojackpot — generowanie kuponów")

    col_btn1, col_btn2 = st.columns(2, gap="large")
    with col_btn1:
        generate = st.button("🎯 GENERUJ KUPONY EUROJACKPOT", type="primary", use_container_width=True)
    with col_btn2:
        daily = st.button("🌿 TWOJE CYFRY DNIA", type="primary", use_container_width=True)

    # -----------------------------------------
    # Helper: create one ticket based on chosen mode
    # -----------------------------------------
    if mode_ui == "Hybryda 70/20/10 (hot/cold/mix)":
        base_mode_kind = "hybrid"
    elif mode_ui == "Tylko 🔥 gorące":
        base_mode_kind = "hot"
    elif mode_ui == "Tylko ❄️ zimne":
        base_mode_kind = "cold"
    else:
        base_mode_kind = "mix"

    def make_one_ticket() -> Dict:
        if base_mode_kind == "hybrid":
            chosen = draw_weighted_mode(0.70, 0.20, 0.10)
        else:
            chosen = base_mode_kind

        main_nums = gen_from_groups(chosen, hot_main, cold_main, pick_count=MAIN_PICK, mix_hot_count=mix_hot_main_count)
        euro_nums = gen_from_groups(chosen, hot_euro, cold_euro, pick_count=EURO_PICK, mix_hot_count=mix_hot_euro_count)

        return {"Typ": chosen, "Main": main_nums, "Euro": euro_nums}

    # -----------------------------------------
    # ACTION 1: Standard generator
    # -----------------------------------------
    if generate:
        if not smart_enabled:
            records = [make_one_ticket() for _ in range(int(n_tickets))]
        else:
            smart_kwargs = {
                "block_run_2": block_run_2,
                "block_run_3": block_run_3,
                "max_adjacent_pairs": max_adj_pairs,
                "even_odd_choice": even_odd_choice
            }
            records = generate_tickets_with_smart(
                make_one_ticket_func=make_one_ticket,
                n_tickets=int(n_tickets),
                max_attempts_per_ticket=int(max_attempts_per_ticket),
                smart_kwargs=smart_kwargs
            )

            if len(records) < int(n_tickets):
                st.warning(
                    f"⚠️ Filtry są dość ostre: wygenerowano **{len(records)}** / {int(n_tickets)} kuponów. "
                    "Poluzuj filtry albo zwiększ limit prób."
                )

        st.markdown("### Wyniki")
        for i, r in enumerate(records, start=1):
            main_nums = r["Main"]
            euro_nums = r["Euro"]
            ev, od = even_odd_split(main_nums)
            pairs = count_adjacent_pairs(sorted(main_nums))
            main_str = " ".join(f"{x:02d}" for x in main_nums)
            euro_str = " ".join(f"{x:02d}" for x in euro_nums)

            st.markdown(
                f'<div class="gg-row"><b>Kupon #{i:03d}</b> '
                f'<span class="gg-muted">[{r["Typ"]}]</span> — '
                f'<b>5/50:</b> {main_str}  |  <b>2/12:</b> {euro_str} '
                f'<span class="gg-muted"> | parzyste/nieparzyste(5/50): {ev}/{od} | pary: {pairs}</span></div>',
                unsafe_allow_html=True
            )

        # EXPORTS
        df_out = pd.DataFrame({
            "Typ": [r["Typ"] for r in records],
            "5_50": [" ".join(f"{x:02d}" for x in r["Main"]) for r in records],
            "2_12": [" ".join(f"{x:02d}" for x in r["Euro"]) for r in records],
        })

        csv_bytes = df_out.to_csv(index=False).encode("utf-8")
        txt_lines = [
            f"{i+1:03d}. [{records[i]['Typ']}] 5/50: " +
            " ".join(f"{x:02d}" for x in records[i]["Main"]) +
            " | 2/12: " +
            " ".join(f"{x:02d}" for x in records[i]["Euro"])
            for i in range(len(records))
        ]
        txt_bytes = ("\n".join(txt_lines)).encode("utf-8")

        report = {
            "pdf_main": PDF_MAIN,
            "pdf_euro": PDF_EURO,
            "draws_main_found": len(draws_main),
            "draws_euro_found": len(draws_euro),
            "groups": {
                "main_hot_size": int(hot_main_size),
                "main_cold_size": int(cold_main_size),
                "euro_hot_size": int(hot_euro_size),
                "euro_cold_size": int(cold_euro_size),
                "main_hot": sorted(hot_main),
                "main_cold": sorted(cold_main),
                "euro_hot": sorted(hot_euro),
                "euro_cold": sorted(cold_euro),
            },
            "mix": {
                "mix_hot_main_count": int(mix_hot_main_count),
                "mix_hot_euro_count": int(mix_hot_euro_count),
            },
            "mode": mode_ui,
            "smart_enabled": bool(smart_enabled),
            "smart_filters": {
                "block_run_2": bool(block_run_2),
                "block_run_3": bool(block_run_3),
                "max_adjacent_pairs": max_adj_pairs,
                "even_odd_choice": even_odd_choice
            } if smart_enabled else {},
            "smart_max_attempts_per_ticket": int(max_attempts_per_ticket) if smart_enabled else None,
        }
        report_bytes = (pd.Series(report).to_json(indent=2, force_ascii=False)).encode("utf-8")

        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as z:
            z.writestr("eurojackpot_kupony.csv", csv_bytes)
            z.writestr("eurojackpot_kupony.txt", txt_bytes)
            z.writestr("raport.json", report_bytes)

        st.download_button(
            "⬇️ Pobierz paczkę (ZIP: kupony + raport)",
            data=zip_buffer.getvalue(),
            file_name="eurojackpot_kupony.zip",
            mime="application/zip",
            use_container_width=True,
        )

        st.caption("Uwaga: to generator analityczno-rozrywkowy — historia losowań nie gwarantuje wygranej.")

    # -----------------------------------------
    # ACTION 2: "Twoje cyfry dnia"
    # -----------------------------------------
    if daily:
        # MAIN (5/50) analysis from last 10
        main_parity_pref = parity_bias_from_last_n(draws_main, 10)
        main_level_pref = high_low_bias_from_last_two(draws_main, threshold=25)
        main_target_spread = avg_spread_last_n(draws_main, 10)

        # EURO (2/12) analysis from last 10
        euro_parity_pref = parity_bias_from_last_n(draws_euro, 10)
        euro_level_pref = high_low_bias_from_last_two(draws_euro, threshold=6)
        euro_target_spread = avg_spread_last_n(draws_euro, 10)

        # Translate parity preference for picker
        def pref_to_text(p: str) -> str:
            if p == "EVEN":
                return "parzyste"
            if p == "ODD":
                return "nieparzyste"
            return "dowolnie"

        def level_to_text(p: str) -> str:
            if p == "LOW":
                return "niższe"
            if p == "HIGH":
                return "wyższe"
            return "dowolnie"

        # Generate "daily" picks from HOT pools with preferences
        # MAIN: pick 5 from hot_main
        daily_main = pick_daily_set_from_hot(
            hot=hot_main,
            pick_count=MAIN_PICK,
            nmin=MAIN_MIN,
            nmax=MAIN_MAX,
            prefer_parity=main_parity_pref,
            prefer_level=main_level_pref,
            threshold=25,
            target_spread=main_target_spread,
            max_attempts=500
        )

        # EURO: pick 2 from hot_euro
        daily_euro = pick_daily_set_from_hot(
            hot=hot_euro,
            pick_count=EURO_PICK,
            nmin=EURO_MIN,
            nmax=EURO_MAX,
            prefer_parity=euro_parity_pref,
            prefer_level=euro_level_pref,
            threshold=6,
            target_spread=euro_target_spread,
            max_attempts=300
        )

        main_str = " ".join(f"{x:02d}" for x in daily_main)
        euro_str = " ".join(f"{x:02d}" for x in daily_euro)

        ev, od = even_odd_split(daily_main)
        pairs = count_adjacent_pairs(sorted(daily_main))

        st.markdown("### 🌿 Twoje cyfry dnia")
        st.markdown(
            f'<div class="gg-row"><b>Kupon dnia</b> — '
            f'<b>5/50:</b> {main_str}  |  <b>2/12:</b> {euro_str} '
            f'<span class="gg-muted"> | parzyste/nieparzyste(5/50): {ev}/{od} | pary: {pairs}</span></div>',
            unsafe_allow_html=True
        )

        st.markdown("#### Jak aplikacja to ustaliła?")
        st.markdown(
            f"- Ostatnie 10 losowań (5/50): częściej wypadały **{pref_to_text(main_parity_pref)}** → dziś preferencja: **{pref_to_text(main_parity_pref)}** (odwrócona logika jest „wbudowana” w dobór)."
        )
        st.markdown(
            f"- Ostatnie 2 losowania (5/50) były bardziej **{level_to_text(main_level_pref)}** → dziś preferujemy **{level_to_text(main_level_pref)}** z puli gorących."
        )
        st.markdown(
            f"- Różnice (spread) w ostatnich 10 losowaniach (5/50) średnio: **{main_target_spread:.1f}** → kupon dnia próbuje trzymać podobny „rozstrzał”."
        )

        st.markdown(
            f"- Ostatnie 10 losowań (2/12): preferencja parzystości: **{pref_to_text(euro_parity_pref)}**, trend niskie/wysokie: **{level_to_text(euro_level_pref)}**."
        )

    st.markdown("</div>", unsafe_allow_html=True)

    # Diagnostics
    with st.expander("📌 Diagnostyka (TOP/LOW)"):
        st.write("TOP 15 (5/50):")
        st.dataframe(freq_main.head(15), use_container_width=True, hide_index=True)
        st.write("LOW 15 (5/50):")
        st.dataframe(freq_main.tail(15).sort_values(["Wystąpienia", "Liczba"]), use_container_width=True, hide_index=True)

        st.write("TOP 12 (2/12):")
        st.dataframe(freq_euro.head(12), use_container_width=True, hide_index=True)
        st.write("LOW 12 (2/12):")
        st.dataframe(freq_euro.tail(12).sort_values(["Wystąpienia", "Liczba"]), use_container_width=True, hide_index=True)


if __name__ == "__main__":
    main()
