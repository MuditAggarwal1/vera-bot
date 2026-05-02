"""
Vera Bot Server — magicpin AI Challenge submission
Full implementation with Claude-powered message composition
"""

from __future__ import annotations
import os
import time
import json
import uuid
import re
from datetime import datetime, timezone
from typing import Any, Optional, Literal

from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
import anthropic

# ─────────────────────────────────────────────
# App setup
# ─────────────────────────────────────────────
app = FastAPI(title="Vera Bot", version="1.0.0")
START = time.time()
client = anthropic.Anthropic()  # uses ANTHROPIC_API_KEY from env

# In-memory stores
contexts: dict[tuple[str, str], dict] = {}   # (scope, context_id) -> {version, payload}
conversations: dict[str, list] = {}           # conversation_id -> [turns]
fired_triggers: set[str] = set()              # suppression keys already fired

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
# Helpers
# ─────────────────────────────────────────────
def get_ctx(scope: str, cid: str) -> Optional[dict]:
    entry = contexts.get((scope, cid))
    return entry["payload"] if entry else None

def get_language_hint(merchant: dict) -> str:
    langs = merchant.get("identity", {}).get("languages", ["en"])
    if "hi" in langs:
        return "Use a natural Hindi-English code-mix (Hinglish). Blend both languages naturally as WhatsApp messages to Indian merchants."
    return "Use English."

def is_auto_reply(message: str) -> bool:
    """Detect likely WhatsApp Business auto-replies."""
    auto_signals = [
        "aapki jaankari ke liye", "thank you for contacting",
        "i am currently unavailable", "main ek automated",
        "automated assistant", "automated response",
        "for contacting us", "we will get back",
        "bahut-bahut shukriya", "aapki madad ke liye shukriya"
    ]
    msg_lower = message.lower()
    return any(sig in msg_lower for sig in auto_signals)

def conversation_has_auto_reply_exit(turns: list) -> bool:
    """Check if we already tried once after auto-reply."""
    auto_count = sum(1 for t in turns if t.get("is_auto_reply"))
    return auto_count >= 2

def merchant_signaled_not_interested(message: str) -> bool:
    """Check if merchant wants to stop."""
    stop_signals = [
        "not interested", "nahi chahiye", "band karo", "stop",
        "don't contact", "remove me", "unsubscribe", "leave me alone",
        "nahin chahiye", "mat karo", "no thanks", "no thank you"
    ]
    msg_lower = message.lower()
    return any(sig in msg_lower for sig in stop_signals)

def merchant_expressed_intent(message: str) -> bool:
    """Detect clear action intent — should route to action immediately."""
    intent_signals = [
        "judrna hai", "join karna hai", "i want to join", "let's do it",
        "go ahead", "yes let's", "kar do", "shuru karo", "haan karo",
        "sign me up", "register me", "yes please", "ok do it"
    ]
    msg_lower = message.lower()
    return any(sig in msg_lower for sig in intent_signals)

# ─────────────────────────────────────────────
# Core Claude composer
# ─────────────────────────────────────────────
SYSTEM_PROMPT = """You are Vera — magicpin's AI assistant that helps local Indian merchants (dentists, salons, restaurants, gyms, pharmacies) grow their Google Business Profile and engage customers over WhatsApp.

Your job: Compose the PERFECT WhatsApp message for a merchant, given their context. The message must be concise, specific, and compelling.

CORE RULES:
1. SPECIFICITY WINS — anchor on a verifiable number, date, stat, or headline from the context. Generic ("10% off") loses; specific ("Haircut @ ₹99", "your 2,410 views", "JIDA Oct trial: 38% better") wins.
2. PEER/COLLEAGUE TONE — you are a knowledgeable assistant, not a salesperson. No "AMAZING DEAL!" No hype.
3. ONE CTA MAX — either a binary YES/NO at the end, or a single open question. Never multiple choices unless it's a booking flow.
4. NO FABRICATION — never invent stats, citations, competitor names, or offers not in the context.
5. LANGUAGE — match the merchant's language pref. Hindi-English code-mix (Hinglish) for merchants with "hi" in languages. Natural blend, not forced.
6. NO LONG PREAMBLES — skip "I hope you're doing well." Jump straight to the hook.
7. NO RE-INTRODUCTION — after the first message, never say "Hi, I'm Vera" again.
8. ANTI-REPETITION — never send the same body you sent before in this conversation.
9. COMPULSION LEVERS (use 1-2 per message):
   - Specificity/verifiability: concrete numbers from their data
   - Loss aversion: "you're missing X searches"
   - Social proof: "3 dentists in your area did Y"
   - Effort externalization: "I've drafted X — just say go"
   - Curiosity: "want to see who?"
   - Single binary commitment: Reply YES / STOP
10. CTA PLACEMENT — always last sentence.
11. For CATEGORY VOICE:
    - dentists: clinical-peer tone, technical vocab OK ("fluoride varnish", "caries"), NO "cure" or "guaranteed"
    - salons: warm, aspirational, price-specific ("Haircut @ ₹149")
    - restaurants: food-first, local pride, deal-specific
    - gyms: energetic but not bro-culture, outcome-focused
    - pharmacies: helpful, trust-building, health-specific

OUTPUT FORMAT — Return ONLY valid JSON, no markdown, no preamble:
{
  "body": "the WhatsApp message text",
  "cta": "open_ended" | "binary_yes_stop" | "none",
  "send_as": "vera" | "merchant_on_behalf",
  "suppression_key": "unique key for dedup e.g. research:dentists:2026-W17",
  "rationale": "1-2 sentences: why this message, what lever it uses"
}"""

def compose_message(
    category: dict,
    merchant: dict,
    trigger: dict,
    customer: Optional[dict] = None,
    conversation_history: Optional[list] = None
) -> dict:
    """Call Claude to compose a Vera message."""
    
    # Build context summary (trim to avoid token bloat)
    ctx_parts = []
    
    ctx_parts.append(f"CATEGORY: {category.get('slug', 'unknown')}")
    ctx_parts.append(f"Voice: {json.dumps(category.get('voice', {}))}")
    ctx_parts.append(f"Peer stats: {json.dumps(category.get('peer_stats', {}))}")
    
    # Top 2 digest items
    digest = category.get("digest", [])[:2]
    if digest:
        ctx_parts.append(f"Recent research/news: {json.dumps(digest)}")
    
    # Offer catalog
    offers = category.get("offer_catalog", [])[:4]
    if offers:
        ctx_parts.append(f"Category offer catalog: {json.dumps(offers)}")
    
    # Seasonal / trend
    seasonal = category.get("seasonal_beats", [])[:2]
    if seasonal:
        ctx_parts.append(f"Seasonal beats: {json.dumps(seasonal)}")
    trends = category.get("trend_signals", [])[:2]
    if trends:
        ctx_parts.append(f"Trend signals: {json.dumps(trends)}")
    
    ctx_parts.append(f"\nMERCHANT: {json.dumps(merchant.get('identity', {}))}")
    ctx_parts.append(f"Subscription: {json.dumps(merchant.get('subscription', {}))}")
    ctx_parts.append(f"Performance (30d): {json.dumps(merchant.get('performance', {}))}")
    ctx_parts.append(f"Active offers: {json.dumps([o for o in merchant.get('offers', []) if o.get('status') == 'active'])}")
    ctx_parts.append(f"Signals: {json.dumps(merchant.get('signals', []))}")
    ctx_parts.append(f"Customer aggregate: {json.dumps(merchant.get('customer_aggregate', {}))}")
    
    # Last 3 conversation turns
    conv_hist = merchant.get("conversation_history", [])[-3:]
    if conv_hist:
        ctx_parts.append(f"Recent conversation history (last 3 turns): {json.dumps(conv_hist)}")
    
    ctx_parts.append(f"\nTRIGGER: {json.dumps(trigger)}")
    
    if customer:
        ctx_parts.append(f"\nCUSTOMER (this message is sent BY the merchant TO their customer): {json.dumps(customer)}")
        ctx_parts.append("send_as must be 'merchant_on_behalf'")
    
    if conversation_history:
        ctx_parts.append(f"\nCONVERSATION SO FAR (in this session): {json.dumps(conversation_history[-4:])}")
    
    lang_hint = get_language_hint(merchant)
    ctx_parts.append(f"\nLANGUAGE INSTRUCTION: {lang_hint}")
    
    user_prompt = "\n".join(ctx_parts) + "\n\nCompose the ideal Vera WhatsApp message now."
    
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        )
        text = resp.content[0].text.strip()
        # Strip markdown if present
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        result = json.loads(text)
        return result
    except Exception as e:
        # Fallback safe message
        name = merchant.get("identity", {}).get("name", "there")
        return {
            "body": f"Hi {name}, checking in on your profile — want a quick update?",
            "cta": "open_ended",
            "send_as": "vera",
            "suppression_key": f"fallback:{merchant.get('merchant_id', 'unk')}:{int(time.time())}",
            "rationale": f"Fallback due to error: {str(e)}"
        }

def compose_reply(
    merchant_message: str,
    merchant: dict,
    category: dict,
    customer: Optional[dict],
    conversation_history: list,
    turn_number: int
) -> dict:
    """Compose a reply to a merchant/customer message."""
    
    # Detect auto-reply
    if is_auto_reply(merchant_message):
        if conversation_has_auto_reply_exit(conversation_history):
            return {
                "action": "end",
                "rationale": "Detected auto-reply twice — gracefully exiting to avoid burning turns."
            }
        name = merchant.get("identity", {}).get("name", "there")
        lang = get_language_hint(merchant)
        
        # One gentle prod after auto-reply
        REPLY_SYS = """You are Vera, magicpin's merchant AI assistant. You just detected a WhatsApp Business auto-reply. 
Compose ONE short gentle follow-up trying to reach the real owner, OR gracefully exit if appropriate.
Return JSON only: {"body": "...", "cta": "open_ended"|"binary_yes_stop"|"none", "rationale": "..."}"""
        
        try:
            resp = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=300,
                temperature=0,
                system=REPLY_SYS,
                messages=[{"role": "user", "content": f"Auto-reply detected from {name}. Language: {lang}. Try once more or exit gracefully."}]
            )
            text = resp.content[0].text.strip()
            text = re.sub(r'^```json\s*', '', text)
            text = re.sub(r'\s*```$', '', text)
            r = json.loads(text)
            return {"action": "send", "body": r["body"], "cta": r.get("cta", "open_ended"), "rationale": r["rationale"]}
        except:
            return {"action": "end", "rationale": "Auto-reply loop detected — exiting politely."}
    
    # Detect explicit stop
    if merchant_signaled_not_interested(merchant_message):
        return {
            "action": "end",
            "rationale": "Merchant signaled not interested — gracefully exiting without further messages."
        }
    
    # Detect intent transition (merchant says yes/go ahead)
    intent_transition = merchant_expressed_intent(merchant_message)
    
    # Build reply prompt
    REPLY_SYS = """You are Vera, magicpin's merchant AI assistant. You're mid-conversation with a merchant.
Compose the BEST next reply to their message. 

RULES:
- If merchant expressed CLEAR INTENT (join, yes, go ahead, do it) — switch to ACTION MODE immediately. Don't ask more qualifying questions. Start doing the thing.
- Match their language (Hinglish if they used Hindi).
- Keep it short and specific.
- One CTA max, at the end.
- If merchant asked a question, answer it directly first.
- No re-introductions.
- Return JSON only: {"body": "...", "cta": "open_ended"|"binary_yes_stop"|"none", "rationale": "..."}"""
    
    ctx = f"""Merchant: {json.dumps(merchant.get('identity', {}))}
Category: {category.get('slug', '')}
Merchant's message: "{merchant_message}"
Intent transition detected: {intent_transition}
Conversation history (last 4 turns): {json.dumps(conversation_history[-4:])}
Language: {get_language_hint(merchant)}"""
    
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            temperature=0,
            system=REPLY_SYS,
            messages=[{"role": "user", "content": ctx}]
        )
        text = resp.content[0].text.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        r = json.loads(text)
        return {"action": "send", "body": r["body"], "cta": r.get("cta", "open_ended"), "rationale": r["rationale"]}
    except Exception as e:
        return {"action": "send", "body": "Got it! Let me take care of that for you.", "cta": "none", "rationale": f"Fallback reply: {str(e)}"}

# ─────────────────────────────────────────────
# Endpoints
# ─────────────────────────────────────────────
@app.get("/v1/healthz")
async def healthz():
    counts = {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}
    for (scope, _) in contexts.keys():
        if scope in counts:
            counts[scope] += 1
    return {
        "status": "ok",
        "uptime_seconds": int(time.time() - START),
        "contexts_loaded": counts
    }

@app.get("/v1/metadata")
async def metadata():
    return {
        "team_name": "Vera Bot",
        "team_members": ["Submission"],
        "model": "claude-sonnet-4-20250514",
        "approach": "Claude-powered 4-context composer with auto-reply detection, intent routing, and Hinglish support",
        "contact_email": "team@example.com",
        "version": "1.0.0",
        "submitted_at": datetime.now(timezone.utc).isoformat()
    }

@app.post("/v1/context")
async def push_context(body: CtxBody):
    valid_scopes = {"category", "merchant", "customer", "trigger"}
    if body.scope not in valid_scopes:
        return JSONResponse(status_code=400, content={
            "accepted": False,
            "reason": "invalid_scope",
            "details": f"scope must be one of {valid_scopes}"
        })
    
    key = (body.scope, body.context_id)
    cur = contexts.get(key)
    if cur and cur["version"] >= body.version:
        return JSONResponse(status_code=409, content={
            "accepted": False,
            "reason": "stale_version",
            "current_version": cur["version"]
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
        trg = get_ctx("trigger", trg_id)
        if not trg:
            continue
        
        # Suppression check
        suppression_key = trg.get("suppression_key", trg_id)
        if suppression_key in fired_triggers:
            continue
        
        merchant_id = trg.get("merchant_id")
        if not merchant_id:
            continue
        
        merchant = get_ctx("merchant", merchant_id)
        if not merchant:
            continue
        
        category_slug = merchant.get("category_slug")
        category = get_ctx("category", category_slug)
        if not category:
            continue
        
        # Optional customer context
        customer_id = trg.get("customer_id")
        customer = get_ctx("customer", customer_id) if customer_id else None
        
        # Compose message
        composed = compose_message(category, merchant, trg, customer)
        
        # Mark as fired
        fired_triggers.add(suppression_key)
        
        conv_id = f"conv_{merchant_id}_{trg_id}_{uuid.uuid4().hex[:6]}"
        conversations[conv_id] = [{
            "from": "vera",
            "body": composed["body"],
            "ts": body.now
        }]
        
        # Build template params (first 3 words as placeholders)
        merchant_name = merchant.get("identity", {}).get("name", "Merchant")
        trigger_kind = trg.get("kind", "update")
        
        action = {
            "conversation_id": conv_id,
            "merchant_id": merchant_id,
            "customer_id": customer_id,
            "send_as": composed.get("send_as", "vera"),
            "trigger_id": trg_id,
            "template_name": f"vera_{trigger_kind}_v1",
            "template_params": [merchant_name, trigger_kind, "magicpin"],
            "body": composed["body"],
            "cta": composed.get("cta", "open_ended"),
            "suppression_key": suppression_key,
            "rationale": composed.get("rationale", "")
        }
        actions.append(action)
        
        # Cap at 20 per tick
        if len(actions) >= 20:
            break
    
    return {"actions": actions}

@app.post("/v1/reply")
async def reply(body: ReplyBody):
    conv_id = body.conversation_id
    
    # Get merchant context
    merchant_id = body.merchant_id
    merchant = get_ctx("merchant", merchant_id) if merchant_id else None
    
    if not merchant:
        # Try to infer from conversation
        return {"action": "end", "rationale": "Merchant context not found — ending conversation."}
    
    category_slug = merchant.get("category_slug", "")
    category = get_ctx("category", category_slug) or {}
    
    customer_id = body.customer_id
    customer = get_ctx("customer", customer_id) if customer_id else None
    
    # Get conversation history
    history = conversations.get(conv_id, [])
    
    # Track if this looks like auto-reply
    is_auto = is_auto_reply(body.message)
    history.append({
        "from": body.from_role,
        "body": body.message,
        "ts": body.received_at,
        "is_auto_reply": is_auto
    })
    conversations[conv_id] = history
    
    # Compose reply
    result = compose_reply(
        merchant_message=body.message,
        merchant=merchant,
        category=category,
        customer=customer,
        conversation_history=history,
        turn_number=body.turn_number
    )
    
    # Store our reply in history
    if result.get("action") == "send":
        history.append({
            "from": "vera",
            "body": result.get("body", ""),
            "ts": datetime.now(timezone.utc).isoformat()
        })
        conversations[conv_id] = history
    
    return result

@app.post("/v1/teardown")
async def teardown():
    contexts.clear()
    conversations.clear()
    fired_triggers.clear()
    return {"status": "cleared"}

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8080))
    uvicorn.run("bot_server:app", host="0.0.0.0", port=port, reload=False)
