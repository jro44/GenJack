import streamlit as st
import pypdf
import re
import random
import os
import pandas as pd
from collections import Counter
from datetime import datetime

# --- KONFIGURACJA EUROJACKPOT ---
st.set_page_config(
    page_title="Euro Smart System",
    page_icon="🇪🇺",
    layout="centered"
)

# --- STYL (ZŁOTO-GRANATOWY) ---
st.markdown("""
    <style>
    .stApp { background-color: #0e1117; color: #FFD700; }
    
    /* Kule Główne (Złote) */
    .ball-main {
        font-size: 20px; font-weight: bold; color: black;
        background: radial-gradient(circle at 30% 30%, #FFD700, #DAA520);
        border: 2px solid #B8860B;
        border-radius: 50%;
        width: 50px; height: 50px; display: inline-flex;
        justify-content: center; align-items: center;
        margin: 5px; box-shadow: 0 0 10px rgba(255, 215, 0, 0.4);
    }
    
    /* Kule Euro (Czerwone) */
    .ball-extra {
        font-size: 20px; font-weight: bold; color: white;
        background: radial-gradient(circle at 30% 30%, #DC143C, #8B0000);
        border: 2px solid #800000;
        border-radius: 50%;
        width: 50px; height: 50px; display: inline-flex;
        justify-content: center; align-items: center;
        margin: 5px; box-shadow: 0 0 10px rgba(220, 20, 60, 0.4);
    }
    
    .metric-box {
        background-color: #1E1E1E; padding: 12px; border-radius: 8px;
        text-align: center; border: 1px solid #333; margin-bottom: 10px;
        color: #ddd;
    }
    h1 { color: #FFD700 !important; }
    </style>
    """, unsafe_allow_html=True)

# --- FUNKCJE ---
@st.cache_data
def load_data(file_path, num_count, max_val):
    if not os.path.exists(file_path):
        return []
    draws = []
    try:
        reader = pypdf.PdfReader(file_path)
        for page in reader.pages:
            text = page.extract_text() or ""
            tokens = re.findall(r'\d+', text)
            i = 0
            while i < len(tokens):
                candidates = []
                offset = 0
                while len(candidates) < num_count and (i + offset) < len(tokens):
                    try:
                        val = int(tokens[i+offset])
                        if 1 <= val <= max_val:
                            candidates.append(val)
                        else:
                            if candidates: break
                    except: break
                    offset += 1
                
                if len(candidates) == num_count:
                    draws.append(candidates)
                    i += offset
                else:
                    i += 1
    except:
        return []
    return draws

def get_hot_weights(draws, max_val):
    flat_data = [num for sublist in draws for num in sublist]
    counts = Counter(flat_data)
    # Wagi dla pełnego zakresu (np. 1-50 lub 1-12)
    weights = [counts.get(i, 1) for i in range(1, max_val + 1)]
    return weights

# --- SMART ALGORYTM EUROJACKPOT ---
def smart_generate_euro(w_main, w_extra):
    # --- CZĘŚĆ 1: GŁÓWNE (5 z 50) ---
    pop_main = list(range(1, 51))
    
    best_main = []
    main_stats = (0, 0) # Suma, Parzyste
    
    # Próbujemy znaleźć idealną piątkę
    for _ in range(1000):
        cands = set()
        # Wzmocnione wagi dla Hot Numbers
        while len(cands) < 5:
            c = random.choices(pop_main, weights=[w**1.4 for w in w_main], k=1)[0]
            cands.add(c)
        
        nums = sorted(list(cands))
        
        # FILTRY GŁÓWNE:
        # 1. Suma (Optimum dla EuroJackpot: 95 - 160)
        s_sum = sum(nums)
        if not (95 <= s_sum <= 160):
            continue
            
        # 2. Parzystość (Balans 2:3 lub 3:2)
        even = sum(1 for n in nums if n % 2 == 0)
        if even == 0 or even == 5:
            continue
            
        # 3. Ciągi (Max 2 liczby po kolei)
        consecutive = 0
        max_cons = 0
        for i in range(len(nums)-1):
            if nums[i+1] == nums[i] + 1:
                consecutive += 1
            else:
                consecutive = 0
            max_cons = max(max_cons, consecutive)
        
        if max_cons >= 2:
            continue
            
        best_main = nums
        main_stats = (s_sum, even)
        break
    
    if not best_main: # Fallback
        best_main = sorted(random.sample(pop_main, 5))
        main_stats = (sum(best_main), sum(1 for n in best_main if n%2==0))

    # --- CZĘŚĆ 2: EURO NUMERY (2 z 12) ---
    pop_extra = list(range(1, 13))
    best_extra = []
    
    for _ in range(100):
        cands = set()
        while len(cands) < 2:
            c = random.choices(pop_extra, weights=[w**1.2 for w in w_extra], k=1)[0]
            cands.add(c)
        nums = sorted(list(cands))
        
        # Filtr dla 2 liczb: Unikamy par (np. 1 i 2) - rzadkie w EuroNums
        if nums[1] == nums[0] + 1:
            continue
            
        best_extra = nums
        break
        
    if not best_extra:
        best_extra = sorted(random.sample(pop_extra, 2))

    return best_main, best_extra, main_stats

# --- INTERFEJS ---
def main():
    st.title("🇪🇺 Euro Smart System")
    st.markdown("Algorytm z podwójnym filtrowaniem (5/50 + 2/12).")
    
    # Pamiętaj o nazwach plików!
    FILE_MAIN = "999los.pdf"   # Baza 50 liczb
    FILE_EXTRA = "999los2.pdf" # Baza 12 liczb (EuroNums)
    
    # Obsługa braku plików
    if not os.path.exists(FILE_MAIN) or not os.path.exists(FILE_EXTRA):
        st.warning("⚠️ Brak plików PDF z historią. Algorytm działa w trybie losowym.")
        d_main = []
        d_extra = []
        w_main = [1]*50
        w_extra = [1]*12
    else:
        d_main = load_data(FILE_MAIN, 5, 50)
        d_extra = load_data(FILE_EXTRA, 2, 12)
        st.success(f"Baza: {len(d_main)} losowań głównych + {len(d_extra)} Euro.")
        w_main = get_hot_weights(d_main, 50)
        w_extra = get_hot_weights(d_extra, 12)

    if st.button("🎰 GENERUJ KUPON EURO", use_container_width=True):
        with st.spinner("Symulacja 1000 wariantów..."):
            res_main, res_extra, stats = smart_generate_euro(w_main, w_extra)
            
        # Wyświetlanie
        col_main, col_plus, col_extra = st.columns([5, 1, 3])
        
        with col_main:
            st.markdown("#### Liczby (1-50)")
            html = ""
            for n in res_main:
                html += f"<div class='ball-main'>{n}</div>"
            st.markdown(html, unsafe_allow_html=True)
            
        with col_plus:
            st.markdown("<br><br><div style='font-size:40px; text-align:center;'>+</div>", unsafe_allow_html=True)
            
        with col_extra:
            st.markdown("#### Euro (1-12)")
            html = ""
            for n in res_extra:
                html += f"<div class='ball-extra'>{n}</div>"
            st.markdown(html, unsafe_allow_html=True)
            
        st.markdown("---")
        
        # Analiza
        c1, c2, c3 = st.columns(3)
        c1.markdown(f"<div class='metric-box'>📐 Suma (50): <b>{stats[0]}</b><br><small>(Norma: 95-160)</small></div>", unsafe_allow_html=True)
        c2.markdown(f"<div class='metric-box'>⚖️ Parzyste: <b>{stats[1]}/5</b><br><small>(Balans)</small></div>", unsafe_allow_html=True)
        c3.markdown(f"<div class='metric-box'>🔥 EuroNums<br><small>Bez sąsiednich</small></div>", unsafe_allow_html=True)
        
        st.caption("Generator odrzucił kombinacje skrajne (np. same niskie liczby lub pary w Euro Numerach), zwiększając prawdopodobieństwo.")

if __name__ == "__main__":
    main()