"""
Streamlit aplikace pro výběr článků z blogu iDoklad a vygenerování textu e‑mailu.

✔️ Uživatel si nyní může vybrat libovolný měsíc / rok (posledních 5 let). 
✔️ Aplikace vybere max. 4 články zvoleného období, které ještě nebyly použity, 
   a zobrazí předmět i tělo e‑mailu.
✔️ Žádný e‑mail se neodesílá, SMTP není potřeba.
"""

from __future__ import annotations

import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Tuple

import requests
import streamlit as st
from bs4 import BeautifulSoup

############################################################
#  Konfigurace
############################################################
BLOG_URL = "https://www.idoklad.cz/blog"
HISTORY_FILE = Path("sent_posts.json")  # lokální soubor s již využitými články
MAX_ARTICLES = 4
RECIPIENT_EMAIL = "anna.gwiltova@seyfor.com"

# České názvy měsíců – indexy 1‑12
CZECH_MONTHS = [
    "",  # dummy, aby leden měl index 1
    "leden", "únor", "březen", "duben", "květen", "červen",
    "červenec", "srpen", "září", "říjen", "listopad", "prosinec",
]

############################################################
#  Pomocné funkce
############################################################

def previous_month(ref: date | None = None) -> tuple[int, int]:
    """Vrátí (rok, měsíc) předchozího měsíce vzhledem k *ref* (nebo dnešku)."""
    if ref is None:
        ref = date.today()
    first_this_month = ref.replace(day=1)
    last_prev = first_this_month - timedelta(days=1)
    return last_prev.year, last_prev.month


def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_history(data: dict) -> None:
    HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_blog_articles() -> List[Tuple[str, str, date]]:
    """Načte všechny články z BLOG_URL → (title, url, publish_date)."""
    resp = requests.get(BLOG_URL, timeout=10)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    articles: list[tuple[str, str, date]] = []
    for art in soup.find_all("article"):
        a_tag = art.find("a", href=True)
        if not a_tag:
            continue
        url = a_tag["href"]
        title = a_tag.get_text(strip=True)

        time_tag = art.find("time", {"datetime": re.compile(r"^\\d{4}-\\d{2}-\\d{2}$")})
        if not time_tag:
            continue
        pub_date = datetime.fromisoformat(time_tag["datetime"]).date()
        articles.append((title, url, pub_date))
    return articles


def select_articles(
    articles: list[tuple[str, str, date]],
    history: dict,
    year: int,
    month: int,
) -> list[tuple[str, str, date]]:
    """Vrátí max. 4 dosud nevybrané články pro daný rok/měsíc."""
    key = f"{year}-{month:02d}"
    already = set(history.get(key, []))

    filtered = [a for a in articles if a[2].year == year and a[2].month == month and a[1] not in already]
    filtered.sort(key=lambda x: x[2], reverse=True)
    return filtered[:MAX_ARTICLES]


def compose_email_body(links: list[str], year: int, month: int) -> tuple[str, str]:
    """Sestaví (subject, body) e‑mailu podle zadaného roku/měsíce."""
    month_name = CZECH_MONTHS[month]
    subject = f"iDoklad blog – tipy na články za {month_name.capitalize()} {year}"
    body = (
        "Ahoj Martine,\n\n"
        f"dal bys prosím dohromady statistiky za iDoklad za {month_name} {year}. Databáze kontaktů by měla být aktuální.\n\n"
        "Články bych tam dala tyto:\n" + "\n".join(links) + "\n\n"
        "S pozdravem\nAnička"
    )
    return subject, body

############################################################
#  Streamlit UI
############################################################

st.set_page_config(page_title="iDoklad Blog – generátor e‑mailu", page_icon="✉️")
st.title("✉️ iDoklad Blog – generátor e‑mailu")

# Načtení článků
with st.spinner("Načítám články …"):
    try:
        all_articles = fetch_blog_articles()
    except Exception as e:
        st.error(f"Chyba při načítání blogu: {e}")
        st.stop()

history = load_history()

# ▼▼  Volba roku a měsíce  ▼▼

def last_n_months(n: int = 12) -> list[tuple[int, int]]:
    ref = date.today().replace(day=15)  # fix middle to avoid DST issues
    res: list[tuple[int, int]] = []
    for _ in range(n):
        res.append((ref.year, ref.month))
        ref = (ref.replace(day=1) - timedelta(days=1)).replace(day=15)
    return res

months_options = last_n_months(60)  # posledních 5 let (~60 měsíců)

# Výchozí – předchozí měsíc
init_year, init_month = previous_month()

def fmt(y_m: tuple[int, int]) -> str:
    y, m = y_m
    return f"{CZECH_MONTHS[m].capitalize()} {y}"

selected_ym = st.selectbox(
    "Zvol měsíc, ze kterého vybrat články:",
    options=months_options,
    format_func=fmt,
    index=months_options.index((init_year, init_month)),
)
sel_year, sel_month = selected_ym

# ▼▼  Výběr článků  ▼▼
selected_articles = select_articles(all_articles, history, sel_year, sel_month)

if not selected_articles:
    st.warning("Pro zvolený měsíc nejsou k dispozici žádné nové (dosud neodeslané) články.")
    st.stop()

st.subheader("Vybrané články")
links: list[str] = []
for title, url, pub_date in selected_articles:
    st.markdown(f"- [{title}]({url}) – {pub_date:%d.%m.%Y}")
    links.append(url)

# ▼▼  Generování e‑mailu  ▼▼
if st.button("Vygenerovat e‑mail", type="primary"):
    subject, body = compose_email_body(links, sel_year, sel_month)

    # uložit do historie (simulace odeslání)
    key = f"{sel_year}-{sel_month:02d}"
    history.setdefault(key, []).extend(links)
    save_history(history)

    st.success("E‑mail byl vygenerován!")
    st.markdown("### Předmět")
    st.code(subject, language="text")
    st.markdown("### Text e‑mailu")
    st.text_area("", body, height=300)
