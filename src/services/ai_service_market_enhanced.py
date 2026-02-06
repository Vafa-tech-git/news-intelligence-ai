"""
Market-Enhanced AI Analysis Service with yfinance and Finnhub Integration
Combines AI analysis with real-time market sentiment for superior recommendations
"""

import json
import os
import sys
import logging
import hashlib
import re
from ollama import Client
from typing import Dict, List, Optional

# Configure logging for AI analyst module
logger = logging.getLogger(__name__)

# Import configuration and services
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.config import OLLAMA_MODEL, OLLAMA_HOST, OLLAMA_KEY, OLLAMA_LOCAL_HOST, LOCAL_OLLAMA_PREFERRED
from src.services.news_service import detect_financial_instruments
from src.services.financial_analysis_service import get_enhanced_recommendation

# Import cache manager for AI analysis caching
try:
    from src.utils.cache import cache_ai_analysis, get_cached_ai_analysis
    cache_enabled = True
except ImportError:
    cache_enabled = False
    logger.warning("Cache manager not available for AI analyst")

def detect_financial_instruments_enhanced(text):
    """Enhanced financial instrument detection"""
    if not text:
        return []
    
    instruments = []
    
    # Romanian stock symbols
    romanian_symbols = re.findall(r'\b[A-Z]{3,4}\b', text)
    
    # Extended known symbols mapping
    known_symbols = {
        'BVB': 'Bursa de Valori Bucuresti',
        'SNG': 'SN Petrom',
        'TLV': 'Banca Transilvania',
        'BRD': 'BRD Groupe Societe Generale',
        'FP': 'Fondul Proprietatea',
        'EL': 'Electrica',
        'SNP': 'OMV Petrom',
        'TGN': 'Transgaz',
        'OTE': 'Orange Romania',
        'CVE': 'Romgaz',
        'SNN': 'Nuclearelectrica',
        'BCR': 'Banca Comerciala Romana',
        'BNR': 'Banca Nationala a Romaniei',
    }
    
    # Known symbols set
    known_symbol_set = {'SNG', 'SNP', 'TLV', 'BRD', 'BCR', 'BNR', 'BVB', 'BET', 'FP', 'EL', 'TGN', 'OTE', 'CVE', 'SNN', 'CMP', 'M', 'ARO', 'PTR', 'CC', 'VNC', 'MED'}
    
    # Filter for known symbols
    for symbol in romanian_symbols:
        if symbol in known_symbol_set:
            instruments.append({
                'symbol': symbol,
                'name': known_symbols.get(symbol, symbol),
                'type': 'stock'
            })
    
    return instruments

def get_ollama_client():
    """Configurează conexiunea către serverul Ollama cu fallback automat."""
    try:
        # Import OllamaManager for fallback client
        try:
            from app import ollama_manager
            return ollama_manager.get_client()
        except ImportError:
            # Fallback to direct client configuration
            headers = {}  
            if OLLAMA_KEY:
                headers["Authorization"] = f"Bearer {OLLAMA_KEY}"
            
            # Try local first if preferred, then fallback to cloud
            if LOCAL_OLLAMA_PREFERRED:
                try:
                    logger.info(f"Trying local Ollama at {OLLAMA_LOCAL_HOST}")
                    # Test local connection
                    local_client = Client(host=OLLAMA_LOCAL_HOST, headers=headers)
                    local_client.list()  # Test connection
                    logger.info("✅ Connected to local Ollama server")
                    return local_client
                except Exception as e:
                    logger.warning(f"Local Ollama failed: {e}, falling back to cloud")
                    # Fallback to cloud
                    return Client(host=OLLAMA_HOST, headers=headers)
            else:
                # Use cloud directly if not preferring local
                logger.info("Using cloud Ollama (local not preferred)")
                return Client(host=OLLAMA_HOST, headers=headers)
                
    except Exception as e:
        logger.error(f"Failed to get Ollama client: {e}")
        # Final fallback
        headers = {}  
        if OLLAMA_KEY:
            headers["Authorization"] = f"Bearer {OLLAMA_KEY}"
        return Client(host=OLLAMA_HOST, headers=headers)

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
        logger.error(f"JSON cleaning error: {type(e).__name__}")
        return None

def analyze_article_with_market_data(text):
    """
    Enhanced analysis combining AI insights with real-time market data
    """
    
    # 1. Validare simplă: Nu trimitem texte goale sau prea scurte la AI
    if not text or len(text) < 80:
        logger.debug("Text too short for AI analysis")
        return None

    # 2. Check cache first for AI analysis
    text_hash = hashlib.md5(text.encode()).hexdigest()
    if cache_enabled:
        cached_result = get_cached_ai_analysis(text_hash)
        if cached_result:
            logger.debug(f"AI analysis cache hit for text hash: {text_hash[:8]}...")
            return cached_result
        logger.debug(f"AI analysis cache miss for text hash: {text_hash[:8]}...")

    # 3. Detect financial instruments first
    instruments = detect_financial_instruments_enhanced(text)
    symbol_list = [inst['symbol'] for inst in instruments]

    # 4. ENHANCED PROMPT ENGINEERING
    prompt = f"""
    Ești un analist financiar expert specializat pe piața românească. Analizează următorul articol de știri financiare.
    
    ARTICOL:
    {text[:6000]}
    
    INSTRUMENTE FINANCIARE IDENTIFICATE:
    {', '.join([inst['symbol'] + ' (' + inst.get('name', inst['symbol']) + ')' for inst in instruments]) if instruments else 'Niciun instrument identificat'}
    
    SARCINĂ:
    Returnează UN SINGUR obiect JSON valid cu următoarele chei:
    1. "summary": Un rezumat concis în limba ROMÂNĂ (maxim 2 fraze).
    2. "impact_score": Un număr întreg de la 1 la 10 (10 = impact critic asupra pieței/bursei).
    3. "is_important": true dacă scorul este >= 7, altfel false.
    4. "sentiment": "pozitiv", "negativ" sau "neutru".
    5. "instruments": Lista de instrumente financiare identificate (ex: ["SNG", "BRD"]).
    6. "recommendation": Una dintre "buy", "sell", "hold", "strong_buy", "strong_sell".
    7. "confidence_score": Scor încredere pentru recomandare (0.0 - 1.0).
    8. "reasoning": Scurtă justificare a recomandării (max 50 caractere).

    GHID RECOMANDĂRI:
    - strong_buy: Știri foarte pozitive, oportunități clare de creștere
    - buy: Știri pozitive, perspective bune de creștere
    - hold: Știri neutre sau mixte, așteptare
    - sell: Știri negative, riscuri de scădere
    - strong_sell: Știri foarte negative, riscuri majore

    IMPORTANT: Nu scrie nimic altceva în afară de JSON. Fără introduceri.
    """

    try:
        logger.info(f"Sending request to {OLLAMA_MODEL}...")
        client = get_ollama_client()
        
        # Trimitem comanda
        response = client.chat(model=OLLAMA_MODEL, messages=[
            {'role': 'user', 'content': prompt},
        ])
        
        # Extragem răspunsul brut
        raw_content = response['message']['content']
        
        # Îl curățăm și îl transformăm în dicționar Python
        data = clean_json_response(raw_content)
        
        if data:
            ai_recommendation = data.get('recommendation', 'hold')
            
            # 5. ENHANCE WITH MARKET DATA
            if symbol_list:
                try:
                    enhanced_rec, confidence, reasoning = get_enhanced_recommendation(ai_recommendation, symbol_list)
                    
                    # Update the AI result with market-enhanced data
                    data['recommendation'] = enhanced_rec
                    data['confidence_score'] = confidence
                    data['reasoning'] = reasoning
                    data['market_analysis_applied'] = True
                    data['analyzed_symbols'] = symbol_list
                    
                    logger.info(f"Enhanced analysis! AI: {ai_recommendation} → Market-Enhanced: {enhanced_rec}")
                    
                except Exception as e:
                    logger.warning(f"Market enhancement failed, using AI recommendation: {e}")
                    data['market_analysis_applied'] = False
                    data['analyzed_symbols'] = []
            else:
                data['market_analysis_applied'] = False
                data['analyzed_symbols'] = []
            
            # Ensure we have the instruments field
            if 'instruments' not in data:
                data['instruments'] = [inst['symbol'] for inst in instruments]
            
            logger.info(f"Final analysis! Score: {data.get('impact_score')}, Rec: {data.get('recommendation')}")
            
            # Cache the successful result
            if cache_enabled:
                cache_ai_analysis(text_hash, data)
                logger.debug(f"Cached AI analysis for text hash: {text_hash[:8]}...")
                
        else:
            logger.warning("AI responded but with invalid JSON")
            
        return data

    except Exception as e:
        logger.error(f"AI connection error: {type(e).__name__}: {e}")
        return None

# Backward compatibility
def analyze_article(text):
    """Backward compatibility wrapper"""
    return analyze_article_with_market_data(text)
