import streamlit as st
import pdfplumber
import re
import random
from collections import Counter
import os

# ==============================================================================
# 1. KONFIGURACJA STRONY
# ==============================================================================

st.set_page_config(
    page_title="EuroJackpot 777 (Trend 50)",
    page_icon="🇪🇺",
    layout="centered",
    initial_sidebar_state="collapsed"
)

# ==============================================================================
# 2. STYLIZACJA (GOLD & NAVY - PRESTIGE)
# ==============================================================================

st.markdown("""
    <style>
    /* TŁO */
    .stApp {
        background-color: #0f172a; /* Ciemny granat */
        color: #f1f5f9;
        font-family: 'Helvetica', sans-serif;
    }
    
    /* NAGŁÓWKI */
    h1 {
        color: #fbbf24 !important; /* Euro Gold */
        text-transform: uppercase;
        text-align: center;
        text-shadow: 0px 0px 15px rgba(251, 191, 36, 0.4);
        font-weight: 800;
    }
    h3 {
        color: #94a3b8 !important;
        text-align: center;
        font-weight: 300;
        font-size: 16px;
    }
    
    /* STATUS PLIKÓW */
    .file-status {
        background-color: #1e293b;
        padding: 12px;
        border-radius: 8px;
        border: 1px solid #334155;
        margin-bottom: 10px;
        text-align: center;
        font-size: 14px;
    }
    .status-ok { color: #4ade80; border-color: #4ade80; }
    .status-err { color: #f87171; border-color: #f87171; }

    /* KULE GŁÓWNE (5 z 50) */
    .ball-container {
        display: flex;
        justify-content: center;
        flex-wrap: wrap;
        gap: 8px;
        margin-bottom: 15px;
    }
    .ball-main {
        display: flex;
        justify-content: center;
        align-items: center;
        width: 55px;
        height: 55px;
        border-radius: 50%;
        background: radial-gradient(circle at 30% 30%, #fbbf24, #d97706);
        color: #0f172a;
        font-weight: bold;
        font-size: 22px;
        border: 2px solid #fffbeb;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* KULE EURO (2 z 12) */
    .ball-euro {
        display: flex;
        justify-content: center;
        align-items: center;
        width: 55px;
        height: 55px;
        border-radius: 50%;
        background: radial-gradient(circle at 30% 30%, #ef4444, #991b1b);
        color: white;
        font-weight: bold;
        font-size: 22px;
        border: 2px solid #fee2e2;
        box-shadow: 0 4px 6px rgba(0,0,0,0.3);
    }
    
    /* PRZYCISK */
    div.stButton > button {
        background: linear-gradient(to right, #fbbf24, #f59e0b);
        color: #0f172a;
        font-size: 18px;
        font-weight: bold;
        border: none;
        padding: 12px 30px;
        border-radius: 50px;
        width: 100%;
        margin-top: 20px;
        transition: all 0.2s;
        text-transform: uppercase;
        letter-spacing: 1px;
    }
    div.stButton > button:hover {
        transform: scale(1.02);
        box-shadow: 0 0 15px rgba(251, 191, 36, 0.6);
    }
    div.stButton > button:active {
        transform: scale(0.98);
    }
    
    /* METRYKI */
    div[data-testid="stMetricValue"] {
        color: #fbbf24 !important;
    }
    div[data-testid="stMetricLabel"] {
        color: #94a3b8 !important;
    }
    
    /* OSTRZEŻENIE */
    .info-box {
        background-color: #1e293b;
        color: #64748b;
        padding: 15px;
        border-radius: 8px;
        font-size: 11px;
        text-align: center;
        margin-top: 40px;
        border-top: 1px solid #334155;
    }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. FUNKCJE CZYTAJĄCE PDF
# ==============================================================================

def parse_pdf_data(filename, range_max, pick_count):
    """
    Czyta liczby z pliku PDF.
    - filename: nazwa pliku
    - range_max: maksymalna liczba (50 lub 12)
    - pick_count: ile liczb jest w jednym losowaniu (5 lub 2)
    """
    if not os.path.exists(filename):
        return [], False 
        
    draws = []
    try:
        with pdfplumber.open(filename) as pdf:
            full_text = ""
            for page in pdf.pages:
                txt = page.extract_text()
                if txt: full_text += txt + "\n"
        
        lines = full_text.split('\n')
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Usuwamy datę (DD.MM.YYYY), żeby nie weszła jako liczba
            clean_line = re.sub(r'\d{2}\.\d{2}\.\d{4}', '', line)
            
            # Szukamy liczb
            nums = [int(n) for n in re.findall(r'\b\d+\b', clean_line)]
            
            # Filtrujemy (musi być w zakresie np. 1-50)
            valid_nums = [n for n in nums if 1 <= n <= range_max]
            
            # Sprawdzamy czy mamy komplet liczb dla danego losowania
            if len(valid_nums) >= pick_count:
                # Bierzemy pierwsze X liczb (w razie gdyby w linii były jakieś śmieci)
                draws.append(valid_nums[:pick_count])
                
        return draws, True
        
    except Exception:
        return [], False

# ==============================================================================
# 4. ALGORYTM SMART (TREND 50)
# ==============================================================================

def generate_main_numbers(history):
    """
    Generuje 5 liczb z 50 (Baza 1).
    Logika: Hot Numbers (ostatnie 50) + Filtry Statystyczne.
    """
    population = list(range(1, 51))
    
    # --- ZMIANA: Limit 50 ostatnich losowań ---
    recent_history = history[:50] if history else []
    
    # 1. Analiza Wag (Częstotliwość)
    weights = [1.0] * 50
    if recent_history:
        flat_list = [n for sublist in recent_history for n in sublist]
        counts = Counter(flat_list)
        # Wzmacniamy liczby częste potęgowaniem
        weights = [(counts.get(i, 0) + 1)**1.7 for i in population]
        
    last_draw = recent_history[0] if recent_history else []
    
    # 2. Symulacja Monte Carlo
    best_set = []
    
    for _ in range(5000):
        candidates = set()
        
        # A) Prawo Serii (30% szans na powtórzenie 1 liczby z ostatniego losowania)
        if last_draw and random.random() < 0.3:
            candidates.add(random.choice(last_draw))
            
        # B) Losowanie Ważone (Hot Numbers)
        while len(candidates) < 5:
            c = random.choices(population, weights=weights, k=1)[0]
            candidates.add(c)
            
        nums = sorted(list(candidates))
        
        # --- FILTRY (Sito) ---
        
        # 1. Suma (Optimum dla 5/50 to 95-160)
        s_sum = sum(nums)
        if not (95 <= s_sum <= 160): continue
        
        # 2. Parzystość (Odrzucamy skrajności 5:0 i 0:5)
        even = sum(1 for n in nums if n % 2 == 0)
        if even == 0 or even == 5: continue
        
        # 3. Delta (Odstępy między liczbami)
        # Unikamy np. 1,2,3,4,5 (za ciasno) lub 1,15,30,45,50 (za luźno)
        deltas = [nums[i+1] - nums[i] for i in range(4)]
        if all(d <= 2 for d in deltas): continue 
        if all(d > 20 for d in deltas): continue 
        
        # Jeśli przeszedł filtry -> Mamy to!
        best_set = nums
        break
        
    if not best_set:
        best_set = sorted(random.sample(population, 5))
        
    return best_set

def generate_euro_numbers(history):
    """
    Generuje 2 liczby z 12 (Baza 2).
    Logika: Hot Numbers (ostatnie 50).
    """
    population = list(range(1, 13))
    
    # --- ZMIANA: Limit 50 ostatnich losowań ---
    recent_history = history[:50] if history else []
    
    weights = [1.0] * 12
    if recent_history:
        flat_list = [n for sublist in recent_history for n in sublist]
        counts = Counter(flat_list)
        # Dla małego zakresu (1-12) wagi są kluczowe
        weights = [(counts.get(i, 0) + 1)**1.5 for i in population]
        
    candidates = set()
    while len(candidates) < 2:
        c = random.choices(population, weights=weights, k=1)[0]
        candidates.add(c)
        
    return sorted(list(candidates))

# ==============================================================================
# 5. INTERFEJS UŻYTKOWNIKA
# ==============================================================================

st.markdown("<h1>🇪🇺 EUROJACKPOT 777 🇪🇺</h1>", unsafe_allow_html=True)
st.markdown("<h3>ALGORYTM TREND 50</h3>", unsafe_allow_html=True)

# --- SPRAWDZANIE PLIKÓW ---
col1, col2 = st.columns(2)

with col1:
    main_draws, main_ok = parse_pdf_data("baza1.pdf", 50, 5)
    # Bierzemy tylko 50 do analizy, ale wyświetlamy ile jest w pliku
    draws_count_main = len(main_draws)
    status_cls = "status-ok" if main_ok else "status-err"
    status_txt = f"BAZA 1: {draws_count_main} WPISÓW" if main_ok else "BRAK PLIKU BAZA1.PDF"
    st.markdown(f'<div class="file-status {status_cls}">{status_txt}</div>', unsafe_allow_html=True)

with col2:
    euro_draws, euro_ok = parse_pdf_data("baza2.pdf", 12, 2)
    draws_count_euro = len(euro_draws)
    status_cls = "status-ok" if euro_ok else "status-err"
    status_txt = f"BAZA 2: {draws_count_euro} WPISÓW" if euro_ok else "BRAK PLIKU BAZA2.PDF"
    st.markdown(f'<div class="file-status {status_cls}">{status_txt}</div>', unsafe_allow_html=True)

# --- PRZYCISK GENERUJĄCY ---

if st.button("🎰 OBLICZ SZCZĘŚLIWE LICZBY"):
    if not main_ok or not euro_ok:
        st.error("⚠️ BŁĄD KRYTYCZNY: Brakuje plików PDF. Wgraj 'baza1.pdf' i 'baza2.pdf'.")
    else:
        # Generowanie
        with st.spinner("Analiza ostatnich 50 losowań..."):
            lucky_main = generate_main_numbers(main_draws)
            lucky_euro = generate_euro_numbers(euro_draws)
        
        # Wyświetlanie wyników
        st.markdown("<br>", unsafe_allow_html=True)
        
        # Kontener na kule
        html_main = "".join([f'<div class="ball-main">{n}</div>' for n in lucky_main])
        html_euro = "".join([f'<div class="ball-euro">{n}</div>' for n in lucky_euro])
        
        st.markdown(f"""
        <div style="text-align: center;">
            <div class="ball-container">
                {html_main}
            </div>
            <div class="ball-container" style="justify-content: center; margin-top: 15px;">
                {html_euro}
            </div>
        </div>
        """, unsafe_allow_html=True)
        
        # Statystyki użyte do obliczeń
        st.markdown("<br>", unsafe_allow_html=True)
        c1, c2, c3 = st.columns(3)
        c1.metric("Analiza Trendu", "Ostatnie 50 gier")
        c2.metric("Suma Głównych", sum(lucky_main))
        c3.metric("Układ Parzystości", f"{sum(1 for n in lucky_main if n%2==0)} P / {sum(1 for n in lucky_main if n%2!=0)} NP")

# --- STOPKA ---
st.markdown("""
<div class="info-box">
    Aplikacja działa w trybie offline na podstawie plików lokalnych.
    Algorytm analizuje wyłącznie ostatnie 50 wyników, aby wykryć aktualne trendy.<br>
    © 2026 EuroJackpot Analyzer
</div>
""", unsafe_allow_html=True)
    
