"""
⚽ Football Prediction Bot - v9
================================
Δεδομένα:
  - football-data.org  → fixtures, form, H2H, standings
  - the-odds-api.com   → αποδόσεις 1X2 + Over/Under

Σύστημα: Έμπειρος αναλυτής 30+ χρόνων
  - BEST BET μόνο με εμπιστοσύνη > 75%
  - Μέγιστο 3 BEST BETS ημερησίως
  - Ultra-Safe για εμπιστοσύνη > 85%
  - Παράλειψη ομάδων εκτός βαθμολογίας
"""

import os
import requests
import anthropic
from datetime import date, timedelta

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

# ─── FOOTBALL-DATA.ORG ───────────────────────────────────────────────────────

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
                timeout=(5, 10)
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
                "stage":       m.get("stage", ""),
            })
    return all_fixtures


def get_team_last_matches(team_id, limit=6):
    today = date.today().isoformat()
    date_from = (date.today() - timedelta(days=120)).isoformat()
    try:
        resp = requests.get(
            f"{FOOTBALL_BASE}/teams/{team_id}/matches",
            headers=FOOTBALL_HEADERS,
            params={"dateFrom": date_from, "dateTo": today, "limit": limit, "status": "FINISHED"},
            timeout=(5, 10)
        )
        if resp.status_code != 200:
            return []
        return resp.json().get("matches", [])[-limit:]
    except:
        return []


def analyze_team_form(matches, team_id):
    if not matches:
        return {
            "form": "N/A", "scored_rate": 0, "win_streak": 0,
            "loss_streak": 0, "goals_per_game": 0, "conceded_per_game": 0,
        }

    results = []
    scored_count = 0
    goals_for = 0
    goals_against = 0

    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        hg, ag = score.get("home"), score.get("away")
        if hg is None or ag is None:
            continue
        is_home = m["homeTeam"]["id"] == team_id
        gf = hg if is_home else ag
        ga = ag if is_home else hg
        goals_for += gf
        goals_against += ga
        if gf > 0:
            scored_count += 1
        results.append("W" if gf > ga else ("D" if gf == ga else "L"))

    n = len(results)
    if n == 0:
        return {
            "form": "N/A", "scored_rate": 0, "win_streak": 0,
            "loss_streak": 0, "goals_per_game": 0, "conceded_per_game": 0,
        }

    win_streak = 0
    for r in reversed(results):
        if r == "W": win_streak += 1
        else: break

    loss_streak = 0
    for r in reversed(results):
        if r == "L": loss_streak += 1
        else: break

    return {
        "form":              "".join(results),
        "scored_rate":       round(scored_count / n, 2),
        "win_streak":        win_streak,
        "loss_streak":       loss_streak,
        "goals_per_game":    round(goals_for / n, 2),
        "conceded_per_game": round(goals_against / n, 2),
    }


def get_h2h(match_id):
    try:
        resp = requests.get(
            f"{FOOTBALL_BASE}/matches/{match_id}/head2head",
            headers=FOOTBALL_HEADERS,
            params={"limit": 5},
            timeout=(5, 10)
        )
        if resp.status_code != 200:
            return {"text": "N/A", "over25_count": 0, "gg_count": 0,
                    "home_wins": 0, "away_wins": 0, "draws": 0, "total": 0}
    except:
        return {"text": "N/A", "over25_count": 0, "gg_count": 0,
                "home_wins": 0, "away_wins": 0, "draws": 0, "total": 0}

    matches = resp.json().get("matches", [])
    if not matches:
        return {"text": "N/A", "over25_count": 0, "gg_count": 0,
                "home_wins": 0, "away_wins": 0, "draws": 0, "total": 0}

    results = []
    over25_count = gg_count = home_wins = away_wins = draws = 0

    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        hg, ag = score.get("home"), score.get("away")
        if hg is not None and ag is not None:
            results.append(f"{m['homeTeam']['name']} {hg}-{ag} {m['awayTeam']['name']}")
            if (hg + ag) > 2: over25_count += 1
            if hg > 0 and ag > 0: gg_count += 1
            if hg > ag: home_wins += 1
            elif hg < ag: away_wins += 1
            else: draws += 1

    return {
        "text":         " | ".join(results) if results else "N/A",
        "over25_count": over25_count,
        "gg_count":     gg_count,
        "home_wins":    home_wins,
        "away_wins":    away_wins,
        "draws":        draws,
        "total":        len(results),
    }


def get_standings(competition_code):
    try:
        resp = requests.get(
            f"{FOOTBALL_BASE}/competitions/{competition_code}/standings",
            headers=FOOTBALL_HEADERS,
            timeout=(5, 10)
        )
        if resp.status_code != 200:
            return {}
    except:
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


def get_odds_full(competition_code, home_team, away_team):
    sport_key = ODDS_SPORT_KEYS.get(competition_code)
    if not sport_key:
        return {"h2h": "N/A", "over25": "N/A"}

    result = {"h2h": "N/A", "over25": "N/A"}

    try:
        resp = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
            params={"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"},
            timeout=(5, 10)
        )
        if resp.status_code == 200:
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
                        result["h2h"] = f"1:{h} X:{d} 2:{a}"
                    break
    except:
        pass

    try:
        resp2 = requests.get(
            f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
            params={"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "totals", "oddsFormat": "decimal"},
            timeout=(5, 10)
        )
        if resp2.status_code == 200:
            for game in resp2.json():
                gh = game.get("home_team", "").lower()
                ga = game.get("away_team", "").lower()
                if home_team.lower()[:5] in gh or away_team.lower()[:5] in ga:
                    bookmakers = game.get("bookmakers", [])
                    if bookmakers:
                        for market in bookmakers[0].get("markets", []):
                            if market.get("key") == "totals":
                                for outcome in market.get("outcomes", []):
                                    if outcome.get("name") == "Over" and str(outcome.get("point", "")) == "2.5":
                                        result["over25"] = outcome["price"]
                    break
    except:
        pass

    return result


# ─── CLAUDE ANALYSIS ──────────────────────────────────────────────────────────

def analyze_with_claude(match_data: list) -> str:
    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)

    matches_text = ""
    for i, m in enumerate(match_data, 1):
        hs   = m.get("home_standing", {})
        as_  = m.get("away_standing", {})
        hf   = m.get("home_form", {})
        af   = m.get("away_form", {})
        h2h  = m.get("h2h", {})
        odds = m.get("odds", {})

        matches_text += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
Αγώνας {i}: {m['home']} vs {m['away']}
  Πρωτάθλημα: {m['league']} | Ώρα (UTC): {m['time']}

  ΒΑΘΜΟΛΟΓΙΑ:
  Home: {hs.get('position','?')}ος | {hs.get('points','?')} βαθμοί | {hs.get('goals_per_game','?')} γκολ/αγώνα | {hs.get('conceded_per_game','?')} δέχεται/αγώνα
  Away: {as_.get('position','?')}ος | {as_.get('points','?')} βαθμοί | {as_.get('goals_per_game','?')} γκολ/αγώνα | {as_.get('conceded_per_game','?')} δέχεται/αγώνα
  Διαφορά βαθμών: {abs(hs.get('points', 0) - as_.get('points', 0))}

  FORM (τελ. 6):
  Home: {hf.get('form','N/A')} | Σκοράρει: {int(hf.get('scored_rate',0)*100)}% | Γκολ/αγώνα: {hf.get('goals_per_game','?')} | Δέχεται: {hf.get('conceded_per_game','?')} | Win streak: {hf.get('win_streak',0)} | Loss streak: {hf.get('loss_streak',0)}
  Away: {af.get('form','N/A')} | Σκοράρει: {int(af.get('scored_rate',0)*100)}% | Γκολ/αγώνα: {af.get('goals_per_game','?')} | Δέχεται: {af.get('conceded_per_game','?')} | Win streak: {af.get('win_streak',0)} | Loss streak: {af.get('loss_streak',0)}

  H2H (τελ. 5):
  {h2h.get('text','N/A')}
  Over 2.5: {h2h.get('over25_count',0)}/{h2h.get('total',0)} | GG: {h2h.get('gg_count',0)}/{h2h.get('total',0)} | Νίκες home: {h2h.get('home_wins',0)} | Νίκες away: {h2h.get('away_wins',0)} | Ισοπαλίες: {h2h.get('draws',0)}

  ΑΠΟΔΟΣΕΙΣ:
  1X2: {odds.get('h2h','N/A')} | Over 2.5: {odds.get('over25','N/A')}
"""

    prompt = f"""Είσαι έμπειρος αναλυτής ποδοσφαίρου με 30+ χρόνια εμπειρία. Έχεις δει χιλιάδες αγώνες και ξέρεις ακριβώς πότε τα στατιστικά λένε την αλήθεια και πότε όχι.

Αναλύεις κάθε αγώνα και δίνεις:
1. Πρόβλεψη 1X2 με % εμπιστοσύνη
2. Πρόβλεψη Over/Under 2.5 με % εμπιστοσύνη

ΚΑΝΟΝΕΣ ΕΜΠΕΙΡΙΑΣ (αυστηροί):
✅ BEST BET μόνο αν εμπιστοσύνη ≥ 75% — αλλιώς ΔΕΝ προτείνεις
🔒 ULTRA-SAFE μόνο αν εμπιστοσύνη ≥ 85%
✅ Μέγιστο 3 BEST BETS — επίλεξε τα 3 με την υψηλότερη εμπιστοσύνη
❌ ΜΗΝ προτείνεις αν: απόδοση < 1.25 | Derby ματς | Ελλιπή δεδομένα (N/A σε form/H2H)
❌ ΜΗΝ "φουσκώνεις" την εμπιστοσύνη — να είσαι ΑΥΣΤΗΡΑ συντηρητικός
✅ Λάβε υπόψη τις αποδόσεις — αν η αγορά διαφωνεί με τα στατιστικά, μείωσε την εμπιστοσύνη

ΑΙΤΙΟΛΟΓΗΣΗ: Για κάθε BEST BET δώσε 2-3 γραμμές με τα συγκεκριμένα στατιστικά που σε πείθουν.

ΜΟΡΦΗ ΕΞΟΔΟΥ (Telegram):

Για κάθε αγώνα γράψε σύντομα τι βλέπεις (1 γραμμή), και αν ΔΕΝ είναι BEST BET εξήγησε γιατί.

Για BEST BET:
⭐ [Αγώνας] — [Πρόταση] ([X]%)
📊 [Αιτιολόγηση με στατιστικά]

Για ULTRA-SAFE:
🔒 ULTRA-SAFE: [Αγώνας] — [Πρόταση] ([X]%)

Στο τέλος:
━━━━━━━━━━━━━━━━
🏆 BEST BETS ΗΜΕΡΑΣ:
[Λίστα μόνο των BEST BETS]
💡 TOP PICK: [Το καλύτερο]

Αν δεν υπάρχει κανένα ≥75%:
⚠️ Σήμερα δεν υπάρχει αξιόπιστη πρόταση. Καλύτερα να μην παίξεις.

Σημερινοί αγώνες:
{matches_text}
"""

    message = client.messages.create(
        model="claude-sonnet-4-5",
        max_tokens=3000,
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
        standings = standings_cache.get(f["competition"], {})

        # Παράλειψη αν η ομάδα δεν υπάρχει στη βαθμολογία
        if f["home_id"] not in standings or f["away_id"] not in standings:
            print(f"  ⚠️ Παράλειψη {f['home']} vs {f['away']} - εκτός βαθμολογίας")
            continue

        print(f"  📊 {f['home']} vs {f['away']}...")
        try:
            enriched.append({
                **f,
                "home_form":     analyze_team_form(get_team_last_matches(f["home_id"]), f["home_id"]),
                "away_form":     analyze_team_form(get_team_last_matches(f["away_id"]), f["away_id"]),
                "h2h":           get_h2h(f["match_id"]),
                "home_standing": standings.get(f["home_id"], {}),
                "away_standing": standings.get(f["away_id"], {}),
                "odds":          get_odds_full(f["competition"], f["home"], f["away"]),
            })
        except Exception as e:
            print(f"  ⚠️ Παράλειψη {f['home']} vs {f['away']}: {e}")

    if not enriched:
        send_telegram("⚽ Δεν βρέθηκαν παιχνίδια με πλήρη δεδομένα σήμερα.")
        return

    print(f"✅ Αναλύω {len(enriched)} παιχνίδια...")
    print("🤖 Ανάλυση με Claude...")
    today_str = date.today().strftime("%A, %d %B %Y")
    analysis  = analyze_with_claude(enriched)

    print("📨 Αποστολή στο Telegram...")
    send_telegram(f"⚽ *ΠΡΟΒΛΕΨΕΙΣ ΗΜΕΡΑΣ — {today_str}*\n\n" + analysis)
    print("✅ Έτοιμο!")


if __name__ == "__main__":
    main()
