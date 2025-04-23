"""
Streamlit aplikace pro výběr článků z blogu iDoklad (přes RSS feed) a vygenerování
textu e‑mailu.

### Co se změnilo
* Namísto scrapování HTML se nyní používá **RSS feed** poskytnutý uživatelem:
  https://rss.app/feeds/2IEcDYoo7hF8d27H.xml → zaručená detekce všech článků.
* Ostatní funkce zůstávají: výběr měsíce, kontrola již použitých článků,
  generování předmětu a těla e‑mailu.

> **Tip k nasazení:** Přidej do `requirements.txt` také `feedparser` ( `feedparser>=6` ).
"""

from __future__ import annotations

import json
import email.utils as eut
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Tuple

import feedparser  # RSS parser
import requests
import streamlit as st

############################################################
#  Konfigurace
############################################################
RSS_FEED_URL = "https://rss.app/feeds/2IEcDYoo7hF8d27H.xml"
HISTORY_FILE = Path("sent_posts.json")  # uchovává URL už použitých článků
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
    """Načte články z RSS feedu → (title, url, publish_date)."""
    # U feedparser není nutné requests; použijeme interní fetch s fallbackem
    feed = feedparser.parse(RSS_FEED_URL)
    if feed.bozo:
        # Pokud parsování selže, zkusíme přes requests (proxy/firewall) a feedparser.parse(obj)
        resp = requests.get(RSS_FEED_URL, timeout=10)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

    articles: list[tuple[str, str, date]] = []
    for entry in feed.entries:
        title = entry.get("title", "Neznámý titulek")
        url = entry.get("link")
        if not url:
            continue
        published_raw = entry.get("published") or entry.get("pubDate") or entry.get("updated")
        if not published_raw:
            continue
        try:
            dt = eut.parsedate_to_datetime(published_raw)
        except (TypeError, ValueError):
            continue
        articles.append((title, url, dt.date()))

    return articles


def select_articles(articles: list[tuple[str, str, date]], history: dict, year: int, month: int) -> list[tuple[str, str, date]]:
    key = f"{year}-{month:02d}"
    used = set(history.get(key, []))
    candidates = [a for a in articles if a[2].year == year and a[2].month == month and a[1] not in used]
    candidates.sort(key=lambda x: x[2], reverse=True)
    return candidates[:MAX_ARTICLES]


def compose_email_body(links: list[str], year: int, month: int) -> tuple[str, str]:
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

st.set_page_config(page_title="iDoklad Blog – generátor e‑mailu (RSS)", page_icon="✉️")
st.title("✉️ iDoklad Blog – generátor e‑mailu (RSS)")

# Načtení článků přes RSS
with st.spinner("Načítám RSS feed …"):
    try:
        all_articles = fetch_blog_articles()
    except Exception as exc:
        st.error(f"Chyba při načítání RSS feedu: {exc}")
        st.stop()

history = load_history()

# ▼▼  Sestavení seznamu měsíců, které mají nové (nevyužité) články  ▼▼

def months_back(limit: int = 60) -> list[tuple[int, int]]:
    ref = date.today().replace(day=15)
    months: list[tuple[int, int]] = []
    for _ in range(limit):
        months.append((ref.year, ref.month))
        ref = (ref.replace(day=1) - timedelta(days=1)).replace(day=15)
    return months

valid_months: list[tuple[int, int]] = []
article_cache: dict[tuple[int, int], list[tuple[str, str, date]]] = {}
for y, m in months_back(60):
    key = (y, m)
    article_cache[key] = select_articles(all_articles, history, y, m)
    if article_cache[key]:
        valid_months.append((y, m))

if not valid_months:
    st.info("Nenalezeny žádné nové (dosud neodeslané) články. 💤")
    st.stop()

selected_ym = st.selectbox(
    "Zvol měsíc, ze kterého vybrat články:",
    options=valid_months,
    format_func=lambda ym: f"{CZECH_MONTHS[ym[1]].capitalize()} {ym[0]}",
    index=0,
)
sel_year, sel_month = selected_ym
selected_articles = article_cache[(sel_year, sel_month)]

# ▼▼  Výpis vybraných článků  ▼▼
st.subheader("Vybrané články")
for title, url, pub_date in selected_articles:
    st.markdown(f"- [{title}]({url}) – {pub_date:%d.%m.%Y}")

# ▼▼  Generování e‑mailu  ▼▼
if st.button("Vygenerovat e‑mail", type="primary"):
    links = [url for _title, url, _ in selected_articles]
    subject, body = compose_email_body(links, sel_year, sel_month)

    # zapsat do historie → simulace odeslání
    hist_key = f"{sel_year}-{sel_month:02d}"
    history.setdefault(hist_key, []).extend(links)
    save_history(history)

    st.success("E‑mail byl vygenerován!")
    st.markdown("### Předmět")
    st.code(subject, language="text")
    st.markdown("### Text e‑mailu")
    st.text_area("", body, height=300)
