"""
⚽ Football Prediction Bot - Stable
=====================================
Δεδομένα:
  - football-data.org  → fixtures, H2H, standings
  - the-odds-api.com   → αποδόσεις

Σύστημα: Έμπειρος αναλυτής - BEST BET ≥ 75%
"""

import os
import requests
import anthropic
from datetime import date

# ─── KEYS ────────────────────────────────────────────────────────────────────

TELEGRAM_BOT_TOKEN = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID   = os.environ["TELEGRAM_CHAT_ID"]
FOOTBALL_DATA_KEY  = os.environ["RAPIDAPI_KEY"]
ODDS_API_KEY       = os.environ["ODDS_API_KEY"]
ANTHROPIC_API_KEY  = os.environ["ANTHROPIC_API_KEY"]

FOOTBALL_BASE    = "https://api.football-data.org/v4"
FOOTBALL_HEADERS = {"X-Auth-Token": FOOTBALL_DATA_KEY}

COMPETITIONS = {
    "PL":  "Premier League",
    "PD":  "La Liga",
    "SA":  "Serie A",
    "BL1": "Bundesliga",
    "FL1": "Ligue 1",
    "CL":  "Champions League",
}

ODDS_SPORT_KEYS = {
    "PL":  "soccer_england_premier_league",
    "PD":  "soccer_spain_la_liga",
    "SA":  "soccer_italy_serie_a",
    "BL1": "soccer_germany_bundesliga",
    "FL1": "soccer_france_ligue_one",
    "CL":  "soccer_uefa_champs_league",
}

# ─── API CALLS ───────────────────────────────────────────────────────────────

def get_fixtures_today():
    today = date.today().isoformat()
    print(f"🔍 Ψάχνω παιχνίδια για: {today}")
    all_fixtures = []
    for code, name in COMPETITIONS.items():
        try:
            resp = requests.get(
                f"{FOOTBALL_BASE}/competitions/{code}/matches",
                headers=FOOTBALL_HEADERS,
                params={"dateFrom": today, "dateTo": today},
                timeout=10
            )
            matches = resp.json().get("matches", []) if resp.status_code == 200 else []
        except:
            matches = []
        print(f"  {name}: {len(matches)} παιχνίδια")
        for m in matches:
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
    """Παίρνει τα τελευταία 5 αποτελέσματα (W/D/L)."""
    try:
        resp = requests.get(
            f"{FOOTBALL_BASE}/persons/{team_id}/matches",
            headers=FOOTBALL_HEADERS,
            params={"limit": 5, "status": "FINISHED"},
            timeout=10
        )
        if resp.status_code != 200:
            return "N/A"
        results = []
        for m in resp.json().get("matches", [])[-5:]:
            score = m.get("score", {}).get("fullTime", {})
            hg, ag = score.get("home"), score.get("away")
            if hg is None or ag is None:
                continue
            is_home = m["homeTeam"]["id"] == team_id
            if is_home:
                results.append("W" if hg > ag else ("D" if hg == ag else "L"))
            else:
                results.append("W" if ag > hg else ("D" if ag == hg else "L"))
        return "".join(results) if results else "N/A"
    except:
        return "N/A"


def get_h2h(match_id):
    """Παίρνει τα τελευταία 5 H2H αποτελέσματα."""
    try:
        resp = requests.get(
            f"{FOOTBALL_BASE}/matches/{match_id}/head2head",
            headers=FOOTBALL_HEADERS,
            params={"limit": 5},
            timeout=10
        )
        if resp.status_code != 200:
            return "N/A"
        results = []
        over25 = 0
        for m in resp.json().get("matches", []):
            score = m.get("score", {}).get("fullTime", {})
            hg, ag = score.get("home"), score.get("away")
            if hg is not None and ag is not None:
                results.append(f"{m['homeTeam']['name']} {hg}-{ag} {m['awayTeam']['name']}")
                if (hg + ag) > 2:
                    over25 += 1
        text = " | ".join(results) if results else "N/A"
        return f"{text} (Over 2.5: {over25}/{len(results)})"
    except:
        return "N/A"


def get_standings(competition_code):
    try:
        resp = requests.get(
            f"{FOOTBALL_BASE}/competitions/{competition_code}/standings",
            headers=FOOTBALL_HEADERS,
            timeout=10
        )
        if resp.status_code != 200:
            return {}
        standings = {}
        for group in resp.json().get("standings", []):
            if group.get("type") == "TOTAL":
                for team in group.get("table", []):
                    played = team.get("playedGames", 1) or 1
                    standings[team["team"]["id"]] = {
                        "position":          team["position"],
                        "points":            team["points"],
                        "gf":                team["goalsFor"],
                        "ga":                team["goalsAgainst"],
                        "goals_per_game":    round(team["goalsFor"] / played, 2),
                        "conceded_per_game": round(team["goalsAgainst"] / played, 2),
                    }
        return standings
    except:
        return {}


def team_name_match(name1, name2):
    """Έξυπνο matching ονομάτων ομάδων μεταξύ διαφορετικών APIs."""
    def clean(n):
        n = n.lower()
        for word in ["fc", "cf", "ac", "sc", "rc", "afc", "cd", "if",
                     "1.", "united", "city", "club", "olympique", "saint", "st"]:
            n = n.replace(word, " ")
        n = n.replace("-", " ").replace(".", " ").replace("'", "")
        return " ".join(n.split())  # normalize spaces

    c1 = clean(name1)
    c2 = clean(name2)

    if c1 == c2:
        return True
    if c1 in c2 or c2 in c1:
        return True
    w1 = c1.split()[0] if c1.split() else ""
    w2 = c2.split()[0] if c2.split() else ""
    if len(w1) > 3 and w1 == w2:
        return True
    if len(c1) > 4 and len(c2) > 4 and c1[:4] == c2[:4]:
        return True
    return False


def get_odds(competition_code, home_team, away_team):
    sport_key = ODDS_SPORT_KEYS.get(competition_code)
    if not sport_key:
        return "N/A"
    try:
        resp = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
            params={"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"},
            timeout=10
        )
        if resp.status_code != 200:
            return "N/A"
        for game in resp.json():
            gh = game.get("home_team", "")
            ga = game.get("away_team", "")
            if team_name_match(home_team, gh) or team_name_match(away_team, ga):
                bookmakers = game.get("bookmakers", [])
                if bookmakers:
                    outcomes = bookmakers[0].get("markets", [{}])[0].get("outcomes", [])
                    odds_dict = {o["name"]: o["price"] for o in outcomes}
                    h = odds_dict.get(game["home_team"], "N/A")
                    d = odds_dict.get("Draw", "N/A")
                    a = odds_dict.get(game["away_team"], "N/A")
                    return f"1:{h} X:{d} 2:{a}"
    except:
        pass
    return "N/A"


# ─── CLAUDE ANALYSIS ──────────────────────────────────────────────────────────

def analyze_with_claude(match_data: list) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    matches_text = ""
    for i, m in enumerate(match_data, 1):
        hs  = m.get("home_standing", {})
        as_ = m.get("away_standing", {})
        matches_text += f"""
Αγώνας {i}: {m['home']} vs {m['away']}
  Πρωτάθλημα    : {m['league']} | Ώρα (UTC): {m['time']}
  Form (home)   : {m.get('home_form', 'N/A')}
  Form (away)   : {m.get('away_form', 'N/A')}
  H2H (τελ. 5) : {m.get('h2h', 'N/A')}
  Βαθμολογία home: {hs.get('position','?')}ος | {hs.get('points','?')} βαθμοί | {hs.get('goals_per_game','?')} γκολ/αγώνα | {hs.get('conceded_per_game','?')} δέχεται/αγώνα
  Βαθμολογία away: {as_.get('position','?')}ος | {as_.get('points','?')} βαθμοί | {as_.get('goals_per_game','?')} γκολ/αγώνα | {as_.get('conceded_per_game','?')} δέχεται/αγώνα
  Αποδόσεις     : {m.get('odds', 'N/A')}
"""

    prompt = f"""Είσαι έμπειρος αναλυτής ποδοσφαίρου με 30+ χρόνια εμπειρία.

Για κάθε αγώνα δώσε:
1. Πρόταση για 1X2 με % εμπιστοσύνη
2. Πρόταση Over/Under 2.5 με % εμπιστοσύνη
3. Σύντομη αιτιολόγηση (2-3 γραμμές)

ΚΑΝΟΝΕΣ:
- ⭐ BEST BET μόνο αν εμπιστοσύνη ≥ 75%
- 🔒 ULTRA-SAFE μόνο αν εμπιστοσύνη ≥ 85%
- Μέγιστο 3 BEST BETS ημερησίως
- ΜΗΝ προτείνεις αν απόδοση < 1.25
- Να είσαι ΑΥΣΤΗΡΑ συντηρητικός
- Λάβε υπόψη τις αποδόσεις

Μορφή εξόδου για Telegram με emoji:

Για BEST BET:
⭐ [Αγώνας] — [Πρόταση] ([X]%)
📊 [Αιτιολόγηση]

Στο τέλος:
━━━━━━━━━━━━━━━━
🏆 BEST BETS ΗΜΕΡΑΣ:
[Λίστα]
💡 TOP PICK: [Καλύτερο]

Αν κανένα ≥75%:
⚠️ Σήμερα δεν υπάρχει αξιόπιστη πρόταση. Καλύτερα να μην παίξεις.

Σημερινοί αγώνες:
{matches_text}
"""

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=2500,
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

    standings_cache = {}
    for comp in set(f["competition"] for f in fixtures):
        standings_cache[comp] = get_standings(comp)

    enriched = []
    for f in fixtures:
        print(f"  📊 {f['home']} vs {f['away']}...")
        standings = standings_cache.get(f["competition"], {})
        enriched.append({
            **f,
            "home_form":     get_team_form(f["home_id"]),
            "away_form":     get_team_form(f["away_id"]),
            "h2h":           get_h2h(f["match_id"]),
            "home_standing": standings.get(f["home_id"], {}),
            "away_standing": standings.get(f["away_id"], {}),
            "odds":          get_odds(f["competition"], f["home"], f["away"]),
        })

    print("🤖 Ανάλυση με Claude...")
    today_str = date.today().strftime("%A, %d %B %Y")
    analysis  = analyze_with_claude(enriched)

    print("📨 Αποστολή στο Telegram...")
    send_telegram(f"⚽ *ΠΡΟΒΛΕΨΕΙΣ ΗΜΕΡΑΣ — {today_str}*\n\n" + analysis)
    print("✅ Έτοιμο!")


if __name__ == "__main__":
    main()
