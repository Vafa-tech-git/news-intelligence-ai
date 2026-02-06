import json
import os
import sys
import re
from ollama import Client

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

GICS_SECTORS = [
    "Technology", "Healthcare", "Financials", "Consumer Discretionary",
    "Consumer Staples", "Energy", "Materials", "Industrials",
    "Utilities", "Real Estate", "Communication Services"
]

COMMON_TICKERS = {
    "AAPL", "MSFT", "GOOGL", "GOOG", "AMZN", "META", "NVDA", "TSLA",
    "JPM", "V", "JNJ", "WMT", "PG", "MA", "UNH", "HD", "DIS", "BAC",
    "XOM", "CVX", "PFE", "KO", "PEP", "ABBV", "MRK", "TMO", "COST",
    "AVGO", "CSCO", "ACN", "ORCL", "CRM", "AMD", "INTC", "QCOM",
    "NFLX", "ADBE", "TXN", "IBM", "PYPL", "NOW", "UBER", "SQ", "SHOP"
}

def validate_tickers(tickers):
    """Filter tickers to known symbols or valid format (1-5 uppercase letters)."""
    if not tickers:
        return []
    validated = []
    for t in tickers:
        t = t.upper().strip()
        if t in COMMON_TICKERS:
            validated.append(t)
        elif re.match(r'^[A-Z]{1,5}$', t):
            validated.append(t)
    return validated

def validate_sector(sector):
    """Map sector to GICS standard."""
    if not sector:
        return None
    sector_lower = sector.lower()
    for gics in GICS_SECTORS:
        if gics.lower() in sector_lower or sector_lower in gics.lower():
            return gics
    if "tech" in sector_lower or "software" in sector_lower:
        return "Technology"
    if "bank" in sector_lower or "finance" in sector_lower:
        return "Financials"
    if "health" in sector_lower or "pharma" in sector_lower or "medical" in sector_lower:
        return "Healthcare"
    if "oil" in sector_lower or "gas" in sector_lower:
        return "Energy"
    if "retail" in sector_lower:
        return "Consumer Discretionary"
    return None

def get_ollama_client():
    """Configurează conexiunea către serverul Cloud."""
    # Dacă avem o cheie în .env, o punem în headers
    headers = {}  
    if config.OLLAMA_KEY:
        headers["Authorization"] = f"Bearer {config.OLLAMA_KEY}"
    
    # Inițializăm clientul cu Host-ul din config
    return Client(host=config.OLLAMA_HOST, headers=headers)

def clean_json_response(response_text):
    """
    AI-ul e vorbăreț. Uneori zice: 'Sigur, iată JSON-ul: { ... }'.
    Noi vrem doar partea dintre acolade { ... }.
    """
    try:
        # Căutăm prima acoladă deschisă și ultima închisă
        start = response_text.find('{')
        end = response_text.rfind('}') + 1
        
        if start == -1 or end == 0:
            return None
            
        json_str = response_text[start:end]
        return json.loads(json_str)
    except Exception as e:
        print(f"❌ Eroare la curățarea JSON: {e}")
        return None

def analyze_article(text):
    """Main analysis function with quant signal extraction."""

    if not text or len(text) < 80:
        print("   [AI] Text too short for analysis.")
        return None

    sectors_list = ", ".join(GICS_SECTORS)
    prompt = f"""You are an expert financial analyst. Analyze this financial news article.

ARTICLE:
{text[:6000]}

TASK:
Return a single valid JSON object with these keys:
1. "summary": A concise summary in ROMANIAN (max 2 sentences).
2. "impact_score": Integer 1-10 (10 = critical market impact).
3. "is_important": true if score >= 7, else false.
4. "sentiment": "positive", "negative", or "neutral".
5. "tickers": Array of stock ticker symbols mentioned (e.g., ["AAPL", "MSFT"]). Empty array if none.
6. "sector": Primary GICS sector from: {sectors_list}. Use null if unclear.
7. "direction": Trading signal - "bullish", "bearish", or "neutral".
8. "confidence": Float 0.0-1.0 indicating confidence in the direction signal.
9. "catalysts": Array of market catalysts (e.g., ["earnings", "acquisition", "guidance", "regulation", "layoffs"]). Empty array if none.

IMPORTANT: Output ONLY the JSON. No introduction or explanation.
"""

    try:
        print(f"   [AI] Sending request to {config.OLLAMA_MODEL}...")
        client = get_ollama_client()

        response = client.chat(model=config.OLLAMA_MODEL, messages=[
            {'role': 'user', 'content': prompt},
        ])

        raw_content = response['message']['content']
        data = clean_json_response(raw_content)

        if data:
            data['tickers'] = validate_tickers(data.get('tickers', []))
            data['sector'] = validate_sector(data.get('sector'))
            if data.get('direction') not in ('bullish', 'bearish', 'neutral'):
                data['direction'] = 'neutral'
            conf = data.get('confidence')
            if conf is None or not isinstance(conf, (int, float)):
                data['confidence'] = 0.5
            else:
                data['confidence'] = max(0.0, min(1.0, float(conf)))
            if not isinstance(data.get('catalysts'), list):
                data['catalysts'] = []

            print(f"   ✅ Analysis complete! Score: {data.get('impact_score')}, "
                  f"Direction: {data.get('direction')}, Tickers: {data.get('tickers')}")
        else:
            print("   ⚠️ AI responded but did not return valid JSON.")

        return data

    except Exception as e:
        print(f"❌ AI connection error: {e}")
        return None