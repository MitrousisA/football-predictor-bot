"""
⚽ Football Prediction Bot - v7 (Expert Analyst System)
=========================================================
Δεδομένα:
  - football-data.org  → fixtures, form, H2H, standings
  - the-odds-api.com   → αποδόσεις 1X2 + Over/Under

Σύστημα: Έμπειρος αναλυτής 30 χρόνων
  - Φίλτρο Α: 1X2 (4/4 κριτήρια)
  - Φίλτρο Β: GG & Over 2.5 (4/5 κριτήρια)
  - Ultra-Safe: Και τα δύο συμφωνούν
  - Μέγιστο 3 BEST BETS ημερησίως
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
                "matchday":    m.get("matchday", "N/A"),
                "stage":       m.get("stage", ""),
            })
    return all_fixtures


def get_team_last_matches(team_id, limit=6):
    """Παίρνει τα τελευταία ματς μιας ομάδας με λεπτομέρειες."""
    today = date.today().isoformat()
    date_from = (date.today() - timedelta(days=120)).isoformat()
    resp = requests.get(
        f"{FOOTBALL_BASE}/teams/{team_id}/matches",
        headers=FOOTBALL_HEADERS,
        params={"dateFrom": date_from, "dateTo": today, "limit": limit, "status": "FINISHED"},
        timeout=10
    )
    if resp.status_code != 200:
        return []
    return resp.json().get("matches", [])[-limit:]


def analyze_team_form(matches, team_id):
    """Αναλύει το form μιας ομάδας από τα τελευταία ματς."""
    if not matches:
        return {
            "form": "N/A",
            "scored_rate": 0,
            "win_streak": 0,
            "loss_streak": 0,
            "goals_per_game": 0,
            "conceded_per_game": 0,
            "over25_rate": 0,
        }

    results = []
    scored_count = 0
    goals_for = 0
    goals_against = 0
    over25_count = 0

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
        if (hg + ag) > 2:
            over25_count += 1

        if gf > ga:
            results.append("W")
        elif gf == ga:
            results.append("D")
        else:
            results.append("L")

    n = len(results)
    if n == 0:
        return {"form": "N/A", "scored_rate": 0, "win_streak": 0,
                "loss_streak": 0, "goals_per_game": 0, "conceded_per_game": 0, "over25_rate": 0}

    # Υπολογισμός streak
    win_streak = 0
    for r in reversed(results):
        if r == "W":
            win_streak += 1
        else:
            break

    loss_streak = 0
    for r in reversed(results):
        if r == "L":
            loss_streak += 1
        else:
            break

    return {
        "form":              "".join(results),
        "scored_rate":       round(scored_count / n, 2),
        "win_streak":        win_streak,
        "loss_streak":       loss_streak,
        "goals_per_game":    round(goals_for / n, 2),
        "conceded_per_game": round(goals_against / n, 2),
        "over25_rate":       round(over25_count / n, 2),
    }


def get_h2h(match_id):
    """Παίρνει H2H με πλήρη ανάλυση."""
    resp = requests.get(
        f"{FOOTBALL_BASE}/matches/{match_id}/head2head",
        headers=FOOTBALL_HEADERS,
        params={"limit": 5},
        timeout=10
    )
    if resp.status_code != 200:
        return {"text": "N/A", "over25_count": 0, "home_wins": 0, "away_wins": 0, "draws": 0, "total": 0}

    matches = resp.json().get("matches", [])
    if not matches:
        return {"text": "N/A", "over25_count": 0, "home_wins": 0, "away_wins": 0, "draws": 0, "total": 0}

    results = []
    over25_count = 0
    gg_count = 0
    home_wins = 0
    away_wins = 0
    draws = 0

    # Παίρνουμε τα ονόματα από το πρώτο ματς για reference
    ref_home = matches[0]["homeTeam"]["name"] if matches else ""

    for m in matches:
        score = m.get("score", {}).get("fullTime", {})
        hg, ag = score.get("home"), score.get("away")
        hn = m["homeTeam"]["name"]
        an = m["awayTeam"]["name"]
        if hg is not None and ag is not None:
            results.append(f"{hn} {hg}-{ag} {an}")
            if (hg + ag) > 2:
                over25_count += 1
            if hg > 0 and ag > 0:
                gg_count += 1
            if hg > ag:
                home_wins += 1
            elif hg < ag:
                away_wins += 1
            else:
                draws += 1

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
                    "position":        team["position"],
                    "points":          team["points"],
                    "played":          played,
                    "won":             team["won"],
                    "gf":              team["goalsFor"],
                    "ga":              team["goalsAgainst"],
                    "goals_per_game":  round(team["goalsFor"] / played, 2),
                    "conceded_per_game": round(team["goalsAgainst"] / played, 2),
                }
    return standings


def get_odds_full(competition_code, home_team, away_team):
    """Παίρνει αποδόσεις 1X2 και Over/Under 2.5."""
    sport_key = ODDS_SPORT_KEYS.get(competition_code)
    if not sport_key:
        return {"h2h": "N/A", "over25": "N/A"}

    result = {"h2h": "N/A", "over25": "N/A"}

    # 1X2
    resp = requests.get(
        f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
        params={"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "h2h", "oddsFormat": "decimal"},
        timeout=10
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

    # Over/Under 2.5
    resp2 = requests.get(
        f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
        params={"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "totals", "oddsFormat": "decimal"},
        timeout=10
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
  Πρωτάθλημα        : {m['league']}
  Ώρα (UTC)         : {m['time']}
  Stage             : {m.get('stage', 'N/A')}

  ΒΑΘΜΟΛΟΓΙΑ:
  Home: {hs.get('position','?')}ος | {hs.get('points','?')} βαθμοί | {hs.get('gf','?')} γκολ υπέρ | {hs.get('ga','?')} κατά | {hs.get('goals_per_game','?')} γκολ/αγώνα | {hs.get('conceded_per_game','?')} δέχεται/αγώνα
  Away: {as_.get('position','?')}ος | {as_.get('points','?')} βαθμοί | {as_.get('gf','?')} γκολ υπέρ | {as_.get('ga','?')} κατά | {as_.get('goals_per_game','?')} γκολ/αγώνα | {as_.get('conceded_per_game','?')} δέχεται/αγώνα
  Διαφορά βαθμών    : {abs(hs.get('points', 0) - as_.get('points', 0))}

  FORM (τελ. 6):
  Home: {hf.get('form','N/A')} | Σκοράρει: {hf.get('scored_rate','?')*100:.0f}% | Γκολ/αγώνα: {hf.get('goals_per_game','?')} | Δέχεται/αγώνα: {hf.get('conceded_per_game','?')} | Win streak: {hf.get('win_streak',0)} | Loss streak: {hf.get('loss_streak',0)}
  Away: {af.get('form','N/A')} | Σκοράρει: {af.get('scored_rate','?')*100:.0f}% | Γκολ/αγώνα: {af.get('goals_per_game','?')} | Δέχεται/αγώνα: {af.get('conceded_per_game','?')} | Win streak: {af.get('win_streak',0)} | Loss streak: {af.get('loss_streak',0)}

  H2H (τελ. 5):
  Αποτελέσματα      : {h2h.get('text','N/A')}
  Over 2.5          : {h2h.get('over25_count',0)}/{h2h.get('total',0)} ματς
  GG (και οι 2)     : {h2h.get('gg_count',0)}/{h2h.get('total',0)} ματς
  Νίκες home team   : {h2h.get('home_wins',0)}/{h2h.get('total',0)}
  Νίκες away team   : {h2h.get('away_wins',0)}/{h2h.get('total',0)}
  Ισοπαλίες         : {h2h.get('draws',0)}/{h2h.get('total',0)}

  ΑΠΟΔΟΣΕΙΣ:
  1X2               : {odds.get('h2h','N/A')}
  Over 2.5          : {odds.get('over25','N/A')}
"""

    prompt = f"""Είσαι έμπειρος αναλυτής ποδοσφαίρου με 30+ χρόνια εμπειρία στην ανάλυση και πρόβλεψη αγώνων. Έχεις αναπτύξει ένα αυστηρό σύστημα που βασίζεται σε αποδεδειγμένα στατιστικά σήματα.

Αναλύεις κάθε αγώνα με δύο ξεχωριστά φίλτρα:

═══════════════════════════════════
ΦΙΛΤΡΟ Α — ΑΠΟΤΕΛΕΣΜΑ (1X2)
Απαιτούνται 4/4:
1. Διαφορά βαθμών > 10 Ή Form διαφορά ≥ 4W vs ≤ 1W στα τελ. 5
2. H2H: ≥ 3/5 νίκες για την ίδια ομάδα
3. Απόδοση 1.25-1.65 (value zone)
4. Εκτός ομάδα σε loss streak ≥ 3 Ή εντός σε win streak ≥ 3
═══════════════════════════════════

═══════════════════════════════════
ΦΙΛΤΡΟ Β — GG & OVER 2.5
Απαιτούνται 4/5:
1. Γκολ υπέρ/αγώνα > 1.4 ΚΑΙ για τις 2 ομάδες
2. Γκολ κατά/αγώνα > 1.2 ΚΑΙ για τις 2 ομάδες
3. H2H: ≥ 3/5 ματς Over 2.5
4. Και οι 2 σκόραραν σε ≥ 80% τελ. ματς
5. Απόδοση Over 2.5 < 1.85
═══════════════════════════════════

ΚΑΝΟΝΕΣ ΕΜΠΕΙΡΙΑΣ:
❌ Αποφεύγω: Derby ματς (απρόβλεπτα)
❌ Αποφεύγω: Αποδόσεις < 1.25 (μηδενικό value)
❌ Αποφεύγω: Ματς χωρίς κίνητρο (ήδη πρωταθλητές/αποβλημένοι)
❌ Αποφεύγω: Stage = GROUP_STAGE τελευταία αγωνιστική (τακτικές ροτάσιες)
✅ Προτιμώ: Αγώνες με υψηλό κίνητρο (τίτλος, CL θέση, υποβιβασμός)
✅ Μέγιστο 3 BEST BETS — αν υπάρχουν περισσότερα επιλέγω τα 3 καλύτερα

ULTRA-SAFE: Όταν ο ΙΔΙΟΣ αγώνας πληροί ΚΑΙ Φίλτρο Α ΚΑΙ Φίλτρο Β

ΜΟΡΦΗ ΕΞΟΔΟΥ (για Telegram):
Για κάθε BEST BET:
⭐ [ΤΥΠΟΣ] | [Αγώνας] | [Πρόταση] | Score: X/4 ή X/5
📊 [Σύντομη αιτιολόγηση 2-3 γραμμές με τα κρίσιμα στατιστικά]

Στο τέλος:
🏆 ΣΥΝΟΨΗ BEST BETS
💡 TOP PICK (μόνο αν υπάρχει Ultra-Safe)
⚠️ Αν κανένας δεν πληροί τα κριτήρια: "Σήμερα δεν υπάρχει αξιόπιστη πρόταση. Μην παίξεις."

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
        print(f"  📊 {f['home']} vs {f['away']}...")
        standings = standings_cache.get(f["competition"], {})

        home_matches = get_team_last_matches(f["home_id"], limit=6)
        away_matches = get_team_last_matches(f["away_id"], limit=6)

        enriched.append({
            **f,
            "home_form":     analyze_team_form(home_matches, f["home_id"]),
            "away_form":     analyze_team_form(away_matches, f["away_id"]),
            "h2h":           get_h2h(f["match_id"]),
            "home_standing": standings.get(f["home_id"], {}),
            "away_standing": standings.get(f["away_id"], {}),
            "odds":          get_odds_full(f["competition"], f["home"], f["away"]),
        })

    print("🤖 Ανάλυση με Claude...")
    today_str = date.today().strftime("%A, %d %B %Y")
    analysis  = analyze_with_claude(enriched)

    print("📨 Αποστολή στο Telegram...")
    send_telegram(f"⚽ *ΠΡΟΒΛΕΨΕΙΣ ΗΜΕΡΑΣ — {today_str}*\n\n" + analysis)
    print("✅ Έτοιμο!")


if __name__ == "__main__":
    main()
