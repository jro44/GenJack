import re
import math
import random
import itertools
from collections import Counter, defaultdict
from dataclasses import dataclass
from typing import List, Dict, Tuple, Optional

try:
    import fitz  # PyMuPDF
except ImportError:
    raise SystemExit(
        "Brakuje biblioteki PyMuPDF. Zainstaluj:\n"
        "pip install pymupdf"
    )


# ============================================================
# KONFIGURACJA
# ============================================================

MAIN_PDF = "wyniki1ej.pdf"   # 5 z 50
EURO_PDF = "wyniki2ej.pdf"   # 2 z 12
MAX_DRAWS = 999

RANDOM_SEED = 42
random.seed(RANDOM_SEED)

# Zakresy
MAIN_MIN = 1
MAIN_MAX = 50
EURO_MIN = 1
EURO_MAX = 12

# Wagi dla generatora
WEIGHT_FREQ = 0.35
WEIGHT_RECENCY = 0.20
WEIGHT_OVERDUE = 0.15
WEIGHT_PAIR = 0.15
WEIGHT_TRIPLE = 0.10
WEIGHT_PATTERN = 0.05

# Ile liczb uznajemy za hot/cold
HOT_POOL_MAIN = 20
HOT_POOL_EURO = 6

# Ile prób przy generowaniu kuponu
GENERATION_ATTEMPTS = 8000


# ============================================================
# MODELE DANYCH
# ============================================================

@dataclass
class Draw:
    draw_id: int
    main_numbers: List[int]
    euro_numbers: List[int]


# ============================================================
# POMOCNICZE
# ============================================================

def normalize_number(n: int) -> int:
    return int(n)


def sorted_tuple(nums: List[int]) -> Tuple[int, ...]:
    return tuple(sorted(nums))


def safe_percent(part: int, whole: int) -> float:
    if whole == 0:
        return 0.0
    return (part / whole) * 100.0


def zscore(value: float, values: List[float]) -> float:
    if not values:
        return 0.0
    mean = sum(values) / len(values)
    variance = sum((x - mean) ** 2 for x in values) / len(values)
    std = math.sqrt(variance)
    if std == 0:
        return 0.0
    return (value - mean) / std


# ============================================================
# PARSER PDF
# ============================================================

def extract_text_from_pdf(pdf_path: str) -> str:
    doc = fitz.open(pdf_path)
    chunks = []
    for page in doc:
        chunks.append(page.get_text("text"))
    doc.close()
    return "\n".join(chunks)


def parse_main_pdf(pdf_path: str, max_draws: int = 999) -> Dict[int, List[int]]:
    """
    Parser dla pliku 5/50.
    Zakłada układ:
    - najpierw wiele wierszy po 5 liczb
    - potem numery losowań 4-cyfrowe
    """
    text = extract_text_from_pdf(pdf_path)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    draws_numbers = []
    draw_ids = []

    draw_id_pattern = re.compile(r"^\d{4}$")
    row_pattern = re.compile(r"^(\d{2}\s+){4}\d{2}$")

    for line in lines:
        if row_pattern.match(line):
            nums = [int(x) for x in line.split()]
            if len(nums) == 5 and all(MAIN_MIN <= x <= MAIN_MAX for x in nums):
                draws_numbers.append(nums)
        elif draw_id_pattern.match(line):
            draw_id = int(line)
            draw_ids.append(draw_id)

    if not draws_numbers or not draw_ids:
        raise ValueError(f"Nie udało się sparsować pliku: {pdf_path}")

    # W tych PDF-ach zwykle najpierw idą wiersze wyników, potem numery losowań
    usable = min(len(draws_numbers), len(draw_ids), max_draws)
    result = {}

    for i in range(usable):
        result[draw_ids[i]] = sorted(draws_numbers[i])

    return result


def parse_euro_pdf(pdf_path: str, max_draws: int = 999) -> Dict[int, List[int]]:
    """
    Parser dla pliku 2/12.
    Zakłada układ:
    - najpierw wiele wierszy po 2 liczby
    - potem numery losowań 4-cyfrowe
    """
    text = extract_text_from_pdf(pdf_path)

    lines = [line.strip() for line in text.splitlines() if line.strip()]
    draws_numbers = []
    draw_ids = []

    draw_id_pattern = re.compile(r"^\d{4}$")
    row_pattern = re.compile(r"^\d{2}\s+\d{2}$")

    for line in lines:
        if row_pattern.match(line):
            nums = [int(x) for x in line.split()]
            if len(nums) == 2 and all(EURO_MIN <= x <= EURO_MAX for x in nums):
                draws_numbers.append(nums)
        elif draw_id_pattern.match(line):
            draw_id = int(line)
            draw_ids.append(draw_id)

    if not draws_numbers or not draw_ids:
        raise ValueError(f"Nie udało się sparsować pliku: {pdf_path}")

    usable = min(len(draws_numbers), len(draw_ids), max_draws)
    result = {}

    for i in range(usable):
        result[draw_ids[i]] = sorted(draws_numbers[i])

    return result


def load_draws(main_pdf: str, euro_pdf: str, max_draws: int = 999) -> List[Draw]:
    main_map = parse_main_pdf(main_pdf, max_draws)
    euro_map = parse_euro_pdf(euro_pdf, max_draws)

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
    return draws


# ============================================================
# ANALIZA STATYSTYK
# ============================================================

class EuroJackpotAnalyzer:
    def __init__(self, draws: List[Draw]):
        self.draws = sorted(draws, key=lambda d: d.draw_id, reverse=True)
        self.total_draws = len(self.draws)

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

            # last seen: idx=0 najnowsze losowanie
            for n in main:
                if n not in self.main_last_seen:
                    self.main_last_seen[n] = idx

            for n in euro:
                if n not in self.euro_last_seen:
                    self.euro_last_seen[n] = idx

            even_main = sum(1 for x in main if x % 2 == 0)
            odd_main = 5 - even_main
            self.main_even_odd_patterns[(even_main, odd_main)] += 1

            low_main = sum(1 for x in main if x <= 25)
            high_main = 5 - low_main
            self.main_low_high_patterns[(low_main, high_main)] += 1

            even_euro = sum(1 for x in euro if x % 2 == 0)
            odd_euro = 2 - even_euro
            self.euro_even_odd_patterns[(even_euro, odd_euro)] += 1

            low_euro = sum(1 for x in euro if x <= 6)
            high_euro = 2 - low_euro
            self.euro_low_high_patterns[(low_euro, high_euro)] += 1

            for pos, n in enumerate(main):
                self.main_positional_counter[pos][n] += 1

            for pos, n in enumerate(euro):
                self.euro_positional_counter[pos][n] += 1

        # jeśli jakaś liczba nie wystąpiła, ustawiamy last_seen = total_draws
        for n in range(MAIN_MIN, MAIN_MAX + 1):
            if n not in self.main_last_seen:
                self.main_last_seen[n] = self.total_draws

        for n in range(EURO_MIN, EURO_MAX + 1):
            if n not in self.euro_last_seen:
                self.euro_last_seen[n] = self.total_draws

    # --------------------------------------------------------
    # Podstawowe statystyki
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
        data = [(n, self.main_counter[n], freq[n]) for n in range(MAIN_MIN, MAIN_MAX + 1)]
        return sorted(data, key=lambda x: (-x[1], x[0]))[:top_n]

    def top_euro_numbers(self, top_n: int = 8) -> List[Tuple[int, int, float]]:
        freq = self.euro_frequency_percent()
        data = [(n, self.euro_counter[n], freq[n]) for n in range(EURO_MIN, EURO_MAX + 1)]
        return sorted(data, key=lambda x: (-x[1], x[0]))[:top_n]

    def cold_main_numbers(self, top_n: int = 10) -> List[Tuple[int, int, float]]:
        freq = self.main_frequency_percent()
        data = [(n, self.main_counter[n], freq[n]) for n in range(MAIN_MIN, MAIN_MAX + 1)]
        return sorted(data, key=lambda x: (x[1], x[0]))[:top_n]

    def cold_euro_numbers(self, top_n: int = 4) -> List[Tuple[int, int, float]]:
        freq = self.euro_frequency_percent()
        data = [(n, self.euro_counter[n], freq[n]) for n in range(EURO_MIN, EURO_MAX + 1)]
        return sorted(data, key=lambda x: (x[1], x[0]))[:top_n]

    def top_main_pairs(self, top_n: int = 15) -> List[Tuple[Tuple[int, int], int]]:
        return self.main_pair_counter.most_common(top_n)

    def top_main_triples(self, top_n: int = 15) -> List[Tuple[Tuple[int, int, int], int]]:
        return self.main_triple_counter.most_common(top_n)

    def top_main_fullsets(self, top_n: int = 10) -> List[Tuple[Tuple[int, ...], int]]:
        repeated = [(k, v) for k, v in self.main_fullset_counter.items() if v > 1]
        repeated.sort(key=lambda x: (-x[1], x[0]))
        return repeated[:top_n]

    def top_euro_pairs(self, top_n: int = 10) -> List[Tuple[Tuple[int, int], int]]:
        return self.euro_pair_counter.most_common(top_n)

    # --------------------------------------------------------
    # Scoring liczb
    # --------------------------------------------------------

    def _recency_window_counts_main(self, windows=(20, 50, 100, 200)) -> Dict[int, float]:
        scores = defaultdict(float)
        for w in windows:
            subset = self.draws[:min(w, self.total_draws)]
            c = Counter()
            for d in subset:
                c.update(d.main_numbers)
            for n in range(MAIN_MIN, MAIN_MAX + 1):
                scores[n] += c[n] / max(1, len(subset))
        return dict(scores)

    def _recency_window_counts_euro(self, windows=(20, 50, 100, 200)) -> Dict[int, float]:
        scores = defaultdict(float)
        for w in windows:
            subset = self.draws[:min(w, self.total_draws)]
            c = Counter()
            for d in subset:
                c.update(d.euro_numbers)
            for n in range(EURO_MIN, EURO_MAX + 1):
                scores[n] += c[n] / max(1, len(subset))
        return dict(scores)

    def compute_main_scores(self) -> Dict[int, float]:
        freq_pct = self.main_frequency_percent()
        recency = self._recency_window_counts_main()

        overdue_values = [self.main_last_seen[n] for n in range(MAIN_MIN, MAIN_MAX + 1)]
        recency_values = [recency[n] for n in range(MAIN_MIN, MAIN_MAX + 1)]
        freq_values = [freq_pct[n] for n in range(MAIN_MIN, MAIN_MAX + 1)]

        top_pairs_by_number = defaultdict(int)
        for (a, b), cnt in self.main_pair_counter.items():
            top_pairs_by_number[a] += cnt
            top_pairs_by_number[b] += cnt

        top_triples_by_number = defaultdict(int)
        for triple, cnt in self.main_triple_counter.items():
            for n in triple:
                top_triples_by_number[n] += cnt

        pair_values = [top_pairs_by_number[n] for n in range(MAIN_MIN, MAIN_MAX + 1)]
        triple_values = [top_triples_by_number[n] for n in range(MAIN_MIN, MAIN_MAX + 1)]

        scores = {}
        for n in range(MAIN_MIN, MAIN_MAX + 1):
            freq_score = zscore(freq_pct[n], freq_values)
            recency_score = zscore(recency[n], recency_values)
            overdue_score = zscore(self.main_last_seen[n], overdue_values)
            pair_score = zscore(top_pairs_by_number[n], pair_values)
            triple_score = zscore(top_triples_by_number[n], triple_values)

            # lekka premia za środkowy zakres 10-40
            pattern_bonus = 0.25 if 10 <= n <= 40 else 0.0

            score = (
                WEIGHT_FREQ * freq_score +
                WEIGHT_RECENCY * recency_score +
                WEIGHT_OVERDUE * overdue_score +
                WEIGHT_PAIR * pair_score +
                WEIGHT_TRIPLE * triple_score +
                WEIGHT_PATTERN * pattern_bonus
            )
            scores[n] = score

        return scores

    def compute_euro_scores(self) -> Dict[int, float]:
        freq_pct = self.euro_frequency_percent()
        recency = self._recency_window_counts_euro()

        overdue_values = [self.euro_last_seen[n] for n in range(EURO_MIN, EURO_MAX + 1)]
        recency_values = [recency[n] for n in range(EURO_MIN, EURO_MAX + 1)]
        freq_values = [freq_pct[n] for n in range(EURO_MIN, EURO_MAX + 1)]

        pair_values_by_number = defaultdict(int)
        for (a, b), cnt in self.euro_pair_counter.items():
            pair_values_by_number[a] += cnt
            pair_values_by_number[b] += cnt

        pair_values = [pair_values_by_number[n] for n in range(EURO_MIN, EURO_MAX + 1)]

        scores = {}
        for n in range(EURO_MIN, EURO_MAX + 1):
            freq_score = zscore(freq_pct[n], freq_values)
            recency_score = zscore(recency[n], recency_values)
            overdue_score = zscore(self.euro_last_seen[n], overdue_values)
            pair_score = zscore(pair_values_by_number[n], pair_values)

            # lekki bonus dla środka zakresu 2-10
            pattern_bonus = 0.25 if 2 <= n <= 10 else 0.0

            score = (
                0.45 * freq_score +
                0.20 * recency_score +
                0.20 * overdue_score +
                0.10 * pair_score +
                0.05 * pattern_bonus
            )
            scores[n] = score

        return scores

    # --------------------------------------------------------
    # Generator kuponu
    # --------------------------------------------------------

    def weighted_sample_without_replacement(
        self,
        candidates: List[int],
        weights: Dict[int, float],
        k: int
    ) -> List[int]:
        pool = candidates[:]
        selected = []

        for _ in range(k):
            if not pool:
                break

            raw_weights = []
            for n in pool:
                w = weights.get(n, 0.0)
                # muszą być dodatnie
                raw_weights.append(max(0.0001, w))

            chosen = random.choices(pool, weights=raw_weights, k=1)[0]
            selected.append(chosen)
            pool.remove(chosen)

        return sorted(selected)

    def _normalize_scores_to_weights(self, scores: Dict[int, float]) -> Dict[int, float]:
        min_score = min(scores.values())
        shifted = {k: (v - min_score + 0.1) for k, v in scores.items()}
        return shifted

    def _validate_main_ticket(self, nums: List[int]) -> bool:
        nums = sorted(nums)

        # 1) brak duplikatów
        if len(nums) != 5 or len(set(nums)) != 5:
            return False

        # 2) balans parzyste/nieparzyste
        evens = sum(1 for x in nums if x % 2 == 0)
        if evens not in (2, 3):
            return False

        # 3) balans niskie/wysokie
        lows = sum(1 for x in nums if x <= 25)
        if lows not in (2, 3):
            return False

        # 4) max 2 liczby sąsiadujące
        consecutive_runs = 1
        max_run = 1
        for i in range(1, len(nums)):
            if nums[i] == nums[i - 1] + 1:
                consecutive_runs += 1
                max_run = max(max_run, consecutive_runs)
            else:
                consecutive_runs = 1
        if max_run > 2:
            return False

        # 5) sensowny rozrzut
        spread = nums[-1] - nums[0]
        if spread < 18:
            return False

        return True

    def _validate_euro_ticket(self, nums: List[int]) -> bool:
        nums = sorted(nums)

        if len(nums) != 2 or len(set(nums)) != 2:
            return False

        evens = sum(1 for x in nums if x % 2 == 0)
        if evens not in (1, 2, 0):
            return False

        # nie bierzemy stale zbyt ciasnych par
        if abs(nums[1] - nums[0]) == 0:
            return False

        return True

    def _score_generated_main_ticket(self, nums: List[int], score_weights: Dict[int, float]) -> float:
        nums = sorted(nums)
        score = sum(score_weights[n] for n in nums)

        # bonus za obecność częstych par
        for pair in itertools.combinations(nums, 2):
            score += self.main_pair_counter[pair] * 0.03

        # bonus za obecność częstych trójek
        for triple in itertools.combinations(nums, 3):
            score += self.main_triple_counter[triple] * 0.05

        # bonus za popularny układ parzyste/nieparzyste i low/high
        evens = sum(1 for x in nums if x % 2 == 0)
        lows = sum(1 for x in nums if x <= 25)
        score += self.main_even_odd_patterns[(evens, 5 - evens)] * 0.02
        score += self.main_low_high_patterns[(lows, 5 - lows)] * 0.02

        return score

    def _score_generated_euro_ticket(self, nums: List[int], score_weights: Dict[int, float]) -> float:
        nums = sorted(nums)
        score = sum(score_weights[n] for n in nums)
        score += self.euro_pair_counter[tuple(nums)] * 0.2

        evens = sum(1 for x in nums if x % 2 == 0)
        lows = sum(1 for x in nums if x <= 6)
        score += self.euro_even_odd_patterns[(evens, 2 - evens)] * 0.03
        score += self.euro_low_high_patterns[(lows, 2 - lows)] * 0.03
        return score

    def generate_ticket(self) -> Tuple[List[int], List[int]]:
        main_scores = self.compute_main_scores()
        euro_scores = self.compute_euro_scores()

        main_weights = self._normalize_scores_to_weights(main_scores)
        euro_weights = self._normalize_scores_to_weights(euro_scores)

        # kandydaci z hot puli + trochę reszty
        main_ranked = sorted(main_scores.items(), key=lambda x: x[1], reverse=True)
        euro_ranked = sorted(euro_scores.items(), key=lambda x: x[1], reverse=True)

        main_candidates = [n for n, _ in main_ranked[:HOT_POOL_MAIN]]
        euro_candidates = [n for n, _ in euro_ranked[:HOT_POOL_EURO]]

        # dodaj trochę zimnych/liczb spoza topu dla zbalansowania
        remaining_main = [n for n in range(MAIN_MIN, MAIN_MAX + 1) if n not in main_candidates]
        remaining_euro = [n for n in range(EURO_MIN, EURO_MAX + 1) if n not in euro_candidates]

        extra_main = random.sample(remaining_main, min(10, len(remaining_main)))
        extra_euro = random.sample(remaining_euro, min(4, len(remaining_euro)))

        main_pool = sorted(set(main_candidates + extra_main))
        euro_pool = sorted(set(euro_candidates + extra_euro))

        best_main = None
        best_main_score = float("-inf")

        for _ in range(GENERATION_ATTEMPTS):
            ticket = self.weighted_sample_without_replacement(main_pool, main_weights, 5)
            if self._validate_main_ticket(ticket):
                sc = self._score_generated_main_ticket(ticket, main_weights)
                if sc > best_main_score:
                    best_main_score = sc
                    best_main = ticket

        if best_main is None:
            # awaryjnie z pełnej puli
            full_main_pool = list(range(MAIN_MIN, MAIN_MAX + 1))
            for _ in range(GENERATION_ATTEMPTS):
                ticket = self.weighted_sample_without_replacement(full_main_pool, main_weights, 5)
                if self._validate_main_ticket(ticket):
                    sc = self._score_generated_main_ticket(ticket, main_weights)
                    if sc > best_main_score:
                        best_main_score = sc
                        best_main = ticket

        best_euro = None
        best_euro_score = float("-inf")

        for _ in range(GENERATION_ATTEMPTS):
            ticket = self.weighted_sample_without_replacement(euro_pool, euro_weights, 2)
            if self._validate_euro_ticket(ticket):
                sc = self._score_generated_euro_ticket(ticket, euro_weights)
                if sc > best_euro_score:
                    best_euro_score = sc
                    best_euro = ticket

        if best_euro is None:
            full_euro_pool = list(range(EURO_MIN, EURO_MAX + 1))
            for _ in range(GENERATION_ATTEMPTS):
                ticket = self.weighted_sample_without_replacement(full_euro_pool, euro_weights, 2)
                if self._validate_euro_ticket(ticket):
                    sc = self._score_generated_euro_ticket(ticket, euro_weights)
                    if sc > best_euro_score:
                        best_euro_score = sc
                        best_euro = ticket

        if best_main is None or best_euro is None:
            raise RuntimeError("Nie udało się wygenerować kuponu.")

        return best_main, best_euro

    def generate_multiple_tickets(self, count: int = 5) -> List[Tuple[List[int], List[int]]]:
        tickets = []
        seen = set()

        attempts = 0
        while len(tickets) < count and attempts < count * 200:
            attempts += 1
            ticket = self.generate_ticket()
            key = (tuple(ticket[0]), tuple(ticket[1]))
            if key not in seen:
                seen.add(key)
                tickets.append(ticket)

        return tickets


# ============================================================
# RAPORT
# ============================================================

def format_number_list(nums: List[int]) -> str:
    return " ".join(f"{n:02d}" for n in nums)


def print_top_number_stats(title: str, rows: List[Tuple[int, int, float]]):
    print(f"\n{title}")
    print("-" * len(title))
    for n, count, pct in rows:
        print(f"Liczba {n:02d} -> {count:>3} trafień | {pct:6.2f}%")


def print_top_combinations(title: str, rows: List[Tuple[Tuple[int, ...], int]]):
    print(f"\n{title}")
    print("-" * len(title))
    if not rows:
        print("Brak powtórzonych układów.")
        return
    for combo, count in rows:
        combo_str = " ".join(f"{x:02d}" for x in combo)
        print(f"{combo_str} -> {count} razy")


def print_pattern_stats(title: str, counter: Counter):
    print(f"\n{title}")
    print("-" * len(title))
    total = sum(counter.values())
    for pattern, count in counter.most_common():
        pct = safe_percent(count, total)
        print(f"{pattern} -> {count} razy | {pct:.2f}%")


# ============================================================
# MAIN
# ============================================================

def main():
    print("Ładowanie danych EuroJackpot z PDF...")
    draws = load_draws(MAIN_PDF, EURO_PDF, MAX_DRAWS)

    analyzer = EuroJackpotAnalyzer(draws)

    print(f"\nZaładowano wspólnych losowań: {analyzer.total_draws}")
    print(f"Najświeższe losowanie ID: {draws[0].draw_id}")
    print(f"Najstarsze losowanie ID:  {draws[-1].draw_id}")

    # TOP liczby
    print_top_number_stats("TOP liczby główne 5/50", analyzer.top_main_numbers(15))
    print_top_number_stats("Najrzadsze liczby główne 5/50", analyzer.cold_main_numbers(10))

    print_top_number_stats("TOP liczby Euro 2/12", analyzer.top_euro_numbers(8))
    print_top_number_stats("Najrzadsze liczby Euro 2/12", analyzer.cold_euro_numbers(4))

    # Pary i trójki
    print_top_combinations("Najczęstsze pary 5/50", analyzer.top_main_pairs(15))
    print_top_combinations("Najczęstsze trójki 5/50", analyzer.top_main_triples(15))
    print_top_combinations("Najczęstsze pełne układy 5/50", analyzer.top_main_fullsets(10))
    print_top_combinations("Najczęstsze pary 2/12", analyzer.top_euro_pairs(10))

    # Wzorce
    print_pattern_stats("Układy parzyste/nieparzyste 5/50", analyzer.main_even_odd_patterns)
    print_pattern_stats("Układy niskie/wysokie 5/50", analyzer.main_low_high_patterns)
    print_pattern_stats("Układy parzyste/nieparzyste 2/12", analyzer.euro_even_odd_patterns)
    print_pattern_stats("Układy niskie/wysokie 2/12", analyzer.euro_low_high_patterns)

    # Generowanie kuponu
    best_main, best_euro = analyzer.generate_ticket()

    print("\n" + "=" * 60)
    print("PROPONOWANY KUPON EUROJACKPOT")
    print("=" * 60)
    print(f"Liczby główne 5/50: {format_number_list(best_main)}")
    print(f"Liczby Euro 2/12:   {format_number_list(best_euro)}")

    # Dodatkowe kupony
    print("\nDodatkowe propozycje:")
    tickets = analyzer.generate_multiple_tickets(5)
    for i, (main_nums, euro_nums) in enumerate(tickets, start=1):
        print(
            f"{i}. "
            f"{format_number_list(main_nums)} + "
            f"{format_number_list(euro_nums)}"
        )


if __name__ == "__main__":
    main()
