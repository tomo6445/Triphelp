"""
Domain data for Italy 2027 mission control.
=============================================

Every figure here is researched as of September 2026 (see RESEARCH.md).
Award charts, card offers and release windows move a few times a year -
these are plain dicts on purpose so they're easy to open and edit without
touching any logic in app.py.
"""

from math import radians, sin, cos, atan2, sqrt

# ------------------------------------------------------------------ airports ---
# lat, lon in decimal degrees, for great-circle (haversine) distance in
# statute miles. Only the codes actually used in an option's routing need
# to be looked up, but the full set from the build spec is kept here.
AIRPORTS = {
    "PER": (-31.9403, 115.9669),
    "FCO": (41.8003, 12.2389),
    "MXP": (45.6306, 8.7281),
    "LIN": (45.4451, 9.2767),
    "VCE": (45.5053, 12.3519),
    "LHR": (51.4700, -0.4543),
    "CDG": (49.0097, 2.5479),
    "DOH": (25.2731, 51.6081),
    "SIN": (1.3644, 103.9915),
    "DXB": (25.2532, 55.3657),
    "AUH": (24.4330, 54.6511),
    "KUL": (2.7456, 101.7099),
    "HKG": (22.3080, 113.9185),
    "BKK": (13.6900, 100.7501),
}


def _haversine_mi(a, b):
    """Great-circle distance between two (lat, lon) pairs, in statute miles."""
    R = 3958.8
    lat1, lon1 = a
    lat2, lon2 = b
    p1, p2 = radians(lat1), radians(lat2)
    dphi = radians(lat2 - lat1)
    dlambda = radians(lon2 - lon1)
    h = sin(dphi / 2) ** 2 + cos(p1) * cos(p2) * sin(dlambda / 2) ** 2
    return R * 2 * atan2(sqrt(h), sqrt(1 - h))


def route_distance(codes):
    """Sum of great-circle legs along an ordered list of airport codes."""
    total = 0.0
    for i in range(len(codes) - 1):
        a, b = codes[i], codes[i + 1]
        if a in AIRPORTS and b in AIRPORTS:
            total += _haversine_mi(AIRPORTS[a], AIRPORTS[b])
    return round(total)


# --------------------------------------------------------- programs & release ---
# release_days = days before departure the airline typically loads its
# schedule and opens reward-seat inventory for that date.
PROGRAMS = [
    {
        "code": "SQ", "name": "Singapore Airlines (KrisFlyer)",
        "release_days": 355, "currency": "KrisFlyer miles",
        "notes": ("The one that matters. SQ loads PER-SIN and SIN-MXP/FCO here; "
                  "Velocity only sees the space after SQ loads it. Saver business "
                  "131,500 each way PER-Milan. Round-trip Saver includes a free "
                  "30-day stopover."),
        "search_url": "https://www.singaporeair.com/en_UK/us/ppsclub-krisflyer/use-miles/redeem-miles/",
    },
    {
        "code": "VA", "name": "Velocity Frequent Flyer",
        "release_days": 331, "currency": "Velocity Points",
        "notes": ("The accumulation currency. Books SQ PER-SIN-Europe at 139,000 "
                  "each way - cheaper than transferring to KrisFlyer for the "
                  "identical seat."),
        "search_url": "https://www.velocityfrequentflyer.com/",
    },
    {
        "code": "CX", "name": "Cathay / Asia Miles",
        "release_days": 360, "currency": "Asia Miles",
        "notes": ("PER-HKG-MXP. Through-prices Australia-Europe as one "
                  "ultra-long haul at 119,000 each way. Hard to earn from "
                  "Australia (Amex transfers at 3:1)."),
        "search_url": "https://www.cathaypacific.com/cx/en_AU/book-a-trip/redeem-flights/redeem-flight-awards.html",
    },
    {
        "code": "QF", "name": "Qantas Frequent Flyer",
        "release_days": 353, "currency": "Qantas Points",
        "notes": ("Loads ~353 days out at 00:00 AEST. Books Cathay via HKG at "
                  "the partner rate of 167,000 points each way."),
        "search_url": "https://flightrewardfinder.qantas.com/",
    },
    {
        "code": "QR", "name": "Qatar Privilege Club",
        "release_days": 361, "currency": "Avios",
        "notes": "Via Doha - Middle East not Asia. Fallback option.",
        "search_url": "https://www.qatarairways.com/en/Privilege-Club.html",
    },
    {
        "code": "TG", "name": "Thai / Star Alliance (via KrisFlyer)",
        "release_days": 355, "currency": "KrisFlyer miles",
        "notes": ("Thai flies PER-BKK and BKK-MXP, bookable as a Star Alliance "
                  "partner award through KrisFlyer."),
        "search_url": "https://www.thaiairways.com/en_AU/rewards/rewards_index.page",
    },
    {
        "code": "EK", "name": "Emirates Skywards",
        "release_days": 331, "currency": "Skywards miles",
        "notes": "PER-DXB-MXP daily. High surcharges, worst value. Last resort.",
        "search_url": "https://www.emirates.com/skywards/",
    },
]

# ------------------------------------------------------------------- options ---
# points_ow = points one way in business class. Sort order = priority.
OPTIONS = [
    {
        "priority": 1,
        "name": "Singapore Airlines via Singapore (Velocity points)",
        "program": "Velocity", "airline": "SQ", "routing": "PER-SIN-MXP",
        "points_ow": 139000, "taxes_return_aud": 550,
        "notes": ("Velocity books the SQ seat at 139,000 each way, cheaper than "
                  "moving points to KrisFlyer for the identical seat (131,500 KF "
                  "x 1.55 = 203,825 Velocity). SQ flies SIN-Milan 6x weekly on "
                  "the A350 (departs 23:30) and SIN-Rome daily. Target: 278,000 "
                  "return."),
    },
    {
        "priority": 2,
        "name": "Singapore Airlines via Singapore (KrisFlyer Saver)",
        "program": "KrisFlyer", "airline": "SQ", "routing": "PER-SIN-MXP",
        "points_ow": 131500, "taxes_return_aud": 550,
        "notes": ("Same seat, fewer miles, and a round-trip Saver includes one "
                  "free stopover up to 30 days. The catch is acquisition: "
                  "Amex->KrisFlyer 3:1, Velocity->KrisFlyer 1.55:1. Use only if "
                  "you want the stopover, or Velocity can't see the space."),
    },
    {
        "priority": 3,
        "name": "Cash fare through Asia - buy on sale",
        "program": "Cash", "airline": "CZ/CX/SQ", "routing": "PER-Asia-Italy",
        "points_ow": 0, "taxes_return_aud": 0,
        "notes": ("China Southern via Guangzhou is routinely the cheapest "
                  "business from Perth to Europe in sales (Perth-Madrid "
                  "business has gone at A$5,829 return). Baseline "
                  "A$8,000-9,500; real sale A$5,000-6,500."),
    },
    {
        "priority": 4,
        "name": "Cathay Pacific via Hong Kong (Asia Miles)",
        "program": "Asia Miles", "airline": "CX", "routing": "PER-HKG-MXP",
        "points_ow": 119000, "taxes_return_aud": 900,
        "notes": ("Cheapest points number on the board, but no Australian bank "
                  "card earns Asia Miles and Amex is 3:1, so 238,000 miles "
                  "approx 714,000 MR."),
    },
    {
        "priority": 5,
        "name": "Singapore Airlines via Singapore (KrisFlyer Advantage)",
        "program": "KrisFlyer", "airline": "SQ", "routing": "PER-SIN-MXP",
        "points_ow": 160000, "taxes_return_aud": 550,
        "notes": ("The pressure valve. Advantage costs ~80% more than Saver "
                  "but has far better availability, and SQ Saver business to "
                  "Europe is genuinely scarce."),
    },
    {
        "priority": 6,
        "name": "Cathay via Hong Kong on Qantas points (partner Classic)",
        "program": "Qantas", "airline": "CX", "routing": "PER-HKG-MXP",
        "points_ow": 167000, "taxes_return_aud": 900,
        "notes": ("Same routing as the Asia Miles option, priced through the "
                  "Qantas partner Classic Reward band instead (8,401-9,600 "
                  "miles = 167,000 points each way). A second currency with a "
                  "shot at the same seat."),
    },
    {
        "priority": 7,
        "name": "Thai via Bangkok (KrisFlyer partner award)",
        "program": "KrisFlyer", "airline": "TG", "routing": "PER-BKK-MXP",
        "points_ow": 155000, "taxes_return_aud": 600,
        "notes": ("Second Asia routing if SQ space is dry. Thai flies PER-BKK "
                  "and BKK-MXP, bookable as a Star Alliance partner award "
                  "through KrisFlyer - confirm exact pricing on the calculator "
                  "before counting on this number."),
    },
    {
        "priority": 8,
        "name": "Qatar Qsuite via Doha to Rome (Velocity)",
        "program": "Velocity", "airline": "QR", "routing": "PER-DOH-FCO",
        "points_ow": 119500, "taxes_return_aud": 700,
        "notes": ("Doha-Rome is 2,510 mi, inside Velocity's 2,711 mi band -> "
                  "119,500. Doha-Milan is 2,748 mi -> 139,000. Same currency "
                  "you're already collecting."),
    },
    {
        "priority": 9,
        "name": "Qantas nonstop Perth-Rome (Classic Reward)",
        "program": "Qantas", "airline": "QF", "routing": "PER-FCO",
        "points_ow": 130100, "taxes_return_aud": 450,
        "notes": ("Ruled out by preference, kept for reference. 8,304 mi sits "
                  "in the 7,001-8,400 band = 130,100, the cheapest Qantas "
                  "number from any Australian city, on a seasonal nonstop "
                  "(2026 season 3 May - 23 Oct)."),
    },
]

# --------------------------------------------------------------------- cards ---
# bonus_points is in the card's own earning currency; convert_ratio converts
# that to the target program named in converts_to.
CARDS = [
    {
        "priority": 1, "name": "Amex Platinum", "issuer": "Amex",
        "currency": "MR (Ascent Premium)", "converts_to": "Velocity",
        "convert_ratio": 0.5, "bonus_points": 200000,
        "min_spend": 5000, "spend_days": 90, "annual_fee": 1450,
        "notes": ("Posts fast and transfers to Velocity in 24-48 hours - "
                  "that's why it's first in the sequence. 200,000 MR / 2 = "
                  "100,000 Velocity, over a third of the target from one card."),
    },
    {
        "priority": 2, "name": "Westpac Altitude Velocity Black", "issuer": "Westpac",
        "currency": "Velocity", "converts_to": "Velocity",
        "convert_ratio": 1.0, "bonus_points": 90000,
        "min_spend": 6000, "spend_days": 90, "annual_fee": 370,
        "notes": ("Earns Velocity directly, no transfer step. Adds a 60,000 "
                  "point renewal bonus in year 2."),
    },
    {
        "priority": 3, "name": "Virgin Money High Flyer", "issuer": "Virgin Money",
        "currency": "Velocity", "converts_to": "Velocity",
        "convert_ratio": 1.0, "bonus_points": 80000,
        "min_spend": 7000, "spend_days": 60, "annual_fee": 329,
        "notes": ("Earns Velocity directly. Adds a 20,000 point renewal bonus "
                  "in year 2."),
    },
    {
        "priority": 4, "name": "Amex Explorer", "issuer": "Amex",
        "currency": "MR (Ascent)", "converts_to": "Velocity",
        "convert_ratio": 0.5, "bonus_points": 125000,
        "min_spend": 4000, "spend_days": 90, "annual_fee": 395,
        "notes": ("Amex Ascent tier - cannot transfer to Qantas, Velocity "
                  "only. Irrelevant here since Velocity is the target."),
    },
    {
        "priority": 5, "name": "Westpac Altitude Qantas Black", "issuer": "Westpac",
        "currency": "Qantas", "converts_to": "Qantas",
        "convert_ratio": 1.0, "bonus_points": 90000,
        "min_spend": 6000, "spend_days": 90, "annual_fee": 370,
        "notes": "Qantas track, kept in case the plan pivots away from Velocity.",
    },
    {
        "priority": 6, "name": "ANZ Frequent Flyer Black", "issuer": "ANZ",
        "currency": "Qantas", "converts_to": "Qantas",
        "convert_ratio": 1.0, "bonus_points": 90000,
        "min_spend": 5000, "spend_days": 90, "annual_fee": 425,
        "notes": "Qantas track, kept in case the plan pivots away from Velocity.",
    },
    {
        "priority": 7, "name": "NAB Qantas Rewards Signature", "issuer": "NAB",
        "currency": "Qantas", "converts_to": "Qantas",
        "convert_ratio": 1.0, "bonus_points": 100000,
        "min_spend": 5000, "spend_days": 90, "annual_fee": 420,
        "notes": "Qantas track, kept in case the plan pivots away from Velocity.",
    },
]

ACCELERATORS = [
    "Velocity / Qantas shopping portals for everyday online purchases.",
    "Pay rates, ATO liabilities, insurance and trade invoices via Sniip or "
    "B2Bpay (~1.0-1.5% fee) to clear minimum spends without buying anything extra.",
    "Add a free supplementary cardholder where a bonus applies.",
    "Amex referrals.",
    "Dining, wine and energy partner sign-up bonuses.",
    "Card-to-Velocity transfer bonuses run roughly twice a year (May and "
    "November) at 10-20% - time your last big transfer into one of these windows.",
    "Never transfer speculatively - points only move one way.",
]

# -------------------------------------------------------------------- watches ---
WATCHES = [
    {"program": "KrisFlyer", "origin": "PER", "dest": "MXP", "cabin": "business"},
    {"program": "KrisFlyer", "origin": "PER", "dest": "FCO", "cabin": "business"},
    {"program": "KrisFlyer", "origin": "PER", "dest": "SIN", "cabin": "business"},
    {"program": "KrisFlyer", "origin": "SIN", "dest": "MXP", "cabin": "business"},
    {"program": "Velocity", "origin": "PER", "dest": "MXP", "cabin": "business"},
    {"program": "Velocity", "origin": "PER", "dest": "FCO", "cabin": "business"},
    {"program": "Asia Miles", "origin": "PER", "dest": "MXP", "cabin": "business"},
    {"program": "Cash", "origin": "PER", "dest": "MXP", "cabin": "business"},
    {"program": "Cash", "origin": "PER", "dest": "FCO", "cabin": "business"},
]

# ------------------------------------------------------------------- playbook ---
# anchor "today" -> today + offset days. anchor "departure" -> departure - offset.
PLAYBOOK = [
    {
        "anchor": "today", "offset": 0, "category": "Points",
        "title": "Apply for American Express Platinum",
        "detail": ("First card in the sequence - it posts fast and transfers "
                   "to Velocity in 24-48 hours once you clear the $5,000 "
                   "minimum spend. 200,000 Membership Rewards points / 2 = "
                   "100,000 Velocity, more than a third of the 278,000 target "
                   "from one card."),
    },
    {
        "anchor": "today", "offset": 2, "category": "Setup",
        "title": "Join every program you might redeem in",
        "detail": ("Create free accounts now for Velocity Frequent Flyer, "
                   "KrisFlyer, Asia Miles, Qantas Frequent Flyer and Qatar "
                   "Privilege Club. You need a membership number to search or "
                   "hold an award seat, and joining costs nothing."),
    },
    {
        "anchor": "today", "offset": 3, "category": "Setup",
        "title": "Set your cash target price and start the fare log",
        "detail": ("Confirm your target (A$6,000) and instant-buy (A$5,500) "
                   "thresholds in Settings, then start logging Perth-Italy "
                   "business quotes on the Cash fares tab so the chart has a "
                   "baseline before any sale appears."),
    },
    {
        "anchor": "today", "offset": 7, "category": "Setup",
        "title": "Subscribe to the deal feeds",
        "detail": ("I Know The Pilot, the Australian Frequent Flyer deals "
                   "forum and Point Hacks all cover Perth-origin business "
                   "sales, which sell out in hours. Subscribe now so you're "
                   "not searching cold when a sale lands."),
    },
    {
        "anchor": "today", "offset": 30, "category": "Points",
        "title": "Meet the Amex Platinum minimum spend",
        "detail": ("Clear the $5,000 spend within the 90-day window - route "
                   "regular bills and invoices through the card rather than "
                   "buying anything extra. The 100,000 Velocity points land "
                   "24-48 hours after the points post."),
    },
    {
        "anchor": "departure", "offset": 360, "category": "Award release",
        "title": "Cathay loads the schedule (T-360)",
        "detail": ("Asia Miles opens the furthest out of any program on your "
                   "list. Search PER-HKG-MXP as a through itinerary and search "
                   "each leg separately - an early Cathay search costs nothing "
                   "and tells you whether Hong Kong routing is realistic this "
                   "year."),
    },
    {
        "anchor": "departure", "offset": 355, "category": "Award release",
        "title": "SINGAPORE AIRLINES OPENS - outbound (T-355)",
        "detail": ("The date that matters most. Be logged into KrisFlyer the "
                   "moment the day rolls over - SQ loads PER-SIN and "
                   "SIN-MXP/FCO here, and Velocity can only see the space once "
                   "SQ has released it. Check the through itinerary and each "
                   "leg separately, both Milan and Rome, and both cabins if "
                   "Saver looks thin."),
    },
    {
        "anchor": "departure", "offset": 353, "category": "Award release",
        "title": "Qantas Classic Rewards open (T-353)",
        "detail": ("Qantas Frequent Flyer loads its own inventory, including "
                   "the Cathay via Hong Kong partner award at 167,000 points "
                   "each way. Worth a look even if Velocity is the primary "
                   "plan, since it's a second currency with a shot at the "
                   "same routing."),
    },
    {
        "anchor": "departure", "offset": 331, "category": "Award release",
        "title": "Velocity sees the Singapore space (T-331)",
        "detail": ("Velocity can now book the SQ seat SQ already loaded at "
                   "T-355, at 139,000 points each way - cheaper than "
                   "transferring to KrisFlyer for the identical seat. This is "
                   "the date to actually book option #1 if Saver-level space "
                   "survived the first rush."),
    },
    {
        "anchor": "today", "offset": 90, "category": "Points",
        "title": "Apply for card 2 (Westpac Altitude Velocity Black)",
        "detail": ("90,000 Velocity points direct, no transfer step, for a "
                   "$6,000 spend over 90 days. Space this about 90 days after "
                   "Amex Platinum so the applications don't cluster on your "
                   "credit file."),
    },
    {
        "anchor": "today", "offset": 180, "category": "Points",
        "title": "Apply for card 3 (Virgin Money High Flyer or Amex Explorer)",
        "detail": ("Either adds another 62,500-80,000 Velocity points. Pick "
                   "whichever has the stronger current offer - check Point "
                   "Hacks and the Australian Frequent Flyer card-offer pages "
                   "before applying, since these change monthly."),
    },
    {
        "anchor": "today", "offset": 240, "category": "Points",
        "title": "Watch for a card-to-Velocity transfer bonus",
        "detail": ("Card-to-Velocity transfer bonuses run roughly twice a "
                   "year, around May and November, at 10-20%. Time your last "
                   "big transfer into one of these windows rather than "
                   "transferring speculatively - points only move one way."),
    },
    {
        "anchor": "departure", "offset": 270, "category": "Decision",
        "title": "DECISION GATE - points or cash",
        "detail": ("About nine months out. If the points plan is on track "
                   "and Saver space has appeared, book the award. If Saver "
                   "space never materialised, choose between KrisFlyer "
                   "Advantage and the cash track now - running both tracks "
                   "past this point just means paying twice for the same "
                   "option."),
    },
    {
        "anchor": "departure", "offset": 180, "category": "Cash",
        "title": "Peak cash-sale window opens",
        "detail": ("Perth-Italy business sales cluster from here. China "
                   "Southern via Guangzhou is routinely the cheapest routing "
                   "in a sale; Cathay and Singapore Airlines discount hard "
                   "too. Log everything, even fares above target, so you can "
                   "spot a real sale against the trend."),
    },
    {
        "anchor": "departure", "offset": 120, "category": "Award release",
        "title": "Second seat-release wave",
        "detail": ("Airlines dump unsold premium inventory 3-4 months before "
                   "departure. This is often a better shot at Saver-level "
                   "space than the initial T-355 rush - search the through "
                   "itinerary and each leg again, both directions."),
    },
    {
        "anchor": "departure", "offset": 90, "category": "Decision",
        "title": "HARD DEADLINE - book something",
        "detail": ("Three months out. Take the best available option today "
                   "rather than waiting for something better - fares only "
                   "rise from here, and award space that hasn't appeared by "
                   "now is unlikely to. Cancellation fees on award tickets "
                   "are cheap insurance if something better turns up later."),
    },
    {
        "anchor": "departure", "offset": 60, "category": "Award release",
        "title": "Final cancellation sweep",
        "detail": ("Cancelled award tickets get released back into inventory, "
                   "often close to departure. One last search across every "
                   "program before you commit fully to whatever you've "
                   "booked."),
    },
    {
        "anchor": "departure", "offset": 30, "category": "Trip",
        "title": "Travel insurance, EU ETIAS, seat selection",
        "detail": ("Buy travel insurance, apply for ETIAS (the EU's entry "
                   "authorisation for Australian passport holders - cheap and "
                   "online, but not something to discover at the airport), "
                   "and lock in seat selection on whatever you've booked."),
    },
]

# ----------------------------------------------------------------------- tips ---
TIPS = [
    "A day in Singapore is free. SIN-Milan departs 23:30 and PER-SIN arrives "
    "morning/early afternoon, so a same-day connection leaves 8-15 hours in "
    "the city. No stopover rules, no extra points.",
    "Longer than a day needs KrisFlyer - the free 30-day stopover exists only "
    "on a round-trip Saver on SQ metal. Velocity's version of the same seat "
    "is a connection, not a stopover.",
    "Don't transfer Velocity to KrisFlyer for this trip. 131,500 KF costs "
    "203,825 Velocity at 1.55:1 vs 139,000 Velocity to book the same seat "
    "directly.",
    "Never transfer until you have the seat. KrisFlyer miles expire hard at "
    "3 years with no activity extension, and no transfer reverses.",
    "Saver space is genuinely scarce. Search through-itinerary and each leg, "
    "both directions, whole flex window, Rome as well as Milan.",
    "Advantage is the pressure valve, not a failure - 160,000 each way still "
    "beats A$9,000 cash.",
    "Two one-ways beat a return; each direction prices independently.",
    "Open jaw (into Milan, home from Rome) usually prices the same as a "
    "straight return.",
    "Never pay cash-plus-points - Points Plus Pay values points at ~0.6c; "
    "this routing values them at 2.5-3.5c.",
    "Cancellation fees are cheap insurance: grab any seat on roughly the "
    "right dates and keep hunting.",
    "Amex 18-month rule, banks 12-24 months per issuer - sequence across "
    "different issuers.",
]
