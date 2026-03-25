import io
import os
import re
import math
import random
import itertools
from dataclasses import dataclass
from collections import Counter, defaultdict
from typing import List, Dict, Tuple

import fitz  # PyMuPDF
import streamlit as st


# ============================================================
# KONFIGURACJA
# ============================================================

APP_TITLE = "EuroJackpot PRO Analyzer"
APP_SUBTITLE = "Analiza PDF + częstotliwości + RYTMIKA (Interwały) + generator kuponów"

DEFAULT_MAIN_PDF = "wyniki1ej.pdf"   # 5/50
DEFAULT_EURO_PDF = "wyniki2ej.pdf"   # 2/12

MAX_DRAWS_DEFAULT = 999
DEFAULT_TICKETS_COUNT = 5
DEFAULT_RANDOM_SEED = 42

MAIN_MIN = 1
MAIN_MAX = 50
EURO_MIN = 1
EURO_MAX = 12

DEFAULT_WEIGHT_FREQ = 0.25
DEFAULT_WEIGHT_RECENCY = 0.15
DEFAULT_WEIGHT_RHYTHM = 0.35  
DEFAULT_WEIGHT_PAIR = 0.15
DEFAULT_WEIGHT_TRIPLE = 0.10

DEFAULT_HOT_POOL_MAIN = 20
DEFAULT_HOT_POOL_EURO = 6
DEFAULT_GENERATION_ATTEMPTS = 5000


# ============================================================
# MODELE
# ============================================================

@dataclass
class Draw:
    draw_id: int
    main_numbers: List[int]
    euro_numbers: List[int]


@dataclass
class AnalyzerConfig:
    weight_freq: float
    weight_recency: float
    weight_rhythm: float
    weight_pair: float
    weight_triple: float
    hot_pool_main: int
    hot_pool_euro: int
    generation_attempts: int
    seed: int
    rule_force_even_odd: bool
    rule_force_spread: bool


# ============================================================
# POMOCNICZE I OPTYMALIZACJE
# ============================================================

def safe_percent(part: int, whole: int) -> float:
    if whole == 0:
        return 0.0
    return (part / whole) * 100.0


def format_num(n: int) -> str:
    return f"{n:02d}"


def format_number_list(nums: List[int]) -> str:
    return " ".join(format_num(n) for n in sorted(nums))


def calculate_zscores(values_dict: Dict[int, float]) -> Dict[int, float]:
    if not values_dict:
        return {}
    
    vals = list(values_dict.values())
    mean = sum(vals) / len(vals)
    variance = sum((x - mean) ** 2 for x in vals) / len(vals)
    std = math.sqrt(variance)
    
    if std == 0:
        return {k: 0.0 for k in values_dict}
        
    return {k: (v - mean) / std for k, v in values_dict.items()}


def count_even(nums: List[int]) -> int:
    return sum(1 for x in nums if x % 2 == 0)


def max_consecutive_run(nums: List[int]) -> int:
    if not nums:
        return 0
    nums = sorted(nums)
    run = 1
    best = 1
    for i in range(1, len(nums)):
        if nums[i] == nums[i - 1] + 1:
            run += 1
            best = max(best, run)
        else:
            run = 1
    return best


def normalize_weights(scores: Dict[int, float]) -> Dict[int, float]:
    if not scores:
        return {}
    min_score = min(scores.values())
    return {k: (v - min_score + 0.1) for k, v in scores.items()}


def make_bytesio_from_upload(uploaded_file) -> io.BytesIO:
    if uploaded_file is None:
        raise ValueError("Brak pliku.")
    return io.BytesIO(uploaded_file.read())


# ============================================================
# INTELIGENTNY PARSER PDF (KULOODPORNY)
# ============================================================

def open_pdf_document(pdf_source):
    if isinstance(pdf_source, str):
        if not os.path.exists(pdf_source):
            raise FileNotFoundError(f"Nie znaleziono pliku: {pdf_source}")
        return fitz.open(pdf_source)
    if isinstance(pdf_source, bytes):
        return fitz.open(stream=pdf_source, filetype="pdf")
    if isinstance(pdf_source, io.BytesIO):
        return fitz.open(stream=pdf_source.getvalue(), filetype="pdf")
    raise TypeError("Nieobsługiwany typ źródła PDF.")


def parse_pdf_multipasko(pdf_source, is_main: bool, max_draws: int = 999) -> Tuple[Dict[int, List[int]], Dict]:
    doc = open_pdf_document(pdf_source)
    all_tokens = []
    
    for page in doc:
        words = page.get_text("words")
        
        # Szykujemy współrzędne: środek Y, X, i sam tekst
        words_with_coords = []
        for w in words:
            mid_y = (w[1] + w[3]) / 2
            words_with_coords.append((mid_y, w[0], w[4]))
        
        # Grupujemy z odstępem Y ~8 pikseli (eliminuje problem lekkich przesunięć)
        words_with_coords.sort(key=lambda x: x[0])
        
        lines = []
        current_line = []
        current_y = -100
        
        for mid_y, x0, text in words_with_coords:
            if abs(mid_y - current_y) > 8:
                if current_line:
                    current_line.sort(key=lambda item: item[0])
                    lines.append(current_line)
                current_line = [(x0, text)]
                current_y = mid_y
            else:
                current_line.append((x0, text))
                
        if current_line:
            current_line.sort(key=lambda item: item[0])
            lines.append(current_line)
            
        # Niezawodne wyciąganie WSZYSTKICH liczb bez względu na to jak skleił je PDF
        for line in lines:
            for x0, text in line:
                for token in re.findall(r'\d+', text):
                    all_tokens.append(token)
                    
    doc.close()
    
    req_count = 5 if is_main else 2
    max_val = MAIN_MAX if is_main else EURO_MAX
    file_label = "5/50" if is_main else "2/12"
    
    draws = {}
    current_id = None
    current_nums = []
    
    for token in all_tokens:
        val = int(token)
        
        # Identyfikujemy ID losowania (zabezpieczone przed wczytywaniem lat z footera np. 2026)
        is_id = False
        if len(token) == 4 and val <= 1500:
            is_id = True
        elif 50 < val <= 1500:
            is_id = True
            
        if is_id:
            # Zapisujemy tylko pierwsze req_count liczb, odcinając śmieci z końca linijki
            if current_id is not None and len(current_nums) >= req_count:
                draws[current_id] = sorted(current_nums[:req_count])
                
            current_id = val
            current_nums = []
            
        elif current_id is not None:
            if 1 <= val <= max_val:
                if val not in current_nums:
                    current_nums.append(val)
                    
    # Zapisz losowanie z końca pliku
    if current_id is not None and len(current_nums) >= req_count:
        draws[current_id] = sorted(current_nums[:req_count])

    # Zwracamy posortowane od najwyższego do najniższego, ucicnając do max_draws
    sorted_draws = {}
    for did in sorted(draws.keys(), reverse=True)[:max_draws]:
        sorted_draws[did] = draws[did]

    diagnostics = {
        "file_type": file_label,
        "parsed_tokens": len(all_tokens),
        "draws_found": len(sorted_draws),
    }

    if not sorted_draws:
        raise ValueError(f"Nie udało się zbudować mapy losowań dla {file_label}.")

    return sorted_draws, diagnostics


def load_draws(main_pdf_source, euro_pdf_source, max_draws: int = 999):
    main_map, main_diag = parse_pdf_multipasko(main_pdf_source, is_main=True, max_draws=max_draws)
    euro_map, euro_diag = parse_pdf_multipasko(euro_pdf_source, is_main=False, max_draws=max_draws)

    common_ids = sorted(set(main_map.keys()) & set(euro_map.keys()), reverse=True)

    if not common_ids:
        raise ValueError("Brak wspólnych numerów losowań między plikami.")

    draws = []
    for draw_id in common_ids[:max_draws]:
        draws.append(
            Draw(
                draw_id=draw_id,
                main_numbers=main_map[draw_id],
                euro_numbers=euro_map[draw_id],
            )
        )

    diagnostics = {
        "main": main_diag,
        "euro": euro_diag,
        "common_ids_count": len(common_ids)
    }

    return draws, diagnostics


# ============================================================
# ANALIZATOR Z RYTMIKĄ
# ============================================================

class EuroJackpotAnalyzer:
    def __init__(self, draws: List[Draw], config: AnalyzerConfig):
        self.draws = sorted(draws, key=lambda d: d.draw_id, reverse=True)
        self.total_draws = len(self.draws)
        self.config = config
        self.random = random.Random(config.seed)

        self.main_counter = Counter()
        self.euro_counter = Counter()
        self.main_pair_counter = Counter()
        self.main_triple_counter = Counter()
        self.euro_pair_counter = Counter()

        self._analyze()
        
        self.main_intervals = self._analyze_intervals(MAIN_MIN, MAIN_MAX, is_main=True)
        self.euro_intervals = self._analyze_intervals(EURO_MIN, EURO_MAX, is_main=False)

    def _analyze(self):
        for idx, draw in enumerate(self.draws):
            main = sorted(draw.main_numbers)
            euro = sorted(draw.euro_numbers)

            self.main_counter.update(main)
            self.euro_counter.update(euro)

            for pair in itertools.combinations(main, 2):
                self.main_pair_counter[pair] += 1
            for triple in itertools.combinations(main, 3):
                self.main_triple_counter[triple] += 1
            for pair in itertools.combinations(euro, 2):
                self.euro_pair_counter[pair] += 1

    def _analyze_intervals(self, min_val: int, max_val: int, is_main: bool) -> Dict[int, Dict]:
        chronological_draws = list(reversed(self.draws))
        
        intervals_data = {n: {'gaps': [], 'most_common_gap': 0, 'current_gap': 0} 
                          for n in range(min_val, max_val + 1)}
        
        last_seen_index = {n: -1 for n in range(min_val, max_val + 1)}

        for idx, draw in enumerate(chronological_draws):
            nums = draw.main_numbers if is_main else draw.euro_numbers
            for number in nums:
                if last_seen_index[number] != -1:
                    gap = idx - last_seen_index[number]
                    intervals_data[number]['gaps'].append(gap)
                
                last_seen_index[number] = idx

        total_draws = len(chronological_draws)
        for n in range(min_val, max_val + 1):
            if last_seen_index[n] != -1:
                intervals_data[n]['current_gap'] = total_draws - 1 - last_seen_index[n]
            else:
                intervals_data[n]['current_gap'] = total_draws

            if intervals_data[n]['gaps']:
                gap_counts = Counter(intervals_data[n]['gaps'])
                most_common = gap_counts.most_common(1)[0][0]
                intervals_data[n]['most_common_gap'] = most_common

        return intervals_data
    
    def compute_main_scores(self) -> Dict[int, float]:
        freq_dict = {n: self.main_counter[n] for n in range(MAIN_MIN, MAIN_MAX + 1)}
        
        pair_by_number = defaultdict(int)
        for (a, b), cnt in self.main_pair_counter.items():
            pair_by_number[a] += cnt
            pair_by_number[b] += cnt

        triple_by_number = defaultdict(int)
        for triple, cnt in self.main_triple_counter.items():
            for n in triple:
                triple_by_number[n] += cnt

        freq_z = calculate_zscores(freq_dict)
        pair_z = calculate_zscores(pair_by_number)
        triple_z = calculate_zscores(triple_by_number)

        scores = {}
        for n in range(MAIN_MIN, MAIN_MAX + 1):
            rhythm_bonus = 0.0
            most_common = self.main_intervals[n]['most_common_gap']
            current = self.main_intervals[n]['current_gap']
            
            if most_common > 0:
                if current == most_common:
                    rhythm_bonus = 3.0  
                elif abs(current - most_common) == 1:
                    rhythm_bonus = 1.0  

            total_score = (
                self.config.weight_freq * freq_z.get(n, 0) +
                self.config.weight_pair * pair_z.get(n, 0) +
                self.config.weight_triple * triple_z.get(n, 0) +
                self.config.weight_rhythm * rhythm_bonus
            )
            scores[n] = total_score

        return scores

    def compute_euro_scores(self) -> Dict[int, float]:
        freq_dict = {n: self.euro_counter[n] for n in range(EURO_MIN, EURO_MAX + 1)}
        
        pair_by_number = defaultdict(int)
        for (a, b), cnt in self.euro_pair_counter.items():
            pair_by_number[a] += cnt
            pair_by_number[b] += cnt

        freq_z = calculate_zscores(freq_dict)
        pair_z = calculate_zscores(pair_by_number)

        scores = {}
        for n in range(EURO_MIN, EURO_MAX + 1):
            rhythm_bonus = 0.0
            most_common = self.euro_intervals[n]['most_common_gap']
            current = self.euro_intervals[n]['current_gap']
            
            if most_common > 0:
                if current == most_common:
                    rhythm_bonus = 3.0
                elif abs(current - most_common) == 1:
                    rhythm_bonus = 1.0

            total_score = (
                0.50 * freq_z.get(n, 0) +
                0.20 * pair_z.get(n, 0) +
                0.30 * rhythm_bonus
            )
            scores[n] = total_score

        return scores

    def validate_main_ticket(self, nums: List[int]) -> bool:
        nums = sorted(nums)

        if len(nums) != 5 or len(set(nums)) != 5:
            return False

        if self.config.rule_force_even_odd:
            evens = count_even(nums)
            if evens not in (2, 3):
                return False

        if max_consecutive_run(nums) > 2:
            return False

        if self.config.rule_force_spread:
            spread = nums[-1] - nums[0]
            if spread < 18:
                return False

        return True

    def validate_euro_ticket(self, nums: List[int]) -> bool:
        if len(nums) != 2 or len(set(nums)) != 2:
            return False
        return True

    def weighted_sample_without_replacement(self, candidates: List[int], weights: Dict[int, float], k: int) -> List[int]:
        pool = list(candidates)
        selected = []
        for _ in range(k):
            if not pool:
                break
            raw_weights = [max(0.0001, weights.get(n, 0.0001)) for n in pool]
            chosen = self.random.choices(pool, weights=raw_weights, k=1)[0]
            selected.append(chosen)
            pool.remove(chosen)
        return sorted(selected)

    def generate_ticket(self) -> Tuple[List[int], List[int]]:
        main_scores = self.compute_main_scores()
        euro_scores = self.compute_euro_scores()

        main_weights = normalize_weights(main_scores)
        euro_weights = normalize_weights(euro_scores)

        main_ranked = sorted(main_scores.items(), key=lambda x: x[1], reverse=True)
        euro_ranked = sorted(euro_scores.items(), key=lambda x: x[1], reverse=True)

        main_candidates = [n for n, _ in main_ranked[:self.config.hot_pool_main]]
        euro_candidates = [n for n, _ in euro_ranked[:self.config.hot_pool_euro]]

        best_main = None
        for _ in range(self.config.generation_attempts):
            ticket = self.weighted_sample_without_replacement(main_candidates, main_weights, 5)
            if self.validate_main_ticket(ticket):
                best_main = ticket
                break

        if best_main is None:
            best_main = sorted(self.random.sample(main_candidates, 5))

        best_euro = None
        for _ in range(self.config.generation_attempts):
            ticket = self.weighted_sample_without_replacement(euro_candidates, euro_weights, 2)
            if self.validate_euro_ticket(ticket):
                best_euro = ticket
                break
                
        if best_euro is None:
            best_euro = sorted(self.random.sample(euro_candidates, 2))

        return best_main, best_euro

    def generate_multiple_tickets(self, count: int = 5) -> List[Tuple[List[int], List[int]]]:
        seen = set()
        results = []
        attempts = 0
        max_attempts = max(200, count * 60)

        while len(results) < count and attempts < max_attempts:
            attempts += 1
            main_nums, euro_nums = self.generate_ticket()
            key = (tuple(main_nums), tuple(euro_nums))
            if key not in seen:
                seen.add(key)
                results.append((main_nums, euro_nums))

        return results

    def get_rhythm_table(self, is_main: bool) -> List[Dict]:
        min_v, max_v = (MAIN_MIN, MAIN_MAX) if is_main else (EURO_MIN, EURO_MAX)
        intervals = self.main_intervals if is_main else self.euro_intervals
        counter = self.main_counter if is_main else self.euro_counter
        
        rows = []
        for n in range(min_v, max_v + 1):
            rows.append({
                "Liczba": format_num(n),
                "Trafienia (Łącznie)": counter[n],
                "Ulubiony Rytm (Odstęp)": intervals[n]['most_common_gap'],
                "Aktualny Odstęp": intervals[n]['current_gap'],
                "W Rytmie?": "✅ TAK" if intervals[n]['current_gap'] == intervals[n]['most_common_gap'] else "❌ NIE",
            })
        
        rows.sort(key=lambda x: (
            abs(x["Aktualny Odstęp"] - x["Ulubiony Rytm (Odstęp)"]), 
            -x["Trafienia (Łącznie)"]
        ))
        return rows


# ============================================================
# UI (STREAMLIT)
# ============================================================

def render_sidebar():
    st.sidebar.header("Ustawienia analizy")

    max_draws = st.sidebar.number_input("Maksymalna liczba losowań", 10, 9999, MAX_DRAWS_DEFAULT, 1)
    tickets_count = st.sidebar.number_input("Ile kuponów wygenerować", 1, 20, DEFAULT_TICKETS_COUNT, 1)

    st.sidebar.subheader("Zasady Kuponu")
    rule_even_odd = st.sidebar.checkbox("Wymuś balans 2/3 (Parzyste/Nieparzyste)", value=True)
    rule_spread = st.sidebar.checkbox("Wymuś rozstrzał (min. 18 różnicy)", value=True)

    st.sidebar.subheader("Wagi algorytmu (Z-Score)")
    weight_freq = st.sidebar.slider("Waga częstotliwości", 0.0, 1.0, DEFAULT_WEIGHT_FREQ, 0.05)
    weight_rhythm = st.sidebar.slider("Waga Rytmiki (Wzorce odstępów)", 0.0, 1.0, DEFAULT_WEIGHT_RHYTHM, 0.05)
    weight_pair = st.sidebar.slider("Waga par", 0.0, 1.0, DEFAULT_WEIGHT_PAIR, 0.05)
    weight_triple = st.sidebar.slider("Waga trójek", 0.0, 1.0, DEFAULT_WEIGHT_TRIPLE, 0.05)

    config = AnalyzerConfig(
        weight_freq=weight_freq,
        weight_recency=0.0, 
        weight_rhythm=weight_rhythm,
        weight_pair=weight_pair,
        weight_triple=weight_triple,
        hot_pool_main=DEFAULT_HOT_POOL_MAIN,
        hot_pool_euro=DEFAULT_HOT_POOL_EURO,
        generation_attempts=DEFAULT_GENERATION_ATTEMPTS,
        seed=DEFAULT_RANDOM_SEED,
        rule_force_even_odd=rule_even_odd,
        rule_force_spread=rule_spread
    )
    return int(max_draws), int(tickets_count), config


def render_file_inputs():
    st.subheader("Pliki wejściowe (PDF z Multipasko)")
    col1, col2 = st.columns(2)
    with col1:
        main_uploaded = st.file_uploader("Wgraj plik 5/50 (wyniki1ej.pdf)", type=["pdf"])
    with col2:
        euro_uploaded = st.file_uploader("Wgraj plik 2/12 (wyniki2ej.pdf)", type=["pdf"])
        
    use_local_files = st.checkbox("Użyj plików z dysku jeśli nie wgrano", value=True)
    return main_uploaded, euro_uploaded, use_local_files


def resolve_pdf_source(uploaded_file, default_path: str):
    if uploaded_file is not None:
        return make_bytesio_from_upload(uploaded_file)
    if os.path.exists(default_path):
        return default_path
    return None


def render_generated_tickets(analyzer: EuroJackpotAnalyzer, tickets_count: int):
    st.subheader("Wygenerowane kupony (Baza: Rytmika + Częstotliwość)")
    best_main, best_euro = analyzer.generate_ticket()
    st.success(f"🔥 Najmocniejsza propozycja algorytmu: **{format_number_list(best_main)} + {format_number_list(best_euro)}**")

    tickets = analyzer.generate_multiple_tickets(tickets_count)
    rows = [{"Kupon": idx, "Liczby główne 5/50": format_number_list(m), "Liczby Euro 2/12": format_number_list(e)} 
            for idx, (m, e) in enumerate(tickets, start=1)]
    st.dataframe(rows, use_container_width=True)


def render_rhythms(analyzer: EuroJackpotAnalyzer):
    st.subheader("Analiza Rytmiki (Odstępy między losowaniami)")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### Rytmy 5/50")
        st.dataframe(analyzer.get_rhythm_table(is_main=True), use_container_width=True, height=500)
    with col2:
        st.markdown("### Rytmy 2/12")
        st.dataframe(analyzer.get_rhythm_table(is_main=False), use_container_width=True, height=500)


def main():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)

    max_draws, tickets_count, analyzer_config = render_sidebar()
    main_uploaded, euro_uploaded, use_local_files = render_file_inputs()

    main_source = resolve_pdf_source(main_uploaded, DEFAULT_MAIN_PDF) if main_uploaded or use_local_files else None
    euro_source = resolve_pdf_source(euro_uploaded, DEFAULT_EURO_PDF) if euro_uploaded or use_local_files else None

    if main_source is None or euro_source is None:
        st.warning("Wgraj oba pliki PDF (Multipasko).")
        st.stop()

    if not st.button("Analizuj pliki i wygeneruj kupony", type="primary"):
        st.stop()

    try:
        with st.spinner("Skanowanie pikseli i odzyskiwanie tabeli z PDF..."):
            draws, diagnostics = load_draws(main_source, euro_source, max_draws)
            analyzer = EuroJackpotAnalyzer(draws, analyzer_config)

        col1, col2, col3 = st.columns(3)
        col1.metric("Wczytane losowania", analyzer.total_draws)
        if analyzer.draws:
            col2.metric("Najnowsze ID", analyzer.draws[0].draw_id)
            col3.metric("Najstarsze ID", analyzer.draws[-1].draw_id)

        render_generated_tickets(analyzer, tickets_count)
        render_rhythms(analyzer)

    except Exception as e:
        st.error(f"Wystąpił błąd podczas analizy: {e}")
        raise


if __name__ == "__main__":
    main()
