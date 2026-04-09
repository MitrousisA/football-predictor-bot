"""
⚽ Football Prediction Telegram Bot - v3 (api-sports.io direct)
===============================================================
"""

import os
import requests
import anthropic
from datetime import date

# ─── KEYS ────────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
API_FOOTBALL_KEY   = os.environ["RAPIDAPI_KEY"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]

BASE_URL = "https://v3.football.api-sports.io"
HEADERS  = {
    "x-apisports-key": API_FOOTBALL_KEY
}

LEAGUE_IDS = {
    39:  "Premier League",
    140: "La Liga",
    135: "Serie A",
    78:  "Bundesliga",
    61:  "Ligue 1",
    2:   "Champions League",
    3:   "Europa League",
}

# ─── API CALLS ───────────────────────────────────────────────────────────────
def get_fixtures_today():
    today = 2026-04-08
    print(f"🔍 Ψάχνω παιχνίδια για: {today}")
    all_fixtures = []
    for league_id, league_name in LEAGUE_IDS.items():
        resp = requests.get(
            f"{BASE_URL}/fixtures",
            headers=HEADERS,
            params={"league": league_id, "date": today, "season": "2025"}
        )
        print(f"  League {league_name}: status={resp.status_code}, results={len(resp.json().get('response', []))}")
        if resp.status_code != 200:
            continue
        for f in resp.json().get("response", []):
            all_fixtures.append({
                "league":     league_name,
                "fixture_id": f["fixture"]["id"],
                "home":       f["teams"]["home"]["name"],
                "away":       f["teams"]["away"]["name"],
                "home_id":    f["teams"]["home"]["id"],
                "away_id":    f["teams"]["away"]["id"],
                "time":       f["fixture"]["date"][11:16],
                "league_id":  league_id,
            })
    return all_fixtures

def get_team_form(team_id):
    resp = requests.get(
        f"{BASE_URL}/fixtures",
        headers=HEADERS,
        params={"team": team_id, "last": 5}
    )
    if resp.status_code != 200:
        return "N/A"
    results = []
    for f in resp.json().get("response", []):
        hg = f["goals"]["home"]
        ag = f["goals"]["away"]
        if hg is None or ag is None:
            continue
        is_home = f["teams"]["home"]["id"] == team_id
        if is_home:
            results.append("W" if hg > ag else ("D" if hg == ag else "L"))
        else:
            results.append("W" if ag > hg else ("D" if ag == hg else "L"))
    return "".join(results) if results else "N/A"


def get_h2h(home_id, away_id):
    resp = requests.get(
        f"{BASE_URL}/fixtures/headtohead",
        headers=HEADERS,
        params={"h2h": f"{home_id}-{away_id}", "last": 5}
    )
    if resp.status_code != 200:
        return "N/A"
    results = []
    for f in resp.json().get("response", []):
        hg = f["goals"]["home"]
        ag = f["goals"]["away"]
        hn = f["teams"]["home"]["name"]
        an = f["teams"]["away"]["name"]
        if hg is not None and ag is not None:
            results.append(f"{hn} {hg}-{ag} {an}")
    return " | ".join(results) if results else "N/A"


def get_team_stats(team_id, league_id):
    resp = requests.get(
        f"{BASE_URL}/teams/statistics",
        headers=HEADERS,
        params={"team": team_id, "league": league_id, "season": "2025"}
    )
    if resp.status_code != 200:
        return {}
    data = resp.json().get("response", {})
    if not data:
        return {}
    goals = data.get("goals", {})
    return {
        "scored_avg":   goals.get("for", {}).get("average", {}).get("total", "N/A"),
        "conceded_avg": goals.get("against", {}).get("average", {}).get("total", "N/A"),
    }


# ─── CLAUDE ANALYSIS ──────────────────────────────────────────────────────────

def analyze_with_claude(match_data: list) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    matches_text = ""
    for i, m in enumerate(match_data, 1):
        matches_text += f"""
Αγώνας {i}: {m['home']} vs {m['away']}
  Πρωτάθλημα       : {m['league']}
  Ώρα              : {m['time']}
  Form (home)      : {m.get('home_form', 'N/A')}
  Form (away)      : {m.get('away_form', 'N/A')}
  H2H (τελ. 5)    : {m.get('h2h', 'N/A')}
  Γκολ/αγώνα home : {m.get('home_stats', {}).get('scored_avg', 'N/A')} scored | {m.get('home_stats', {}).get('conceded_avg', 'N/A')} conceded
  Γκολ/αγώνα away : {m.get('away_stats', {}).get('scored_avg', 'N/A')} scored | {m.get('away_stats', {}).get('conceded_avg', 'N/A')} conceded
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
            "home_form":  get_team_form(f["home_id"]),
            "away_form":  get_team_form(f["away_id"]),
            "h2h":        get_h2h(f["home_id"], f["away_id"]),
            "home_stats": get_team_stats(f["home_id"], f["league_id"]),
            "away_stats": get_team_stats(f["away_id"], f["league_id"]),
        })

    print("🤖 Ανάλυση με Claude...")
    today_str = date.today().strftime("%A, %d %B %Y")
    analysis = analyze_with_claude(enriched)

    print("📨 Αποστολή στο Telegram...")
    send_telegram(f"⚽ *ΠΡΟΒΛΕΨΕΙΣ ΗΜΕΡΑΣ — {today_str}*\n\n" + analysis)
    print("✅ Έτοιμο!")


if __name__ == "__main__":
    main()
