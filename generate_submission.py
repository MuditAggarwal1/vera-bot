"""
Generate submission.jsonl — 30 test pairs, one per line.
Run: python generate_submission.py
"""

from __future__ import annotations
import json
import os
import re
import sys
from pathlib import Path
import anthropic

EXPANDED = Path("/home/claude/magicpin-challenge/expanded")
client = anthropic.Anthropic()

SYSTEM_PROMPT = """You are Vera — magicpin's AI assistant that helps local Indian merchants (dentists, salons, restaurants, gyms, pharmacies) grow via WhatsApp.

Compose the PERFECT WhatsApp message for a merchant, given their context.

CORE RULES:
1. SPECIFICITY WINS — anchor on a verifiable number, date, stat, or headline from the context.
2. PEER/COLLEAGUE TONE — knowledgeable assistant, not a salesperson.
3. ONE CTA MAX — binary YES/STOP at end, OR single open question.
4. NO FABRICATION — never invent stats, citations, competitor names, or offers not in the context.
5. LANGUAGE — match the merchant's language pref. Use Hinglish for "hi" language merchants.
6. NO LONG PREAMBLES — jump straight to the hook.
7. COMPULSION LEVERS (use 1-2): specificity, loss aversion, social proof, effort externalization, curiosity, single binary CTA.
8. CTA PLACEMENT — always last sentence.
9. CATEGORY VOICE:
   - dentists: clinical-peer, technical vocab OK, NO "cure"/"guaranteed"
   - salons: warm, aspirational, price-specific
   - restaurants: food-first, local, deal-specific
   - gyms: energetic, outcome-focused
   - pharmacies: helpful, trust-building

OUTPUT FORMAT — Return ONLY valid JSON, no markdown fences:
{
  "body": "the WhatsApp message text",
  "cta": "open_ended" | "binary_yes_stop" | "none",
  "send_as": "vera" | "merchant_on_behalf",
  "suppression_key": "unique key for dedup",
  "rationale": "1-2 sentences: why this message, what lever it uses"
}"""

def load_json(path: Path) -> dict:
    with open(path) as f:
        return json.load(f)

def get_language_hint(merchant: dict) -> str:
    langs = merchant.get("identity", {}).get("languages", ["en"])
    if "hi" in langs:
        return "Use natural Hindi-English code-mix (Hinglish)."
    return "Use English."

def compose(test_id: str, trigger: dict, merchant: dict, category: dict, customer: dict | None) -> dict:
    ctx_parts = []
    
    ctx_parts.append(f"CATEGORY: {category.get('slug', '')}")
    ctx_parts.append(f"Voice: {json.dumps(category.get('voice', {}))}")
    ctx_parts.append(f"Peer stats: {json.dumps(category.get('peer_stats', {}))}")
    
    digest = category.get("digest", [])[:2]
    if digest:
        ctx_parts.append(f"Research/news digest: {json.dumps(digest)}")
    
    offers_cat = category.get("offer_catalog", [])[:4]
    if offers_cat:
        ctx_parts.append(f"Category offers: {json.dumps(offers_cat)}")
    
    seasonal = category.get("seasonal_beats", [])[:2]
    if seasonal:
        ctx_parts.append(f"Seasonal beats: {json.dumps(seasonal)}")
    
    trends = category.get("trend_signals", [])[:2]
    if trends:
        ctx_parts.append(f"Trend signals: {json.dumps(trends)}")
    
    ctx_parts.append(f"\nMERCHANT: {json.dumps(merchant.get('identity', {}))}")
    ctx_parts.append(f"Subscription: {json.dumps(merchant.get('subscription', {}))}")
    ctx_parts.append(f"Performance (30d): {json.dumps(merchant.get('performance', {}))}")
    active_offers = [o for o in merchant.get('offers', []) if o.get('status') == 'active']
    ctx_parts.append(f"Active offers: {json.dumps(active_offers)}")
    ctx_parts.append(f"Signals: {json.dumps(merchant.get('signals', []))}")
    ctx_parts.append(f"Customer aggregate: {json.dumps(merchant.get('customer_aggregate', {}))}")
    
    conv_hist = merchant.get("conversation_history", [])[-3:]
    if conv_hist:
        ctx_parts.append(f"Recent conversation history: {json.dumps(conv_hist)}")
    
    ctx_parts.append(f"\nTRIGGER: {json.dumps(trigger)}")
    
    if customer:
        ctx_parts.append(f"\nCUSTOMER (message is from merchant TO customer): {json.dumps(customer)}")
        ctx_parts.append("send_as must be 'merchant_on_behalf'")
    
    ctx_parts.append(f"\nLANGUAGE: {get_language_hint(merchant)}")
    ctx_parts.append("\nCompose the ideal Vera WhatsApp message now.")
    
    user_prompt = "\n".join(ctx_parts)
    
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=800,
            temperature=0,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_prompt}]
        )
        text = resp.content[0].text.strip()
        text = re.sub(r'^```json\s*', '', text)
        text = re.sub(r'\s*```$', '', text)
        return json.loads(text)
    except Exception as e:
        print(f"  ERROR on {test_id}: {e}")
        return {
            "body": f"Hi, checking in on your profile update — Reply YES to proceed.",
            "cta": "binary_yes_stop",
            "send_as": "vera",
            "suppression_key": f"fallback:{test_id}",
            "rationale": "Fallback due to error"
        }

def main():
    test_pairs_path = EXPANDED / "test_pairs.json"
    test_pairs = load_json(test_pairs_path)["pairs"]
    print(f"Generating {len(test_pairs)} test pairs...")
    
    results = []
    for pair in test_pairs:
        test_id = pair["test_id"]
        trigger_id = pair["trigger_id"]
        merchant_id = pair["merchant_id"]
        customer_id = pair.get("customer_id")
        
        print(f"  {test_id}: {merchant_id} + {trigger_id}")
        
        # Load trigger
        trg_path = EXPANDED / "triggers" / f"{trigger_id}.json"
        if not trg_path.exists():
            print(f"    WARNING: trigger file not found: {trg_path}")
            continue
        trigger = load_json(trg_path)
        
        # Load merchant
        merch_path = EXPANDED / "merchants" / f"{merchant_id}.json"
        if not merch_path.exists():
            print(f"    WARNING: merchant file not found: {merch_path}")
            continue
        merchant = load_json(merch_path)
        
        # Load category
        cat_slug = merchant.get("category_slug", "")
        cat_path = EXPANDED / "categories" / f"{cat_slug}.json"
        if not cat_path.exists():
            print(f"    WARNING: category file not found: {cat_path}")
            continue
        category = load_json(cat_path)
        
        # Load customer if needed
        customer = None
        if customer_id:
            cust_path = EXPANDED / "customers" / f"{customer_id}.json"
            if cust_path.exists():
                customer = load_json(cust_path)
        
        composed = compose(test_id, trigger, merchant, category, customer)
        
        row = {
            "test_id": test_id,
            "body": composed.get("body", ""),
            "cta": composed.get("cta", "open_ended"),
            "send_as": composed.get("send_as", "vera"),
            "suppression_key": composed.get("suppression_key", f"{test_id}:key"),
            "rationale": composed.get("rationale", "")
        }
        results.append(row)
        print(f"    OK: {row['body'][:80]}...")
    
    out_path = Path("/home/claude/magicpin-challenge/submission.jsonl")
    with open(out_path, "w") as f:
        for row in results:
            f.write(json.dumps(row, ensure_ascii=False) + "\n")
    
    print(f"\nDone. {len(results)} rows written to {out_path}")

if __name__ == "__main__":
    main()
