import io
import os
import re
import math
import random
import itertools
from dataclasses import dataclass
from collections import Counter, defaultdict
from typing import List, Dict, Tuple, Optional

import fitz  # PyMuPDF
import streamlit as st


# ============================================================
# KONFIGURACJA GŁÓWNA
# ============================================================

APP_TITLE = "EuroJackpot PRO Analyzer"
APP_SUBTITLE = "Analiza PDF + częstotliwości + wzorce + generator kuponów"

DEFAULT_MAIN_PDF = "wyniki1ej.pdf"   # 5 z 50
DEFAULT_EURO_PDF = "wyniki2ej.pdf"   # 2 z 12

MAX_DRAWS_DEFAULT = 999
RANDOM_SEED_DEFAULT = 42

MAIN_MIN = 1
MAIN_MAX = 50

EURO_MIN = 1
EURO_MAX = 12

# Domyślne wagi generatora
DEFAULT_WEIGHT_FREQ = 0.35
DEFAULT_WEIGHT_RECENCY = 0.20
DEFAULT_WEIGHT_OVERDUE = 0.15
DEFAULT_WEIGHT_PAIR = 0.15
DEFAULT_WEIGHT_TRIPLE = 0.10
DEFAULT_WEIGHT_PATTERN = 0.05

DEFAULT_HOT_POOL_MAIN = 20
DEFAULT_HOT_POOL_EURO = 6
DEFAULT_GENERATION_ATTEMPTS = 5000

# Zakresy okien czasowych
RECENCY_WINDOWS_MAIN = (20, 50, 100, 200)
RECENCY_WINDOWS_EURO = (20, 50, 100, 200)


# ============================================================
# MODELE DANYCH
# ============================================================

@dataclass
class Draw:
    draw_id: int
    main_numbers: List[int]
    euro_numbers: List[int]


@dataclass
class AnalyzerConfig:
    weight_freq: float = DEFAULT_WEIGHT_FREQ
    weight_recency: float = DEFAULT_WEIGHT_RECENCY
    weight_overdue: float = DEFAULT_WEIGHT_OVERDUE
    weight_pair: float = DEFAULT_WEIGHT_PAIR
    weight_triple: float = DEFAULT_WEIGHT_TRIPLE
    weight_pattern: float = DEFAULT_WEIGHT_PATTERN
    hot_pool_main: int = DEFAULT_HOT_POOL_MAIN
    hot_pool_euro: int = DEFAULT_HOT_POOL_EURO
    generation_attempts: int = DEFAULT_GENERATION_ATTEMPTS
    seed: int = RANDOM_SEED_DEFAULT


# ============================================================
# POMOCNICZE
# ============================================================

def safe_percent(part: int, whole: int) -> float:
    if whole == 0:
        return 0.0
    return (part / whole) * 100.0


def sorted_tuple(nums: List[int]) -> Tuple[int, ...]:
    return tuple(sorted(nums))


def format_num(n: int) -> str:
    return f"{n:02d}"


def format_number_list(nums: List[int]) -> str:
    return " ".join(format_num(n) for n in sorted(nums))


def zscore(value: float, values: List[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (value - mean) / std


def normalize_weights(scores: Dict[int, float]) -> Dict[int, float]:
    if not scores:
        return {}
    min_score = min(scores.values())
    shifted = {k: (v - min_score + 0.1) for k, v in scores.items()}
    return shifted


def unique_sorted(nums: List[int]) -> bool:
    return nums == sorted(nums) and len(nums) == len(set(nums))


def count_even(nums: List[int]) -> int:
    return sum(1 for x in nums if x % 2 == 0)


def count_low_main(nums: List[int]) -> int:
    return sum(1 for x in nums if x <= 25)


def count_low_euro(nums: List[int]) -> int:
    return sum(1 for x in nums if x <= 6)


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


def ensure_bytesio(uploaded_file) -> io.BytesIO:
    if uploaded_file is None:
        raise ValueError("Brak pliku wejściowego.")
    data = uploaded_file.read()
    return io.BytesIO(data)


# ============================================================
# ODCZYT PDF
# ============================================================

def open_pdf_document(pdf_source):
    """
    Obsługuje:
    - ścieżkę do pliku
    - bytes
    - BytesIO
    """
    if isinstance(pdf_source, str):
        if not os.path.exists(pdf_source):
            raise FileNotFoundError(f"Nie znaleziono pliku: {pdf_source}")
        return fitz.open(pdf_source)

    if isinstance(pdf_source, bytes):
        return fitz.open(stream=pdf_source, filetype="pdf")

    if isinstance(pdf_source, io.BytesIO):
        return fitz.open(stream=pdf_source.getvalue(), filetype="pdf")

    raise TypeError("Nieobsługiwany typ źródła PDF.")


def extract_pages_text(pdf_source) -> List[str]:
    doc = open_pdf_document(pdf_source)
    pages = []
    for page in doc:
        pages.append(page.get_text("text"))
    doc.close()
    return pages


def extract_pages_words(pdf_source) -> List[List[str]]:
    """
    Zwraca listę stron, a dla każdej strony listę tokenów/słów
    pobranych przez get_text('words'), posortowanych wg pozycji.
    """
    doc = open_pdf_document(pdf_source)
    pages_tokens = []

    for page in doc:
        words = page.get_text("words")
        # words: (x0, y0, x1, y1, "text", block_no, line_no, word_no)
        words_sorted = sorted(words, key=lambda w: (round(w[1], 1), w[0]))
        tokens = [str(w[4]).strip() for w in words_sorted if str(w[4]).strip()]
        pages_tokens.append(tokens)

    doc.close()
    return pages_tokens


# ============================================================
# PARSER POMOCNICZY
# ============================================================

DRAW_ID_RE = re.compile(r"^\d{4}$")
TWO_DIGIT_RE = re.compile(r"^\d{2}$")


def is_draw_id_token(token: str) -> bool:
    if not DRAW_ID_RE.match(token):
        return False
    value = int(token)
    # dodatkowy filtr bezpieczeństwa
    return 1 <= value <= 9999


def is_main_number_token(token: str) -> bool:
    if not TWO_DIGIT_RE.match(token):
        return False
    value = int(token)
    return MAIN_MIN <= value <= MAIN_MAX


def is_euro_number_token(token: str) -> bool:
    if not TWO_DIGIT_RE.match(token):
        return False
    value = int(token)
    return EURO_MIN <= value <= EURO_MAX


def group_draw_ids_per_page(page_tokens: List[str]) -> List[int]:
    """
    Wyciąga ID losowań z danej strony.
    W PDF z tabelą zwykle występują jako osobne 4-cyfrowe tokeny.
    """
    draw_ids = []
    for token in page_tokens:
        if is_draw_id_token(token):
            draw_ids.append(int(token))
    return draw_ids


def extract_candidate_number_tokens(page_tokens: List[str], kind: str) -> List[int]:
    """
    kind:
    - 'main' => 1..50
    - 'euro' => 1..12
    """
    out = []
    for token in page_tokens:
        if kind == "main":
            if is_main_number_token(token):
                out.append(int(token))
        else:
            if is_euro_number_token(token):
                out.append(int(token))
    return out


def rows_from_sequence_strict(tokens: List[int], row_size: int) -> List[List[int]]:
    """
    Surowe składanie wierszy: bierzemy tylko ciągi:
    - rosnące
    - bez powtórzeń
    - o dokładnym rozmiarze row_size
    Przesuwamy okno elastycznie.
    """
    rows = []
    i = 0
    while i <= len(tokens) - row_size:
        chunk = tokens[i:i + row_size]
        if chunk == sorted(chunk) and len(set(chunk)) == row_size:
            rows.append(chunk)
            i += row_size
        else:
            i += 1
    return rows


def rows_from_text_lines(text: str, row_size: int, low: int, high: int) -> List[List[int]]:
    """
    Parser awaryjny po liniach tekstowych.
    """
    rows = []
    lines = [line.strip() for line in text.splitlines() if line.strip()]

    for line in lines:
        parts = re.findall(r"\b\d{2}\b", line)
        if len(parts) != row_size:
            continue

        nums = [int(x) for x in parts]
        if all(low <= x <= high for x in nums) and nums == sorted(nums) and len(set(nums)) == row_size:
            rows.append(nums)

    return rows


def parse_pdf_draw_map(pdf_source, kind: str, max_draws: int = 999, debug: bool = False) -> Tuple[Dict[int, List[int]], Dict]:
    """
    Parser ogólny dla:
    - kind='main' => 5/50
    - kind='euro' => 2/12

    Zwraca:
    - mapę draw_id -> numbers
    - diagnostykę
    """
    if kind not in ("main", "euro"):
        raise ValueError("kind musi być 'main' albo 'euro'")

    row_size = 5 if kind == "main" else 2
    low = MAIN_MIN if kind == "main" else EURO_MIN
    high = MAIN_MAX if kind == "main" else EURO_MAX

    pages_tokens = extract_pages_words(pdf_source)
    pages_text = extract_pages_text(pdf_source)

    all_draw_ids = []
    all_rows = []

    diagnostics = {
        "kind": kind,
        "pages": len(pages_tokens),
        "page_info": [],
        "total_draw_ids_found": 0,
        "total_rows_found_words": 0,
        "total_rows_found_text": 0,
    }

    for page_index, (page_tokens, page_text) in enumerate(zip(pages_tokens, pages_text), start=1):
        page_draw_ids = group_draw_ids_per_page(page_tokens)

        candidate_tokens = extract_candidate_number_tokens(page_tokens, kind=kind)
        rows_words = rows_from_sequence_strict(candidate_tokens, row_size=row_size)
        rows_text = rows_from_text_lines(page_text, row_size=row_size, low=low, high=high)

        # Łączymy wyniki z priorytetem dla words, bo zwykle lepiej czyta tabelę
        rows_page = rows_words if len(rows_words) >= len(rows_text) else rows_text

        diagnostics["page_info"].append({
            "page": page_index,
            "draw_ids_found": len(page_draw_ids),
            "candidate_tokens_count": len(candidate_tokens),
            "rows_from_words": len(rows_words),
            "rows_from_text": len(rows_text),
            "rows_selected": len(rows_page),
            "first_tokens_preview": page_tokens[:80],
            "first_text_preview": page_text[:1000],
        })

        diagnostics["total_draw_ids_found"] += len(page_draw_ids)
        diagnostics["total_rows_found_words"] += len(rows_words)
        diagnostics["total_rows_found_text"] += len(rows_text)

        all_draw_ids.extend(page_draw_ids)
        all_rows.extend(rows_page)

    if not all_draw_ids:
        raise ValueError(f"Nie znaleziono numerów losowań w pliku {kind}.")

    if not all_rows:
        raise ValueError(f"Nie znaleziono poprawnych układów {row_size} liczb w pliku {kind}.")

    usable = min(len(all_draw_ids), len(all_rows), max_draws)

    result = {}
    for i in range(usable):
        result[all_draw_ids[i]] = sorted(all_rows[i])

    if not result:
        raise ValueError(f"Nie udało się zbudować mapy losowań dla pliku {kind}.")

    diagnostics["usable"] = usable
    diagnostics["draw_ids_preview"] = all_draw_ids[:20]
    diagnostics["rows_preview"] = all_rows[:20]

    return result, diagnostics


def parse_main_pdf(pdf_source, max_draws: int = 999, debug: bool = False) -> Tuple[Dict[int, List[int]], Dict]:
    return parse_pdf_draw_map(pdf_source, kind="main", max_draws=max_draws, debug=debug)


def parse_euro_pdf(pdf_source, max_draws: int = 999, debug: bool = False) -> Tuple[Dict[int, List[int]], Dict]:
    return parse_pdf_draw_map(pdf_source, kind="euro", max_draws=max_draws, debug=debug)


def load_draws(main_pdf_source, euro_pdf_source, max_draws: int = 999, debug: bool = False):
    main_map, main_diag = parse_main_pdf(main_pdf_source, max_draws=max_draws, debug=debug)
    euro_map, euro_diag = parse_euro_pdf(euro_pdf_source, max_draws=max_draws, debug=debug)

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
        "common_ids_count": len(common_ids),
        "common_ids_preview": common_ids[:30],
    }

    return draws, diagnostics


# ============================================================
# ANALIZATOR
# ============================================================

class EuroJackpotAnalyzer:
    def __init__(self, draws: List[Draw], config: AnalyzerConfig):
        self.draws = sorted(draws, key=lambda d: d.draw_id, reverse=True)
        self.total_draws = len(self.draws)
        self.config = config

        self.main_counter = Counter()
        self.euro_counter = Counter()

        self.main_pair_counter = Counter()
        self.main_triple_counter = Counter()
        self.main_fullset_counter = Counter()

        self.euro_pair_counter = Counter()
        self.euro_fullset_counter = Counter()

        self.main_last_seen = {}
        self.euro_last_seen = {}

        self.main_even_odd_patterns = Counter()
        self.main_low_high_patterns = Counter()

        self.euro_even_odd_patterns = Counter()
        self.euro_low_high_patterns = Counter()

        self.main_positional_counter = [Counter() for _ in range(5)]
        self.euro_positional_counter = [Counter() for _ in range(2)]

        self.random = random.Random(self.config.seed)

        self._analyze()

    def _analyze(self):
        for idx, draw in enumerate(self.draws):
            main = sorted(draw.main_numbers)
            euro = sorted(draw.euro_numbers)

            self.main_counter.update(main)
            self.euro_counter.update(euro)

            self.main_fullset_counter[tuple(main)] += 1
            self.euro_fullset_counter[tuple(euro)] += 1

            for pair in itertools.combinations(main, 2):
                self.main_pair_counter[pair] += 1

            for triple in itertools.combinations(main, 3):
                self.main_triple_counter[triple] += 1

            for pair in itertools.combinations(euro, 2):
                self.euro_pair_counter[pair] += 1

            for n in main:
                if n not in self.main_last_seen:
                    self.main_last_seen[n] = idx

            for n in euro:
                if n not in self.euro_last_seen:
                    self.euro_last_seen[n] = idx

            even_main = count_even(main)
            odd_main = 5 - even_main
            self.main_even_odd_patterns[(even_main, odd_main)] += 1

            low_main = count_low_main(main)
            high_main = 5 - low_main
            self.main_low_high_patterns[(low_main, high_main)] += 1

            even_euro = count_even(euro)
            odd_euro = 2 - even_euro
            self.euro_even_odd_patterns[(even_euro, odd_euro)] += 1

            low_euro = count_low_euro(euro)
            high_euro = 2 - low_euro
            self.euro_low_high_patterns[(low_euro, high_euro)] += 1

            for pos, n in enumerate(main):
                self.main_positional_counter[pos][n] += 1

            for pos, n in enumerate(euro):
                self.euro_positional_counter[pos][n] += 1

        for n in range(MAIN_MIN, MAIN_MAX + 1):
            if n not in self.main_last_seen:
                self.main_last_seen[n] = self.total_draws

        for n in range(EURO_MIN, EURO_MAX + 1):
            if n not in self.euro_last_seen:
                self.euro_last_seen[n] = self.total_draws

    # --------------------------------------------------------
    # CZĘSTOTLIWOŚCI
    # --------------------------------------------------------

    def main_frequency_percent(self) -> Dict[int, float]:
        return {
            n: safe_percent(self.main_counter[n], self.total_draws)
            for n in range(MAIN_MIN, MAIN_MAX + 1)
        }

    def euro_frequency_percent(self) -> Dict[int, float]:
        return {
            n: safe_percent(self.euro_counter[n], self.total_draws)
            for n in range(EURO_MIN, EURO_MAX + 1)
        }

    def top_main_numbers(self, top_n: int = 15) -> List[Tuple[int, int, float]]:
        freq = self.main_frequency_percent()
        rows = [(n, self.main_counter[n], freq[n]) for n in range(MAIN_MIN, MAIN_MAX + 1)]
        rows.sort(key=lambda x: (-x[1], x[0]))
        return rows[:top_n]

    def cold_main_numbers(self, top_n: int = 10) -> List[Tuple[int, int, float]]:
        freq = self.main_frequency_percent()
        rows = [(n, self.main_counter[n], freq[n]) for n in range(MAIN_MIN, MAIN_MAX + 1)]
        rows.sort(key=lambda x: (x[1], x[0]))
        return rows[:top_n]

    def top_euro_numbers(self, top_n: int = 8) -> List[Tuple[int, int, float]]:
        freq = self.euro_frequency_percent()
        rows = [(n, self.euro_counter[n], freq[n]) for n in range(EURO_MIN, EURO_MAX + 1)]
        rows.sort(key=lambda x: (-x[1], x[0]))
        return rows[:top_n]

    def cold_euro_numbers(self, top_n: int = 4) -> List[Tuple[int, int, float]]:
        freq = self.euro_frequency_percent()
        rows = [(n, self.euro_counter[n], freq[n]) for n in range(EURO_MIN, EURO_MAX + 1)]
        rows.sort(key=lambda x: (x[1], x[0]))
        return rows[:top_n]

    # --------------------------------------------------------
    # UKŁADY
    # --------------------------------------------------------

    def top_main_pairs(self, top_n: int = 20) -> List[Tuple[Tuple[int, int], int]]:
        return self.main_pair_counter.most_common(top_n)

    def top_main_triples(self, top_n: int = 20) -> List[Tuple[Tuple[int, int, int], int]]:
        return self.main_triple_counter.most_common(top_n)

    def top_main_fullsets(self, top_n: int = 10) -> List[Tuple[Tuple[int, ...], int]]:
        repeated = [(k, v) for k, v in self.main_fullset_counter.items() if v > 1]
        repeated.sort(key=lambda x: (-x[1], x[0]))
        return repeated[:top_n]

    def top_euro_pairs(self, top_n: int = 15) -> List[Tuple[Tuple[int, int], int]]:
        return self.euro_pair_counter.most_common(top_n)

    def top_euro_fullsets(self, top_n: int = 10) -> List[Tuple[Tuple[int, ...], int]]:
        repeated = [(k, v) for k, v in self.euro_fullset_counter.items() if v > 1]
        repeated.sort(key=lambda x: (-x[1], x[0]))
        return repeated[:top_n]

    # --------------------------------------------------------
    # REGENCY / OKNA CZASOWE
    # --------------------------------------------------------

    def _recency_window_counts_main(self, windows=RECENCY_WINDOWS_MAIN) -> Dict[int, float]:
        scores = defaultdict(float)
        for w in windows:
            subset = self.draws[:min(w, self.total_draws)]
            c = Counter()
            for d in subset:
                c.update(d.main_numbers)
            for n in range(MAIN_MIN, MAIN_MAX + 1):
                scores[n] += c[n] / max(1, len(subset))
        return dict(scores)

    def _recency_window_counts_euro(self, windows=RECENCY_WINDOWS_EURO) -> Dict[int, float]:
        scores = defaultdict(float)
        for w in windows:
            subset = self.draws[:min(w, self.total_draws)]
            c = Counter()
            for d in subset:
                c.update(d.euro_numbers)
            for n in range(EURO_MIN, EURO_MAX + 1):
                scores[n] += c[n] / max(1, len(subset))
        return dict(scores)

    # --------------------------------------------------------
    # SCORING
    # --------------------------------------------------------

    def compute_main_scores(self) -> Dict[int, float]:
        freq_pct = self.main_frequency_percent()
        recency = self._recency_window_counts_main()

        overdue_values = [self.main_last_seen[n] for n in range(MAIN_MIN, MAIN_MAX + 1)]
        recency_values = [recency[n] for n in range(MAIN_MIN, MAIN_MAX + 1)]
        freq_values = [freq_pct[n] for n in range(MAIN_MIN, MAIN_MAX + 1)]

        pair_by_number = defaultdict(int)
        for (a, b), cnt in self.main_pair_counter.items():
            pair_by_number[a] += cnt
            pair_by_number[b] += cnt

        triple_by_number = defaultdict(int)
        for triple, cnt in self.main_triple_counter.items():
            for n in triple:
                triple_by_number[n] += cnt

        pair_values = [pair_by_number[n] for n in range(MAIN_MIN, MAIN_MAX + 1)]
        triple_values = [triple_by_number[n] for n in range(MAIN_MIN, MAIN_MAX + 1)]

        scores = {}
        for n in range(MAIN_MIN, MAIN_MAX + 1):
            freq_score = zscore(freq_pct[n], freq_values)
            recency_score = zscore(recency[n], recency_values)
            overdue_score = zscore(self.main_last_seen[n], overdue_values)
            pair_score = zscore(pair_by_number[n], pair_values)
            triple_score = zscore(triple_by_number[n], triple_values)

            pattern_bonus = 0.25 if 10 <= n <= 40 else 0.0

            total_score = (
                self.config.weight_freq * freq_score +
                self.config.weight_recency * recency_score +
                self.config.weight_overdue * overdue_score +
                self.config.weight_pair * pair_score +
                self.config.weight_triple * triple_score +
                self.config.weight_pattern * pattern_bonus
            )
            scores[n] = total_score

        return scores

    def compute_euro_scores(self) -> Dict[int, float]:
        freq_pct = self.euro_frequency_percent()
        recency = self._recency_window_counts_euro()

        overdue_values = [self.euro_last_seen[n] for n in range(EURO_MIN, EURO_MAX + 1)]
        recency_values = [recency[n] for n in range(EURO_MIN, EURO_MAX + 1)]
        freq_values = [freq_pct[n] for n in range(EURO_MIN, EURO_MAX + 1)]

        pair_by_number = defaultdict(int)
        for (a, b), cnt in self.euro_pair_counter.items():
            pair_by_number[a] += cnt
            pair_by_number[b] += cnt

        pair_values = [pair_by_number[n] for n in range(EURO_MIN, EURO_MAX + 1)]

        scores = {}
        for n in range(EURO_MIN, EURO_MAX + 1):
            freq_score = zscore(freq_pct[n], freq_values)
            recency_score = zscore(recency[n], recency_values)
            overdue_score = zscore(self.euro_last_seen[n], overdue_values)
            pair_score = zscore(pair_by_number[n], pair_values)

            pattern_bonus = 0.25 if 2 <= n <= 10 else 0.0

            total_score = (
                0.45 * freq_score +
                0.20 * recency_score +
                0.20 * overdue_score +
                0.10 * pair_score +
                0.05 * pattern_bonus
            )
            scores[n] = total_score

        return scores

    # --------------------------------------------------------
    # WALIDACJA KUPONÓW
    # --------------------------------------------------------

    def validate_main_ticket(self, nums: List[int]) -> bool:
        nums = sorted(nums)

        if len(nums) != 5 or len(set(nums)) != 5:
            return False

        evens = count_even(nums)
        if evens not in (2, 3):
            return False

        lows = count_low_main(nums)
        if lows not in (2, 3):
            return False

        run = max_consecutive_run(nums)
        if run > 2:
            return False

        spread = nums[-1] - nums[0]
        if spread < 18:
            return False

        return True

    def validate_euro_ticket(self, nums: List[int]) -> bool:
        nums = sorted(nums)

        if len(nums) != 2 or len(set(nums)) != 2:
            return False

        if nums[0] == nums[1]:
            return False

        return True

    # --------------------------------------------------------
    # GENERATOR
    # --------------------------------------------------------

    def weighted_sample_without_replacement(
        self,
        candidates: List[int],
        weights: Dict[int, float],
        k: int
    ) -> List[int]:
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

    def score_generated_main_ticket(self, nums: List[int], weights: Dict[int, float]) -> float:
        nums = sorted(nums)
        score = sum(weights[n] for n in nums)

        for pair in itertools.combinations(nums, 2):
            score += self.main_pair_counter[pair] * 0.03

        for triple in itertools.combinations(nums, 3):
            score += self.main_triple_counter[triple] * 0.05

        evens = count_even(nums)
        lows = count_low_main(nums)
        score += self.main_even_odd_patterns[(evens, 5 - evens)] * 0.02
        score += self.main_low_high_patterns[(lows, 5 - lows)] * 0.02

        return score

    def score_generated_euro_ticket(self, nums: List[int], weights: Dict[int, float]) -> float:
        nums = sorted(nums)
        score = sum(weights[n] for n in nums)
        score += self.euro_pair_counter[tuple(nums)] * 0.2

        evens = count_even(nums)
        lows = count_low_euro(nums)
        score += self.euro_even_odd_patterns[(evens, 2 - evens)] * 0.03
        score += self.euro_low_high_patterns[(lows, 2 - lows)] * 0.03
        return score

    def generate_ticket(self) -> Tuple[List[int], List[int]]:
        main_scores = self.compute_main_scores()
        euro_scores = self.compute_euro_scores()

        main_weights = normalize_weights(main_scores)
        euro_weights = normalize_weights(euro_scores)

        main_ranked = sorted(main_scores.items(), key=lambda x: x[1], reverse=True)
        euro_ranked = sorted(euro_scores.items(), key=lambda x: x[1], reverse=True)

        main_candidates = [n for n, _ in main_ranked[:self.config.hot_pool_main]]
        euro_candidates = [n for n, _ in euro_ranked[:self.config.hot_pool_euro]]

        remaining_main = [n for n in range(MAIN_MIN, MAIN_MAX + 1) if n not in main_candidates]
        remaining_euro = [n for n in range(EURO_MIN, EURO_MAX + 1) if n not in euro_candidates]

        extra_main = self.random.sample(remaining_main, min(10, len(remaining_main))) if remaining_main else []
        extra_euro = self.random.sample(remaining_euro, min(4, len(remaining_euro))) if remaining_euro else []

        main_pool = sorted(set(main_candidates + extra_main))
        euro_pool = sorted(set(euro_candidates + extra_euro))

        best_main = None
        best_main_score = float("-inf")

        for _ in range(self.config.generation_attempts):
            ticket = self.weighted_sample_without_replacement(main_pool, main_weights, 5)
            if self.validate_main_ticket(ticket):
                score = self.score_generated_main_ticket(ticket, main_weights)
                if score > best_main_score:
                    best_main_score = score
                    best_main = ticket

        if best_main is None:
            full_main = list(range(MAIN_MIN, MAIN_MAX + 1))
            for _ in range(self.config.generation_attempts):
                ticket = self.weighted_sample_without_replacement(full_main, main_weights, 5)
                if self.validate_main_ticket(ticket):
                    score = self.score_generated_main_ticket(ticket, main_weights)
                    if score > best_main_score:
                        best_main_score = score
                        best_main = ticket

        best_euro = None
        best_euro_score = float("-inf")

        for _ in range(self.config.generation_attempts):
            ticket = self.weighted_sample_without_replacement(euro_pool, euro_weights, 2)
            if self.validate_euro_ticket(ticket):
                score = self.score_generated_euro_ticket(ticket, euro_weights)
                if score > best_euro_score:
                    best_euro_score = score
                    best_euro = ticket

        if best_euro is None:
            full_euro = list(range(EURO_MIN, EURO_MAX + 1))
            for _ in range(self.config.generation_attempts):
                ticket = self.weighted_sample_without_replacement(full_euro, euro_weights, 2)
                if self.validate_euro_ticket(ticket):
                    score = self.score_generated_euro_ticket(ticket, euro_weights)
                    if score > best_euro_score:
                        best_euro_score = score
                        best_euro = ticket

        if best_main is None or best_euro is None:
            raise RuntimeError("Nie udało się wygenerować kuponu.")

        return best_main, best_euro

    def generate_multiple_tickets(self, count: int = 5) -> List[Tuple[List[int], List[int]]]:
        seen = set()
        out = []

        attempts = 0
        max_attempts = max(count * 50, 200)

        while len(out) < count and attempts < max_attempts:
            attempts += 1
            main_nums, euro_nums = self.generate_ticket()
            key = (tuple(main_nums), tuple(euro_nums))
            if key not in seen:
                seen.add(key)
                out.append((main_nums, euro_nums))

        return out

    # --------------------------------------------------------
    # TABELE POD STREAMLIT
    # --------------------------------------------------------

    def get_main_frequency_table(self) -> List[Dict]:
        freq = self.main_frequency_percent()
        rows = []
        for n in range(MAIN_MIN, MAIN_MAX + 1):
            rows.append({
                "Liczba": format_num(n),
                "Trafienia": self.main_counter[n],
                "Częstotliwość %": round(freq[n], 2),
                "Ostatnio widziana (ile losowań temu)": self.main_last_seen[n],
            })
        rows.sort(key=lambda x: (-x["Trafienia"], int(x["Liczba"])))
        return rows

    def get_euro_frequency_table(self) -> List[Dict]:
        freq = self.euro_frequency_percent()
        rows = []
        for n in range(EURO_MIN, EURO_MAX + 1):
            rows.append({
                "Liczba": format_num(n),
                "Trafienia": self.euro_counter[n],
                "Częstotliwość %": round(freq[n], 2),
                "Ostatnio widziana (ile losowań temu)": self.euro_last_seen[n],
            })
        rows.sort(key=lambda x: (-x["Trafienia"], int(x["Liczba"])))
        return rows

    def get_main_pairs_table(self, top_n: int = 20) -> List[Dict]:
        rows = []
        for pair, count in self.top_main_pairs(top_n):
            rows.append({
                "Para 5/50": " ".join(format_num(x) for x in pair),
                "Powtórzenia": count,
            })
        return rows

    def get_main_triples_table(self, top_n: int = 20) -> List[Dict]:
        rows = []
        for triple, count in self.top_main_triples(top_n):
            rows.append({
                "Trójka 5/50": " ".join(format_num(x) for x in triple),
                "Powtórzenia": count,
            })
        return rows

    def get_euro_pairs_table(self, top_n: int = 15) -> List[Dict]:
        rows = []
        for pair, count in self.top_euro_pairs(top_n):
            rows.append({
                "Para 2/12": " ".join(format_num(x) for x in pair),
                "Powtórzenia": count,
            })
        return rows

    def get_pattern_table(self, counter: Counter, label: str) -> List[Dict]:
        total = sum(counter.values())
        rows = []
        for pattern, count in counter.most_common():
            rows.append({
                label: str(pattern),
                "Powtórzenia": count,
                "Częstotliwość %": round(safe_percent(count, total), 2),
            })
        return rows


# ============================================================
# UI / STREAMLIT
# ============================================================

def render_header():
    st.set_page_config(page_title=APP_TITLE, layout="wide")
    st.title(APP_TITLE)
    st.caption(APP_SUBTITLE)


def render_sidebar():
    st.sidebar.header("Ustawienia")

    max_draws = st.sidebar.number_input(
        "Maksymalna liczba losowań do analizy",
        min_value=10,
        max_value=9999,
        value=MAX_DRAWS_DEFAULT,
        step=1,
    )

    ticket_count = st.sidebar.number_input(
        "Ile kuponów wygenerować",
        min_value=1,
        max_value=20,
        value=5,
        step=1,
    )

    debug_mode = st.sidebar.checkbox("Pokaż diagnostykę parsera PDF", value=False)

    st.sidebar.subheader("Wagi algorytmu")

    weight_freq = st.sidebar.slider("Waga częstotliwości", 0.0, 1.0, DEFAULT_WEIGHT_FREQ, 0.01)
    weight_recency = st.sidebar.slider("Waga świeżości", 0.0, 1.0, DEFAULT_WEIGHT_RECENCY, 0.01)
    weight_overdue = st.sidebar.slider("Waga opóźnienia", 0.0, 1.0, DEFAULT_WEIGHT_OVERDUE, 0.01)
    weight_pair = st.sidebar.slider("Waga par", 0.0, 1.0, DEFAULT_WEIGHT_PAIR, 0.01)
    weight_triple = st.sidebar.slider("Waga trójek", 0.0, 1.0, DEFAULT_WEIGHT_TRIPLE, 0.01)
    weight_pattern = st.sidebar.slider("Waga wzorca", 0.0, 1.0, DEFAULT_WEIGHT_PATTERN, 0.01)

    hot_pool_main = st.sidebar.number_input(
        "Hot pool 5/50",
        min_value=5,
        max_value=50,
        value=DEFAULT_HOT_POOL_MAIN,
        step=1,
    )

    hot_pool_euro = st.sidebar.number_input(
        "Hot pool 2/12",
        min_value=2,
        max_value=12,
        value=DEFAULT_HOT_POOL_EURO,
        step=1,
    )

    generation_attempts = st.sidebar.number_input(
        "Liczba prób generatora",
        min_value=100,
        max_value=50000,
        value=DEFAULT_GENERATION_ATTEMPTS,
        step=100,
    )

    seed = st.sidebar.number_input(
        "Seed losowania",
        min_value=0,
        max_value=999999,
        value=RANDOM_SEED_DEFAULT,
        step=1,
    )

    config = AnalyzerConfig(
        weight_freq=weight_freq,
        weight_recency=weight_recency,
        weight_overdue=weight_overdue,
        weight_pair=weight_pair,
        weight_triple=weight_triple,
        weight_pattern=weight_pattern,
        hot_pool_main=int(hot_pool_main),
        hot_pool_euro=int(hot_pool_euro),
        generation_attempts=int(generation_attempts),
        seed=int(seed),
    )

    return int(max_draws), int(ticket_count), debug_mode, config


def render_file_inputs():
    st.subheader("Pliki wejściowe PDF")

    col1, col2 = st.columns(2)

    with col1:
        main_uploaded = st.file_uploader(
            "Wgraj plik 5/50 (wyniki1ej.pdf)",
            type=["pdf"],
            key="main_pdf",
        )

    with col2:
        euro_uploaded = st.file_uploader(
            "Wgraj plik 2/12 (wyniki2ej.pdf)",
            type=["pdf"],
            key="euro_pdf",
        )

    use_default_files = st.checkbox(
        "Użyj plików z lokalnego folderu aplikacji, jeśli nie wgrywam ręcznie",
        value=True,
    )

    return main_uploaded, euro_uploaded, use_default_files


def resolve_pdf_source(uploaded_file, default_path: str):
    if uploaded_file is not None:
        return ensure_bytesio(uploaded_file)

    if os.path.exists(default_path):
        return default_path

    return None


def render_summary(analyzer: EuroJackpotAnalyzer):
    st.subheader("Podsumowanie")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("Wczytane losowania", analyzer.total_draws)
    with col2:
        st.metric("Zakres główny", "5 z 50")
    with col3:
        st.metric("Zakres Euro", "2 z 12")

    if analyzer.draws:
        newest = analyzer.draws[0].draw_id
        oldest = analyzer.draws[-1].draw_id
        st.write(f"**Najświeższe losowanie ID:** {newest}")
        st.write(f"**Najstarsze losowanie ID:** {oldest}")


def render_top_numbers(analyzer: EuroJackpotAnalyzer):
    st.subheader("Najczęstsze liczby")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### TOP liczby 5/50")
        st.dataframe(analyzer.get_main_frequency_table(), use_container_width=True, height=500)

    with col2:
        st.markdown("### TOP liczby 2/12")
        st.dataframe(analyzer.get_euro_frequency_table(), use_container_width=True, height=500)


def render_patterns(analyzer: EuroJackpotAnalyzer):
    st.subheader("Wzorce")

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Najczęstsze pary 5/50")
        st.dataframe(analyzer.get_main_pairs_table(20), use_container_width=True)

        st.markdown("### Najczęstsze trójki 5/50")
        st.dataframe(analyzer.get_main_triples_table(20), use_container_width=True)

        st.markdown("### Układ parzyste/nieparzyste 5/50")
        st.dataframe(
            analyzer.get_pattern_table(analyzer.main_even_odd_patterns, "Układ"),
            use_container_width=True,
        )

        st.markdown("### Układ niskie/wysokie 5/50")
        st.dataframe(
            analyzer.get_pattern_table(analyzer.main_low_high_patterns, "Układ"),
            use_container_width=True,
        )

    with col2:
        st.markdown("### Najczęstsze pary 2/12")
        st.dataframe(analyzer.get_euro_pairs_table(15), use_container_width=True)

        st.markdown("### Układ parzyste/nieparzyste 2/12")
        st.dataframe(
            analyzer.get_pattern_table(analyzer.euro_even_odd_patterns, "Układ"),
            use_container_width=True,
        )

        st.markdown("### Układ niskie/wysokie 2/12")
        st.dataframe(
            analyzer.get_pattern_table(analyzer.euro_low_high_patterns, "Układ"),
            use_container_width=True,
        )


def render_generated_tickets(analyzer: EuroJackpotAnalyzer, ticket_count: int):
    st.subheader("Wygenerowane kupony")

    best_main, best_euro = analyzer.generate_ticket()

    st.success(
        f"Najmocniejsza propozycja: "
        f"**{format_number_list(best_main)} + {format_number_list(best_euro)}**"
    )

    tickets = analyzer.generate_multiple_tickets(ticket_count)

    rows = []
    for i, (main_nums, euro_nums) in enumerate(tickets, start=1):
        rows.append({
            "Kupon": i,
            "Liczby główne 5/50": format_number_list(main_nums),
            "Liczby Euro 2/12": format_number_list(euro_nums),
        })

    st.dataframe(rows, use_container_width=True)


def render_diagnostics(diagnostics: Dict):
    st.subheader("Diagnostyka parsera")

    st.markdown("### Podsumowanie wspólnych losowań")
    st.json({
        "common_ids_count": diagnostics.get("common_ids_count"),
        "common_ids_preview": diagnostics.get("common_ids_preview"),
    })

    for kind_key, title in [("main", "Diagnostyka pliku 5/50"), ("euro", "Diagnostyka pliku 2/12")]:
        if kind_key not in diagnostics:
            continue

        st.markdown(f"### {title}")
        block = diagnostics[kind_key]

        summary = {
            "kind": block.get("kind"),
            "pages": block.get("pages"),
            "total_draw_ids_found": block.get("total_draw_ids_found"),
            "total_rows_found_words": block.get("total_rows_found_words"),
            "total_rows_found_text": block.get("total_rows_found_text"),
            "usable": block.get("usable"),
            "draw_ids_preview": block.get("draw_ids_preview"),
            "rows_preview": block.get("rows_preview"),
        }
        st.json(summary)

        for page_info in block.get("page_info", []):
            with st.expander(f"Strona {page_info['page']}"):
                st.write({
                    "draw_ids_found": page_info["draw_ids_found"],
                    "candidate_tokens_count": page_info["candidate_tokens_count"],
                    "rows_from_words": page_info["rows_from_words"],
                    "rows_from_text": page_info["rows_from_text"],
                    "rows_selected": page_info["rows_selected"],
                })

                st.markdown("**Podgląd tokenów:**")
                st.code(" ".join(page_info["first_tokens_preview"][:120]), language="text")

                st.markdown("**Podgląd tekstu:**")
                st.code(page_info["first_text_preview"], language="text")


def render_scores_preview(analyzer: EuroJackpotAnalyzer):
    st.subheader("Podgląd scoringu liczb")

    main_scores = analyzer.compute_main_scores()
    euro_scores = analyzer.compute_euro_scores()

    main_rows = []
    for n, score in sorted(main_scores.items(), key=lambda x: x[1], reverse=True):
        main_rows.append({
            "Liczba 5/50": format_num(n),
            "Score": round(score, 4),
        })

    euro_rows = []
    for n, score in sorted(euro_scores.items(), key=lambda x: x[1], reverse=True):
        euro_rows.append({
            "Liczba 2/12": format_num(n),
            "Score": round(score, 4),
        })

    col1, col2 = st.columns(2)

    with col1:
        st.markdown("### Score 5/50")
        st.dataframe(main_rows, use_container_width=True, height=500)

    with col2:
        st.markdown("### Score 2/12")
        st.dataframe(euro_rows, use_container_width=True, height=500)


def render_footer_note():
    st.info(
        "To narzędzie analizuje historyczne dane i generuje kupony na podstawie częstotliwości, "
        "powtarzalnych układów i scoringu. Nie gwarantuje trafienia, bo losowanie pozostaje losowe."
    )


# ============================================================
# GŁÓWNA LOGIKA APLIKACJI
# ============================================================

def main():
    render_header()

    max_draws, ticket_count, debug_mode, analyzer_config = render_sidebar()
    main_uploaded, euro_uploaded, use_default_files = render_file_inputs()

    main_source = None
    euro_source = None

    if main_uploaded is not None:
        main_source = resolve_pdf_source(main_uploaded, DEFAULT_MAIN_PDF)
    elif use_default_files:
        main_source = resolve_pdf_source(None, DEFAULT_MAIN_PDF)

    if euro_uploaded is not None:
        euro_source = resolve_pdf_source(euro_uploaded, DEFAULT_EURO_PDF)
    elif use_default_files:
        euro_source = resolve_pdf_source(None, DEFAULT_EURO_PDF)

    if main_source is None or euro_source is None:
        st.warning(
            "Wgraj oba pliki PDF albo umieść w katalogu aplikacji pliki "
            "`wyniki1ej.pdf` i `wyniki2ej.pdf`."
        )
        st.stop()

    analyze_clicked = st.button("Analizuj pliki i wygeneruj kupony", type="primary")

    if not analyze_clicked:
        st.stop()

    try:
        with st.spinner("Wczytywanie i analiza PDF..."):
            draws, diagnostics = load_draws(
                main_source,
                euro_source,
                max_draws=max_draws,
                debug=debug_mode,
            )

        analyzer = EuroJackpotAnalyzer(draws, analyzer_config)

        render_summary(analyzer)
        render_generated_tickets(analyzer, ticket_count)
        render_top_numbers(analyzer)
        render_patterns(analyzer)
        render_scores_preview(analyzer)

        if debug_mode:
            render_diagnostics(diagnostics)

        render_footer_note()

    except Exception as e:
        st.error(f"Wystąpił błąd: {str(e)}")

        st.markdown("## Diagnostyka awaryjna")

        try:
            if main_source is not None:
                main_text_pages = extract_pages_text(main_source)
                st.markdown("### Podgląd pierwszej strony pliku 5/50")
                if main_text_pages:
                    st.code(main_text_pages[0][:4000], language="text")

        except Exception as diag_err:
            st.warning(f"Nie udało się pokazać diagnostyki pliku 5/50: {diag_err}")

        try:
            if euro_source is not None:
                euro_text_pages = extract_pages_text(euro_source)
                st.markdown("### Podgląd pierwszej strony pliku 2/12")
                if euro_text_pages:
                    st.code(euro_text_pages[0][:4000], language="text")

        except Exception as diag_err:
            st.warning(f"Nie udało się pokazać diagnostyki pliku 2/12: {diag_err}")

        raise


# ============================================================
# START
# ============================================================

if __name__ == "__main__":
    main()
