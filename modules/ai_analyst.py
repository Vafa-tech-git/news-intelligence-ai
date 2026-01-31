import json
import os
import sys
from ollama import Client

# Truc pentru a importa config-ul din folderul părinte
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import config

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
    """Funcția principală apelată de aplicație."""
    
    # 1. Validare simplă: Nu trimitem texte goale sau prea scurte la AI
    if not text or len(text) < 80:
        print("   [AI] Textul e prea scurt pentru analiză.")
        return None

    # 2. PROMPT ENGINEERING
    # Aici îi spunem exact ce vrem. Cu cât ești mai clar, cu atât 120b răspunde mai bine.
    # Limităm textul la primele 6000 caractere ca să nu depășim limitele (și costurile/timpul).
    prompt = f"""
    Ești un analist financiar expert. Analizează următorul articol de știri financiare.
    
    ARTICOL:
    {text[:6000]}
    
    SARCINĂ:
    Returnează UN SINGUR obiect JSON valid cu următoarele chei:
    1. "summary": Un rezumat concis în limba ROMÂNĂ (maxim 2 fraze).
    2. "impact_score": Un număr întreg de la 1 la 10 (10 = impact critic asupra pieței/bursei).
    3. "is_important": true dacă scorul este >= 7, altfel false.
    4. "sentiment": "pozitiv", "negativ" sau "neutru".

    IMPORTANT: Nu scrie nimic altceva în afară de JSON. Fără introduceri.
    """

    try:
        print(f"   [AI] Trimit cererea către {config.OLLAMA_MODEL}...")
        client = get_ollama_client()
        
        # Trimitem comanda
        response = client.chat(model=config.OLLAMA_MODEL, messages=[
            {'role': 'user', 'content': prompt},
        ])
        
        # Extragem răspunsul brut
        raw_content = response['message']['content']
        
        # Îl curățăm și îl transformăm în dicționar Python
        data = clean_json_response(raw_content)
        
        if data:
            print(f"   ✅ Analiză completă! Scor: {data.get('impact_score')}")
        else:
            print("   ⚠️ AI-ul a răspuns, dar nu a dat un JSON valid.")
            
        return data

    except Exception as e:
        print(f"❌ Eroare conexiune AI: {e}")
        return None