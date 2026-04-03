import io
import math
import random
import re
import statistics
from dataclasses import dataclass
from itertools import combinations
from typing import Dict, List, Tuple, Optional

import fitz  # PyMuPDF
import pandas as pd
import streamlit as st


# =========================================================
# KONFIGURACJA
# =========================================================
APP_TITLE = "🌟 EuroJackpot PRO Generator"
APP_SUBTITLE = "Losowy • Hot • Cold • 50/50 • Złoty Strzał • Ranking • Szlaczek"

MAIN_MIN = 1
MAIN_MAX = 50
MAIN_PICK = 5

EURO_MIN = 1
EURO_MAX = 12
EURO_PICK = 2

DEFAULT_HISTORY_WINDOW = 999
DEFAULT_CANDIDATES = 3000
DEFAULT_RANDOM_SEED = 42

LINE_DRAWNO = re.compile(r"^\d{4}$")
NUM_TOKEN_RE = re.compile(r"^\d{1,2}$")


# =========================================================
# STYLE
# =========================================================
st.set_page_config(page_title=APP_TITLE, layout="wide")

APP_CSS = """
<style>
:root{
  --bg0:#eef8ef;
  --bg1:#ffffff;
  --card:#ffffff;
  --card2:#f8fff8;
  --txt:#111111;
  --mut:#4b5563;
  --green:#0d7a34;
  --green2:#2ea85d;
  --gold:#d3aa2b;
  --gold2:#ffdd67;
  --border: rgba(13,122,52,0.18);
  --shadow: 0 10px 28px rgba(0,0,0,.08);
}

.stApp{
  background-color: var(--bg0) !important;
  background-image:
    radial-gradient(1200px 800px at 12% 10%, rgba(46,168,93,0.08), transparent 58%),
    radial-gradient(950px 650px at 92% 18%, rgba(211,170,43,0.07), transparent 55%),
    linear-gradient(180deg, var(--bg0), var(--bg1)) !important;
}

.block-container{
  padding-top: 1.2rem !important;
}

.v-card{
  background: linear-gradient(180deg, var(--card), var(--card2));
  border: 1px solid var(--border);
  box-shadow: var(--shadow);
  border-radius: 18px;
  padding: 16px;
  margin-bottom: 16px;
}

.v-title{
  font-size: 1.06rem;
  font-weight: 800;
  margin-bottom: 8px;
}

.v-muted{
  color: var(--mut);
  font-size: .95rem;
}

.ticket-card{
  background: linear-gradient(180deg, #ffffff, #f6fff8);
  border: 1px solid rgba(13,122,52,0.18);
  border-radius: 18px;
  padding: 16px;
  margin: 10px 0;
  box-shadow: 0 8px 18px rgba(0,0,0,.05);
}

.ticket-card-gold{
  background: linear-gradient(135deg, #fff7dd 0%, #fff0b8 100%);
  border: 2px solid #f3c63a;
  border-radius: 18px;
  padding: 18px;
  margin: 10px 0;
  box-shadow: 0 12px 24px rgba(243,198,58,0.22);
}

.ticket-title{
  font-size: 1.02rem;
  font-weight: 900;
  margin-bottom: 8px;
}

.ticket-main{
  font-size: 1.18rem;
  font-weight: 900;
  letter-spacing: .5px;
  margin-bottom: 8px;
}

.ticket-meta{
  font-size: .94rem;
  line-height: 1.55;
  color: #1f2937;
}

.pill{
  display:inline-block;
  padding: 6px 10px;
  margin: 3px 4px 0 0;
  border-radius: 999px;
  border: 1px solid rgba(13,122,52,0.25);
  background: rgba(13,122,52,0.08);
  font-weight: 800;
  font-size: .9rem;
}

.help-box{
  background: rgba(255,255,255,.75);
  border: 1px solid rgba(13,122,52,0.16);
  border-radius: 16px;
  padding: 14px;
  margin: 10px 0;
}

div.stButton > button{
  width: 100%;
  border-radius: 14px;
  min-height: 3.1rem;
  border: 0 !important;
  background: linear-gradient(90deg, var(--green) 0%, var(--green2) 100%) !important;
  color: white !important;
  font-weight: 800 !important;
}

div.stDownloadButton > button{
  width: 100%;
  border-radius: 14px;
  min-height: 3rem;
  font-weight: 800 !important;
}
</style>
"""
st.markdown(APP_CSS, unsafe_allow_html=True)


# =========================================================
# MODELE DANYCH
# =========================================================
@dataclass
class Draw:
    draw_id: int
    main: List[int]
    euro: List[int]


@dataclass
class TicketResult:
    mode: str
    main: List[int]
    euro: List[int]
    score: float
    note: str


# =========================================================
# POMOCNICZE
# =========================================================
def fmt_nums(nums: List[int]) -> str:
    return " ".join(f"{n:02d}" for n in sorted(nums))


def clamp(value: int, low: int, high: int) -> int:
    return max(low, min(high, value))


def count_even(nums: List[int]) -> int:
    return sum(1 for n in nums if n % 2 == 0)


def count_adjacent_pairs(nums: List[int]) -> int:
    s = sorted(nums)
    return sum(1 for a, b in zip(s, s[1:]) if b == a + 1)


def max_run(nums: List[int]) -> int:
    s = sorted(nums)
    if not s:
        return 0
    best = 1
    cur = 1
    for a, b in zip(s, s[1:]):
        if b == a + 1:
            cur += 1
            best = max(best, cur)
        else:
            cur = 1
    return best


def safe_mean(values: List[float], default: float = 0.0) -> float:
    return sum(values) / len(values) if values else default


def weighted_sample_without_replacement(
    population: List[int],
    weights: List[float],
    k: int,
    rng: random.Random
) -> List[int]:
    if k > len(population):
        raise ValueError("k nie może być większe niż populacja.")
    pop = population[:]
    wts = weights[:]
    result = []
    for _ in range(k):
        total = sum(wts)
        if total <= 0:
            pick_idx = rng.randrange(len(pop))
        else:
            r = rng.uniform(0, total)
            acc = 0.0
            pick_idx = 0
            for i, w in enumerate(wts):
                acc += w
                if acc >= r:
                    pick_idx = i
                    break
        result.append(pop.pop(pick_idx))
        wts.pop(pick_idx)
    return sorted(result)


def sanitize_txt_filename(name: str) -> str:
    name = (name or "").strip()
    if not name:
        name = "eurojackpot_kupony.txt"
    name = name.replace("\\", "_").replace("/", "_").replace("..", "_")
    if not name.lower().endswith(".txt"):
        name += ".txt"
    return name


def normalize_score_dict(raw: Dict[int, float]) -> Dict[int, float]:
    if not raw:
        return {}
    vals = list(raw.values())
    mn = min(vals)
    mx = max(vals)
    if mx == mn:
        return {k: 1.0 for k in raw}
    return {k: 0.1 + ((v - mn) / (mx - mn)) for k, v in raw.items()}


# =========================================================
# PDF PARSER
# =========================================================
def _validate_pdf_bytes(pdf_bytes: bytes) -> None:
    if not pdf_bytes.startswith(b"%PDF"):
        preview = pdf_bytes[:180].decode("utf-8", errors="replace")
        raise ValueError(
            "Plik nie wygląda jak prawdziwy PDF (brak nagłówka %PDF).\n"
            f"Początek pliku:\n{preview}"
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
    words_sorted = sorted(words, key=lambda w: (round(float(w[1]), 1), float(w[0])))
    rows = []
    current = []
    current_y = None

    for w in words_sorted:
        y = float(w[1])
        if current_y is None:
            current = [w]
            current_y = y
            continue

        if abs(y - current_y) <= y_tolerance:
            current.append(w)
            current_y = (current_y + y) / 2.0
        else:
            rows.append(sorted(current, key=lambda x: x[0]))
            current = [w]
            current_y = y

    if current:
        rows.append(sorted(current, key=lambda x: x[0]))
    return rows


def _is_noise_row(texts: List[str]) -> bool:
    joined = " ".join(texts).lower()
    noise_markers = ["multipasko", "www.", "mapy", "lotto", "liczbowe", "©"]
    return any(marker in joined and "eurojackpot" not in joined for marker in noise_markers)


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
            if _is_noise_row(texts):
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
                records.append({"draw_no": draw_no, "nums": nums})

    dedup = {}
    order = []
    for r in records:
        dno = r["draw_no"]
        if dno not in dedup:
            dedup[dno] = r["nums"]
            order.append(dno)

    final_records = [{"draw_no": dno, "nums": dedup[dno]} for dno in order]
    final_records.sort(key=lambda r: r["draw_no"], reverse=True)
    return final_records


@st.cache_data(show_spinner=False)
def load_draws_from_pdf_bytes(pdf_main_bytes: bytes, pdf_euro_bytes: bytes) -> Tuple[List[Draw], Dict]:
    main_pages_words = _read_pdf_pages_words(pdf_main_bytes)
    euro_pages_words = _read_pdf_pages_words(pdf_euro_bytes)

    main_records = _extract_records_from_grid_words(
        main_pages_words,
        MAIN_MIN,
        MAIN_MAX,
        MAIN_PICK,
        "Eurojackpot 5/50"
    )
    euro_records = _extract_records_from_grid_words(
        euro_pages_words,
        EURO_MIN,
        EURO_MAX,
        EURO_PICK,
        "Eurojackpot 2/12"
    )

    if not main_records:
        raise RuntimeError("Nie udało się odczytać wyników 5/50 z PDF.")
    if not euro_records:
        raise RuntimeError("Nie udało się odczytać wyników 2/12 z PDF.")

    main_map = {r["draw_no"]: r["nums"] for r in main_records}
    euro_map = {r["draw_no"]: r["nums"] for r in euro_records}

    common_draws = sorted(set(main_map.keys()) & set(euro_map.keys()), reverse=True)
    if not common_draws:
        raise RuntimeError("Brak wspólnych numerów losowań między plikami 5/50 i 2/12.")

    draws = [Draw(draw_id=dno, main=main_map[dno], euro=euro_map[dno]) for dno in common_draws]

    diagnostics = {
        "draws_main": len(main_records),
        "draws_euro": len(euro_records),
        "draws_common": len(draws),
        "latest_draw_id": draws[0].draw_id if draws else None,
        "oldest_draw_id": draws[-1].draw_id if draws else None,
    }
    return draws, diagnostics


# =========================================================
# DANE DOMYŚLNE BEZ PDF
# =========================================================
DEFAULT_DRAWS: List[Draw] = [
    Draw(1005, [5, 15, 18, 20, 35], [7, 8]),
    Draw(1004, [21, 23, 25, 38, 40], [7, 11]),
    Draw(1003, [9, 15, 23, 43, 48], [3, 5]),
    Draw(1002, [2, 17, 21, 25, 30], [2, 6]),
    Draw(1001, [12, 13, 16, 17, 37], [4, 11]),
    Draw(1000, [7, 23, 37, 44, 47], [2, 6]),
    Draw(999, [2, 3, 17, 18, 28], [4, 10]),
    Draw(998, [8, 17, 26, 31, 47], [1, 6]),
    Draw(997, [1, 9, 14, 35, 49], [2, 10]),
    Draw(996, [7, 17, 19, 28, 47], [2, 7]),
]


# =========================================================
# ANALITYKA
# =========================================================
class EuroAnalyzer:
    def __init__(self, draws: List[Draw]):
        self.draws = sorted(draws, key=lambda d: d.draw_id, reverse=True)
        self.total_draws = len(self.draws)

        self.main_draws = [d.main for d in self.draws]
        self.euro_draws = [d.euro for d in self.draws]

        self.main_freq = self._freq_map(self.main_draws, MAIN_MIN, MAIN_MAX)
        self.euro_freq = self._freq_map(self.euro_draws, EURO_MIN, EURO_MAX)

        self.main_presence_pct = self._presence_pct(self.main_draws, MAIN_MIN, MAIN_MAX)
        self.euro_presence_pct = self._presence_pct(self.euro_draws, EURO_MIN, EURO_MAX)

        self.main_last_seen = self._last_seen_map(self.main_draws, MAIN_MIN, MAIN_MAX)
        self.euro_last_seen = self._last_seen_map(self.euro_draws, EURO_MIN, EURO_MAX)

        self.main_avg_gaps, self.main_gap_consistency = self._gap_stats(self.main_draws, MAIN_MIN, MAIN_MAX)
        self.euro_avg_gaps, self.euro_gap_consistency = self._gap_stats(self.euro_draws, EURO_MIN, EURO_MAX)

        self.main_pair_counter = self._pair_counter(self.main_draws)
        self.euro_pair_counter = self._pair_counter(self.euro_draws)

        self.main_triple_counter = self._triple_counter(self.main_draws)

        self.main_target_profile = self._target_profile(self.main_draws, threshold=25)
        self.euro_target_profile = self._target_profile(self.euro_draws, threshold=6)

    def _freq_map(self, draws: List[List[int]], low: int, high: int) -> Dict[int, int]:
        freq = {n: 0 for n in range(low, high + 1)}
        for d in draws:
            for n in d:
                freq[n] += 1
        return freq

    def _presence_pct(self, draws: List[List[int]], low: int, high: int) -> Dict[int, float]:
        total = len(draws)
        if total == 0:
            return {n: 0.0 for n in range(low, high + 1)}
        pct = {}
        for n in range(low, high + 1):
            hits = sum(1 for d in draws if n in d)
            pct[n] = 100.0 * hits / total
        return pct

    def _last_seen_map(self, draws: List[List[int]], low: int, high: int) -> Dict[int, int]:
        out = {}
        for n in range(low, high + 1):
            idx = next((i for i, d in enumerate(draws) if n in d), None)
            out[n] = idx if idx is not None else len(draws) + 10
        return out

    def _gap_stats(self, draws: List[List[int]], low: int, high: int) -> Tuple[Dict[int, float], Dict[int, float]]:
        positions = {n: [] for n in range(low, high + 1)}
        chronological = list(reversed(draws))
        for idx, d in enumerate(chronological):
            for n in d:
                positions[n].append(idx)

        avg_gaps = {}
        consistency = {}
        for n in range(low, high + 1):
            pos = positions[n]
            if len(pos) < 2:
                avg_gaps[n] = 999.0
                consistency[n] = 0.0
                continue
            gaps = [b - a for a, b in zip(pos, pos[1:])]
            avg_gaps[n] = safe_mean(gaps, 999.0)
            try:
                std = statistics.pstdev(gaps) if len(gaps) > 1 else 0.0
                consistency[n] = 1.0 / (1.0 + std)
            except Exception:
                consistency[n] = 0.0
        return avg_gaps, consistency

    def _pair_counter(self, draws: List[List[int]]) -> Dict[Tuple[int, int], int]:
        counter = {}
        for d in draws:
            for pair in combinations(sorted(d), 2):
                counter[pair] = counter.get(pair, 0) + 1
        return counter

    def _triple_counter(self, draws: List[List[int]]) -> Dict[Tuple[int, int, int], int]:
        counter = {}
        for d in draws:
            for tri in combinations(sorted(d), 3):
                counter[tri] = counter.get(tri, 0) + 1
        return counter

    def _target_profile(self, draws: List[List[int]], threshold: int) -> Dict:
        if not draws:
            return {
                "target_even": 2,
                "target_spread": 20.0,
                "target_pairs": 0.5,
                "target_sum": 0.0
            }

        even_counts = []
        spreads = []
        adj_pairs = []
        sums_ = []

        for d in draws:
            s = sorted(d)
            even_counts.append(count_even(s))
            spreads.append(max(s) - min(s))
            adj_pairs.append(count_adjacent_pairs(s))
            sums_.append(sum(s))

        target_even = max(set(even_counts), key=even_counts.count)
        return {
            "target_even": target_even,
            "target_spread": safe_mean(spreads),
            "target_pairs": safe_mean(adj_pairs),
            "target_sum": safe_mean(sums_),
            "threshold": threshold,
        }

    def main_percent_df(self) -> pd.DataFrame:
        rows = []
        for n in range(MAIN_MIN, MAIN_MAX + 1):
            rows.append({
                "Liczba": n,
                "Wystąpienia": self.main_freq[n],
                "Procent_losowań": round(self.main_presence_pct[n], 2),
                "Opóźnienie": self.main_last_seen[n],
                "Średnia_przerwa": round(self.main_avg_gaps[n], 2),
            })
        return pd.DataFrame(rows).sort_values(
            ["Procent_losowań", "Wystąpienia", "Liczba"],
            ascending=[False, False, True]
        ).reset_index(drop=True)

    def euro_percent_df(self) -> pd.DataFrame:
        rows = []
        for n in range(EURO_MIN, EURO_MAX + 1):
            rows.append({
                "Liczba": n,
                "Wystąpienia": self.euro_freq[n],
                "Procent_losowań": round(self.euro_presence_pct[n], 2),
                "Opóźnienie": self.euro_last_seen[n],
                "Średnia_przerwa": round(self.euro_avg_gaps[n], 2),
            })
        return pd.DataFrame(rows).sort_values(
            ["Procent_losowań", "Wystąpienia", "Liczba"],
            ascending=[False, False, True]
        ).reset_index(drop=True)


# =========================================================
# SILNIK SCORINGU
# =========================================================
class ScoringEngine:
    def __init__(self, analyzer: EuroAnalyzer):
        self.a = analyzer

        self.main_component = self._build_number_scores(
            self.a.main_presence_pct,
            self.a.main_last_seen,
            self.a.main_avg_gaps,
            self.a.main_gap_consistency
        )
        self.euro_component = self._build_number_scores(
            self.a.euro_presence_pct,
            self.a.euro_last_seen,
            self.a.euro_avg_gaps,
            self.a.euro_gap_consistency
        )

    def _build_number_scores(
        self,
        pct_map: Dict[int, float],
        last_seen_map: Dict[int, int],
        avg_gap_map: Dict[int, float],
        consistency_map: Dict[int, float],
    ) -> Dict[int, float]:
        raw = {}
        for n, pct in pct_map.items():
            hotness = pct
            recency_bonus = max(0.0, 18.0 - abs(last_seen_map[n] - 7))
            rhythm_bonus = consistency_map[n] * 25.0
            avg_gap_bonus = 0.0 if avg_gap_map[n] >= 900 else max(0.0, 12.0 - abs(avg_gap_map[n] - 8))
            raw[n] = hotness + recency_bonus + rhythm_bonus + avg_gap_bonus
        return normalize_score_dict(raw)

    def score_ticket(self, main_nums: List[int], euro_nums: List[int]) -> float:
        main_score = self._score_main_ticket(main_nums)
        euro_score = self._score_euro_ticket(euro_nums)
        return round(main_score + euro_score, 4)

    def _score_main_ticket(self, nums: List[int]) -> float:
        nums = sorted(nums)
        base = sum(self.main_component.get(n, 0.1) for n in nums)

        pair_bonus = sum(self.a.main_pair_counter.get(tuple(sorted(pair)), 0) for pair in combinations(nums, 2)) * 0.02
        triple_bonus = sum(self.a.main_triple_counter.get(tuple(sorted(tri)), 0) for tri in combinations(nums, 3)) * 0.03

        even_target = self.a.main_target_profile["target_even"]
        even_penalty = abs(count_even(nums) - even_target) * 0.25

        spread = max(nums) - min(nums)
        spread_penalty = abs(spread - self.a.main_target_profile["target_spread"]) / 80.0

        sum_penalty = abs(sum(nums) - self.a.main_target_profile["target_sum"]) / 200.0

        seq_penalty = max(0, max_run(nums) - 2) * 0.35

        recent_similarity_penalty = 0.0
        for d in self.a.main_draws[:8]:
            common = len(set(nums) & set(d))
            if common >= 4:
                recent_similarity_penalty += 0.5
            elif common == 5:
                recent_similarity_penalty += 2.0

        return base + pair_bonus + triple_bonus - even_penalty - spread_penalty - sum_penalty - seq_penalty - recent_similarity_penalty

    def _score_euro_ticket(self, nums: List[int]) -> float:
        nums = sorted(nums)
        base = sum(self.euro_component.get(n, 0.1) for n in nums)
        pair_bonus = self.a.euro_pair_counter.get(tuple(nums), 0) * 0.08

        even_target = self.a.euro_target_profile["target_even"]
        even_penalty = abs(count_even(nums) - even_target) * 0.18

        spread = max(nums) - min(nums)
        spread_penalty = abs(spread - self.a.euro_target_profile["target_spread"]) / 30.0

        recent_similarity_penalty = 0.0
        for d in self.a.euro_draws[:8]:
            common = len(set(nums) & set(d))
            if common == 2:
                recent_similarity_penalty += 0.6

        return base + pair_bonus - even_penalty - spread_penalty - recent_similarity_penalty


# =========================================================
# SZLACZEK
# =========================================================
def build_position_paths(draws: List[Draw], count: int, euro: bool = False) -> List[List[int]]:
    paths = [[] for _ in range(count)]
    chronological = list(reversed(draws))  # od najstarszych do najnowszych

    for d in chronological:
        nums = sorted(d.euro if euro else d.main)
        for i in range(count):
            paths[i].append(nums[i])
    return paths


def fix_duplicates(nums: List[int], low: int, high: int) -> List[int]:
    seen = set()
    result = []
    for n in nums:
        candidate = n
        while candidate in seen:
            candidate += 1
            if candidate > high:
                candidate = low
        seen.add(candidate)
        result.append(candidate)
    return result


def predict_single_path(
    path: List[int],
    low: int,
    high: int,
    window_short: int = 5,
    window_long: int = 10,
    use_position_range: bool = True
) -> Tuple[int, Dict]:
    if len(path) < 3:
        pred = clamp(path[-1], low, high)
        return pred, {
            "last_value": path[-1],
            "avg_delta_short": 0.0,
            "avg_delta_long": 0.0,
            "common_delta": 0,
            "bounce": 0,
            "confidence": "LOW",
            "raw": float(pred),
            "final": pred,
        }

    deltas = [path[i] - path[i - 1] for i in range(1, len(path))]
    last_value = path[-1]

    short = deltas[-window_short:] if len(deltas) >= window_short else deltas[:]
    long_ = deltas[-window_long:] if len(deltas) >= window_long else deltas[:]

    avg_short = safe_mean(short)
    avg_long = safe_mean(long_)

    try:
        common_delta = max(set(deltas), key=deltas.count)
    except Exception:
        common_delta = 0

    trend = sum(short)
    bounce = 0
    if trend > 5:
        bounce = -1
    elif trend < -5:
        bounce = 1

    raw = (
        last_value
        + 0.40 * avg_short
        + 0.25 * avg_long
        + 0.20 * common_delta
        + 0.15 * bounce
    )

    predicted = int(round(raw))
    predicted = clamp(predicted, low, high)

    if use_position_range and len(path) >= 8:
        try:
            q = statistics.quantiles(path, n=10, method="inclusive")
            local_low = int(q[1])
            local_high = int(q[-2])
            if local_low <= local_high:
                predicted = clamp(predicted, max(low, local_low), min(high, local_high))
        except Exception:
            pass

    try:
        std = statistics.pstdev(deltas) if len(deltas) > 1 else 999.0
        if std < 2:
            confidence = "HIGH"
        elif std < 5:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"
    except Exception:
        confidence = "LOW"

    return predicted, {
        "last_value": last_value,
        "avg_delta_short": round(avg_short, 3),
        "avg_delta_long": round(avg_long, 3),
        "common_delta": common_delta,
        "bounce": bounce,
        "confidence": confidence,
        "raw": round(raw, 3),
        "final": predicted,
    }


def predict_positions(
    paths: List[List[int]],
    low: int,
    high: int,
    window_short: int = 5,
    window_long: int = 10,
    use_position_range: bool = True
) -> Tuple[List[int], List[Dict]]:
    results = []
    details = []

    for idx, path in enumerate(paths, start=1):
        pred, info = predict_single_path(
            path=path,
            low=low,
            high=high,
            window_short=window_short,
            window_long=window_long,
            use_position_range=use_position_range
        )
        info["position"] = idx
        results.append(pred)
        details.append(info)

    return results, details


def predict_from_szlaczek(draws: List[Draw], pro: bool = False) -> Tuple[List[int], List[int], List[Dict], List[Dict]]:
    main_paths = build_position_paths(draws, count=MAIN_PICK, euro=False)
    euro_paths = build_position_paths(draws, count=EURO_PICK, euro=True)

    main_pred, main_details = predict_positions(
        main_paths, MAIN_MIN, MAIN_MAX,
        window_short=5, window_long=10, use_position_range=pro
    )
    euro_pred, euro_details = predict_positions(
        euro_paths, EURO_MIN, EURO_MAX,
        window_short=5, window_long=10, use_position_range=pro
    )

    main_fixed = sorted(fix_duplicates(main_pred, MAIN_MIN, MAIN_MAX))
    euro_fixed = sorted(fix_duplicates(euro_pred, EURO_MIN, EURO_MAX))

    if pro:
        main_fixed = adjust_distribution(main_fixed, euro=False)
        euro_fixed = adjust_distribution(euro_fixed, euro=True)

    return main_fixed, euro_fixed, main_details, euro_details


def adjust_distribution(nums: List[int], euro: bool = False) -> List[int]:
    nums = sorted(nums)
    if not nums:
        return nums

    low = EURO_MIN if euro else MAIN_MIN
    high = EURO_MAX if euro else MAIN_MAX

    evens = count_even(nums)

    if evens == len(nums):
        nums[-1] = clamp(nums[-1] - 1, low, high)
    elif evens == 0:
        nums[-1] = clamp(nums[-1] + 1, low, high)

    if max_run(nums) >= 4:
        nums[-1] = clamp(nums[-1] + 2, low, high)

    nums = sorted(fix_duplicates(nums, low, high))
    return nums


# =========================================================
# GENERATORY
# =========================================================
class TicketGenerator:
    def __init__(self, analyzer: EuroAnalyzer, scorer: ScoringEngine, seed: int = DEFAULT_RANDOM_SEED):
        self.a = analyzer
        self.s = scorer
        self.rng = random.Random(seed)

    def generate_random_ticket(self) -> TicketResult:
        main = sorted(self.rng.sample(list(range(MAIN_MIN, MAIN_MAX + 1)), MAIN_PICK))
        euro = sorted(self.rng.sample(list(range(EURO_MIN, EURO_MAX + 1)), EURO_PICK))
        score = self.s.score_ticket(main, euro)
        return TicketResult("Losowy", main, euro, score, "Czysty los bez analizy danych.")

    def generate_hot_ticket(self, top_main: int = 18, top_euro: int = 6) -> TicketResult:
        main_pool = self._top_numbers(self.a.main_presence_pct, top_main)
        euro_pool = self._top_numbers(self.a.euro_presence_pct, top_euro)
        main = sorted(self.rng.sample(main_pool, MAIN_PICK))
        euro = sorted(self.rng.sample(euro_pool, EURO_PICK))
        score = self.s.score_ticket(main, euro)
        return TicketResult("Hot %", main, euro, score, "Zestaw z puli liczb najczęściej występujących procentowo.")

    def generate_cold_ticket(self, bottom_main: int = 18, bottom_euro: int = 6) -> TicketResult:
        main_pool = self._bottom_numbers(self.a.main_presence_pct, bottom_main)
        euro_pool = self._bottom_numbers(self.a.euro_presence_pct, bottom_euro)
        main = sorted(self.rng.sample(main_pool, MAIN_PICK))
        euro = sorted(self.rng.sample(euro_pool, EURO_PICK))
        score = self.s.score_ticket(main, euro)
        return TicketResult("Cold %", main, euro, score, "Zestaw z puli liczb najrzadziej występujących procentowo.")

    def generate_hybrid_ticket(self, hot_main_n: int = 2, cold_main_n: int = 2, hot_euro_n: int = 1) -> TicketResult:
        hot_main_pool = self._top_numbers(self.a.main_presence_pct, 18)
        cold_main_pool = self._bottom_numbers(self.a.main_presence_pct, 18)
        neutral_main = [n for n in range(MAIN_MIN, MAIN_MAX + 1) if n not in hot_main_pool and n not in cold_main_pool]

        hot_euro_pool = self._top_numbers(self.a.euro_presence_pct, 6)
        cold_euro_pool = self._bottom_numbers(self.a.euro_presence_pct, 6)
        neutral_euro = [n for n in range(EURO_MIN, EURO_MAX + 1) if n not in hot_euro_pool and n not in cold_euro_pool]

        main = []
        main.extend(self.rng.sample(hot_main_pool, hot_main_n))
        main.extend(self.rng.sample(cold_main_pool, cold_main_n))
        main.extend(self.rng.sample([n for n in neutral_main if n not in main], MAIN_PICK - len(main)))

        euro = []
        euro.extend(self.rng.sample(hot_euro_pool, hot_euro_n))
        euro.extend(self.rng.sample([n for n in cold_euro_pool if n not in euro], 1))
        if len(euro) < EURO_PICK:
            euro.extend(self.rng.sample([n for n in neutral_euro if n not in euro], EURO_PICK - len(euro)))

        main = sorted(main)
        euro = sorted(euro)
        score = self.s.score_ticket(main, euro)
        return TicketResult("50/50", main, euro, score, "Mieszanka hot, cold i neutral dla bardziej zbalansowanego kuponu.")

    def generate_golden_ticket(self) -> TicketResult:
        main_pop = list(range(MAIN_MIN, MAIN_MAX + 1))
        euro_pop = list(range(EURO_MIN, EURO_MAX + 1))

        main_weights = [self.s.main_component[n] for n in main_pop]
        euro_weights = [self.s.euro_component[n] for n in euro_pop]

        best_ticket = None
        best_score = -999999.0

        for _ in range(400):
            main = weighted_sample_without_replacement(main_pop, main_weights, MAIN_PICK, self.rng)
            euro = weighted_sample_without_replacement(euro_pop, euro_weights, EURO_PICK, self.rng)
            score = self.s.score_ticket(main, euro)
            if score > best_score:
                best_score = score
                best_ticket = (main, euro)

        main, euro = best_ticket
        return TicketResult(
            "Złoty Strzał",
            main,
            euro,
            best_score,
            "Najmocniejszy kupon znaleziony z wykorzystaniem score częstotliwości, rytmu, opóźnienia i zgodności układu."
        )

    def generate_probability_ranking(self, candidates: int = DEFAULT_CANDIDATES, top_n: int = 10) -> List[TicketResult]:
        results = []

        main_pop = list(range(MAIN_MIN, MAIN_MAX + 1))
        euro_pop = list(range(EURO_MIN, EURO_MAX + 1))
        main_weights = [self.s.main_component[n] for n in main_pop]
        euro_weights = [self.s.euro_component[n] for n in euro_pop]

        seen = set()
        for _ in range(candidates):
            main = tuple(weighted_sample_without_replacement(main_pop, main_weights, MAIN_PICK, self.rng))
            euro = tuple(weighted_sample_without_replacement(euro_pop, euro_weights, EURO_PICK, self.rng))
            key = (main, euro)
            if key in seen:
                continue
            seen.add(key)
            score = self.s.score_ticket(list(main), list(euro))
            results.append(
                TicketResult(
                    "Ranking prawdopodobieństwa",
                    list(main),
                    list(euro),
                    score,
                    "Kupon rankingowy z dużej puli kandydatów ocenionych przez silnik scoringu."
                )
            )

        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_n]

    def generate_szlaczek_ticket(self, pro: bool = False) -> Tuple[TicketResult, List[Dict], List[Dict]]:
        main, euro, main_details, euro_details = predict_from_szlaczek(self.a.draws, pro=pro)
        score = self.s.score_ticket(main, euro)
        mode = "Szlaczek PRO" if pro else "Szlaczek"
        note = (
            "Prognoza pozycyjna na bazie trajektorii każdej pozycji osobno + korekta rozkładu."
            if pro else
            "Prognoza pozycyjna na bazie trajektorii każdej pozycji osobno."
        )
        return TicketResult(mode, main, euro, score, note), main_details, euro_details

    def _top_numbers(self, pct_map: Dict[int, float], k: int) -> List[int]:
        return [n for n, _ in sorted(pct_map.items(), key=lambda x: (-x[1], x[0]))[:k]]

    def _bottom_numbers(self, pct_map: Dict[int, float], k: int) -> List[int]:
        return [n for n, _ in sorted(pct_map.items(), key=lambda x: (x[1], x[0]))[:k]]


# =========================================================
# RENDER
# =========================================================
def render_ticket(ticket: TicketResult, highlight: bool = False) -> None:
    css = "ticket-card-gold" if highlight else "ticket-card"
    st.markdown(
        f"""
        <div class="{css}">
          <div class="ticket-title">{ticket.mode}</div>
          <div class="ticket-main">Main: {fmt_nums(ticket.main)} &nbsp;&nbsp;|&nbsp;&nbsp; Euro: {fmt_nums(ticket.euro)}</div>
          <div class="ticket-meta">
            <b>Score:</b> {ticket.score:.4f}<br>
            <b>Opis:</b> {ticket.note}<br>
            <b>Parzyste main:</b> {count_even(ticket.main)}/{len(ticket.main)-count_even(ticket.main)} |
            <b>Pary kolejne main:</b> {count_adjacent_pairs(ticket.main)} |
            <b>Suma main:</b> {sum(ticket.main)}<br>
            <b>Parzyste euro:</b> {count_even(ticket.euro)}/{len(ticket.euro)-count_even(ticket.euro)} |
            <b>Pary kolejne euro:</b> {count_adjacent_pairs(ticket.euro)} |
            <b>Suma euro:</b> {sum(ticket.euro)}
          </div>
        </div>
        """,
        unsafe_allow_html=True
    )


def render_pattern_details(title: str, details: List[Dict]) -> None:
    st.markdown(f"### {title}")
    rows = []
    for d in details:
        rows.append({
            "Pozycja": d["position"],
            "Ostatnia wartość": d["last_value"],
            "Śr. delta 5": d["avg_delta_short"],
            "Śr. delta 10": d["avg_delta_long"],
            "Najczęstsza delta": d["common_delta"],
            "Bounce": d["bounce"],
            "Pewność": d["confidence"],
            "Prognoza surowa": d["raw"],
            "Prognoza końcowa": d["final"],
        })
    st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)


def ticket_list_to_txt(tickets: List[TicketResult]) -> str:
    lines = []
    for i, t in enumerate(tickets, start=1):
        lines.append(f"#{i:03d} | {t.mode}")
        lines.append(f"Main: {fmt_nums(t.main)}")
        lines.append(f"Euro: {fmt_nums(t.euro)}")
        lines.append(f"Score: {t.score:.4f}")
        lines.append(f"Opis: {t.note}")
        lines.append("")
    return "\n".join(lines)


def render_help_tab() -> None:
    st.header("📚 Opis funkcji i przykłady użycia")

    help_items = [
        (
            "🎲 Losowy",
            "Generuje całkowicie losowy zestaw bez opierania się na historii. Dobry, gdy chcesz czysty los i nie chcesz żadnej analizy.",
            "Przykład najlepszego użycia: gdy chcesz szybko wygenerować 3–5 kuponów bez sugerowania się historią."
        ),
        (
            "🔥 Hot %",
            "Buduje kupon z puli liczb, które procentowo występowały najczęściej w analizowanej historii.",
            "Przykład najlepszego użycia: gdy chcesz oprzeć kupon na liczbach 'gorących' z ostatnich 999 lub 250 losowań."
        ),
        (
            "❄️ Cold %",
            "Buduje kupon z puli liczb, które procentowo występowały najrzadziej.",
            "Przykład najlepszego użycia: gdy chcesz zagrać pod liczby rzadkie i nietypowe."
        ),
        (
            "⚖️ 50/50",
            "Miesza pule hot, cold i neutral, żeby kupon nie był ani zbyt gorący, ani zbyt zimny.",
            "Przykład najlepszego użycia: gdy chcesz zbalansowany zestaw i nie chcesz iść skrajnie w hot albo cold."
        ),
        (
            "🏆 Złoty Strzał",
            "Silnik tworzy wiele kandydatów i wybiera statystycznie najmocniejszy według score: częstotliwość, rytm, opóźnienie, zgodność par i kształtu układu.",
            "Przykład najlepszego użycia: gdy chcesz dostać jeden najmocniejszy kupon z całej aplikacji."
        ),
        (
            "📈 Ranking prawdopodobieństwa",
            "Generator tworzy dużą pulę kandydatów i pokazuje TOP kupony o najwyższym score.",
            "Przykład najlepszego użycia: gdy chcesz dostać nie 1, lecz np. 10 najlepszych kuponów do wyboru."
        ),
        (
            "🧠 Szlaczek",
            "Analizuje każdą pozycję osobno: pozycja 1 do 1, 2 do 2, 3 do 3 itd. Patrzy na ruch, delty, odbicia i przewiduje następną liczbę pozycyjną.",
            "Przykład najlepszego użycia: gdy chcesz typować na bazie wizualnego toru ruchu liczb, tak jak po Twoim zaznaczonym szlaczku."
        ),
        (
            "🚀 Szlaczek PRO",
            "To samo co szlaczek, ale z korektą zakresu pozycji i poprawą rozkładu zestawu.",
            "Przykład najlepszego użycia: gdy chcesz zachować logikę szlaczka, ale ograniczyć dziwne układy."
        ),
        (
            "📂 Tryb bez PDF",
            "Aplikacja korzysta z małego, wbudowanego zestawu danych startowych, żeby dało się testować funkcje bez plików.",
            "Przykład najlepszego użycia: gdy chcesz sprawdzić interfejs i działanie aplikacji od razu."
        ),
        (
            "📄 Tryb z PDF",
            "Aplikacja czyta Twoje dwa pliki PDF, łączy wyniki po numerze losowania i na tej podstawie buduje analizę.",
            "Przykład najlepszego użycia: gdy chcesz pełną analizę rzeczywistych losowań."
        ),
    ]

    for title, desc, ex in help_items:
        with st.expander(title):
            st.write(desc)
            st.markdown(f"**Przykład najlepszego użycia:** {ex}")


# =========================================================
# GŁÓWNA APLIKACJA
# =========================================================
def main():
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    if "generated_tickets" not in st.session_state:
        st.session_state.generated_tickets = []

    with st.sidebar:
        st.markdown("## ⚙️ Ustawienia")

        data_mode = st.radio(
            "Źródło danych",
            ["Tryb bez PDF", "Tryb z PDF"],
            index=0
        )

        uploaded_main = None
        uploaded_euro = None

        if data_mode == "Tryb z PDF":
            uploaded_main = st.file_uploader("Wgraj PDF 5/50", type=["pdf"])
            uploaded_euro = st.file_uploader("Wgraj PDF 2/12", type=["pdf"])

        history_window = st.selectbox(
            "Zakres historii do analizy",
            [50, 100, 250, 500, 999],
            index=4
        )

        ranking_candidates = st.slider(
            "Ile kandydatów dla rankingu i złotego strzału",
            min_value=300,
            max_value=10000,
            value=3000,
            step=100
        )

        seed = st.number_input("Seed losowania", min_value=1, max_value=999999, value=DEFAULT_RANDOM_SEED)

        txt_filename = st.text_input("Nazwa pliku TXT do eksportu", value="eurojackpot_kupony.txt")

    draws: List[Draw] = []
    diagnostics = {}

    try:
        if data_mode == "Tryb z PDF":
            if uploaded_main is None or uploaded_euro is None:
                st.info("Wgraj oba pliki PDF, aby uruchomić pełną analizę.")
                draws = DEFAULT_DRAWS[:]
                diagnostics = {
                    "draws_common": len(draws),
                    "latest_draw_id": draws[0].draw_id,
                    "oldest_draw_id": draws[-1].draw_id,
                    "mode": "fallback_demo"
                }
            else:
                pdf_main_bytes = uploaded_main.read()
                pdf_euro_bytes = uploaded_euro.read()
                draws, diagnostics = load_draws_from_pdf_bytes(pdf_main_bytes, pdf_euro_bytes)
        else:
            draws = DEFAULT_DRAWS[:]
            diagnostics = {
                "draws_common": len(draws),
                "latest_draw_id": draws[0].draw_id,
                "oldest_draw_id": draws[-1].draw_id,
                "mode": "demo"
            }
    except Exception as e:
        st.error(f"Błąd wczytywania danych: {e}")
        draws = DEFAULT_DRAWS[:]
        diagnostics = {
            "draws_common": len(draws),
            "latest_draw_id": draws[0].draw_id,
            "oldest_draw_id": draws[-1].draw_id,
            "mode": "fallback_error"
        }

    draws = draws[: min(history_window, len(draws))]

    analyzer = EuroAnalyzer(draws)
    scorer = ScoringEngine(analyzer)
    generator = TicketGenerator(analyzer, scorer, seed=int(seed))

    tab1, tab2, tab3, tab4 = st.tabs([
        "🚀 Generator",
        "📊 Analiza",
        "🧠 Szlaczek",
        "📚 Opisy funkcji"
    ])

    with tab1:
        c1, c2, c3 = st.columns(3)

        with c1:
            if st.button("🎲 Generuj: Losowy"):
                t = generator.generate_random_ticket()
                st.session_state.generated_tickets = [t]

            if st.button("🔥 Generuj: Hot %"):
                t = generator.generate_hot_ticket()
                st.session_state.generated_tickets = [t]

            if st.button("❄️ Generuj: Cold %"):
                t = generator.generate_cold_ticket()
                st.session_state.generated_tickets = [t]

        with c2:
            if st.button("⚖️ Generuj: 50/50"):
                t = generator.generate_hybrid_ticket()
                st.session_state.generated_tickets = [t]

            if st.button("🏆 Generuj: Złoty Strzał"):
                # dynamicznie nadpisujemy ilość kandydatów
                results = generator.generate_probability_ranking(candidates=ranking_candidates, top_n=1)
                best = results[0]
                best.mode = "Złoty Strzał"
                best.note = "Najmocniejszy kupon wybrany spośród dużej puli kandydatów ocenionych scoringiem."
                st.session_state.generated_tickets = [best]

            if st.button("📈 Generuj: Ranking TOP 10"):
                results = generator.generate_probability_ranking(candidates=ranking_candidates, top_n=10)
                st.session_state.generated_tickets = results

        with c3:
            if st.button("🧠 Generuj: Szlaczek"):
                t, _, _ = generator.generate_szlaczek_ticket(pro=False)
                st.session_state.generated_tickets = [t]

            if st.button("🚀 Generuj: Szlaczek PRO"):
                t, _, _ = generator.generate_szlaczek_ticket(pro=True)
                st.session_state.generated_tickets = [t]

            if st.button("🧹 Wyczyść wyniki"):
                st.session_state.generated_tickets = []

        st.markdown("---")

        st.markdown("### Wyniki")
        if st.session_state.generated_tickets:
            for idx, ticket in enumerate(st.session_state.generated_tickets):
                render_ticket(ticket, highlight=(idx == 0 and "Złoty Strzał" in ticket.mode))

            txt_content = ticket_list_to_txt(st.session_state.generated_tickets)
            st.download_button(
                "💾 Pobierz wyniki jako TXT",
                data=txt_content.encode("utf-8"),
                file_name=sanitize_txt_filename(txt_filename),
                mime="text/plain"
            )
        else:
            st.info("Wybierz jedną z funkcji generatora, aby zobaczyć kupony.")

        st.markdown("---")
        st.markdown("### Informacje o danych")
        col_a, col_b, col_c, col_d = st.columns(4)
        col_a.metric("Liczba losowań", diagnostics.get("draws_common", len(draws)))
        col_b.metric("Najnowsze ID", diagnostics.get("latest_draw_id", "—"))
        col_c.metric("Najstarsze ID", diagnostics.get("oldest_draw_id", "—"))
        col_d.metric("Tryb", data_mode)

    with tab2:
        st.markdown("### Top liczby main 5/50")
        st.dataframe(analyzer.main_percent_df().head(15), use_container_width=True, hide_index=True)

        st.markdown("### Top liczby euro 2/12")
        st.dataframe(analyzer.euro_percent_df().head(12), use_container_width=True, hide_index=True)

        st.markdown("### Wykres obecności % main")
        chart_main_df = analyzer.main_percent_df().sort_values("Liczba")
        st.line_chart(chart_main_df.set_index("Liczba")["Procent_losowań"])

        st.markdown("### Wykres obecności % euro")
        chart_euro_df = analyzer.euro_percent_df().sort_values("Liczba")
        st.line_chart(chart_euro_df.set_index("Liczba")["Procent_losowań"])

        st.markdown("### Ostatnie losowania")
        rows = []
        for d in draws[:15]:
            rows.append({
                "ID": d.draw_id,
                "Main": fmt_nums(d.main),
                "Euro": fmt_nums(d.euro),
                "Suma main": sum(d.main),
                "Parzyste main": count_even(d.main),
            })
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tab3:
        st.markdown("### Moduł szlaczka")
        st.caption("Każda pozycja jest analizowana osobno: 1→1, 2→2, 3→3, 4→4, 5→5 oraz euro 1→1, 2→2.")

        szl_simple, main_det, euro_det = generator.generate_szlaczek_ticket(pro=False)
        szl_pro, main_det_pro, euro_det_pro = generator.generate_szlaczek_ticket(pro=True)

        st.markdown("#### Wynik Szlaczek")
        render_ticket(szl_simple)

        st.markdown("#### Wynik Szlaczek PRO")
        render_ticket(szl_pro, highlight=True)

        col_left, col_right = st.columns(2)
        with col_left:
            render_pattern_details("Szczegóły main 5/50", main_det_pro)
        with col_right:
            render_pattern_details("Szczegóły euro 2/12", euro_det_pro)

        st.markdown("### Wizualizacja ścieżek pozycji")
        main_paths = build_position_paths(draws, MAIN_PICK, euro=False)
        euro_paths = build_position_paths(draws, EURO_PICK, euro=True)

        df_main_paths = pd.DataFrame(
            {f"Poz {i+1}": path for i, path in enumerate(main_paths)}
        )
        df_euro_paths = pd.DataFrame(
            {f"Euro Poz {i+1}": path for i, path in enumerate(euro_paths)}
        )

        st.markdown("#### Szlaczki main")
        st.line_chart(df_main_paths)

        st.markdown("#### Szlaczki euro")
        st.line_chart(df_euro_paths)

        with st.expander("Jak najlepiej używać funkcji Szlaczek?"):
            st.write(
                "Najlepiej używać jej wtedy, gdy chcesz typować zestaw na podstawie trajektorii pozycji. "
                "To nie jest zwykłe liczenie częstotliwości, tylko analiza ruchu każdej pozycji osobno. "
                "Wersja PRO jest zwykle lepsza, bo koryguje nienaturalne zakresy i układ zestawu."
            )

    with tab4:
        render_help_tab()


if __name__ == "__main__":
    main()
