"""
⚽ Football Prediction Telegram Bot - v4 (football-data.org)
=============================================================
"""

import os
import requests
import anthropic
from datetime import date, datetime, timedelta

# ─── KEYS ────────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN   = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID     = os.environ["TELEGRAM_CHAT_ID"]
FOOTBALL_DATA_KEY    = os.environ["RAPIDAPI_KEY"]  # βάλε το νέο key εδώ
ANTHROPIC_API_KEY    = os.environ["ANTHROPIC_API_KEY"]

BASE_URL = "https://api.football-data.org/v4"
HEADERS  = {"X-Auth-Token": FOOTBALL_DATA_KEY}

# Competition codes στο football-data.org
COMPETITIONS = {
    "PL":  "Premier League",
    "PD":  "La Liga",
    "SA":  "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "CL":  "Champions League",
    "EL":  "Europa League",
}

# ─── API CALLS ───────────────────────────────────────────────────────────────

def get_fixtures_today():
    """Παίρνει όλα τα παιχνίδια της σημερινής ημέρας."""
    today = "2026-04-05"
    print(f"🔍 Ψάχνω παιχνίδια για: {today}")
    all_fixtures = []

    for code, name in COMPETITIONS.items():
        resp = requests.get(
            f"{BASE_URL}/competitions/{code}/matches",
            headers=HEADERS,
            params={"dateFrom": today, "dateTo": today},
            timeout=10
        )
        print(f"  {name}: status={resp.status_code}, results={len(resp.json().get('matches', []))}")
        if resp.status_code != 200:
            continue
        for m in resp.json().get("matches", []):
            all_fixtures.append({
                "league":      name,
                "match_id":    m["id"],
                "home":        m["homeTeam"]["name"],
                "away":        m["awayTeam"]["name"],
                "home_id":     m["homeTeam"]["id"],
                "away_id":     m["awayTeam"]["id"],
                "time":        m["utcDate"][11:16],
                "competition": code,
            })
    return all_fixtures


def get_team_form(team_id):
    """Παίρνει τα τελευταία 5 αποτελέσματα μιας ομάδας."""
    today = date.today().isoformat()
    date_from = (date.today() - timedelta(days=120)).isoformat()

    resp = requests.get(
        f"{BASE_URL}/teams/{team_id}/matches",
        headers=HEADERS,
        params={"dateFrom": date_from, "dateTo": today, "limit": 5, "status": "FINISHED"},
        timeout=10
    )
    if resp.status_code != 200:
        return "N/A"

    results = []
    for m in resp.json().get("matches", [])[-5:]:
        score = m.get("score", {}).get("fullTime", {})
        hg = score.get("home")
        ag = score.get("away")
        if hg is None or ag is None:
            continue
        is_home = m["homeTeam"]["id"] == team_id
        if is_home:
            results.append("W" if hg > ag else ("D" if hg == ag else "L"))
        else:
            results.append("W" if ag > hg else ("D" if ag == hg else "L"))
    return "".join(results) if results else "N/A"


def get_h2h(match_id):
    """Παίρνει τα τελευταία H2H αποτελέσματα μέσω match ID."""
    resp = requests.get(
        f"{BASE_URL}/matches/{match_id}/head2head",
        headers=HEADERS,
        params={"limit": 5},
        timeout=10
    )
    if resp.status_code != 200:
        return "N/A"

    results = []
    for m in resp.json().get("matches", []):
        score = m.get("score", {}).get("fullTime", {})
        hg = score.get("home")
        ag = score.get("away")
        hn = m["homeTeam"]["name"]
        an = m["awayTeam"]["name"]
        if hg is not None and ag is not None:
            results.append(f"{hn} {hg}-{ag} {an}")
    return " | ".join(results) if results else "N/A"


# ─── CLAUDE ANALYSIS ──────────────────────────────────────────────────────────

def analyze_with_claude(match_data: list) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    matches_text = ""
    for i, m in enumerate(match_data, 1):
        matches_text += f"""
Αγώνας {i}: {m['home']} vs {m['away']}
  Πρωτάθλημα    : {m['league']}
  Ώρα (UTC)     : {m['time']}
  Form (home)   : {m.get('home_form', 'N/A')}
  Form (away)   : {m.get('away_form', 'N/A')}
  H2H (τελ. 5) : {m.get('h2h', 'N/A')}
"""

    prompt = f"""Είσαι ειδικός αναλυτής ποδοσφαίρου. Σου δίνω πραγματικά στατιστικά για τους σημερινούς αγώνες.

Για κάθε αγώνα δώσε:
1. Πρόταση για 1X2 με % εμπιστοσύνη
2. Πρόταση Over/Under 2.5 γκολ με % εμπιστοσύνη
3. Σύντομη αιτιολόγηση (1-2 γραμμές)
4. Αν εμπιστοσύνη > 70% σήμανε ως ⭐ BEST BET

Μορφοποίησε για Telegram με emoji. Στο τέλος βάλε σύνοψη BEST BETs.

Σημερινοί αγώνες:
{matches_text}
"""

    message = client.messages.create(
        model="claude-sonnet-4-20250514",
        max_tokens=2000,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


# ─── TELEGRAM ────────────────────────────────────────────────────────────────

def send_telegram(text: str):
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    for chunk in [text[i:i+4000] for i in range(0, len(text), 4000)]:
        requests.post(url, json={
            "chat_id":    TELEGRAM_CHAT_ID,
            "text":       chunk,
            "parse_mode": "Markdown"
        })


# ─── MAIN ────────────────────────────────────────────────────────────────────

def main():
    print("⚽ Ξεκινάει η ανάλυση ποδοσφαίρου...")

    fixtures = get_fixtures_today()

    if not fixtures:
        send_telegram("⚽ Δεν βρέθηκαν παιχνίδια σήμερα στα επιλεγμένα πρωταθλήματα.")
        return

    print(f"✅ Βρέθηκαν {len(fixtures)} παιχνίδια. Συλλογή στατιστικών...")

    enriched = []
    for f in fixtures:
        print(f"  📊 {f['home']} vs {f['away']}...")
        enriched.append({
            **f,
            "home_form": get_team_form(f["home_id"]),
            "away_form": get_team_form(f["away_id"]),
            "h2h":       get_h2h(f["match_id"]),
        })

    print("🤖 Ανάλυση με Claude...")
    today_str = date.today().strftime("%A, %d %B %Y")
    analysis = analyze_with_claude(enriched)

    print("📨 Αποστολή στο Telegram...")
    send_telegram(f"⚽ *ΠΡΟΒΛΕΨΕΙΣ ΗΜΕΡΑΣ — {today_str}*\n\n" + analysis)
    print("✅ Έτοιμο!")


if __name__ == "__main__":
    main()
