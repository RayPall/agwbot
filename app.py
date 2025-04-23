"""
Streamlit aplikace pro výběr 4 nových článků z blogu iDoklad za předchozí měsíc
(a vynechání již použitých) a následné vygenerování textu e‑mailu.

Aplikace již **neodesílá** e‑mail – pouze zobrazí předmět a tělo připravené zprávy,
abys je mohl(a) ručně zkopírovat nebo předat dál.

Není potřeba nastavovat žádné SMTP údaje ani secrets.
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
HISTORY_FILE = Path("sent_posts.json")  # Lokální soubor s již využitými články
MAX_ARTICLES = 4
RECIPIENT_EMAIL = "anna.gwiltova@seyfor.com"

# České názvy měsíců (indexy 1‑12)
CZECH_MONTHS = [
    "",  # dummy, aby leden měl index 1
    "leden", "únor", "březen", "duben", "květen", "červen",
    "červenec", "srpen", "září", "říjen", "listopad", "prosinec",
]

############################################################
#  Pomocné funkce
############################################################

def previous_month(ref: date | None = None) -> tuple[int, int]:
    """Vrátí (rok, měsíc) předchozího měsíce vzhledem k datu *ref* (nebo dnešku)."""
    if ref is None:
        ref = date.today()
    first_this_month = ref.replace(day=1)
    last_prev_month = first_this_month - timedelta(days=1)
    return last_prev_month.year, last_prev_month.month


def load_history() -> dict:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            return {}
    return {}


def save_history(data: dict) -> None:
    HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def fetch_blog_articles() -> List[Tuple[str, str, date]]:
    """Načte články z BLOG_URL → list (title, url, publish_date)."""
    r = requests.get(BLOG_URL, timeout=10)
    r.raise_for_status()
    soup = BeautifulSoup(r.text, "html.parser")

    out: list[tuple[str, str, date]] = []
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
        out.append((title, url, pub_date))
    return out


def select_articles(all_articles: list[tuple[str, str, date]], history: dict) -> list[tuple[str, str, date]]:
    year_prev, month_prev = previous_month()
    key = f"{year_prev}-{month_prev:02d}"
    already = set(history.get(key, []))

    filtered = [art for art in all_articles if art[2].year == year_prev and art[2].month == month_prev and art[1] not in already]
    filtered.sort(key=lambda x: x[2], reverse=True)
    return filtered[:MAX_ARTICLES]


def compose_email_body(links: list[str]) -> tuple[str, str]:
    """Vrátí (subject, body) e‑mailu v češtině."""
    year_prev, month_prev = previous_month()
    month_name = CZECH_MONTHS[month_prev]

    subject = f"iDoklad blog – tipy na články za {month_name.capitalize()} {year_prev}"

    body = (
        "Ahoj Martine,\n\n"
        f"dal bys prosím dohromady statistiky za iDoklad za {month_name} {year_prev}. Databáze kontaktů by měla být aktuální.\n\n"
        "Články bych tam dala tyto:\n" + "\n".join(links) + "\n\n"
        "S pozdravem\nAnička"
    )
    return subject, body

############################################################
#  Streamlit UI
############################################################

st.set_page_config(page_title="iDoklad Blog – generátor e‑mailu", page_icon="✉️")
st.title("✉️ iDoklad Blog – generátor e‑mailu")

with st.spinner("Načítám články …"):
    try:
        all_articles = fetch_blog_articles()
    except Exception as e:
        st.error(f"Chyba při načítání blogu: {e}")
        st.stop()

history = load_history()
selected = select_articles(all_articles, history)

if not selected:
    st.warning("Pro předchozí měsíc nejsou žádné nové články nebo už byly všechny použity.")
    st.stop()

st.subheader("Vybrané články")
links: list[str] = []
for title, url, pub_date in selected:
    st.markdown(f"- [{title}]({url}) – {pub_date:%d.%m.%Y}")
    links.append(url)

if st.button("Vygenerovat e‑mail", type="primary"):
    subject, body = compose_email_body(links)

    # zapsat do historie (simulujeme "odeslání")
    y, m = previous_month()
    key = f"{y}-{m:02d}"
    history.setdefault(key, []).extend(links)
    save_history(history)

    st.success("E‑mail byl vygenerován!")
    st.markdown("### Předmět")
    st.code(subject, language="text")
    st.markdown("### Text e‑mailu")
    st.text_area("", body, height=300)
