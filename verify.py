"""
LOCAL VERIFIER — Tests every single thing the judge checks before submission.
Run this BEFORE submitting to catch all issues.

Usage:
    python verify.py --url http://localhost:8080
    python verify.py --url https://web-production-37d85b.up.railway.app
"""

import json
import time
import sys
import argparse
import urllib.request
import urllib.error

# ─────────────────────────────────────────────────────────
# HTTP helpers (no extra dependencies)
# ─────────────────────────────────────────────────────────
def get(url, timeout=10):
    try:
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read()), None, r.status
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except:
            body = {}
        return body, str(e), e.code
    except Exception as e:
        return None, str(e), 0

def post(url, data, timeout=30):
    try:
        payload = json.dumps(data).encode()
        req = urllib.request.Request(url, data=payload,
            headers={"Content-Type": "application/json"}, method="POST")
        t0 = time.time()
        with urllib.request.urlopen(req, timeout=timeout) as r:
            body = json.loads(r.read())
            return body, None, r.status, round((time.time()-t0)*1000)
    except urllib.error.HTTPError as e:
        try:
            body = json.loads(e.read())
        except:
            body = {}
        return body, str(e), e.code, 0
    except Exception as e:
        return None, str(e), 0, 0

# ─────────────────────────────────────────────────────────
# Colors
# ─────────────────────────────────────────────────────────
GREEN  = "\033[92m"
RED    = "\033[91m"
YELLOW = "\033[93m"
CYAN   = "\033[96m"
BOLD   = "\033[1m"
RESET  = "\033[0m"
DIM    = "\033[2m"

def ok(msg):   print(f"  {GREEN}✅ PASS{RESET}  {msg}")
def fail(msg): print(f"  {RED}❌ FAIL{RESET}  {msg}"); FAILURES.append(msg)
def warn(msg): print(f"  {YELLOW}⚠️  WARN{RESET}  {msg}"); WARNINGS.append(msg)
def info(msg): print(f"  {CYAN}ℹ️  {RESET}{DIM}{msg}{RESET}")
def section(msg): print(f"\n{BOLD}{'─'*55}\n  {msg}\n{'─'*55}{RESET}")

FAILURES = []
WARNINGS = []

# ─────────────────────────────────────────────────────────
# Sample data for tests
# ─────────────────────────────────────────────────────────
CATEGORY_DENTISTS = {
    "slug": "dentists",
    "voice": {
        "tone": "peer_clinical",
        "vocab_allowed": ["fluoride varnish", "caries", "occlusion", "periapical"],
        "taboos": ["cure", "guaranteed", "best in city"]
    },
    "peer_stats": {"avg_rating": 4.4, "avg_reviews": 62, "avg_ctr": 0.030, "scope": "delhi_solo"},
    "offer_catalog": [
        {"title": "Dental Cleaning @ ₹299", "value": "299"},
        {"title": "Teeth Whitening @ ₹1499", "value": "1499"},
        {"title": "Free Consultation", "value": "0"}
    ],
    "digest": [
        {
            "id": "d_2026W17_jida_fluoride",
            "kind": "research",
            "title": "3-mo fluoride recall cuts caries 38% better than 6-mo",
            "source": "JIDA Oct 2026, p.14",
            "trial_n": 2100,
            "patient_segment": "high_risk_adults",
            "summary": "Trial of 2,100 patients showed 3-month recall significantly better for caries prevention."
        }
    ],
    "seasonal_beats": [{"month_range": "Nov-Feb", "note": "exam-stress bruxism spike"}],
    "trend_signals": [{"query": "clear aligners delhi", "delta_yoy": 0.62, "segment_age": "28-45"}]
}

MERCHANT_DRMEERA = {
    "merchant_id": "m_001_drmeera",
    "category_slug": "dentists",
    "identity": {
        "name": "Dr. Meera's Dental Clinic",
        "city": "Delhi",
        "locality": "Lajpat Nagar",
        "place_id": "ChIJ_TEST_001",
        "verified": True,
        "languages": ["en", "hi"],
        "owner_first_name": "Meera"
    },
    "subscription": {"status": "active", "plan": "Pro", "days_remaining": 82},
    "performance": {
        "window_days": 30,
        "views": 2410, "calls": 18, "directions": 45, "ctr": 0.021,
        "delta_7d": {"views_pct": 0.18, "calls_pct": -0.05}
    },
    "offers": [
        {"id": "o_001", "title": "Dental Cleaning @ ₹299", "status": "active"},
        {"id": "o_002", "title": "Deep Cleaning @ ₹499", "status": "expired"}
    ],
    "conversation_history": [
        {"ts": "2026-04-24T10:00:00Z", "from": "vera",
         "body": "Profile audit done — want me to draft 3 posts?", "engagement": "merchant_replied"},
        {"ts": "2026-04-24T10:05:00Z", "from": "merchant",
         "body": "Yes please, focus on whitening and aligners"}
    ],
    "customer_aggregate": {"total_unique_ytd": 540, "lapsed_180d_plus": 78, "retention_6mo_pct": 0.38},
    "signals": ["stale_posts:22d", "ctr_below_peer_median", "high_risk_adult_cohort"]
}

MERCHANT_STUDIO11 = {
    "merchant_id": "m_002_studio11",
    "category_slug": "salons",
    "identity": {
        "name": "Studio11 Family Salon",
        "city": "Hyderabad",
        "locality": "Kondapur",
        "verified": True,
        "languages": ["en", "hi", "te"],
        "owner_first_name": "Priya"
    },
    "subscription": {"status": "active", "plan": "Pro", "days_remaining": 45},
    "performance": {"views": 3200, "calls": 28, "ctr": 0.048},
    "offers": [
        {"id": "o_s1", "title": "Haircut @ ₹99", "status": "active"},
        {"id": "o_s2", "title": "Hair Spa @ ₹499", "status": "active"}
    ],
    "conversation_history": [],
    "signals": ["high_engagement", "above_peer_median_calls"],
    "customer_aggregate": {"total_unique_ytd": 320, "lapsed_180d_plus": 45, "retention_6mo_pct": 0.52}
}

CATEGORY_SALONS = {
    "slug": "salons",
    "voice": {"tone": "warm_aspirational", "vocab_allowed": ["balayage", "keratin"], "taboos": ["cheapest"]},
    "peer_stats": {"avg_rating": 4.3, "avg_reviews": 48, "avg_ctr": 0.040},
    "offer_catalog": [{"title": "Haircut @ ₹99"}, {"title": "Hair Spa @ ₹499"}],
    "digest": [],
    "seasonal_beats": [{"month_range": "Oct-Nov", "note": "Diwali makeover peak"}],
    "trend_signals": []
}

TRIGGER_RESEARCH = {
    "id": "trg_001_research_dentists",
    "scope": "merchant",
    "kind": "research_digest",
    "source": "external",
    "merchant_id": "m_001_drmeera",
    "customer_id": None,
    "payload": {"category": "dentists", "top_item_id": "d_2026W17_jida_fluoride"},
    "urgency": 2,
    "suppression_key": "research:dentists:2026-W17",
    "expires_at": "2026-05-03T00:00:00Z"
}

TRIGGER_RECALL = {
    "id": "trg_002_recall_priya",
    "scope": "customer",
    "kind": "recall_due",
    "source": "internal",
    "merchant_id": "m_001_drmeera",
    "customer_id": "c_001_priya",
    "payload": {
        "service_due": "6_month_cleaning",
        "last_service_date": "2025-11-04",
        "due_date": "2026-05-04",
        "available_slots": [
            {"iso": "2026-05-07T18:00:00+05:30", "label": "Wed 7 May, 6pm"},
            {"iso": "2026-05-08T17:00:00+05:30", "label": "Thu 8 May, 5pm"}
        ]
    },
    "urgency": 3,
    "suppression_key": "recall:c_001_priya:2026-05",
    "expires_at": "2026-05-10T00:00:00Z"
}

TRIGGER_COMPETITOR = {
    "id": "trg_003_competitor",
    "scope": "merchant",
    "kind": "competitor_opened",
    "source": "external",
    "merchant_id": "m_001_drmeera",
    "customer_id": None,
    "payload": {
        "competitor_name": "Smile Studio",
        "distance_km": 1.3,
        "their_offer": "Dental Cleaning @ ₹199",
        "opened_date": "2026-04-08"
    },
    "urgency": 3,
    "suppression_key": "competitor:smile_studio:m_001:2026",
    "expires_at": "2026-05-10T00:00:00Z"
}

TRIGGER_PERF_DIP = {
    "id": "trg_004_perf_dip",
    "scope": "merchant",
    "kind": "perf_dip",
    "source": "internal",
    "merchant_id": "m_002_studio11",
    "customer_id": None,
    "payload": {"metric": "calls", "delta_pct": -0.40, "window": "7d", "vs_baseline": 28},
    "urgency": 4,
    "suppression_key": "perf_dip:calls:m_002:2026",
    "expires_at": "2026-05-10T00:00:00Z"
}

TRIGGER_FESTIVAL = {
    "id": "trg_005_diwali",
    "scope": "merchant",
    "kind": "festival_upcoming",
    "source": "external",
    "merchant_id": "m_002_studio11",
    "customer_id": None,
    "payload": {"festival": "Diwali", "date": "2026-10-31", "days_until": 180},
    "urgency": 2,
    "suppression_key": "festival:diwali:m_002:2026",
    "expires_at": "2026-11-01T00:00:00Z"
}

TRIGGER_MILESTONE = {
    "id": "trg_006_milestone",
    "scope": "merchant",
    "kind": "milestone_reached",
    "source": "internal",
    "merchant_id": "m_001_drmeera",
    "customer_id": None,
    "payload": {"metric": "review_count", "value_now": 98, "milestone_value": 100, "is_imminent": True},
    "urgency": 2,
    "suppression_key": "milestone:reviews:100:m_001:2026",
    "expires_at": "2026-05-10T00:00:00Z"
}

CUSTOMER_PRIYA = {
    "customer_id": "c_001_priya",
    "merchant_id": "m_001_drmeera",
    "identity": {"name": "Priya", "phone_redacted": "<phone>", "language_pref": "hi-en mix"},
    "relationship": {
        "first_visit": "2025-11-04", "last_visit": "2025-11-04",
        "visits_total": 1, "services_received": ["cleaning"]
    },
    "state": "lapsed_soft",
    "preferences": {"preferred_slots": "weekday_evening", "channel": "whatsapp"},
    "consent": {"opted_in_at": "2025-11-04", "scope": ["recall_reminders"]}
}

# ─────────────────────────────────────────────────────────
# Test helpers
# ─────────────────────────────────────────────────────────
def push_context(base, scope, cid, version, payload):
    data, err, status, ms = post(f"{base}/v1/context", {
        "scope": scope, "context_id": cid, "version": version,
        "payload": payload, "delivered_at": "2026-05-01T10:00:00Z"
    })
    return data, err, status

def check_message_quality(body, label):
    """Heuristic quality checks mirroring the judge rubric."""
    issues = []
    good = []

    # Specificity — numbers are a strong signal
    import re
    numbers = re.findall(r'[\d,]+(?:\.\d+)?%?', body)
    rupee = "₹" in body
    if len(numbers) >= 2 or rupee:
        good.append(f"specificity: {len(numbers)} numbers, rupee={rupee}")
    else:
        issues.append("LOW SPECIFICITY — no concrete numbers or ₹ amounts found")

    # No generic phrases
    generic = ["checking in", "profile update", "let me take care", "got it!", "working on it"]
    found_generic = [g for g in generic if g.lower() in body.lower()]
    if found_generic:
        issues.append(f"GENERIC PHRASES: {found_generic}")
    else:
        good.append("no generic fallback phrases")

    # No fabrication red flags (just check length makes sense)
    if len(body) < 20:
        issues.append("TOO SHORT — likely a fallback response")
    else:
        good.append(f"length OK ({len(body)} chars)")

    # Language check — for Hinglish merchants
    hindi_words = ["hai", "ka", "ke", "aap", "main", "karo", "hoon", "thi", "tha", "bhi"]
    has_hindi = any(w in body.lower().split() for w in hindi_words)

    return issues, good, has_hindi

# ─────────────────────────────────────────────────────────
# VERIFICATION TESTS
# ─────────────────────────────────────────────────────────

def test_1_healthz(base):
    section("TEST 1: GET /v1/healthz")
    data, err, status = get(f"{base}/v1/healthz")
    if err and status == 0:
        fail(f"Bot unreachable: {err}")
        return False
    if status != 200:
        fail(f"Status {status}: {err}")
        return False
    if data.get("status") != "ok":
        fail(f"status field not 'ok': {data}")
        return False
    ok(f"healthz returned 'ok' — uptime={data.get('uptime_seconds')}s")
    info(f"contexts_loaded: {data.get('contexts_loaded', {})}")
    return True

def test_2_metadata(base):
    section("TEST 2: GET /v1/metadata")
    data, err, status = get(f"{base}/v1/metadata")
    if status != 200:
        fail(f"Status {status}: {err}")
        return False
    required = ["team_name", "model", "version", "approach"]
    missing = [k for k in required if not data.get(k)]
    if missing:
        fail(f"Missing fields: {missing}")
        return False
    ok(f"metadata OK — model={data.get('model')}, version={data.get('version')}")
    return True

def test_3_context_push(base):
    section("TEST 3: POST /v1/context — push all 4 scopes")
    passed = True

    # Push category
    d, err, status = push_context(base, "category", "dentists", 1, CATEGORY_DENTISTS)
    if status == 200 and d.get("accepted"):
        ok("category context accepted")
    else:
        fail(f"category push failed: status={status}, {d}")
        passed = False

    # Push merchant
    d, err, status = push_context(base, "merchant", "m_001_drmeera", 1, MERCHANT_DRMEERA)
    if status == 200 and d.get("accepted"):
        ok("merchant context accepted")
    else:
        fail(f"merchant push failed: {d}")
        passed = False

    # Push customer
    d, err, status = push_context(base, "customer", "c_001_priya", 1, CUSTOMER_PRIYA)
    if status == 200 and d.get("accepted"):
        ok("customer context accepted")
    else:
        fail(f"customer push failed: {d}")
        passed = False

    # Push trigger
    d, err, status = push_context(base, "trigger", TRIGGER_RESEARCH["id"], 1, TRIGGER_RESEARCH)
    if status == 200 and d.get("accepted"):
        ok("trigger context accepted")
    else:
        fail(f"trigger push failed: {d}")
        passed = False

    return passed

def test_4_context_idempotent(base):
    section("TEST 4: /v1/context — idempotency (stale version → 409)")

    # Re-push same version → should get 409
    d, err, status = push_context(base, "category", "dentists", 1, CATEGORY_DENTISTS)
    if status == 409:
        ok("stale version correctly returned 409")
    elif status == 200 and d.get("accepted") == False:
        ok("stale version rejected (accepted=false)")
    else:
        fail(f"Expected 409 for same version, got {status}: {d}")
        return False

    # Push higher version → should accept
    d, err, status = push_context(base, "category", "dentists", 2, CATEGORY_DENTISTS)
    if status == 200 and d.get("accepted"):
        ok("higher version accepted (v2 > v1)")
    else:
        fail(f"Higher version not accepted: {d}")
        return False

    return True

def test_5_tick_with_triggers(base):
    section("TEST 5: POST /v1/tick — fires proactive messages with triggers")

    # Push all needed contexts first
    push_context(base, "category", "dentists", 3, CATEGORY_DENTISTS)
    push_context(base, "merchant", "m_001_drmeera", 2, MERCHANT_DRMEERA)
    push_context(base, "trigger", TRIGGER_RESEARCH["id"], 2, TRIGGER_RESEARCH)

    data, err, status, ms = post(f"{base}/v1/tick", {
        "now": "2026-05-01T10:00:00Z",
        "available_triggers": [TRIGGER_RESEARCH["id"]]
    })

    if status != 200:
        fail(f"tick failed: status={status}, {err}")
        return False, None

    actions = data.get("actions", [])
    info(f"Response time: {ms}ms (must be <30000ms)")
    if ms > 30000:
        fail(f"TIMEOUT — {ms}ms exceeds 30s limit")
        return False, None
    else:
        ok(f"Response time OK: {ms}ms")

    if not actions:
        warn("tick returned 0 actions — trigger may have been suppressed already. Testing again with new trigger ID...")
        return True, None

    action = actions[0]
    body = action.get("body", "")
    info(f"Message: \"{body[:120]}{'...' if len(body)>120 else ''}\"")

    # Quality checks
    issues, good, has_hindi = check_message_quality(body, "research_digest")
    for g in good:
        ok(f"quality: {g}")
    for i in issues:
        fail(f"quality: {i}")

    # Required fields
    for field_name in ["conversation_id", "merchant_id", "body", "cta", "rationale", "suppression_key"]:
        if action.get(field_name):
            ok(f"field present: {field_name}")
        else:
            fail(f"missing field: {field_name}")

    return len(issues) == 0, action.get("conversation_id")

def test_6_six_trigger_kinds(base):
    section("TEST 6: Trigger Coverage — all 6 kinds must fire")
    KINDS_TO_TEST = [
        ("research_digest",   "cat_d2", "m_d2", "trg_research_2", "dentists", CATEGORY_DENTISTS, MERCHANT_DRMEERA,   TRIGGER_RESEARCH,    None),
        ("competitor_opened", "cat_d3", "m_d3", "trg_competitor",  "dentists", CATEGORY_DENTISTS, MERCHANT_DRMEERA,   TRIGGER_COMPETITOR,  None),
        ("perf_dip",          "cat_s1", "m_s1", "trg_perf_dip",    "salons",   CATEGORY_SALONS,   MERCHANT_STUDIO11,  TRIGGER_PERF_DIP,    None),
        ("festival_upcoming", "cat_s2", "m_s2", "trg_festival",    "salons",   CATEGORY_SALONS,   MERCHANT_STUDIO11,  TRIGGER_FESTIVAL,    None),
        ("milestone_reached", "cat_d4", "m_d4", "trg_milestone",   "dentists", CATEGORY_DENTISTS, MERCHANT_DRMEERA,   TRIGGER_MILESTONE,   None),
        ("recall_due",        "cat_d5", "m_d5", "trg_recall",      "dentists", CATEGORY_DENTISTS, MERCHANT_DRMEERA,   TRIGGER_RECALL,      CUSTOMER_PRIYA),
    ]

    passed = 0
    for kind, cat_id, merch_id, trg_id, slug, cat_data, merch_data, trg_raw, cust_data in KINDS_TO_TEST:
        # Build unique copies with unique IDs to avoid suppression
        import copy, time as _time
        trg = copy.deepcopy(trg_raw)
        trg["id"] = trg_id
        trg["suppression_key"] = f"verify:{kind}:{int(_time.time())}"
        trg["merchant_id"] = merch_id
        if trg.get("customer_id"):
            trg["customer_id"] = "c_verify_priya"

        merch = copy.deepcopy(merch_data)
        merch["merchant_id"] = merch_id
        merch["category_slug"] = slug

        cat = copy.deepcopy(cat_data)
        cat["slug"] = slug

        push_context(base, "category", slug, 1, cat)
        push_context(base, "merchant", merch_id, 1, merch)
        if cust_data:
            cust = copy.deepcopy(cust_data)
            cust["merchant_id"] = merch_id
            push_context(base, "customer", "c_verify_priya", 1, cust)
        push_context(base, "trigger", trg_id, 1, trg)

        data, err, status, ms = post(f"{base}/v1/tick", {
            "now": "2026-05-01T10:00:00Z",
            "available_triggers": [trg_id]
        })

        if status != 200 or not data.get("actions"):
            fail(f"trigger kind '{kind}' — no action returned")
            continue

        action = data["actions"][0]
        body = action.get("body", "")
        issues, good, _ = check_message_quality(body, kind)
        if issues:
            warn(f"trigger kind '{kind}' fired but low quality: {issues[0]}")
            warn(f"  message: \"{body[:80]}...\"")
        else:
            ok(f"trigger kind '{kind}' — good message: \"{body[:70]}...\"")
            passed += 1

    if passed == 6:
        ok("All 6 trigger kinds fire with quality messages")
    elif passed >= 4:
        warn(f"Only {passed}/6 trigger kinds had quality messages")
    else:
        fail(f"Only {passed}/6 trigger kinds working")
    return passed >= 4

def test_7_reply_merchant(base):
    section("TEST 7: POST /v1/reply — merchant replies (engaged, intent, hostile)")

    # Push base contexts
    push_context(base, "category", "dentists", 4, CATEGORY_DENTISTS)
    push_context(base, "merchant", "m_001_drmeera", 3, MERCHANT_DRMEERA)

    # 7a: Engaged merchant reply
    print(f"\n  {CYAN}7a: Engaged merchant reply{RESET}")
    data, err, status, ms = post(f"{base}/v1/reply", {
        "conversation_id": "conv_verify_engage",
        "merchant_id": "m_001_drmeera",
        "customer_id": None,
        "from_role": "merchant",
        "message": "Yes please send me the JIDA abstract and draft the patient WhatsApp",
        "received_at": "2026-05-01T10:05:00Z",
        "turn_number": 2
    })
    if status != 200:
        fail(f"reply failed: {status}")
    else:
        action = data.get("action", "")
        body = data.get("body", "")
        if action == "send" and body and len(body) > 20:
            issues, good, _ = check_message_quality(body, "engaged_reply")
            ok(f"engaged reply: action=send, body OK ({len(body)} chars)")
            info(f"reply: \"{body[:100]}\"")
            if issues:
                warn(f"quality issue: {issues[0]}")
        else:
            fail(f"engaged reply: action={action}, body='{body[:50]}'")

    # 7b: Intent transition — "Ok let's do it"
    print(f"\n  {CYAN}7b: Intent transition — must switch to ACTION not qualify{RESET}")
    data, err, status, ms = post(f"{base}/v1/reply", {
        "conversation_id": "conv_verify_intent",
        "merchant_id": "m_001_drmeera",
        "customer_id": None,
        "from_role": "merchant",
        "message": "Ok lets do it. Whats next?",
        "received_at": "2026-05-01T10:06:00Z",
        "turn_number": 2
    })
    if status != 200:
        fail(f"intent reply failed: {status}")
    else:
        body = data.get("body", "").lower()
        action = data.get("action", "")
        qualifying = ["would you", "do you", "can you tell me", "what if", "how about", "could you"]
        actioning = ["done", "sending", "draft", "here", "confirm", "proceed", "next", "working", "ready", "prepare"]
        is_qualifying = any(w in body for w in qualifying)
        is_actioning = any(w in body for w in actioning)
        if action == "send" and is_actioning and not is_qualifying:
            ok(f"intent: correctly switched to ACTION mode")
            info(f"reply: \"{data.get('body','')[:100]}\"")
        elif is_qualifying:
            fail(f"intent: still QUALIFYING after commitment — '{data.get('body','')[:80]}'")
        else:
            warn(f"intent: unclear response — '{data.get('body','')[:80]}'")

    # 7c: STOP signal
    print(f"\n  {CYAN}7c: STOP handling — must end conversation{RESET}")
    data, err, status, ms = post(f"{base}/v1/reply", {
        "conversation_id": "conv_verify_stop",
        "merchant_id": "m_001_drmeera",
        "customer_id": None,
        "from_role": "merchant",
        "message": "Stop messaging me. This is useless spam.",
        "received_at": "2026-05-01T10:07:00Z",
        "turn_number": 2
    })
    if status != 200:
        fail(f"stop reply failed: {status}")
    else:
        action = data.get("action", "")
        if action == "end":
            ok("STOP handled correctly — action=end")
        elif action == "send":
            body = data.get("body", "").lower()
            if any(w in body for w in ["sorry", "won't", "noted", "understood"]):
                ok("STOP handled — sent polite acknowledgment")
            else:
                fail(f"STOP not handled — sent: '{data.get('body','')[:60]}'")
        else:
            fail(f"STOP: unexpected action={action}")

    return True

def test_8_auto_reply(base):
    section("TEST 8: Auto-reply detection")
    AUTO_MSG = "Thank you for contacting us! Our team will respond shortly."

    push_context(base, "category", "dentists", 5, CATEGORY_DENTISTS)
    push_context(base, "merchant", "m_001_drmeera", 4, MERCHANT_DRMEERA)

    ended_at_turn = None
    for i in range(1, 5):
        data, err, status, ms = post(f"{base}/v1/reply", {
            "conversation_id": "conv_auto_reply_test",
            "merchant_id": "m_001_drmeera",
            "customer_id": None,
            "from_role": "merchant",
            "message": AUTO_MSG,
            "received_at": "2026-05-01T10:10:00Z",
            "turn_number": i + 1
        })
        if status != 200:
            fail(f"auto-reply turn {i}: request failed")
            continue
        action = data.get("action", "")
        body = data.get("body", "")[:50]
        info(f"auto-reply turn {i}: action={action}, body='{body}'")
        if action == "end":
            ended_at_turn = i
            ok(f"Bot ended at turn {i} — correct auto-reply detection")
            break

    if ended_at_turn is None:
        fail("Bot never ended after 4 identical auto-replies — must detect and exit")
        return False
    elif ended_at_turn <= 2:
        ok(f"Auto-reply detection: ended at turn {ended_at_turn} (good — tried once then exited)")
    else:
        warn(f"Auto-reply detection: took {ended_at_turn} turns to exit (should be ≤2)")
    return True

def test_9_customer_slot_pick(base):
    section("TEST 9: Customer slot pick — must address customer by name")

    push_context(base, "category", "dentists", 6, CATEGORY_DENTISTS)
    push_context(base, "merchant", "m_001_drmeera", 5, MERCHANT_DRMEERA)
    push_context(base, "customer", "c_001_priya", 2, CUSTOMER_PRIYA)

    # Simulate customer picking a slot
    data, err, status, ms = post(f"{base}/v1/reply", {
        "conversation_id": "conv_customer_slot",
        "merchant_id": "m_001_drmeera",
        "customer_id": "c_001_priya",
        "from_role": "customer",
        "message": "Yes please book me for Wed 7 May 6pm",
        "received_at": "2026-05-01T10:15:00Z",
        "turn_number": 2
    })

    if status != 200:
        fail(f"customer slot reply failed: {status}")
        return False

    action = data.get("action", "")
    body = data.get("body", "")
    info(f"Customer slot reply: action={action}")
    info(f"Body: \"{body[:150]}\"")

    passed = True

    # Must be action=send
    if action != "send":
        fail(f"Customer slot: action must be 'send', got '{action}'")
        passed = False
    else:
        ok("action=send ✓")

    # Must address customer by name
    if "priya" in body.lower():
        ok("Customer addressed by name (Priya) ✓")
    else:
        fail("Customer NOT addressed by name — judge will penalize this")
        passed = False

    # Must confirm booking details
    slot_signals = ["wed", "may", "6pm", "confirm", "book", "see you", "appointment"]
    found_slot = [s for s in slot_signals if s in body.lower()]
    if found_slot:
        ok(f"Slot confirmation present: {found_slot}")
    else:
        fail("No slot confirmation in reply — must confirm the specific booking")
        passed = False

    # Must NOT address merchant instead of customer
    merchant_signals = ["dr. meera", "your clinic", "your profile", "your ctr"]
    found_merchant = [s for s in merchant_signals if s in body.lower()]
    if found_merchant:
        fail(f"Reply addresses MERCHANT not customer — wrong! Found: {found_merchant}")
        passed = False
    else:
        ok("Reply correctly addresses customer (not merchant) ✓")

    return passed

def test_10_context_adaptation(base):
    section("TEST 10: Context adaptation — bot uses NEW context injected mid-test")

    # Push updated merchant context with new performance data
    updated_merchant = dict(MERCHANT_DRMEERA)
    updated_merchant["performance"] = {
        "window_days": 30, "views": 4820, "calls": 36, "ctr": 0.041,
        "delta_7d": {"views_pct": 1.00, "calls_pct": 1.00}
    }
    updated_merchant["signals"] = ["perf_spike:100pct", "ctr_above_peer"]
    push_context(base, "merchant", "m_adapt_test", 1, updated_merchant)
    push_context(base, "category", "dentists_adapt", 1, CATEGORY_DENTISTS)

    import copy, time as _time
    trg = copy.deepcopy(TRIGGER_RESEARCH)
    trg["id"] = "trg_adapt_test"
    trg["merchant_id"] = "m_adapt_test"
    trg["suppression_key"] = f"adapt_test:{int(_time.time())}"
    push_context(base, "trigger", "trg_adapt_test", 1, trg)

    # Fix category slug reference
    updated_merchant2 = dict(updated_merchant)
    updated_merchant2["category_slug"] = "dentists_adapt"
    push_context(base, "merchant", "m_adapt_test", 2, updated_merchant2)

    data, err, status, ms = post(f"{base}/v1/tick", {
        "now": "2026-05-01T11:00:00Z",
        "available_triggers": ["trg_adapt_test"]
    })

    if status != 200 or not data.get("actions"):
        warn("context adaptation test: no action returned")
        return True  # Not a hard fail

    body = data["actions"][0].get("body", "")
    # Check if it uses the NEW performance numbers (4820 views, 4.1% CTR)
    has_new_data = "4820" in body or "4,820" in body or "4.1" in body or "36" in body or "spike" in body.lower()
    if has_new_data:
        ok(f"Bot used UPDATED context data in message")
    else:
        warn(f"Bot may not be using latest context — check if new perf numbers appear in message")
    info(f"Message: \"{body[:100]}\"")
    return True

def test_11_schema_compliance(base):
    section("TEST 11: Schema compliance — all response fields correct")

    push_context(base, "category", "dentists", 7, CATEGORY_DENTISTS)
    push_context(base, "merchant", "m_001_drmeera", 6, MERCHANT_DRMEERA)

    import copy, time as _time
    trg = copy.deepcopy(TRIGGER_RESEARCH)
    trg["id"] = "trg_schema_test"
    trg["suppression_key"] = f"schema_test:{int(_time.time())}"
    push_context(base, "trigger", "trg_schema_test", 1, trg)

    data, err, status, ms = post(f"{base}/v1/tick", {
        "now": "2026-05-01T11:30:00Z",
        "available_triggers": ["trg_schema_test"]
    })

    if not data.get("actions"):
        warn("no actions to schema-check")
        return True

    action = data["actions"][0]
    required = {
        "conversation_id": str,
        "merchant_id": str,
        "body": str,
        "cta": str,
        "send_as": str,
        "suppression_key": str,
        "rationale": str
    }
    valid_ctas = {"open_ended", "binary_yes_stop", "none"}
    valid_send_as = {"vera", "merchant_on_behalf"}

    passed = True
    for field_name, ftype in required.items():
        val = action.get(field_name)
        if val is None:
            fail(f"schema: missing field '{field_name}'")
            passed = False
        elif not isinstance(val, ftype):
            fail(f"schema: '{field_name}' wrong type (got {type(val).__name__})")
            passed = False
        else:
            ok(f"schema: '{field_name}' present and correct type")

    if action.get("cta") not in valid_ctas:
        fail(f"schema: cta='{action.get('cta')}' not in {valid_ctas}")
        passed = False
    if action.get("send_as") not in valid_send_as:
        fail(f"schema: send_as='{action.get('send_as')}' not in {valid_send_as}")
        passed = False

    # Reply schema
    data2, err2, status2, ms2 = post(f"{base}/v1/reply", {
        "conversation_id": "conv_schema_reply",
        "merchant_id": "m_001_drmeera",
        "customer_id": None,
        "from_role": "merchant",
        "message": "Tell me more about this research",
        "received_at": "2026-05-01T11:31:00Z",
        "turn_number": 2
    })
    if status2 == 200:
        r_action = data2.get("action")
        if r_action not in {"send", "wait", "end"}:
            fail(f"reply schema: action='{r_action}' not in send/wait/end")
        else:
            ok(f"reply schema: action='{r_action}' valid")
        if r_action == "send" and not data2.get("body"):
            fail("reply schema: action=send but body is empty")
        elif r_action == "send":
            ok(f"reply schema: body present ({len(data2.get('body',''))} chars)")

    return passed

# ─────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────
def main():
    parser = argparse.ArgumentParser(description="Vera Bot Verifier")
    parser.add_argument("--url", default="http://localhost:8080", help="Bot base URL")
    args = parser.parse_args()
    base = args.url.rstrip("/")

    print(f"\n{BOLD}{'='*55}")
    print(f"  VERA BOT VERIFIER")
    print(f"  Testing: {base}")
    print(f"{'='*55}{RESET}")

    tests = [
        ("healthz",              test_1_healthz),
        ("metadata",             test_2_metadata),
        ("context push",         test_3_context_push),
        ("context idempotency",  test_4_context_idempotent),
        ("tick with triggers",   lambda b: test_5_tick_with_triggers(b)[0]),
        ("6 trigger kinds",      test_6_six_trigger_kinds),
        ("merchant replies",     test_7_reply_merchant),
        ("auto-reply detection", test_8_auto_reply),
        ("customer slot pick",   test_9_customer_slot_pick),
        ("context adaptation",   test_10_context_adaptation),
        ("schema compliance",    test_11_schema_compliance),
    ]

    results = []
    for name, fn in tests:
        try:
            result = fn(base)
            results.append((name, result))
        except Exception as e:
            fail(f"{name} CRASHED: {e}")
            results.append((name, False))

    # Summary
    print(f"\n{BOLD}{'='*55}")
    print("  FINAL SUMMARY")
    print(f"{'='*55}{RESET}")
    passed_count = sum(1 for _, r in results if r)
    for name, result in results:
        symbol = f"{GREEN}✅" if result else f"{RED}❌"
        print(f"  {symbol} {name}{RESET}")

    print(f"\n  Score: {passed_count}/{len(tests)} tests passed")

    if FAILURES:
        print(f"\n{RED}{BOLD}  FAILURES to fix before submitting:{RESET}")
        for f in FAILURES:
            print(f"  {RED}• {f}{RESET}")

    if WARNINGS:
        print(f"\n{YELLOW}  WARNINGS (review these):{RESET}")
        for w in WARNINGS:
            print(f"  {YELLOW}• {w}{RESET}")

    if passed_count == len(tests) and not FAILURES:
        print(f"\n{GREEN}{BOLD}  ✅ ALL TESTS PASSED — Safe to submit!{RESET}\n")
        sys.exit(0)
    else:
        print(f"\n{RED}{BOLD}  ❌ Fix failures above before submitting{RESET}\n")
        sys.exit(1)

if __name__ == "__main__":
    main()
