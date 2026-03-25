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
APP_SUBTITLE = "Analiza PDF + Rytmika + Inteligentne Cykle Historyczne"

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
# INTELIGENTNY PARSER PDF
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
        words_with_coords = []
        for w in words:
            mid_y = (w[1] + w[3]) / 2
            words_with_coords.append((mid_y, w[0], w[4]))
        
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
        is_id = False
        if len(token) == 4 and val <= 1500:
            is_id = True
        elif 50 < val <= 1500:
            is_id = True
            
        if is_id:
            if current_id is not None and len(current_nums) >= req_count:
                draws[current_id] = sorted(current_nums[:req_count])
            current_id = val
            current_nums = []
        elif current_id is not None:
            if 1 <= val <= max_val:
                if val not in current_nums:
                    current_nums.append(val)
                    
    if current_id is not None and len(current_nums) >= req_count:
        draws[current_id] = sorted(current_nums[:req_count])

    sorted_draws = {}
    for did in sorted(draws.keys(), reverse=True)[:max_draws]:
        sorted_draws[did] = draws[did]

    diagnostics = {"file_type": file_label, "parsed_tokens": len(all_tokens), "draws_found": len(sorted_draws)}
    if not sorted_draws:
        raise ValueError(f"Nie udało się zbudować mapy losowań dla {file_label}.")

    return sorted_draws, diagnostics


def load_draws(main_pdf_source, euro_pdf_source, max_draws: int = 999):
    main_map, main_diag = parse_pdf_multipasko(main_pdf_source, is_main=True, max_draws=max_draws)
    euro_map, euro_diag = parse_pdf_multipasko(euro_pdf_source, is_main=False, max_draws=max_draws)

    common_ids = sorted(set(main_map.keys()) & set(euro_map.keys()), reverse=True)
    if not common_ids:
        raise ValueError("Brak wspólnych numerów losowań między plikami.")

    draws = [Draw(draw_id=did, main_numbers=main_map[did], euro_numbers=euro_map[did]) for did in common_ids[:max_draws]]
    diagnostics = {"main": main_diag, "euro": euro_diag, "common_ids_count": len(common_ids)}
    return draws, diagnostics


# ============================================================
# ANALIZATOR
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
        self.main_quad_counter = Counter() # Nowość! Szukamy czwórek!
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
            for quad in itertools.combinations(main, 4):
                self.main_quad_counter[quad] += 1
                
            for pair in itertools.combinations(euro, 2):
                self.euro_pair_counter[pair] += 1

    def _analyze_intervals(self, min_val: int, max_val: int, is_main: bool) -> Dict[int, Dict]:
        chronological_draws = list(reversed(self.draws))
        intervals_data = {n: {'gaps': [], 'most_common_gap': 0, 'current_gap': 0} for n in range(min_val, max_val + 1)}
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
                if current == most_common: rhythm_bonus = 3.0  
                elif abs(current - most_common) == 1: rhythm_bonus = 1.0  

            scores[n] = (self.config.weight_freq * freq_z.get(n, 0) + self.config.weight_pair * pair_z.get(n, 0) +
                         self.config.weight_triple * triple_z.get(n, 0) + self.config.weight_rhythm * rhythm_bonus)
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
                if current == most_common: rhythm_bonus = 3.0
                elif abs(current - most_common) == 1: rhythm_bonus = 1.0

            scores[n] = (0.50 * freq_z.get(n, 0) + 0.20 * pair_z.get(n, 0) + 0.30 * rhythm_bonus)
        return scores

    def validate_main_ticket(self, nums: List[int]) -> bool:
        nums = sorted(nums)
        if len(nums) != 5 or len(set(nums)) != 5: return False
        if self.config.rule_force_even_odd:
            evens = count_even(nums)
            if evens not in (2, 3): return False
        if max_consecutive_run(nums) > 2: return False
        if self.config.rule_force_spread:
            spread = nums[-1] - nums[0]
            if spread < 18: return False
        return True

    # --------------------------------------------------------
    # NOWY INTELIGENTNY GENERATOR OPARTY O HISTORYCZNE PACZKI
    # --------------------------------------------------------

    def generate_smart_tickets(self, count: int = 5) -> List[Dict]:
        """
        Tworzy kupony budując je dookoła historycznych paczek (cykli), 
        które już kiedyś wypadły razem. Następnie uzupełnia je o pewniaki.
        """
        results = []
        main_scores = self.compute_main_scores()
        euro_scores = self.compute_euro_scores()

        # Wyciągamy najlepiej punktujące liczby (jako wypełniacze do reszty kuponu)
        main_ranked = [n for n, score in sorted(main_scores.items(), key=lambda x: x[1], reverse=True)]
        euro_ranked = [n for n, score in sorted(euro_scores.items(), key=lambda x: x[1], reverse=True)]

        # Wyciągamy powtarzające się wzorce historyczne
        top_quads = [q for q, c in self.main_quad_counter.most_common(5) if c > 1]
        top_triples = [t for t, c in self.main_triple_counter.most_common(20) if c > 1]
        top_pairs = [p for p, c in self.main_pair_counter.most_common(30) if c > 1]
        
        top_euro_pairs = [p for p, c in self.euro_pair_counter.most_common(10) if c > 1]

        # Komponujemy bazę historyczną do zasilenia kuponów
        historical_bases = []
        for q in top_quads: historical_bases.append((list(q), f"Złota Czwórka (padła {self.main_quad_counter[q]}x)"))
        for t in top_triples: historical_bases.append((list(t), f"Częsta Trójka (padła {self.main_triple_counter[t]}x)"))
        for p in top_pairs: historical_bases.append((list(p), f"Częsta Para (padła {self.main_pair_counter[p]}x)"))

        seen_main = set()
        
        for i in range(count):
            base_main = []
            desc = "Pewniaki (Z-Score + Rytm)"

            # Bierzemy rdzeń z historii, upewniając się, że nie dublujemy tych samych rdzeni
            if i < len(historical_bases):
                base_main = historical_bases[i][0]
                desc = historical_bases[i][1]

            current_main = set(base_main)
            
            # Uzupełniamy resztę najlepszymi dostępnymi liczbami
            for n in main_ranked:
                if len(current_main) == 5:
                    break
                current_main.add(n)

            # Próba "zwalidowania" i przetasowania, by kupon miał sens
            ticket_main = sorted(list(current_main))
            attempts = 0
            while not self.validate_main_ticket(ticket_main) and attempts < 100:
                attempts += 1
                current_main = set(base_main)
                fillers = self.random.sample(main_ranked[:25], 5 - len(base_main))
                for f in fillers: current_main.add(f)
                if len(current_main) == 5:
                    ticket_main = sorted(list(current_main))
            
            seen_main.add(tuple(ticket_main))

            # Euro
            if i < len(top_euro_pairs):
                ticket_euro = list(top_euro_pairs[i])
            else:
                ticket_euro = sorted(self.random.sample(euro_ranked[:6], 2))

            results.append({
                "Kupon": i + 1,
                "Liczby główne 5/50": format_number_list(ticket_main),
                "Liczby Euro 2/12": format_number_list(ticket_euro),
                "Geneza (Skąd te liczby?)": desc
            })

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
                "Częstotliwość %": round(safe_percent(counter[n], self.total_draws), 2),
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
    tickets_count = st.sidebar.number_input("Ile różnorodnych kuponów wygenerować?", 1, 20, DEFAULT_TICKETS_COUNT, 1)

    st.sidebar.subheader("Zasady Kuponu")
    rule_even_odd = st.sidebar.checkbox("Wymuś balans 2/3 (Parzyste/Nieparzyste)", value=True)
    rule_spread = st.sidebar.checkbox("Wymuś rozstrzał (min. 18 różnicy)", value=True)

    config = AnalyzerConfig(
        weight_freq=DEFAULT_WEIGHT_FREQ,
        weight_recency=0.0, 
        weight_rhythm=DEFAULT_WEIGHT_RHYTHM,
        weight_pair=DEFAULT_WEIGHT_PAIR,
        weight_triple=DEFAULT_WEIGHT_TRIPLE,
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
    st.subheader("Wielowariantowe Kupony (Na bazie historycznych powtórzeń)")
    st.info("Aplikacja szuka 'paczek' (2, 3 lub 4 cyfr), które lubią padać razem. Zamraża je jako bazę kuponu, a resztę luk uzupełnia cyframi z najlepszym wynikiem rytmiczno-częstotliwościowym!")

    tickets_data = analyzer.generate_smart_tickets(tickets_count)
    st.dataframe(tickets_data, use_container_width=True)

    # Przygotowanie pliku TXT do pobrania
    txt_content = "=== TWOJE KUPONY EUROJACKPOT (Wygenerowane przez AI na bazie cykli) ===\n\n"
    for row in tickets_data:
        txt_content += f"Kupon {row['Kupon']}:\n"
        txt_content += f"5/50: {row['Liczby główne 5/50']}\n"
        txt_content += f"2/12: {row['Liczby Euro 2/12']}\n"
        txt_content += f"Powód: {row['Geneza (Skąd te liczby?)']}\n\n"

    st.download_button(
        label="📥 Pobierz listę kuponów (.txt)",
        data=txt_content,
        file_name="kupony_eurojackpot_wzorce.txt",
        mime="text/plain",
        type="primary"
    )


def render_rhythms(analyzer: EuroJackpotAnalyzer):
    st.subheader("Analiza Rytmiki i Procentowa Częstotliwość")
    col1, col2 = st.columns(2)
    with col1:
        st.markdown("### 5/50")
        st.dataframe(analyzer.get_rhythm_table(is_main=True), use_container_width=True, height=500)
    with col2:
        st.markdown("### 2/12")
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
        with st.spinner("Przeszukiwanie bazy pod kątem powtarzających się cykli..."):
            draws, diagnostics = load_draws(main_source, euro_source, max_draws)
            analyzer = EuroJackpotAnalyzer(draws, analyzer_config)

        col1, col2, col3 = st.columns(3)
        col1.metric("Przeanalizowane losowania", analyzer.total_draws)
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
