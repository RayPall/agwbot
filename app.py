"""
Streamlit aplikace pro výběr článků z blogu iDoklad (přes RSS feed) a vygenerování
textu e-mailu — **nyní strategicky skládá mix 4 článků** dle zadání marketingu:

| Kategorie | Cíl |
|-----------|-----|
| **ENGAGEMENT** | Atraktivní téma s potenciálem vysoké návštěvnosti |
| **CONVERSION** | Článek, který pravděpodobně navede ke koupi / upgradu |
| **EDUCATIONAL** | Edukace, budování důvěry a know-how |
| **SEASONAL** | Reaguje na aktuální období (daně, začátky roku, atd.) |

Aplikace se snaží vybrat **1 článek z každé kategorie**. Pokud pro některou není
k dispozici vhodný kandidát, doplní se jiným dostupným (podle data).

> ⚠️ Klasifikace je založená na jednoduchých klíčových slovech v titulku a
> popisu RSS položky. Pokud se netrefí, klíčová slova lze kdykoli rozšířit v diktu
> `CATEGORY_KEYWORDS`.

`requirements.txt`:
```
feedparser>=6
```
"""

from __future__ import annotations

import email.utils as eut
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import List, Tuple, Dict

import feedparser  # RSS parser
import requests
import streamlit as st

############################################################
#  Konfigurace
############################################################
RSS_FEED_URL = "https://rss.app/feeds/2IEcDYoo7hF8d27H.xml"
HISTORY_FILE = Path("sent_posts.json")  # uchovává URL již použitých článků
MAX_ARTICLES = 4
MONTHS_TO_SHOW = 3   # aktuální měsíc + 2 předchozí

# České názvy měsíců – indexy 1-12
CZECH_MONTHS = [
    "",  # dummy index
    "leden", "únor", "březen", "duben", "květen", "červen",
    "červenec", "srpen", "září", "říjen", "listopad", "prosinec",
]

# ---------- Kategorie & klíčová slova ----------
CATEGORY_ORDER = ["ENGAGEMENT", "CONVERSION", "EDUCATIONAL", "SEASONAL"]
CATEGORY_KEYWORDS: Dict[str, list[str]] = {
    "ENGAGEMENT": ["tip", "trik", "příběh", "trend", "nej", "inspir"],
    "CONVERSION": ["tarif", "funkc", "premium", "automat", "online platb", "API", "propojení"],
    "EDUCATIONAL": ["jak", "průvodce", "návod", "začínaj", "krok", "vysvětlen"],
    "SEASONAL": ["daň", "DPH", "silvestr", "váno", "uzávěr", "přiznání", "leden", "únor", "březen", "duben", "květen", "červen", "červenec", "srpen", "září", "říjen", "listopad", "prosinec"],
}

############################################################
#  Pomocné funkce
############################################################

def rerun() -> None:
    if hasattr(st, "rerun"):
        st.rerun()
    elif hasattr(st, "experimental_rerun"):
        st.experimental_rerun()


def load_history() -> Dict[str, List[str]]:
    if HISTORY_FILE.exists():
        try:
            return json.loads(HISTORY_FILE.read_text("utf-8"))
        except json.JSONDecodeError:
            pass
    return {}


def save_history(data: dict) -> None:
    HISTORY_FILE.write_text(json.dumps(data, ensure_ascii=False, indent=2), "utf-8")


def clear_history() -> None:
    HISTORY_FILE.unlink(missing_ok=True)

# ---------- RSS načtení ----------

def parse_date(raw: str | None):
    if not raw:
        return None
    try:
        return eut.parsedate_to_datetime(raw).date()
    except Exception:
        return None


def fetch_blog_articles() -> List[Tuple[str, str, date, str]]:
    """Vrátí list (title, url, publish_date, summary)."""
    feed = feedparser.parse(RSS_FEED_URL)
    if feed.bozo:
        resp = requests.get(RSS_FEED_URL, timeout=10)
        resp.raise_for_status()
        feed = feedparser.parse(resp.content)

    out: list[tuple[str, str, date, str]] = []
    for e in feed.entries:
        title: str = e.get("title", "")
        url: str | None = e.get("link")
        if not url:
            continue
        published = parse_date(e.get("published") or e.get("updated") or e.get("pubDate"))
        if not published:
            continue
        summary: str = e.get("summary", "")
        out.append((title, url, published, summary))
    return out

# ---------- Kategorizace ----------

def classify_article(title: str, summary: str) -> str | None:
    text = (title + " " + summary).lower()
    for cat in CATEGORY_ORDER:
        for kw in CATEGORY_KEYWORDS[cat]:
            if re.search(rf"{kw}", text):
                return cat
    return None  # nic nenašlo

# ---------- Výběr článků ----------

def select_articles_for_month(articles: list[tuple[str, str, date, str]], history: dict, year: int, month: int):
    key = f"{year}-{month:02d}"
    used_links = set(history.get(key, []))

    # filtrovat na daný měsíc a nevyužité
    pool = [a for a in articles if a[2].year == year and a[2].month == month and a[1] not in used_links]
    pool.sort(key=lambda x: x[2], reverse=True)

    selected: dict[str, tuple[str, str, date, str] | None] = {c: None for c in CATEGORY_ORDER}
    others: list[tuple[str, str, date, str]] = []

    for art in pool:
        cat = classify_article(art[0], art[3]) or "OTHER"
        if cat in selected and selected[cat] is None:
            selected[cat] = art
        else:
            others.append(art)

    # poskládat finální seznam – nejprve kategorie ve správném pořadí, pak doplnit zbytky
    final: list[tuple[str, str, date, str]] = [a for a in (selected[c] for c in CATEGORY_ORDER) if a is not None]
    for art in others:
        if len(final) >= MAX_ARTICLES:
            break
        final.append(art)
    return final[:MAX_ARTICLES]

############################################################
#  Streamlit UI
############################################################

st.set_page_config(page_title="iDoklad Blog – strategický výběr článků", page_icon="✉️")

history = load_history()

# ░░ SIDEBAR ░░
with st.sidebar:
    st.header("⚙️ Nastavení")
    if st.button("🗑️ Vymazat historii výběru"):
        clear_history()
        st.success("Historie byla smazána.")
        rerun()

    with st.expander("📜 Historie vybraných článků", expanded=False):
        if not history:
            st.write("(prázdná)")
        else:
            for key in sorted(history.keys(), reverse=True):
                y, m = map(int, key.split("-"))
                st.markdown(f"#### {CZECH_MONTHS[m].capitalize()} {y}")
                for link in history[key]:
                    st.markdown(f"- <{link}>")
                st.markdown("---")

# ░░ HLAVNÍ ░░
st.title("✉️ iDoklad Blog – strategický výběr 4 článků")
if st.button("🔄 Aktualizovat články"):
    rerun()

with st.spinner("Načítám RSS feed …"):
    try:
        all_articles = fetch_blog_articles()
    except Exception as e:
        st.error(f"Chyba při načítání RSS: {e}")
        st.stop()

# poslední tři měsíce
months = [(date.today().replace(day=15) - timedelta(days=30 * i)).replace(day=15) for i in range(MONTHS_TO_SHOW)]
months_opts = [(dt.year, dt.month) for dt in months]
sel_year, sel_month = st.selectbox(
    "Vyber měsíc (aktuální + 2 předchozí):",
    options=months_opts,
    format_func=lambda ym: f"{CZECH_MONTHS[ym[1]].capitalize()} {ym[0]}",
    index=0,
)

selected_articles = select_articles_for_month(all_articles, history, sel_year, sel_month)

# Výpis
if not selected_articles:
    st.warning("Pro daný měsíc nejsou dostupné nové články.")
else:
    st.subheader("Vybraný mix článků")
    for art in selected_articles:
        title, url, pub_d, _ = art
        cat = classify_article(title, "") or "OTHER"
        st.markdown(f"- **[{title}]({url})**   *({cat.lower()}, {pub_d.strftime('%d.%m.%Y')})*")

    if st.button("✉️ Vygenerovat e-mail", type="primary"):
        links = [url for _, url, _, _ in selected_articles]
        subject = f"iDoklad blog – strategický mix článků ({CZECH_MONTHS[sel_month]} {sel_year})"
        body = (
            "Ahoj Martine,\n\n"
            "dal bys prosím dohromady statistiky za iDoklad a připravil mailing.\n\n"
            "Články bych tam dala tyto (v pořadí ENGAGEMENT, CONVERSION, EDUCATIONAL, SEASONAL):\n" +
            "\n".join(links) + "\n\nS pozdravem\nA"
        )

        key = f"{sel_year}-{sel_month:02d}"
        history.setdefault(key, []).extend(links)
        save_history(history)

        st.success("E-mail byl vygenerován!")
        st.code(subject)
        st.text_area("Text e-mailu", body, height=300)
