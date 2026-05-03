"""
Vera Bot — magicpin AI Challenge
Fixed version: direct HTTP to Anthropic, proper from_role branching, rich context-grounded prompts
"""

import os
import json
import time
import httpx
from datetime import datetime, timezone
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse

app = FastAPI()

# ─── In-memory stores ────────────────────────────────────────────────────────
contexts: dict[str, dict] = {}          # key: f"{scope}::{context_id}"
reply_state: dict[str, dict] = {}       # key: session_id → {turns, auto_reply_count}
suppression: dict[str, float] = {}     # key: suppression_key → expires_ts

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
MODEL = "claude-3-5-haiku-20241022"
START_TIME = time.time()

# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_api_key():
    key = os.environ.get("ANTHROPIC_API_KEY", "")
    if not key:
        raise RuntimeError("ANTHROPIC_API_KEY not set")
    return key


async def call_claude(system: str, user: str, max_tokens: int = 300) -> str:
    """Direct HTTP call to Anthropic — no SDK, no import issues."""
    try:
        api_key = get_api_key()
        async with httpx.AsyncClient(timeout=25.0) as client:
            resp = await client.post(
                ANTHROPIC_API_URL,
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": MODEL,
                    "max_tokens": max_tokens,
                    "system": system,
                    "messages": [{"role": "user", "content": user}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            return data["content"][0]["text"].strip()
    except Exception as e:
        return f"[API_ERROR: {e}]"


def ctx(scope: str, context_id: str) -> dict:
    return contexts.get(f"{scope}::{context_id}", {}).get("payload", {})


def is_suppressed(key: str) -> bool:
    exp = suppression.get(key)
    if exp and time.time() < exp:
        return True
    return False


def suppress(key: str, hours: float = 24.0):
    suppression[key] = time.time() + hours * 3600


# ─── Endpoints ───────────────────────────────────────────────────────────────

@app.get("/v1/healthz")
async def healthz():
    counts = {}
    for k in contexts:
        scope = k.split("::")[0]
        counts[scope] = counts.get(scope, 0) + 1
    return {
        "status": "ok",
        "uptime_seconds": round(time.time() - START_TIME),
        "contexts_loaded": counts,
        "api_key_set": bool(os.environ.get("ANTHROPIC_API_KEY")),
    }


@app.get("/v1/metadata")
async def metadata():
    return {
        "bot_name": "Vera",
        "version": "3.0.0",
        "author": "Mudit Aggarwal",
        "description": "Context-grounded merchant engagement bot powered by Claude",
        "capabilities": ["tick", "context", "reply"],
    }


@app.post("/v1/context")
async def push_context(request: Request):
    body = await request.json()
    scope = body["scope"]
    context_id = body["context_id"]
    version = body["version"]
    key = f"{scope}::{context_id}"

    existing = contexts.get(key)
    if existing:
        if version < existing["version"]:
            raise HTTPException(status_code=409, detail="Stale version rejected")
        if version == existing["version"]:
            return JSONResponse({"status": "duplicate", "key": key}, status_code=200)

    contexts[key] = {
        "scope": scope,
        "context_id": context_id,
        "version": version,
        "payload": body.get("payload", {}),
        "delivered_at": body.get("delivered_at"),
    }
    return {"status": "accepted", "key": key, "version": version}


@app.post("/v1/tick")
async def tick(request: Request):
    body = await request.json()
    now_str = body.get("now", datetime.now(timezone.utc).isoformat())
    available_triggers = body.get("available_triggers", [])

    if not available_triggers:
        return {"actions": []}

    actions = []
    for trigger in available_triggers:
        trigger_id = trigger.get("trigger_id", "")
        merchant_id = trigger.get("merchant_id", "")
        category_slug = trigger.get("category_slug", "")
        customer_id = trigger.get("customer_id")
        kind = trigger.get("kind", "")
        payload = trigger.get("payload", {})

        # Only suppress if same trigger_id already fired (not just kind+merchant)
        sup_key = f"tick::{trigger_id}"
        if is_suppressed(sup_key):
            continue

        # Gather all context
        merchant_ctx = ctx("merchant", merchant_id)
        category_ctx = ctx("category", category_slug)
        customer_ctx = ctx("customer", customer_id) if customer_id else {}
        trigger_ctx = ctx("trigger", trigger_id)

        merchant_name = merchant_ctx.get("name") or merchant_ctx.get("business_name") or f"Merchant {merchant_id}"
        merchant_type = merchant_ctx.get("type") or category_ctx.get("name") or category_slug
        owner_name = merchant_ctx.get("owner_name") or merchant_ctx.get("contact_name") or ""
        top_offer = ""
        if merchant_ctx.get("offers"):
            top_offer = merchant_ctx["offers"][0] if isinstance(merchant_ctx["offers"], list) else str(merchant_ctx["offers"])
        avg_rating = merchant_ctx.get("avg_rating") or merchant_ctx.get("rating", "")
        ctr = merchant_ctx.get("ctr") or merchant_ctx.get("click_through_rate", "")

        customer_name = customer_ctx.get("name") or customer_ctx.get("customer_name") or ""
        customer_history = customer_ctx.get("last_visit") or customer_ctx.get("visit_history") or ""

        system_prompt = f"""You are Vera, a friendly and sharp AI assistant from magicpin who helps merchants grow their business.
You compose short WhatsApp messages (1-3 sentences, max 60 words) that are:
- Conversational and warm, mixing Hindi and English naturally (Hinglish)
- Hyper-specific: mention real numbers, offers, merchant name, or recent stats when available
- Action-oriented: always end with a clear next step or question
- Never generic — every message should feel tailor-made

Merchant info:
- Name: {merchant_name}
- Type: {merchant_type}
- Owner: {owner_name}
- Top offer: {top_offer}
- Rating: {avg_rating}
- CTR: {ctr}

Trigger kind: {kind}
Trigger payload: {json.dumps(payload)}
Category context: {json.dumps(category_ctx)}
"""

        # Build kind-specific instruction with hard payload injection
        kind_instructions = {
            "perf_dip": f"Views {payload.get('drop_pct', '')}% girein hain {payload.get('period', 'recently')} mein. Yeh number ZAROOR mention karo.",
            "new_competitor": f"'{payload.get('competitor_name', 'ek naya competitor')}' sirf {payload.get('distance_km', '')} km door khula hai. Yeh naam aur distance ZAROOR mention karo.",
            "festival": f"{payload.get('festival', 'upcoming festival')} mein sirf {payload.get('days_until', '')} din bacha hai. Festival name aur days ZAROOR mention karo.",
            "research_digest": f"'{payload.get('top_query', '')}' {payload.get('search_volume', '')} baar search hua is week. Query aur volume ZAROOR mention karo.",
            "regulation_change": f"Naya regulation: '{payload.get('regulation', '')}'. Yeh regulation name ZAROOR mention karo.",
            "low_inventory": f"'{payload.get('item', '')}' sirf {payload.get('units_left', '')} units bachi hain. Item name aur count ZAROOR mention karo.",
        }
        specificity_instruction = kind_instructions.get(kind, f"Payload data: {json.dumps(payload)} — koi bhi specific number ya naam zaroor mention karo.")

        user_prompt = f"""Write a WhatsApp message from Vera to {merchant_name} for trigger kind '{kind}'.

CRITICAL RULE: {specificity_instruction}

Full trigger payload: {json.dumps(payload)}

Additional rules:
- Max 60 words, Hinglish (Hindi + English mix)
- End with a specific question or CTA
- Sound like a helpful business advisor, not a bot
- Max 1 emoji

Write ONLY the message text, nothing else."""

        message = await call_claude(system_prompt, user_prompt, max_tokens=150)

        # Fallback if API failed — always include payload-specific numbers
        if message.startswith("[API_ERROR"):
            kind_msgs = {
                "perf_dip": f"{merchant_name}, aapke {payload.get('metric','views')} {payload.get('drop_pct','')}% gire hain {payload.get('period','recently')}. Ek naya offer try karein? 📊",
                "new_competitor": f"{merchant_name}, '{payload.get('competitor_name','ek naya clinic')}' sirf {payload.get('distance_km','')} km door khula hai. Profile update karein aaj! 💡",
                "festival": f"{merchant_name}, {payload.get('festival','festival')} mein sirf {payload.get('days_until','')} din bache hain! Special deal launch karein? 🎉",
                "research_digest": f"{merchant_name}, '{payload.get('top_query','aapki service')}' {payload.get('search_volume','')} baar search hua this week. Offer add karein?",
                "regulation_change": f"{merchant_name}, '{payload.get('regulation','naya regulation')}' implement karna hoga. Compliance mein help chahiye?",
                "low_inventory": f"{merchant_name}, '{payload.get('item','aapka item')}' sirf {payload.get('units_left','')} units bacha hai. Restock kab hoga?",
            }
            message = kind_msgs.get(kind, f"{merchant_name}, important update: {json.dumps(payload)}. Baat karein?")

        suppress(sup_key, hours=23)
        actions.append({
            "action": "send",
            "trigger_id": trigger_id,
            "merchant_id": merchant_id,
            "body": message,
        })

    return {"actions": actions}


@app.post("/v1/reply")
async def reply(request: Request):
    body = await request.json()
    session_id = body.get("session_id", "default")
    from_role = body.get("from_role", "merchant")   # "merchant" or "customer"
    message_text = body.get("body", "")
    merchant_id = body.get("merchant_id", "")
    customer_id = body.get("customer_id", "")
    category_slug = body.get("category_slug", "")
    conversation_history = body.get("conversation_history", [])

    # Init session state
    if session_id not in reply_state:
        reply_state[session_id] = {"turns": 0, "auto_reply_count": 0, "intent": None}
    state = reply_state[session_id]
    state["turns"] += 1

    # ── STOP handling ─────────────────────────────────────────────────────────
    stop_words = {"stop", "unsubscribe", "opt out", "opt-out", "band karo", "mat bhejo", "nahi chahiye"}
    if any(w in message_text.lower() for w in stop_words):
        del reply_state[session_id]
        return {
            "action": "end",
            "body": "Samajh gaye! Aapko aage koi message nahi aayega. Agar kabhi zaroorat ho toh hum yahan hain. 🙏",
        }

    # ── Auto-reply detection ───────────────────────────────────────────────────
    auto_reply_signals = [
        "i am out of office", "out of office", "auto", "automatic reply",
        "on leave", "unavailable", "will get back", "vacation",
        "abhi available nahi", "bahar hoon",
    ]
    is_auto = any(sig in message_text.lower() for sig in auto_reply_signals)
    if is_auto:
        state["auto_reply_count"] += 1
        if state["auto_reply_count"] >= 2:
            del reply_state[session_id]
            return {"action": "end", "body": None}
        return {
            "action": "send",
            "body": "Koi baat nahi! Jab free hon tab baat karte hain. 😊",
        }

    # ── Gather context ────────────────────────────────────────────────────────
    merchant_ctx = ctx("merchant", merchant_id)
    category_ctx = ctx("category", category_slug)
    customer_ctx = ctx("customer", customer_id) if customer_id else {}

    merchant_name = merchant_ctx.get("name") or merchant_ctx.get("business_name") or f"Merchant {merchant_id}"
    owner_name = merchant_ctx.get("owner_name") or merchant_ctx.get("contact_name") or "aap"
    merchant_type = merchant_ctx.get("type") or category_ctx.get("name") or category_slug

    customer_name = customer_ctx.get("name") or customer_ctx.get("customer_name") or "customer"
    customer_phone = customer_ctx.get("phone") or ""
    customer_history = customer_ctx.get("last_visit") or ""

    # Format conversation history for Claude
    history_text = ""
    if conversation_history:
        for turn in conversation_history[-6:]:  # last 6 turns
            role = turn.get("role", "unknown")
            text = turn.get("body", "")
            history_text += f"{role}: {text}\n"

    # ── CUSTOMER message handling ─────────────────────────────────────────────
    if from_role == "customer":
        system_prompt = f"""You are Vera, magicpin's AI assistant helping {merchant_name} respond to customer messages.
You write SHORT replies (1-3 sentences, max 50 words) from the MERCHANT'S perspective TO THE CUSTOMER.
Tone: warm, professional, helpful. Mix Hindi/English naturally.

Merchant: {merchant_name} ({merchant_type})
Customer name: {customer_name}
Customer history: {customer_history}

IMPORTANT: Address the customer by name ({customer_name}). Confirm their request specifically. Be friendly."""

        user_prompt = f"""Conversation so far:
{history_text}

Customer just said: "{message_text}"

Write the merchant's reply to this customer. Address them as {customer_name}.
If they're booking/scheduling: confirm the specific time/date they mentioned.
If they're asking about services: answer specifically based on {merchant_type} services.
Keep it under 50 words. Hinglish tone. Write ONLY the reply, nothing else."""

        reply_body = await call_claude(system_prompt, user_prompt, max_tokens=120)

        if reply_body.startswith("[API_ERROR"):
            # Smart fallback for customer
            low = message_text.lower()
            if any(w in low for w in ["book", "appointment", "slot", "schedule", "time", "date"]):
                reply_body = f"Bilkul {customer_name}! Aapki booking confirm ho gayi. Hum aapko reminder bhejenge. 😊"
            elif any(w in low for w in ["price", "cost", "kitna", "charge", "fees"]):
                reply_body = f"Hi {customer_name}! Pricing ke liye please humse directly contact karein — best deal milega!"
            else:
                reply_body = f"Hi {customer_name}! Message mila, jald hi response karenge. Thank you! 🙏"

        return {"action": "send", "body": reply_body}

    # ── MERCHANT message handling ─────────────────────────────────────────────
    system_prompt = f"""You are Vera, magicpin's AI assistant helping merchants grow their business.
You respond to merchant messages with helpful, specific, action-oriented replies (1-3 sentences, max 60 words).
Tone: friendly, knowledgeable, like a business advisor who speaks Hinglish.

Merchant: {merchant_name} ({merchant_type})
Owner: {owner_name}
Context: {json.dumps(merchant_ctx)}
Category: {json.dumps(category_ctx)}

RULES:
- Be specific — reference what they said
- Offer concrete next steps
- Mix Hindi and English naturally
- Do NOT use filler like "Got it! Let me take care of that."
- If they mention a specific problem, address it directly"""

    # Detect intent
    low = message_text.lower()
    intent = None
    if any(w in low for w in ["audit", "compliance", "regulation", "x-ray", "equipment", "license"]):
        intent = "compliance"
    elif any(w in low for w in ["offer", "discount", "deal", "cashback", "promo"]):
        intent = "offers"
    elif any(w in low for w in ["review", "rating", "feedback", "complaint"]):
        intent = "reviews"
    elif any(w in low for w in ["photo", "image", "picture", "gallery"]):
        intent = "photos"
    elif any(w in low for w in ["slot", "appointment", "booking", "timing", "available"]):
        intent = "booking"
    elif any(w in low for w in ["competitor", "competition", "others", "nearby"]):
        intent = "competition"

    state["intent"] = intent

    user_prompt = f"""Conversation so far:
{history_text}

Merchant just said: "{message_text}"
Detected intent: {intent or "general"}

Write a helpful reply from Vera to {owner_name} at {merchant_name}.
- Address the specific thing they mentioned
- Give ONE concrete actionable suggestion
- Keep it under 60 words, Hinglish
- Write ONLY the reply, nothing else."""

    reply_body = await call_claude(system_prompt, user_prompt, max_tokens=150)

    if reply_body.startswith("[API_ERROR"):
        intent_fallbacks = {
            "compliance": f"Zaroor {owner_name}! Compliance checklist taiyaar karte hain — aapka equipment model share karein toh specific guidance de sakta hoon.",
            "offers": f"Great idea {owner_name}! Magicpin pe ek limited-time offer add karein — 15-20% discount wale deals mein 3x zyada clicks aate hain.",
            "reviews": f"Samjha {owner_name}! Recent negative reviews pe personally respond karein — yeh rating improve karne ka sabse fast tarika hai.",
            "photos": f"Photo update karna excellent step hai {owner_name}! Fresh high-quality photos se profile visits 40% tak badh sakti hain.",
            "booking": f"Booking slots set up karte hain {owner_name}! Magicpin pe calendar integration se customers directly book kar sakte hain.",
        }
        reply_body = intent_fallbacks.get(intent, f"Shukriya {owner_name}! Yeh important hai — chalte hain step by step. Pehle mujhe batao aapka main concern kya hai?")

    # Decide action
    action = "send"
    # If merchant has disengaged (very short message or signing off)
    if len(message_text.strip()) < 5 or any(w in low for w in ["bye", "ok thanks", "theek hai", "chal"]):
        if state["turns"] > 3:
            action = "end"
            reply_body = f"Bilkul {owner_name}! Koi bhi help chahiye toh ping karein. All the best! 🙌"
            del reply_state[session_id]

    return {"action": action, "body": reply_body}
