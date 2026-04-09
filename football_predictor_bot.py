"""
⚽ Football Prediction Telegram Bot
====================================
Κάθε πρωί παίρνει στατιστικά από API-Football,
τα στέλνει στον Claude για ανάλυση, και
προωθεί τις προβλέψεις στο Telegram σου.

ΑΠΑΙΤΟΥΜΕΝΑ KEYS (βάλτα στα environment variables):
  - TELEGRAM_BOT_TOKEN  : Από @BotFather
  - TELEGRAM_CHAT_ID    : Το ID σου (βλ. οδηγίες)
  - RAPIDAPI_KEY        : Από rapidapi.com/api-sports
  - ANTHROPIC_API_KEY   : Από console.anthropic.com
"""

import os
import requests
import anthropic
from datetime import date

# ─── ΡΥΘΜΙΣΕΙΣ ───────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
RAPIDAPI_KEY       = os.environ["RAPIDAPI_KEY"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]

# Πρωταθλήματα που θέλεις (API-Football league IDs)
LEAGUE_IDS = {
    39:  "Premier League",
    140: "La Liga",
    135: "Serie A",
    78:  "Bundesliga",
    61:  "Ligue 1",
    2:   "Champions League",
    3:   "Europa League",
}

# ─── API-FOOTBALL ─────────────────────────────────────────────────────────────

def get_fixtures_today():
    """Παίρνει όλα τα παιχνίδια της σημερινής ημέρας."""
    today = date.today().isoformat()
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    all_fixtures = []
    for league_id, league_name in LEAGUE_IDS.items():
        params = {"league": league_id, "date": today, "season": "2024"}
        resp = requests.get(url, headers=headers, params=params)
        if resp.status_code == 200:
            fixtures = resp.json().get("response", [])
            for f in fixtures:
                all_fixtures.append({
                    "league": league_name,
                    "home":   f["teams"]["home"]["name"],
                    "away":   f["teams"]["away"]["name"],
                    "time":   f["fixture"]["date"][11:16],  # HH:MM
                    "fixture_id": f["fixture"]["id"],
                })
    return all_fixtures


def get_team_form(team_id, league_id):
    """Παίρνει τα τελευταία 5 αποτελέσματα μιας ομάδας."""
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    params = {"team": team_id, "league": league_id, "last": 5, "season": "2024"}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        return "N/A"
    results = []
    for f in resp.json().get("response", []):
        home_goals = f["goals"]["home"]
        away_goals = f["goals"]["away"]
        home_id    = f["teams"]["home"]["id"]
        if home_id == team_id:
            if home_goals > away_goals:   results.append("W")
            elif home_goals == away_goals: results.append("D")
            else:                          results.append("L")
        else:
            if away_goals > home_goals:   results.append("W")
            elif away_goals == home_goals: results.append("D")
            else:                          results.append("L")
    return "".join(results) if results else "N/A"


def get_h2h(home_team_id, away_team_id):
    """Παίρνει τα τελευταία 5 H2H αποτελέσματα."""
    url = "https://api-football-v1.p.rapidapi.com/v3/fixtures/headtohead"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    params = {"h2h": f"{home_team_id}-{away_team_id}", "last": 5}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        return "N/A"
    h2h_list = []
    for f in resp.json().get("response", []):
        h = f["goals"]["home"]
        a = f["goals"]["away"]
        hn = f["teams"]["home"]["name"]
        an = f["teams"]["away"]["name"]
        h2h_list.append(f"{hn} {h}-{a} {an}")
    return " | ".join(h2h_list) if h2h_list else "N/A"


def get_fixture_statistics(fixture_id):
    """
    Παίρνει στατιστικά για ένα fixture (team stats όπως shots, possession).
    Χρησιμοποιείται μόνο εφόσον υπάρχουν δεδομένα.
    """
    url = f"https://api-football-v1.p.rapidapi.com/v3/fixtures/statistics"
    headers = {
        "X-RapidAPI-Key": RAPIDAPI_KEY,
        "X-RapidAPI-Host": "api-football-v1.p.rapidapi.com"
    }
    params = {"fixture": fixture_id}
    resp = requests.get(url, headers=headers, params=params)
    if resp.status_code != 200:
        return {}
    return resp.json().get("response", {})


# ─── CLAUDE ANALYSIS ──────────────────────────────────────────────────────────

def analyze_with_claude(match_data: list[dict]) -> str:
    """
    Στέλνει τα δεδομένα των αγώνων στον Claude και παίρνει ανάλυση.
    match_data: λίστα με dict ανά αγώνα.
    """
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    # Φτιάχνουμε το prompt με όλα τα δεδομένα
    matches_text = ""
    for i, m in enumerate(match_data, 1):
        matches_text += f"""
Αγώνας {i}: {m['home']} vs {m['away']}
  Πρωτάθλημα : {m['league']}
  Ώρα        : {m['time']}
  Form (home): {m.get('home_form', 'N/A')}
  Form (away): {m.get('away_form', 'N/A')}
  H2H        : {m.get('h2h', 'N/A')}
"""

    prompt = f"""Είσαι ειδικός αναλυτής ποδοσφαίρου. Σου δίνω τα στατιστικά για τους σημερινούς αγώνες.

Για κάθε αγώνα δώσε:
1. Πρόταση για 1X2 (ποιος κερδίζει ή ισοπαλία) με % εμπιστοσύνη
2. Πρόταση Over/Under 2.5 γκολ με % εμπιστοσύνη
3. Σύντομη αιτιολόγηση (1-2 γραμμές)
4. ⭐ Αν η εμπιστοσύνη > 70%, σήμαν τον αγώνα ως "BEST BET"

Μορφοποίησε την απάντηση ξεκάθαρα για Telegram (χρησιμοποίησε emoji).
Στο τέλος βάλε σύνοψη με τα BEST BETs της ημέρας.

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
    """Στέλνει μήνυμα στο Telegram."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage"
    # Telegram έχει όριο 4096 χαρακτήρες — σπάμε αν χρειαστεί
    chunks = [text[i:i+4000] for i in range(0, len(text), 4000)]
    for chunk in chunks:
        payload = {
            "chat_id": TELEGRAM_CHAT_ID,
            "text": chunk,
            "parse_mode": "Markdown"
        }
        requests.post(url, json=payload)


# ─── ΚΥΡΙΟ ΠΡΟΓΡΑΜΜΑ ─────────────────────────────────────────────────────────

def main():
    print("⚽ Ξεκινάει η ανάλυση ποδοσφαίρου...")

    # 1. Παίρνουμε τα σημερινά παιχνίδια
    fixtures = get_fixtures_today()

    if not fixtures:
        send_telegram("⚽ Δεν βρέθηκαν παιχνίδια σήμερα στα επιλεγμένα πρωταθλήματα.")
        return

    print(f"✅ Βρέθηκαν {len(fixtures)} παιχνίδια.")

    # 2. Για κάθε παιχνίδι παίρνουμε form & H2H
    # Σημ: Στο free plan παίρνουμε IDs από τα fixture data
    enriched = []
    for f in fixtures:
        # Τα team IDs τα βρίσκουμε από το fixture — εδώ απλοποιούμε
        # Σε πλήρη υλοποίηση: f["teams"]["home"]["id"] κλπ
        enriched.append({
            "league":     f["league"],
            "home":       f["home"],
            "away":       f["away"],
            "time":       f["time"],
            "home_form":  "WWDLW",   # placeholder — αντικατέστησε με get_team_form()
            "away_form":  "LWWDW",   # placeholder
            "h2h":        "3-1 υπέρ home (τελ. 5)",  # placeholder
        })

    # 3. Ανάλυση με Claude
    print("🤖 Ανάλυση με Claude...")
    today_str = date.today().strftime("%A, %d %B %Y")
    header = f"⚽ *ΠΡΟΒΛΕΨΕΙΣ ΗΜΕΡΑΣ — {today_str}*\n\n"
    analysis = analyze_with_claude(enriched)

    # 4. Αποστολή στο Telegram
    print("📨 Αποστολή στο Telegram...")
    send_telegram(header + analysis)
    print("✅ Έτοιμο!")


if __name__ == "__main__":
    main()
