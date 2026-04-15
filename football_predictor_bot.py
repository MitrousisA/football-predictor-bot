"""
⚽ Football Prediction Bot - v6
================================
Δεδομένα:
  - football-data.org  → fixtures, form, H2H, standings
  - the-odds-api.com   → αποδόσεις
  - understat.com      → xG, xGA data (δωρεάν)

Σύστημα ανάλυσης: 8-point GG & Over 2.5 filter
"""

import os
import asyncio
import aiohttp
import requests
import anthropic
from datetime import date, timedelta
from understat import Understat

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

UNDERSTAT_LEAGUES = {
    "PL":  "EPL",
    "PD":  "La_Liga",
    "SA":  "Serie_A",
    "BL1": "Bundesliga",
    "FL1": "Ligue_1",
}

ODDS_SPORT_KEYS = {
    "PL":  "soccer_england_premier_league",
    "PD":  "soccer_spain_la_liga",
    "SA":  "soccer_italy_serie_a",
    "BL1": "soccer_germany_bundesliga",
    "FL1": "soccer_france_ligue_one",
    "CL":  "soccer_uefa_champs_league",
}

# ─── FOOTBALL-DATA.ORG ───────────────────────────────────────────────────────

def get_fixtures_today():
    today = "2026-04-15"
    print(f"🔍 Ψάχνω παιχνίδια για: {today}")
    all_fixtures = []
    for code, name in COMPETITIONS.items():
        resp = requests.get(
            f"{FOOTBALL_BASE}/competitions/{code}/matches",
            headers=FOOTBALL_HEADERS,
            params={"dateFrom": today, "dateTo": today},
            timeout=10
        )
        matches = resp.json().get("matches", []) if resp.status_code == 200 else []
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
    today = date.today().isoformat()
    date_from = (date.today() - timedelta(days=120)).isoformat()
    resp = requests.get(
        f"{FOOTBALL_BASE}/teams/{team_id}/matches",
        headers=FOOTBALL_HEADERS,
        params={"dateFrom": date_from, "dateTo": today, "limit": 6, "status": "FINISHED"},
        timeout=10
    )
    if resp.status_code != 200:
        return "N/A"
    results = []
    for m in resp.json().get("matches", [])[-6:]:
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


def get_h2h(match_id):
    resp = requests.get(
        f"{FOOTBALL_BASE}/matches/{match_id}/head2head",
        headers=FOOTBALL_HEADERS,
        params={"limit": 5},
        timeout=10
    )
    if resp.status_code != 200:
        return "N/A", 0
    matches = resp.json().get("matches", [])
    results = []
    gg_over25_count = 0
    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        hg, ag = score.get("home"), score.get("away")
        hn = m["homeTeam"]["name"]
        an = m["awayTeam"]["name"]
        if hg is not None and ag is not None:
            results.append(f"{hn} {hg}-{ag} {an}")
            if hg > 0 and ag > 0 and (hg + ag) > 2:
                gg_over25_count += 1
    return " | ".join(results) if results else "N/A", gg_over25_count


def get_standings(competition_code):
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
                standings[team["team"]["id"]] = {
                    "position": team["position"],
                    "points":   team["points"],
                    "gf":       team["goalsFor"],
                    "ga":       team["goalsAgainst"],
                }
    return standings


# ─── UNDERSTAT (xG DATA) ─────────────────────────────────────────────────────

async def get_xg_data_async(home_team_name, away_team_name, league_code):
    understat_league = UNDERSTAT_LEAGUES.get(league_code)
    if not understat_league:
        return {}, {}

    async with aiohttp.ClientSession() as session:
        understat = Understat(session)
        try:
            teams_data = await understat.get_teams(understat_league, 2025)
            home_xg, away_xg = {}, {}

            for team in teams_data:
                team_name = team.get("title", "")
                history = team.get("history", [])[-5:]
                if not history:
                    continue

                xg_vals  = [float(h.get("xG", 0)) for h in history]
                xga_vals = [float(h.get("xGA", 0)) for h in history]
                stats = {
                    "xG_avg":  round(sum(xg_vals) / len(xg_vals), 2),
                    "xGA_avg": round(sum(xga_vals) / len(xga_vals), 2),
                }

                home_words = home_team_name.split()[:2]
                away_words = away_team_name.split()[:2]

                if any(w.lower() in team_name.lower() for w in home_words):
                    home_xg = stats
                if any(w.lower() in team_name.lower() for w in away_words):
                    away_xg = stats

            return home_xg, away_xg

        except Exception as e:
            print(f"  ⚠️ Understat error: {e}")
            return {}, {}


def get_xg_data(home_team_name, away_team_name, league_code):
    return asyncio.run(get_xg_data_async(home_team_name, away_team_name, league_code))


# ─── THE ODDS API ─────────────────────────────────────────────────────────────

def get_odds(competition_code, home_team, away_team):
    sport_key = ODDS_SPORT_KEYS.get(competition_code)
    if not sport_key:
        return "N/A"
    resp = requests.get(
        f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
        params={
            "apiKey":     ODDS_API_KEY,
            "regions":    "eu",
            "markets":    "h2h",
            "oddsFormat": "decimal",
        },
        timeout=10
    )
    if resp.status_code != 200:
        return "N/A"
    for game in resp.json():
        gh = game.get("home_team", "").lower()
        ga = game.get("away_team", "").lower()
        if home_team.lower()[:5] in gh or away_team.lower()[:5] in ga:
            bookmakers = game.get("bookmakers", [])
            if bookmakers:
                outcomes = bookmakers[0].get("markets", [{}])[0].get("outcomes", [])
                odds_dict = {o["name"]: o["price"] for o in outcomes}
                h = odds_dict.get(game["home_team"], "N/A")
                d = odds_dict.get("Draw", "N/A")
                a = odds_dict.get(game["away_team"], "N/A")
                return f"1:{h} X:{d} 2:{a}"
    return "N/A"


# ─── CLAUDE ANALYSIS ──────────────────────────────────────────────────────────

def analyze_with_claude(match_data: list) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    matches_text = ""
    for i, m in enumerate(match_data, 1):
        hs  = m.get("home_standing", {})
        as_ = m.get("away_standing", {})
        hxg = m.get("home_xg", {})
        axg = m.get("away_xg", {})

        matches_text += f"""
Αγώνας {i}: {m['home']} vs {m['away']}
  Πρωτάθλημα       : {m['league']}
  Ώρα (UTC)        : {m['time']}
  Form (home)      : {m.get('home_form', 'N/A')}
  Form (away)      : {m.get('away_form', 'N/A')}
  H2H (τελ. 5)    : {m.get('h2h', 'N/A')}
  H2H GG+Over2.5  : {m.get('h2h_gg_over25', 0)}/5 ματς
  Βαθμολογία home : {hs.get('position','?')}ος | {hs.get('gf','?')} γκολ υπέρ | {hs.get('ga','?')} γκολ κατά
  Βαθμολογία away : {as_.get('position','?')}ος | {as_.get('gf','?')} γκολ υπέρ | {as_.get('ga','?')} γκολ κατά
  xG home (avg5)  : {hxg.get('xG_avg', 'N/A')} | xGA: {hxg.get('xGA_avg', 'N/A')}
  xG away (avg5)  : {axg.get('xG_avg', 'N/A')} | xGA: {axg.get('xGA_avg', 'N/A')}
  Αποδόσεις       : {m.get('odds', 'N/A')}
"""

    prompt = f"""Είσαι έμπειρος αναλυτής αθλητικών δεδομένων με εξειδίκευση στα προγνωστικά μοντέλα GG & Over 2.5.

Για κάθε αγώνα εφάρμοσε το παρακάτω αυστηρό φίλτρο 8 σημείων:

CORE CRITERIA (Part 1) - Βαθμολόγησε 0 ή 1 για κάθε κριτήριο:
1. xG > 1.40 ΚΑΙ xGA > 1.20 και για τις 2 ομάδες
2. Γκολ κατά/αγώνα > 1.2 (από βαθμολογία) και για τις 2 ομάδες
3. Σκοράρει εκτός έδρας ο φιλοξενούμενος: ≥ 80% ματς (από form)
4. H2H: ≥ 2/5 ματς GG & Over 2.5
5. Αποδόσεις Over 2.5 < 1.90 (αγορά το υποστηρίζει)

ULTRA-SAFE FILTERS (Part 2) - Βαθμολόγησε 0 ή 1:
6. xG home avg > 1.5
7. xGA away avg > 1.3
8. H2H GG+Over2.5 ≥ 3/5

Παρουσίασε αποτελέσματα σε πίνακα:
| Αγώνας | Score (0-8) | Ultra-Safe | Σύσταση | Αιτιολόγηση |

ΚΑΝΟΝΕΣ:
- ⭐ BEST BET: Score ≥ 6/8
- 🔒 ULTRA-SAFE: Score ≥ 6/8 + και τα 3 Part 2 φίλτρα ΝΑΙ
- Να είσαι ΑΥΣΤΗΡΑ ΣΥΝΤΗΡΗΤΙΚΟΣ
- Αν κανένας αγώνας δεν πληροί τα κριτήρια, πες το ξεκάθαρα

Στο τέλος: σύνοψη BEST BETS και 💡 TOP PICK μόνο αν υπάρχει Ultra-Safe.

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
        standings  = standings_cache.get(f["competition"], {})
        h2h_text, h2h_gg = get_h2h(f["match_id"])
        home_xg, away_xg  = get_xg_data(f["home"], f["away"], f["competition"])

        enriched.append({
            **f,
            "home_form":     get_team_form(f["home_id"]),
            "away_form":     get_team_form(f["away_id"]),
            "h2h":           h2h_text,
            "h2h_gg_over25": h2h_gg,
            "home_standing": standings.get(f["home_id"], {}),
            "away_standing": standings.get(f["away_id"], {}),
            "home_xg":       home_xg,
            "away_xg":       away_xg,
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
