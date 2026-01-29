import streamlit as st
import pypdf
import re
import random
import os
import pandas as pd
from collections import Counter
from datetime import datetime

# --- 1. KONFIGURACJA STRONY (Złoto-Czarna dla EuroJackpot) ---
st.set_page_config(
    page_title="EuroMaster 999",
    page_icon="🇪🇺",
    layout="wide"
)

# Nazwy plików (takie jak podałeś)
FILE_MAIN = "999los.pdf"  # Baza 5 liczb (1-50)
FILE_EXTRA = "999los2.pdf"  # Baza 2 liczb (1-12)


# --- 2. STYLIZACJA (ZŁOTO I GRANAT) ---
def local_css():
    st.markdown("""
    <style>
    /* Tło - ciemny granat */
    .stApp {
        background-color: #0e1117;
        color: #FFD700;
    }

    /* Nagłówki - Złote */
    h1, h2, h3 {
        color: #FFD700 !important; /* Gold */
        font-family: 'Arial Black', sans-serif;
    }

    /* Przyciski - Złote z czarnym tekstem */
    div.stButton > button {
        background-color: #FFD700 !important;
        color: #000000 !important;
        border-radius: 8px;
        font-weight: bold;
        border: 2px solid #DAA520 !important;
        font-size: 20px;
    }
    div.stButton > button:hover {
        background-color: #FFC125 !important;
        transform: scale(1.05);
    }

    /* Ramki sukcesu */
    .stSuccess {
        background-color: #1E1E1E;
        border-left: 5px solid #FFD700;
        color: #FFD700;
    }

    /* Sidebar */
    [data-testid="stSidebar"] {
        background-color: #111;
        border-right: 1px solid #333;
    }

    /* Kule z liczbami */
    .ball {
        display: inline-block;
        width: 50px;
        height: 50px;
        line-height: 50px;
        border-radius: 50%;
        text-align: center;
        font-weight: bold;
        font-size: 20px;
        margin: 5px;
        box-shadow: 2px 2px 5px rgba(0,0,0,0.5);
    }
    .ball-main {
        background: radial-gradient(circle at 30% 30%, #FFD700, #DAA520);
        color: black;
        border: 2px solid #B8860B;
    }
    .ball-extra {
        background: radial-gradient(circle at 30% 30%, #DC143C, #8B0000); /* Czerwony dla EuroNums */
        color: white;
        border: 2px solid #800000;
    }
    </style>
    """, unsafe_allow_html=True)


local_css()


# --- 3. PARSER DANYCH ---
@st.cache_data
def parse_pdf_data(file_path, count_per_draw, max_val):
    """
    Uniwersalna funkcja do wyciągania liczb z PDF.
    - count_per_draw: ile liczb szukamy w jednym ciągu (5 lub 2)
    - max_val: maksymalna wartość liczby (50 lub 12)
    """
    if not os.path.exists(file_path):
        return []

    draws = []
    try:
        reader = pypdf.PdfReader(file_path)
        for page in reader.pages:
            text = page.extract_text() or ""
            # Znajdź wszystkie liczby w tekście
            tokens = re.findall(r'\d+', text)

            i = 0
            while i < len(tokens):
                # Próbujemy znaleźć ciąg 'count_per_draw' liczb mieszczących się w zakresie
                candidates = []
                offset = 0

                # Szukamy ciągu liczb (pomijamy te, które są za duże, bo to mogą być ID losowania)
                # Ale w EuroJackpot numery są po ID.
                # Prosta heurystyka: Bierzemy liczby, które pasują do zakresu.

                while len(candidates) < count_per_draw and (i + offset) < len(tokens):
                    try:
                        val = int(tokens[i + offset])
                        if 1 <= val <= max_val:
                            candidates.append(val)
                        else:
                            # Liczba poza zakresem (np. ID losowania lub rok), przerywamy serię
                            if candidates:  # Jeśli mieliśmy już jakieś, a trafiliśmy na śmieć -> odrzucamy serię
                                break
                    except:
                        break
                    offset += 1

                if len(candidates) == count_per_draw:
                    draws.append(candidates)
                    i += offset  # Przesuwamy wskaźnik
                else:
                    i += 1  # Próbujemy od następnego tokena
    except Exception as e:
        st.error(f"Błąd odczytu {file_path}: {e}")

    return draws


# --- 4. LOGIKA GENERATORA (WAŻONA CZĘSTOTLIWOŚCIĄ) ---
def generate_euro_set(draws_main, draws_extra):
    # 1. Analiza Głównych (1-50)
    flat_main = [num for sublist in draws_main for num in sublist]
    counts_main = Counter(flat_main)

    # 2. Analiza Dodatkowych (1-12)
    flat_extra = [num for sublist in draws_extra for num in sublist]
    counts_extra = Counter(flat_extra)

    # 3. Losowanie ważone (Im częściej liczba padała, tym większa szansa teraz)
    # Dla liczb głównych
    population_main = list(range(1, 51))
    weights_main = [counts_main.get(n, 1) for n in population_main]  # Min waga 1

    # Losujemy 5 bez powtórzeń (używając wag)
    # random.choices zwraca z powtórzeniami, więc musimy pętlić
    chosen_main = set()
    while len(chosen_main) < 5:
        # Podbijamy wagi jeszcze bardziej (kwadrat), żeby faworyzować "częste"
        draw = random.choices(population_main, weights=[w ** 1.5 for w in weights_main], k=1)[0]
        chosen_main.add(draw)

    # Dla liczb dodatkowych (Euro Numbers)
    population_extra = list(range(1, 13))
    weights_extra = [counts_extra.get(n, 1) for n in population_extra]

    chosen_extra = set()
    while len(chosen_extra) < 2:
        draw = random.choices(population_extra, weights=[w ** 1.5 for w in weights_extra], k=1)[0]
        chosen_extra.add(draw)

    return sorted(list(chosen_main)), sorted(list(chosen_extra))


# --- 5. PRZYGOTOWANIE PLIKU TXT ---
def get_txt_file(history):
    txt = "--- EURO MASTER 999 - TWOJE TYPY ---\n"
    txt += f"Data utworzenia: {datetime.now().strftime('%Y-%m-%d %H:%M')}\n\n"
    for item in history:
        txt += f"[{item['Time']}] Główne: {item['Main']} + Euro: {item['Extra']}\n"
    return txt


# --- 6. GŁÓWNA APLIKACJA ---
def main():
    if 'euro_history' not in st.session_state:
        st.session_state['euro_history'] = []

    st.title("🇪🇺 EuroMaster 999")
    st.markdown("**Generator oparty na prawdopodobieństwie historycznym.**")
    st.markdown("Algorytm analizuje, które liczby wypadają najczęściej i zwiększa ich szansę w Twoim losowaniu.")

    # Wczytanie danych
    with st.spinner("Analiza baz danych PDF..."):
        data_main = parse_pdf_data(FILE_MAIN, 5, 50)
        data_extra = parse_pdf_data(FILE_EXTRA, 2, 12)

    if not data_main or not data_extra:
        st.error("⚠️ Brak plików PDF (999los.pdf lub 999los2.pdf) w repozytorium!")
        return

    # Wyświetlenie statystyk bazy
    c1, c2, c3 = st.columns(3)
    c1.metric("Baza Losowań (5 z 50)", len(data_main))
    c2.metric("Baza Losowań (2 z 12)", len(data_extra))
    c3.success("System Gotowy")

    st.divider()

    # Przycisk Generowania
    col_btn, col_res = st.columns([1, 2])

    with col_btn:
        st.markdown("<br>", unsafe_allow_html=True)
        if st.button("🎰 GENERUJ KUPON 🎰", use_container_width=True):
            main_nums, extra_nums = generate_euro_set(data_main, data_extra)

            # Zapis do historii
            st.session_state['euro_history'].insert(0, {
                "Time": datetime.now().strftime("%H:%M:%S"),
                "Main": str(main_nums),
                "Extra": str(extra_nums)
            })

            # Wyświetlenie wyniku (Animacja kul)
            html_balls = ""
            for n in main_nums:
                html_balls += f"<div class='ball ball-main'>{n}</div>"
            html_balls += "<span style='font-size:30px; margin:0 10px;'>+</span>"
            for n in extra_nums:
                html_balls += f"<div class='ball ball-extra'>{n}</div>"

            with col_res:
                st.markdown(html_balls, unsafe_allow_html=True)
                st.caption("Złote: 1-50 | Czerwone: 1-12")

    # Sekcja Historii i Pobierania
    st.divider()
    st.subheader("📜 Twoje wygenerowane kupony")

    if st.session_state['euro_history']:
        # Przycisk pobierania
        st.download_button(
            label="💾 POBIERZ WYNIKI (.txt)",
            data=get_txt_file(st.session_state['euro_history']),
            file_name="EuroMaster_Kupony.txt",
            mime="text/plain"
        )

        # Tabela
        df_hist = pd.DataFrame(st.session_state['euro_history'])
        st.table(df_hist)
    else:
        st.info("Kliknij GENERUJ, aby stworzyć swój pierwszy zestaw.")


if __name__ == "__main__":
    main()