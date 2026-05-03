"""
verify.py — Full judge-simulation test suite for Vera bot
Run: python verify.py --url https://web-production-37d85b.up.railway.app
"""
import sys
import json
import argparse
import requests

GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
RESET = "\033[0m"
BOLD = "\033[1m"

passed = 0
failed = 0

def ok(label, detail=""):
    global passed
    passed += 1
    print(f"  {GREEN}✅ PASS{RESET} {label}" + (f" — {detail}" if detail else ""))

def fail(label, detail=""):
    global failed
    failed += 1
    print(f"  {RED}❌ FAIL{RESET} {label}" + (f" — {detail}" if detail else ""))

def warn(label, detail=""):
    print(f"  {YELLOW}⚠️  WARN{RESET} {label}" + (f" — {detail}" if detail else ""))

def post(url, path, body):
    r = requests.post(f"{url}{path}", json=body, timeout=30)
    return r

def get(url, path):
    r = requests.get(f"{url}{path}", timeout=10)
    return r

def test_healthz(BASE):
    print(f"\n{BOLD}[1] Health Check{RESET}")
    r = get(BASE, "/v1/healthz")
    if r.status_code == 200 and r.json().get("status") == "ok":
        ok("healthz returns 200 with status:ok", str(r.json()))
        if r.json().get("api_key_set"):
            ok("API key is set on Railway")
        else:
            fail("api_key_set is False — ANTHROPIC_API_KEY not set on Railway!")
    else:
        fail("healthz failed", f"status={r.status_code} body={r.text[:100]}")

def test_metadata(BASE):
    print(f"\n{BOLD}[2] Metadata{RESET}")
    r = get(BASE, "/v1/metadata")
    if r.status_code != 200:
        fail("metadata not 200", r.text[:100])
        return
    d = r.json()
    for field in ["bot_name", "version", "author"]:
        if d.get(field):
            ok(f"metadata.{field} = {d[field]}")
        else:
            fail(f"metadata.{field} missing or empty")

def test_context(BASE):
    print(f"\n{BOLD}[3] Context Push & Idempotency{RESET}")
    scopes = [
        {"scope": "category", "context_id": "dentists", "version": 1, "payload": {
            "slug": "dentists", "name": "Dental Clinics",
            "avg_ctr": 0.034, "top_searches": ["teeth cleaning", "braces", "root canal"],
            "avg_rating": 4.2
        }},
        {"scope": "merchant", "context_id": "M001", "version": 1, "payload": {
            "name": "Dr. Meera's Dental Clinic", "type": "dentist",
            "owner_name": "Dr. Meera", "avg_rating": 4.5,
            "offers": ["20% off teeth cleaning", "Free consultation"],
            "ctr": 0.041, "monthly_visits": 230
        }},
        {"scope": "customer", "context_id": "C001", "version": 1, "payload": {
            "name": "Priya Sharma", "customer_name": "Priya",
            "last_visit": "2026-03-15", "preferred_service": "teeth cleaning"
        }},
        {"scope": "trigger", "context_id": "T001", "version": 1, "payload": {
            "description": "regulation change about X-ray equipment standards"
        }},
    ]
    for s in scopes:
        r = post(BASE, "/v1/context", s)
        if r.status_code in (200, 201):
            ok(f"context {s['scope']}::{s['context_id']} accepted")
        else:
            fail(f"context {s['scope']} failed", f"{r.status_code} {r.text[:80]}")

    # Stale version → 409
    r = post(BASE, "/v1/context", {**scopes[0], "version": 0})
    if r.status_code == 409:
        ok("stale version (v0) correctly rejected with 409")
    else:
        fail("stale version should return 409", f"got {r.status_code}")

    # Same version → 200 (idempotent)
    r = post(BASE, "/v1/context", scopes[0])
    if r.status_code == 200:
        ok("duplicate version accepted idempotently (200)")
    else:
        fail("duplicate version should return 200", f"got {r.status_code}")

def test_tick_basic(BASE):
    print(f"\n{BOLD}[4] Tick — Basic{RESET}")
    r = post(BASE, "/v1/tick", {"now": "2026-05-03T10:00:00Z", "available_triggers": []})
    if r.status_code == 200 and r.json().get("actions") == []:
        ok("empty triggers returns empty actions")
    else:
        fail("empty tick failed", r.text[:100])

def test_tick_triggers(BASE):
    print(f"\n{BOLD}[5] Tick — All 6 Trigger Kinds{RESET}")
    trigger_kinds = [
        ("perf_dip", {"drop_pct": 22, "metric": "views", "period": "last 7 days"}),
        ("new_competitor", {"competitor_name": "SmileCare Dental", "distance_km": 0.3}),
        ("festival", {"festival": "Diwali", "days_until": 5}),
        ("research_digest", {"top_query": "teeth whitening", "search_volume": 1200}),
        ("regulation_change", {"regulation": "BIS X-ray equipment standard 2026"}),
        ("low_inventory", {"item": "dental gloves", "units_left": 12}),
    ]

    for kind, payload in trigger_kinds:
        trigger = {
            "trigger_id": f"TRG_{kind.upper()}",
            "merchant_id": "M001",
            "category_slug": "dentists",
            "kind": kind,
            "payload": payload,
        }
        r = post(BASE, "/v1/tick", {
            "now": "2026-05-03T10:00:00Z",
            "available_triggers": [trigger]
        })
        if r.status_code != 200:
            fail(f"tick/{kind} failed", f"{r.status_code} {r.text[:80]}")
            continue
        actions = r.json().get("actions", [])
        if not actions:
            fail(f"tick/{kind} returned no actions (suppressed?)", "try restarting server between tests")
            continue
        body = actions[0].get("body", "")
        word_count = len(body.split())
        if len(body) < 20:
            fail(f"tick/{kind} message too short", repr(body))
        elif word_count > 70:
            warn(f"tick/{kind} message long ({word_count} words)", body[:80])
        else:
            ok(f"tick/{kind}", repr(body[:70]))

        # Check specificity — does it mention real data?
        payload_str = json.dumps(payload).lower()
        body_lower = body.lower()
        specificity_keywords = [str(v).lower() for v in payload.values() if isinstance(v, (str, int, float))]
        hits = [k for k in specificity_keywords if k in body_lower]
        if hits:
            ok(f"  specificity: mentions {hits}")
        else:
            warn(f"  specificity: no payload data in message — score will drop", f"payload was {payload}")

def test_merchant_replies(BASE):
    print(f"\n{BOLD}[6] Reply — Merchant Flow{RESET}")

    session = "sess_merchant_001"

    # Turn 1: engaged reply
    r = post(BASE, "/v1/reply", {
        "session_id": session,
        "from_role": "merchant",
        "merchant_id": "M001",
        "category_slug": "dentists",
        "body": "Got it doc — need help auditing my X-ray setup. We have an old D-speed film unit.",
        "conversation_history": [],
    })
    if r.status_code == 200:
        d = r.json()
        body = d.get("body", "")
        if d.get("action") == "send" and len(body) > 20:
            ok("merchant engaged reply — action=send", repr(body[:70]))
            # Check not generic
            generic = "got it! let me take care" in body.lower()
            if generic:
                fail("reply is GENERIC fallback — Claude not being called")
            else:
                ok("reply is specific (not generic fallback)")
        else:
            fail("merchant reply bad action or empty body", str(d))
    else:
        fail("merchant reply failed", r.text[:100])

    # Turn 2: STOP
    r = post(BASE, "/v1/reply", {
        "session_id": "sess_stop",
        "from_role": "merchant",
        "merchant_id": "M001",
        "body": "STOP",
        "conversation_history": [],
    })
    if r.status_code == 200 and r.json().get("action") == "end":
        ok("STOP correctly returns action=end")
    else:
        fail("STOP not handled correctly", str(r.json() if r.status_code == 200 else r.text[:80]))

def test_auto_reply(BASE):
    print(f"\n{BOLD}[7] Auto-Reply Detection{RESET}")
    session = "sess_auto_001"
    auto_msg = "I am out of office and will reply when I return."

    r1 = post(BASE, "/v1/reply", {
        "session_id": session,
        "from_role": "merchant",
        "merchant_id": "M001",
        "body": auto_msg,
        "conversation_history": [],
    })
    if r1.status_code == 200:
        a1 = r1.json().get("action")
        if a1 == "send":
            ok("first auto-reply → action=send (try once)")
        elif a1 == "end":
            warn("first auto-reply → end immediately (acceptable but not optimal)")
        else:
            fail("unexpected action on first auto-reply", a1)

    r2 = post(BASE, "/v1/reply", {
        "session_id": session,
        "from_role": "merchant",
        "merchant_id": "M001",
        "body": auto_msg,
        "conversation_history": [],
    })
    if r2.status_code == 200 and r2.json().get("action") == "end":
        ok("second auto-reply → action=end (correct exit)")
    else:
        fail("second auto-reply should return end", str(r2.json() if r2.status_code == 200 else r2.text[:80]))

def test_customer_slot(BASE):
    print(f"\n{BOLD}[8] Reply — Customer Slot Pick{RESET}")
    r = post(BASE, "/v1/reply", {
        "session_id": "sess_customer_001",
        "from_role": "customer",
        "merchant_id": "M001",
        "customer_id": "C001",
        "category_slug": "dentists",
        "body": "Yes please book me for Wed 5 Nov, 6pm.",
        "conversation_history": [
            {"role": "vera", "body": "Hi Priya! Dr. Meera ki clinic mein appointment book karein?"}
        ],
    })
    if r.status_code != 200:
        fail("customer reply failed", r.text[:100])
        return
    d = r.json()
    body = d.get("body", "")
    if d.get("action") == "send" and len(body) > 10:
        ok("customer reply action=send", repr(body[:80]))
        # Check it addresses customer
        if "priya" in body.lower():
            ok("reply addresses customer by name ✅")
        else:
            warn("reply doesn't mention customer name — Specificity score hit")
        # Check it confirms the slot
        if any(w in body.lower() for w in ["5 nov", "6pm", "6 pm", "wednesday", "wed", "confirm", "book"]):
            ok("reply confirms the booking slot ✅")
        else:
            warn("reply doesn't confirm slot details — will cost Specificity points")
    else:
        fail("customer reply bad response", str(d))

def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--url", required=True, help="Bot base URL e.g. https://mybot.up.railway.app")
    args = parser.parse_args()
    BASE = args.url.rstrip("/")

    print(f"\n{'='*60}")
    print(f"  VERA BOT VERIFICATION SUITE")
    print(f"  Testing: {BASE}")
    print(f"{'='*60}")

    try:
        test_healthz(BASE)
        test_metadata(BASE)
        test_context(BASE)
        test_tick_basic(BASE)
        test_tick_triggers(BASE)
        test_merchant_replies(BASE)
        test_auto_reply(BASE)
        test_customer_slot(BASE)
    except requests.exceptions.ConnectionError:
        print(f"\n{RED}FATAL: Cannot connect to {BASE}{RESET}")
        print("Make sure your Railway deployment is running.")
        sys.exit(1)

    print(f"\n{'='*60}")
    total = passed + failed
    if failed == 0:
        print(f"  {GREEN}{BOLD}ALL {total} TESTS PASSED ✅ — Ready to submit!{RESET}")
    else:
        print(f"  {RED}{BOLD}{failed}/{total} TESTS FAILED{RESET} — Fix before submitting")
        print(f"  {GREEN}{passed}/{total} passed{RESET}")
    print(f"{'='*60}\n")

if __name__ == "__main__":
    main()
