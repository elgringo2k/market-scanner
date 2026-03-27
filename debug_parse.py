import re, json

with open("debug_listing.html") as f:
    html = f.read()

blobs = re.findall(r"<!--(\{.*?\})-->", html, re.DOTALL)

for i, blob in enumerate(blobs):
    try:
        data = json.loads(blob)
        if not (data.get("subevents", {}).get("ids") and data.get("bestOdds", {}).get("ids")):
            continue

        subevents = data["subevents"]["entities"]
        markets = data["markets"]["entities"]
        bets = data["bets"]["entities"]
        best_odds = data["bestOdds"]["entities"]

        # Build: subeventId -> {HOME, DRAW, AWAY} decimal odds
        # markets: marketId -> subeventId
        market_to_sub = {str(m["ocMarketId"]): m["subeventId"] for m in markets.values()}
        # bets: betId -> {genericName, marketId}
        # best_odds: betId -> decimal

        sub_odds = {}  # subeventId -> {HOME, DRAW, AWAY}
        for bet_id, bet in bets.items():
            odds = best_odds.get(bet_id)
            if not odds:
                continue
            market_id = str(bet["marketId"])
            sub_id = market_to_sub.get(market_id)
            if not sub_id:
                continue
            role = bet.get("genericName")  # HOME, DRAW, AWAY
            if role not in ("HOME", "DRAW", "AWAY"):
                continue
            sub_odds.setdefault(sub_id, {})[role] = odds["decimal"]

        print(f"Blob {i}: odds for {len(sub_odds)} subevents")
        for sub_id, odds in list(sub_odds.items())[:3]:
            se = subevents.get(str(sub_id), {})
            print(f"  {se.get('homeTeamName')} vs {se.get('awayTeamName')}: {odds}")
        break
    except Exception as e:
        print(f"Blob {i} error: {e}")
