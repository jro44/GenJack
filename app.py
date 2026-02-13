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
    page_title="Saloon Lotto 777 (Offline)",
    page_icon="🤠",
    layout="wide",
    initial_sidebar_state="collapsed"
)

# ==============================================================================
# 2. STYL WESTERN (CSS)
# ==============================================================================

st.markdown("""
    <style>
    .stApp {
        background-color: #2b2118;
        background-image: radial-gradient(#3d2e22 2px, transparent 2px);
        background-size: 20px 20px;
        color: #f0e6d2;
        font-family: 'Courier New', Courier, monospace;
    }
    h1, h2, h3 {
        color: #e6b800 !important;
        text-shadow: 2px 2px 0px #000;
        font-family: 'Georgia', serif;
        text-transform: uppercase;
        letter-spacing: 2px;
    }
    .wanted-poster {
        background-color: #fdf5e6;
        color: #3e2723;
        border: 4px solid #3e2723;
        padding: 15px;
        border-radius: 2px;
        font-family: 'Courier New', monospace;
        text-align: center;
        margin-bottom: 20px;
        box-shadow: 5px 5px 15px rgba(0,0,0,0.5);
        background-image: url("https://www.transparenttextures.com/patterns/aged-paper.png");
    }
    .ball {
        display: inline-flex;
        justify-content: center;
        align-items: center;
        width: 50px;
        height: 50px;
        border-radius: 50%;
        background: radial-gradient(circle at 30% 30%, #ffd700, #b8860b);
        color: #2b2118;
        font-weight: bold;
        font-size: 20px;
        border: 3px solid #5c4033;
        margin: 4px;
        box-shadow: 2px 4px 8px rgba(0,0,0,0.6);
        font-family: 'Arial', sans-serif;
    }
    .ball-euro {
        background: radial-gradient(circle at 30% 30%, #cd5c5c, #8b0000);
        color: white;
        border-color: #5c4033;
    }
    .slot-machine {
        background-color: #4a3525;
        border: 8px solid #8B4513;
        border-radius: 15px;
        padding: 20px;
        box-shadow: inset 0 0 20px #000;
        text-align: center;
        margin-top: 20px;
    }
    div.stButton > button {
        background: linear-gradient(to bottom, #d4af37 5%, #a67c00 100%);
        background-color: #d4af37;
        border-radius: 10px;
        border: 2px solid #5c4033;
        color: #2b2118;
        font-family: 'Georgia', serif;
        font-weight: bold;
        font-size: 20px;
        padding: 10px 24px;
        text-shadow: 0px 1px 0px #ffffff;
        box-shadow: 0px 4px 0px #5c4033;
        transition: all 0.1s;
        width: 100%;
    }
    div.stButton > button:active {
        transform: translateY(4px);
        box-shadow: 0px 0px 0px #5c4033;
    }
    .result-row {
        background-color: #3d2e22;
        padding: 10px;
        margin: 5px 0;
        border-left: 5px solid #e6b800;
        border-radius: 4px;
    }
    div[data-testid="stMetricValue"] {
        color: #e6b800;
    }
    </style>
    """, unsafe_allow_html=True)

# ==============================================================================
# 3. OSTRZEŻENIE NA START
# ==============================================================================

st.markdown("""
<div class="wanted-poster">
    <h3>⚠ SYSTEM PLIKÓW LOKALNYCH (PDF) ⚠</h3>
    <p>Tryb manualny: Pobieranie z osobnych plików (np. <b>wynlotto.pdf</b>).</p>
    <p>Algorytm: <b>Trend 100 + Delta + Repetition</b>.</p>
    <p>Pamiętaj: Dom (Kasyno) zawsze ma przewagę. Graj odpowiedzialnie.</p>
</div>
""", unsafe_allow_html=True)

# ==============================================================================
# 4. KONFIGURACJA GIER I PLIKÓW
# ==============================================================================

GAME_CONFIG = {
    "Lotto": {
        "filename": "wynlotto.pdf",
        "range": 49, "pick": 6, "sum_min": 100, "sum_max": 200, "has_bonus": False
    },
    "Lotto Plus": {
        "filename": "wynlotto+.pdf",
        "range": 49, "pick": 6, "sum_min": 100, "sum_max": 200, "has_bonus": False
    },
    "Multi Multi": {
        "filename": "wynmulti.pdf",
        "range": 80, "pick": 10, "sum_min": 250, "sum_max": 550, "has_bonus": False
    },
    "EuroJackpot": {
        "filename": "wynjack.pdf",
        "range": 50, "pick": 5, "sum_min": 95, "sum_max": 160, 
        "has_bonus": True, "bonus_range": 12, "bonus_pick": 2
    },
    "Szybkie 600": {
        "filename": "wyn600.pdf",
        "range": 32, "pick": 6, "sum_min": 75, "sum_max": 125, "has_bonus": False
    },
    "Keno": {
        "filename": "wynkeno.pdf",
        "range": 70, "pick": 10, "sum_min": 200, "sum_max": 500, "has_bonus": False
    },
    "Mini Lotto": {
        "filename": "wynmini.pdf",
        "range": 42, "pick": 5, "sum_min": 85, "sum_max": 135, "has_bonus": False
    },
    "Ekstra Pensja": {
        "filename": "wynpensja.pdf",
        "range": 35, "pick": 5, "sum_min": 60, "sum_max": 120, 
        "has_bonus": True, "bonus_range": 4, "bonus_pick": 1
    }
}

# ==============================================================================
# 5. READER PDF (OBSŁUGA OSOBNYCH PLIKÓW)
# ==============================================================================

def load_data_from_specific_pdf(selected_game):
    """
    Pobiera nazwę pliku z konfiguracji i czyta go w całości.
    """
    config = GAME_CONFIG[selected_game]
    filename = config["filename"]
    
    if not os.path.exists(filename):
        return [], f"BRAK PLIKU: {filename}. Wgraj go na GitHub."
    
    draws = []
    
    try:
        with pdfplumber.open(filename) as pdf:
            full_text = ""
            for page in pdf.pages:
                text = page.extract_text()
                if text:
                    full_text += text + "\n"
                
        # Podział na linie
        lines = full_text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line: continue
            
            # Prosty parser: szukamy daty i liczb w linii
            
            # 1. Wyciągamy datę (opcjonalnie, do wyświetlania)
            date_match = re.search(r'\d{2}\.\d{2}\.\d{4}', line)
            date_str = date_match.group(0) if date_match else "Wynik"
            
            # 2. Czyścimy linię z daty, żeby nie pomylić roku z kulą
            clean_line = re.sub(r'\d{2}\.\d{2}\.\d{4}', '', line)
            
            # 3. Znajdź wszystkie liczby
            numbers = [int(n) for n in re.findall(r'\b\d+\b', clean_line)]
            
            # 4. Filtrujemy liczby z zakresu gry (np. 1-49 dla Lotto)
            valid_nums = [n for n in numbers if 1 <= n <= config["range"]]
            
            # 5. Sprawdzamy czy linia ma sensowne dane (minimum liczb)
            min_req = config["pick"]
            # Dla Multi/Keno w PDF powinno być 20 liczb, mimo że gramy na 10
            if selected_game in ["Multi Multi", "Keno"]:
                min_req = 15 
            
            if len(valid_nums) >= min_req:
                draws.append({
                    "date": date_str,
                    "numbers": valid_nums
                })
                    
        if not draws:
            return [], f"Plik {filename} jest pusty lub nie zawiera poprawnych liczb."
            
        return draws, None

    except Exception as e:
        return [], f"Błąd odczytu pliku {filename}: {str(e)}"

# ==============================================================================
# 6. ALGORYTM SMART (TREND 100 + DELTA + REPETITION)
# ==============================================================================

def smart_generator_pdf(draws, game_name):
    config = GAME_CONFIG[game_name]
    population = list(range(1, config["range"] + 1))
    
    # --- LIMIT 100 NAJNOWSZYCH ---
    # Zakładamy, że w PDF najnowsze są na górze (index 0) lub na dole.
    # Zazwyczaj przy czytaniu PDF kolejność jest zachowana z góry na dół.
    # Bierzemy pierwsze 100 wierszy (zakładając że wpisujesz od najnowszego na górze)
    # Jeśli wpisujesz odwrotnie, algorytm i tak wyłapie częstotliwość.
    analysis_data = draws[:100] if draws else []
    
    # 1. WAGI (HOT NUMBERS)
    weights = [1.0] * len(population)
    if analysis_data:
        all_nums = [n for d in analysis_data for n in d['numbers']]
        counts = Counter(all_nums)
        # Potęgowanie wzmacnia liczby częste
        weights = [(counts.get(i, 0) + 1)**1.6 for i in population]

    best_set = []
    
    # 2. POWTÓRKI (Z ostatniego dostępnego losowania)
    last_draw_nums = analysis_data[0]['numbers'] if analysis_data else []
    
    # 3. SYMULACJA MONTE CARLO
    for _ in range(5000):
        candidates = set()
        
        # A) MECHANIZM POWTÓRZEŃ
        if game_name in ["Keno", "Multi Multi", "Szybkie 600"] and last_draw_nums:
            if random.random() < 0.6: 
                repeats = random.sample(last_draw_nums, k=random.randint(1, 2))
                valid_repeats = [r for r in repeats if r in population]
                candidates.update(valid_repeats[:2]) 

        # B) RESZTA WAŻONA
        while len(candidates) < config["pick"]:
            c = random.choices(population, weights=weights, k=1)[0]
            candidates.add(c)
        
        nums = sorted(list(candidates))
        
        # FILTRY
        # Delta (odstępy) - tylko dla małych zestawów
        if config["pick"] <= 10:
            deltas = [nums[i+1] - nums[i] for i in range(len(nums)-1)]
            if all(d <= 2 for d in deltas): continue 
            if all(d > 15 for d in deltas): continue 
        
        # Suma (nie dla Keno/Multi)
        if game_name not in ["Keno", "Multi Multi"]:
            s_sum = sum(nums)
            if not (config["sum_min"] <= s_sum <= config["sum_max"]): continue
            
        # Parzystość
        even = sum(1 for n in nums if n % 2 == 0)
        if even == 0 or even == config["pick"]: continue 
            
        # Ciągi
        cons_groups = 0
        current_seq = 0
        max_seq = 0
        for i in range(len(nums)-1):
            if nums[i+1] == nums[i] + 1:
                current_seq += 1
            else:
                if current_seq > 0: cons_groups += 1
                current_seq = 0
            max_seq = max(max_seq, current_seq)
        if current_seq > 0: cons_groups += 1
        
        if max_seq >= 2: continue 
        if cons_groups > 1: continue 
        
        best_set = nums
        break
        
    if not best_set: best_set = sorted(random.sample(population, config["pick"]))
        
    special_set = []
    if config["has_bonus"]:
        bonus_pop = list(range(1, config["bonus_range"] + 1))
        special_set = sorted(random.sample(bonus_pop, config["bonus_pick"]))
        
    return best_set, special_set, len(analysis_data)

# ==============================================================================
# 7. INTERFEJS UŻYTKOWNIKA
# ==============================================================================

tab_gen, tab_res = st.tabs(["🎰 GENERATOR", "📂 PODGLĄD PLIKU"])

# --- ZAKŁADKA 1: GENERATOR ---
with tab_gen:
    st.markdown("<h1 style='text-align: center;'>SALOON LOTTO 777</h1>", unsafe_allow_html=True)
    
    selected_game = st.selectbox("Wybierz grę:", list(GAME_CONFIG.keys()))
    
    # Pobieramy nazwę pliku do wyświetlenia
    current_file = GAME_CONFIG[selected_game]['filename']
    
    col_l, col_c, col_r = st.columns([1, 2, 1])
    with col_c:
        st.markdown(f"""
        <div class="slot-machine">
            <h2 style="margin:0;">{selected_game.upper()}</h2>
            <p style="color:#aaa;">Źródło: {current_file}</p>
        </div>
        """, unsafe_allow_html=True)
        
        st.markdown("<br>", unsafe_allow_html=True)
        
        if st.button("🤠 OBLICZ UKŁAD (PDF)", use_container_width=True):
            
            with st.spinner(f"Czytanie pliku {current_file}..."):
                draws, error = load_data_from_specific_pdf(selected_game)
            
            if error:
                st.error(error)
                st.info(f"Upewnij się, że plik '{current_file}' jest wgrany na GitHub.")
            else:
                with st.spinner(f"Analiza {len(draws)} losowań..."):
                    main_nums, spec_nums, count = smart_generator_pdf(draws, selected_game)
                
                st.markdown("<div style='text-align: center; margin-top: 20px;'>", unsafe_allow_html=True)
                
                html = ""
                for n in main_nums:
                    html += f"""<div class='ball'>{n}</div>"""
                st.markdown(html, unsafe_allow_html=True)
                
                if spec_nums:
                    st.markdown("<h3 style='margin:10px; color:#cd5c5c;'>+ BONUS +</h3>", unsafe_allow_html=True)
                    html_spec = ""
                    for n in spec_nums:
                        html_spec += f"""<div class='ball ball-euro'>{n}</div>"""
                    st.markdown(html_spec, unsafe_allow_html=True)
                    
                st.markdown("</div>", unsafe_allow_html=True)
                
                st.markdown("---")
                c1, c2, c3 = st.columns(3)
                c1.metric("Baza Danych", current_file)
                c2.metric("Trend (Ilość)", f"Ostatnie {count}")
                c3.metric("Suma Liczb", sum(main_nums))

# --- ZAKŁADKA 2: PODGLĄD PLIKU ---
with tab_res:
    st.markdown("### 📂 ZAWARTOŚĆ PLIKÓW")
    st.caption("Podgląd danych wczytanych z Twoich plików PDF.")
    
    view_game = st.selectbox("Pokaż zawartość pliku dla:", list(GAME_CONFIG.keys()), key="pdf_view")
    target_file = GAME_CONFIG[view_game]['filename']
    
    if st.button(f"🔄 Wczytaj {target_file}"):
        draws, error = load_data_from_specific_pdf(view_game)
        
        if error:
            st.error(error)
        else:
            st.success(f"Znaleziono {len(draws)} wpisów w pliku {target_file}")
            # Wyświetl 10 pierwszych z góry
            for d in draws[:10]:
                nums_str = ", ".join([str(n) for n in d['numbers']])
                st.markdown(f"""
                <div class="result-row">
                    <div style="color: #e6b800; font-size: 0.8em;">📄 {d['date']}</div>
                    <div style="font-size: 1.1em; font-weight: bold;">{nums_str}</div>
                </div>
                """, unsafe_allow_html=True)

st.markdown("---")
st.markdown("<div style='text-align: center; color: #888; font-size: 12px;'>Generator Szczęśliwych Cyfr © 2026 | By A.K #</div>", unsafe_allow_html=True)
                
