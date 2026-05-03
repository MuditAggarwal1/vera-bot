"""
Vera Bot Server — magicpin AI Challenge submission v2
Full Claude-powered implementation fixing all judge feedback issues.
"""

from __future__ import annotations
import os
import time
import json
import uuid
import re
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import httpx

# ─────────────────────────────────────────────
# App + stores
# ─────────────────────────────────────────────
app = FastAPI(title="Vera Bot", version="2.0.0")
START = time.time()

contexts: dict[tuple[str, str], dict] = {}
conversations: dict[str, dict] = {}
fired_suppression: set[str] = set()

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-haiku-4-5-20251001"

# ─────────────────────────────────────────────
# Claude caller — direct HTTP, bypasses SDK auth issues
# ─────────────────────────────────────────────
def call_claude(system: str, user: str, max_tokens: int = 1000) -> str:
    api_key = os.environ.get("ANTHROPIC_API_KEY", "")
    headers = {
        "x-api-key": api_key,
        "anthropic-version": "2023-06-01",
        "content-type": "application/json",
    }
    body = {
        "model": MODEL,
        "max_tokens": max_tokens,
        "temperature": 0,
        "system": system,
        "messages": [{"role": "user", "content": user}],
    }
    with httpx.Client(timeout=25.0) as client:
        resp = client.post(ANTHROPIC_API_URL, headers=headers, json=body)
        resp.raise_for_status()
        data = resp.json()
        return data["content"][0]["text"].strip()

def parse_json(text: str) -> dict:
    text = re.sub(r"^```json\s*", "", text)
    text = re.sub(r"^```\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return json.loads(text.strip())

# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────
def get_payload(scope: str, cid: str) -> Optional[dict]:
    entry = contexts.get((scope, cid))
    return entry["payload"] if entry else None

def lang_hint(merchant: dict) -> str:
    langs = merchant.get("identity", {}).get("languages", ["en"])
    if "hi" in langs:
        return "Use natural Hindi-English code-mix (Hinglish) throughout — as real WhatsApp messages to Indian merchants sound."
    if any(l in langs for l in ["ta", "te", "kn", "mr"]):
        return "Use warm, friendly English. Keep it local and personal."
    return "Use clear, friendly English."

def is_auto_reply(msg: str) -> bool:
    sigs = [
        "aapki jaankari ke liye", "thank you for contacting",
        "i am currently unavailable", "main ek automated",
        "automated assistant", "automated response",
        "we will get back", "bahut-bahut shukriya",
        "aapki madad ke liye shukriya", "hamari team tak pahuncha",
        "i will pass this on", "forwarding your message",
        "this is an automated", "auto-reply",
    ]
    lower = msg.lower()
    return any(s in lower for s in sigs)

def wants_stop(msg: str) -> bool:
    sigs = [
        "not interested", "nahi chahiye", "band karo", "stop messaging",
        "don't contact", "remove me", "unsubscribe", "nahin chahiye",
        "mat bhejo", "please stop", "mujhe nahi chahiye",
    ]
    return any(s in msg.lower() for s in sigs)

def has_intent(msg: str) -> bool:
    sigs = [
        "judrna hai", "join karna hai", "i want to join", "let's do it",
        "go ahead", "yes let's", "kar do", "shuru karo", "haan karo",
        "sign me up", "ok do it", "chalega", "theek hai karo", "haan bilkul",
        "please do it", "yes please proceed",
    ]
    return any(s in msg.lower() for s in sigs)

# ─────────────────────────────────────────────
# System prompts
# ─────────────────────────────────────────────
COMPOSER_SYSTEM = """You are Vera — magicpin's AI WhatsApp assistant for Indian merchants (dentists, salons, restaurants, gyms, pharmacies).

Compose ONE perfect WhatsApp message grounded entirely in the provided context.

MANDATORY RULES:
1. SPECIFICITY: Use real numbers from context — CTR%, call counts, peer stats, dates, prices. "Your CTR is 2.1% vs peer 3.0%" beats vague advice. Service+price ("Dental Cleaning @ ₹299") beats "10% off".
2. NO FABRICATION: Never invent stats, citations, competitor names, offers not in context.
3. VOICE by category:
   - dentists: clinical-peer tone, technical vocab OK ("fluoride varnish", "caries"), NO "cure"/"guaranteed"
   - salons: warm, aspirational, price-specific
   - restaurants: food-first, local pride, deal-specific
   - gyms: energetic, outcome-focused
   - pharmacies: helpful, trust-building, health-specific
4. ONE CTA MAX: Binary YES/STOP for action triggers. Open question for info triggers. None for pure reminders. CTA always LAST sentence.
5. NO PREAMBLE: Never start with "I hope you're doing well". Jump to the hook.
6. LANGUAGE: Match merchant's language. Hinglish for "hi" merchants. Natural blend, not forced.
7. SHORT: 3-6 sentences for merchant messages. 2-4 for customer messages.
8. COMPULSION LEVERS (use 1-2): loss aversion, social proof, effort externalization ("I've drafted X — just say go"), curiosity ("want to see?"), specificity, single binary CTA.

FOR CUSTOMER-FACING (send_as=merchant_on_behalf):
- Address THE CUSTOMER by their first name
- Write AS the merchant/clinic/salon
- Use the customer's language preference
- Reference their specific service, slots, relationship
- Warm and personal tone

OUTPUT: JSON only, no markdown:
{
  "body": "message text",
  "cta": "open_ended" | "binary_yes_stop" | "none",
  "send_as": "vera" | "merchant_on_behalf",
  "suppression_key": "kind:merchant_id:period",
  "rationale": "1-2 sentences on lever used and why"
}"""

REPLY_SYSTEM = """You are Vera — magicpin's AI WhatsApp assistant for Indian merchants.

You are in an active conversation. Produce the best next reply.

CRITICAL — READ from_role carefully:
- from_role = "merchant": Reply AS VERA to the MERCHANT. Be helpful, specific, action-oriented.
- from_role = "customer": Reply AS THE MERCHANT (Vera drafts it) addressed TO THE CUSTOMER by name. Confirm bookings, answer service questions, provide slot details.

SLOT BOOKING (most important):
- Customer picks a slot ("Yes book Wed 6pm" / "1" / "confirm") → Confirm clearly: name, service, day, time, any price. Thank them. End warmly.
- Example good reply: "Perfect Priya! Your Dental Cleaning (₹299) is confirmed for Wed 5 Nov at 6pm. Dr. Meera's clinic, Lajpat Nagar. See you then! 🦷"

INTENT ROUTING:
- Merchant says YES/go ahead/kar do → Switch to ACTION immediately. Do NOT ask another qualifying question.
- Merchant says STOP/not interested → action = "end"

SPECIFICITY: Use real data from context. Never generic.
LANGUAGE: Match merchant's or customer's preference.
NO REPETITION: Never repeat the previous turn verbatim.

OUTPUT: JSON only:
{
  "action": "send" | "wait" | "end",
  "body": "text (required if send)",
  "cta": "open_ended" | "binary_yes_stop" | "none",
  "rationale": "brief reason"
}"""

# ─────────────────────────────────────────────
# Composers
# ─────────────────────────────────────────────
def build_compose_prompt(category, merchant, trigger, customer):
    p = []
    p.append("=== CATEGORY ===")
    p.append(f"Slug: {category.get('slug','')}")
    p.append(f"Voice: {json.dumps(category.get('voice', {}))}")
    p.append(f"Peer stats: {json.dumps(category.get('peer_stats', {}))}")
    digest = category.get("digest", [])[:3]
    if digest:
        p.append(f"Digest/research: {json.dumps(digest)}")
    offers_cat = category.get("offer_catalog", [])[:4]
    if offers_cat:
        p.append(f"Offer templates: {json.dumps(offers_cat)}")
    seasonal = category.get("seasonal_beats", [])[:2]
    if seasonal:
        p.append(f"Seasonal beats: {json.dumps(seasonal)}")
    trends = category.get("trend_signals", [])[:2]
    if trends:
        p.append(f"Trends: {json.dumps(trends)}")

    p.append("\n=== MERCHANT ===")
    p.append(f"Identity: {json.dumps(merchant.get('identity', {}))}")
    p.append(f"Subscription: {json.dumps(merchant.get('subscription', {}))}")
    p.append(f"Performance 30d: {json.dumps(merchant.get('performance', {}))}")
    active = [o for o in merchant.get("offers", []) if o.get("status") == "active"]
    p.append(f"Active offers: {json.dumps(active)}")
    p.append(f"Signals: {json.dumps(merchant.get('signals', []))}")
    p.append(f"Customer aggregate: {json.dumps(merchant.get('customer_aggregate', {}))}")
    hist = merchant.get("conversation_history", [])[-3:]
    if hist:
        p.append(f"Recent Vera history: {json.dumps(hist)}")

    p.append("\n=== TRIGGER ===")
    p.append(json.dumps(trigger, indent=2))

    if customer:
        p.append("\n=== CUSTOMER (message goes TO this person, FROM the merchant) ===")
        p.append(json.dumps(customer, indent=2))
        p.append("send_as = 'merchant_on_behalf'. Address the customer by their first name.")

    p.append(f"\nLanguage: {lang_hint(merchant)}")
    p.append("\nCompose now. Return JSON only.")
    return "\n".join(p)

def compose_initial(category, merchant, trigger, customer):
    prompt = build_compose_prompt(category, merchant, trigger, customer)
    try:
        text = call_claude(COMPOSER_SYSTEM, prompt, max_tokens=900)
        return parse_json(text)
    except Exception as e:
        name = merchant.get("identity", {}).get("name", "there")
        kind = trigger.get("kind", "update")
        mid = merchant.get("merchant_id", "x")
        return {
            "body": f"Hi {name}, aapke {kind} ke baare mein ek update hai — dekhen? Reply YES.",
            "cta": "binary_yes_stop",
            "send_as": "vera",
            "suppression_key": f"{kind}:{mid}:2026",
            "rationale": f"Fallback ({str(e)[:80]})"
        }

def compose_reply(from_role, message, merchant, category, customer, history, turn_number, conv_id):
    auto_count = sum(1 for t in history if t.get("is_auto_reply"))

    # Auto-reply logic
    if is_auto_reply(message):
        if auto_count >= 1:
            return {"action": "end", "rationale": "Second auto-reply detected — gracefully exiting."}
        name = merchant.get("identity", {}).get("name", "")
        try:
            text = call_claude(
                REPLY_SYSTEM,
                f"""Merchant name: {name}
Language: {lang_hint(merchant)}
Situation: WhatsApp Business auto-reply just detected (first time). 
Compose one short, direct message to reach the real owner — acknowledge you know it's auto-reply, ask if they're available.
Return JSON: {{"action":"send","body":"...","cta":"open_ended","rationale":"..."}}"""
            )
            return parse_json(text)
        except:
            return {
                "action": "send",
                "body": f"Hi, main samajh gayi yeh auto-reply hai — kya aap khud 2 minute available hain? Ek important update share karni thi.",
                "cta": "open_ended",
                "rationale": "Gentle prod after first auto-reply."
            }

    if wants_stop(message):
        return {"action": "end", "rationale": "Stop signal detected — exiting politely."}

    # Build full context for reply
    p = [
        f"from_role: {from_role}",
        f"message: \"{message}\"",
        f"turn_number: {turn_number}",
        f"merchant: {json.dumps(merchant.get('identity', {}))}",
        f"category: {category.get('slug', '')}",
        f"peer_stats: {json.dumps(category.get('peer_stats', {}))}",
        f"active_offers: {json.dumps([o for o in merchant.get('offers',[]) if o.get('status')=='active'])}",
        f"signals: {json.dumps(merchant.get('signals', []))}",
        f"language: {lang_hint(merchant)}",
        f"intent_expressed: {has_intent(message)}",
    ]

    if customer and from_role == "customer":
        p.append(f"customer_context: {json.dumps(customer)}")
        p.append("IMPORTANT: Reply is FROM merchant TO customer. Address customer by first name. Confirm their slot/request specifically.")

    p.append(f"\nconversation_history:\n{json.dumps(history[-6:], indent=2)}")
    p.append("\nCompose the ideal reply. JSON only.")

    try:
        text = call_claude(REPLY_SYSTEM, "\n".join(p), max_tokens=600)
        result = parse_json(text)
        if "action" not in result:
            result["action"] = "send"
        return result
    except Exception as e:
        if from_role == "customer":
            cname = customer.get("identity", {}).get("name", "there") if customer else "there"
            return {
                "action": "send",
                "body": f"Thank you {cname}! We've noted your request and will confirm very shortly. Looking forward to seeing you! 😊",
                "cta": "none",
                "rationale": f"Customer fallback: {str(e)[:60]}"
            }
        return {
            "action": "send",
            "body": "Noted! Working on it right now — will share details shortly.",
            "cta": "none",
            "rationale": f"Merchant fallback: {str(e)[:60]}"
        }

# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────
class CtxBody(BaseModel):
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: str

class TickBody(BaseModel):
    now: str
    available_triggers: list[str] = []

class ReplyBody(BaseModel):
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str
    message: str
    received_at: str
    turn_number: int

# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────
@app.get("/v1/healthz")
async def healthz():
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _) in contexts.keys():
        if scope in counts:
            counts[scope] += 1
    return {"status": "ok", "uptime_seconds": int(time.time() - START), "contexts_loaded": counts}

@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": "Vera Bot",
        "team_members": ["Mudit Aggarwal"],
        "model": MODEL,
        "approach": "Claude-powered 4-context composer with customer-voiced replies, auto-reply detection, intent routing, Hinglish support",
        "contact_email": "team@example.com",
        "version": "2.0.0",
        "submitted_at": datetime.now(timezone.utc).isoformat()
    }

@app.post("/v1/context")
async def push_context(body: CtxBody):
    valid = {"category", "merchant", "customer", "trigger"}
    if body.scope not in valid:
        return JSONResponse(status_code=400, content={
            "accepted": False, "reason": "invalid_scope", "details": f"Must be one of {valid}"
        })
    key = (body.scope, body.context_id)
    cur = contexts.get(key)
    if cur and cur["version"] >= body.version:
        return JSONResponse(status_code=409, content={
            "accepted": False, "reason": "stale_version", "current_version": cur["version"]
        })
    contexts[key] = {"version": body.version, "payload": body.payload}
    return {
        "accepted": True,
        "ack_id": f"ack_{body.context_id}_v{body.version}",
        "stored_at": datetime.now(timezone.utc).isoformat()
    }

@app.post("/v1/tick")
async def tick(body: TickBody):
    actions = []
    for trg_id in body.available_triggers:
        trg = get_payload("trigger", trg_id)
        if not trg:
            continue
        suppression_key = trg.get("suppression_key", trg_id)
        if suppression_key in fired_suppression:
            continue
        merchant_id = trg.get("merchant_id")
        if not merchant_id:
            continue
        merchant = get_payload("merchant", merchant_id)
        if not merchant:
            continue
        category_slug = merchant.get("category_slug", "")
        category = get_payload("category", category_slug)
        if not category:
            continue
        customer_id = trg.get("customer_id")
        customer = get_payload("customer", customer_id) if customer_id else None

        composed = compose_initial(category, merchant, trg, customer)
        fired_suppression.add(suppression_key)

        conv_id = f"conv_{merchant_id}_{trg_id}_{uuid.uuid4().hex[:6]}"
        conversations[conv_id] = {
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "turns": [{"from": "vera", "body": composed["body"], "ts": body.now}]
        }

        merchant_name = merchant.get("identity", {}).get("name", "Merchant")
        trg_kind = trg.get("kind", "update")

        actions.append({
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": composed.get("send_as", "vera"),
            "trigger_id": trg_id,
            "template_name": f"vera_{trg_kind}_v2",
            "template_params": [merchant_name, trg_kind, "magicpin"],
            "body": composed["body"],
            "cta": composed.get("cta", "open_ended"),
            "suppression_key": suppression_key,
            "rationale": composed.get("rationale", "")
        })

        if len(actions) >= 20:
            break

    return {"actions": actions}

@app.post("/v1/reply")
async def reply(body: ReplyBody):
    conv_id = body.conversation_id
    conv = conversations.get(conv_id, {})

    merchant_id = body.merchant_id or conv.get("merchant_id")
    customer_id = body.customer_id or conv.get("customer_id")

    merchant = get_payload("merchant", merchant_id) if merchant_id else None
    if not merchant:
        return {"action": "end", "rationale": "Merchant context not found."}

    category = get_payload("category", merchant.get("category_slug", "")) or {}
    customer = get_payload("customer", customer_id) if customer_id else None

    if conv_id not in conversations:
        conversations[conv_id] = {"merchant_id": merchant_id, "customer_id": customer_id, "turns": []}
        conv = conversations[conv_id]

    history = conversations[conv_id].get("turns", [])
    is_auto = is_auto_reply(body.message)

    history.append({
        "from": body.from_role,
        "body": body.message,
        "ts": body.received_at,
        "is_auto_reply": is_auto,
        "turn_number": body.turn_number
    })

    result = compose_reply(
        from_role=body.from_role,
        message=body.message,
        merchant=merchant,
        category=category,
        customer=customer,
        history=history,
        turn_number=body.turn_number,
        conv_id=conv_id,
    )

    if result.get("action") == "send":
        history.append({
            "from": "vera",
            "body": result.get("body", ""),
            "ts": datetime.now(timezone.utc).isoformat()
        })

    conversations[conv_id]["turns"] = history
    return result

@app.post("/v1/teardown")
async def teardown():
    contexts.clear()
    conversations.clear()
    fired_suppression.clear()
    return {"status": "cleared"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("bot_server:app", host="0.0.0.0", port=port, reload=False)
