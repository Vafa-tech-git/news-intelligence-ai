import json
import os
import sys
import logging
import hashlib
import time
from typing import Optional, Dict, List
from ollama import Client
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.config import OLLAMA_MODEL, OLLAMA_HOST, OLLAMA_KEY

try:
    from src.utils.cache import cache_ai_analysis, get_cached_ai_analysis
    cache_enabled = True
except ImportError:
    cache_enabled = False
    logger.warning("Cache manager not available for AI analyst")

class OptimizedAIAnalyzer:
    """Optimized AI analyzer with timeouts, retries, and batching"""
    
    def __init__(self):
        self.client = self._get_ollama_client()
        self.timeout = 60  # seconds
        self.max_retries = 3
        self.rate_limit_delay = 1  # seconds between calls
        
        # Model selection based on task complexity
        self.models = {
            'simple': 'gpt-oss:7b-chat',  # Faster for simple tasks
            'complex': OLLAMA_MODEL,       # Accurate for complex analysis
            'fallback': 'llama2:7b'       # Emergency fallback
        }
    
    def _get_ollama_client(self):
        """Get Ollama client with fallback"""
        try:
            from app import ollama_manager
            return ollama_manager.get_client()
        except ImportError:
            headers = {}  
            if OLLAMA_KEY:
                headers["Authorization"] = f"Bearer {OLLAMA_KEY}"
            return Client(host=OLLAMA_HOST, headers=headers)
    
    def _select_model(self, text_length: int) -> str:
        """Select appropriate model based on text length and complexity"""
        if text_length < 1000:
            return self.models['simple']
        elif text_length < 5000:
            return self.models['complex']
        else:
            # For very long texts, truncate and use complex model
            return self.models['complex']
    
    def _clean_json_response(self, response_text: str) -> Optional[Dict]:
        """Clean and parse JSON response"""
        try:
            start = response_text.find('{')
            end = response_text.rfind('}') + 1
            
            if start == -1 or end == 0:
                return None
                
            json_str = response_text[start:end]
            return json.loads(json_str)
        except Exception as e:
            logger.error(f"JSON cleaning error: {e}")
            return None
    
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=10),
        retry=retry_if_exception_type((TimeoutError, ConnectionError))
    )
    def _call_ai_with_retry(self, prompt: str, model: str) -> Optional[str]:
        """Call AI with retry logic and timeout"""
        try:
            response = self.client.chat(
                model=model, 
                messages=[{'role': 'user', 'content': prompt}],
                options={
                    'temperature': 0.1,  # More consistent responses
                    'top_p': 0.9,
                    'num_predict': 500   # Limit response length
                },
                timeout=self.timeout
            )
            
            return response['message']['content']
            
        except Exception as e:
            logger.error(f"AI call error with model {model}: {e}")
            raise
    
    def analyze_article_optimized(self, text: str) -> Optional[Dict]:
        """Analyze article with optimized model selection and caching"""
        # Input validation
        if not text or len(text) < 80:
            logger.debug("Text too short for AI analysis")
            return None
        
        # Check cache first
        text_hash = hashlib.md5(text.encode()).hexdigest()
        if cache_enabled:
            cached_result = get_cached_ai_analysis(text_hash)
            if cached_result:
                logger.debug(f"AI analysis cache hit for hash: {text_hash[:8]}...")
                return cached_result
        
        # Select appropriate model
        model = self._select_model(len(text))
        logger.debug(f"Using model {model} for text length {len(text)}")
        
        # Prepare optimized prompt
        prompt = self._prepare_optimized_prompt(text, model)
        
        try:
            # Rate limiting
            time.sleep(self.rate_limit_delay)
            
            # Call AI with retry
            raw_content = self._call_ai_with_retry(prompt, model)
            
            if not raw_content:
                logger.error("AI returned empty response")
                return None
            
            # Clean response
            data = self._clean_json_response(raw_content)
            
            if data and self._validate_response(data):
                logger.info(f"Analysis complete with model {model}! Score: {data.get('impact_score')}")
                
                # Cache successful result
                if cache_enabled:
                    cache_ai_analysis(text_hash, data)
                
                return data
            else:
                logger.warning("AI responded with invalid data")
                return None
                
        except Exception as e:
            logger.error(f"AI analysis failed: {e}")
            
            # Try fallback model if available
            if model != self.models['fallback']:
                logger.info(f"Trying fallback model: {self.models['fallback']}")
                return self._try_fallback_analysis(text)
            
            return None
    
    def _prepare_optimized_prompt(self, text: str, model: str) -> str:
        """Prepare optimized prompt based on model"""
        # Truncate text for performance
        max_length = 6000 if model == self.models['complex'] else 3000
        truncated_text = text[:max_length]
        
        if model == self.models['simple']:
            # Simpler prompt for smaller models
            return f"""
Analizează acest articol financiar în ROMÂNĂ:
{truncated_text}

Returnează JSON cu:
- "summary": rezumat în 1 frază
- "impact_score": număr 1-10
- "is_important": true/false
- "sentiment": "pozitiv"/"negativ"/"neutru"
Doar JSON, fără alt text.
"""
        else:
            # Detailed prompt for larger models
            return f"""
Ești un analist financiar expert. Analizează următorul articol:

ARTICOL:
{truncated_text}

SARCINĂ:
Returnează UN SINGUR obiect JSON valid cu:
1. "summary": Rezumat concis în limba ROMÂNĂ (maxim 2 fraze)
2. "impact_score": Număr întreg 1-10 (10 = impact critic)
3. "is_important": true dacă scorul >= 7, altfel false
4. "sentiment": "pozitiv", "negativ" sau "neutru"

IMPORTANT: Doar JSON valid, fără introduceri.
"""
    
    def _validate_response(self, data: Dict) -> bool:
        """Validate AI response structure"""
        required_fields = ['summary', 'impact_score', 'is_important', 'sentiment']
        
        if not all(field in data for field in required_fields):
            return False
        
        if not isinstance(data['impact_score'], int) or not (1 <= data['impact_score'] <= 10):
            return False
        
        if not isinstance(data['is_important'], bool):
            return False
        
        if data['sentiment'] not in ['pozitiv', 'negativ', 'neutru']:
            return False
        
        if not isinstance(data['summary'], str) or len(data['summary'].strip()) < 10:
            return False
        
        return True
    
    def _try_fallback_analysis(self, text: str) -> Optional[Dict]:
        """Try fallback analysis with simplified logic"""
        try:
            fallback_model = self.models['fallback']
            
            # Very simple prompt for fallback
            prompt = f"""
Analizează textul: {text[:1000]}
Returnează JSON: {{"summary": "scurt rezumat", "impact_score": 5, "is_important": false, "sentiment": "neutru"}}
"""
            
            raw_content = self._call_ai_with_retry(prompt, fallback_model)
            data = self._clean_json_response(raw_content)
            
            if data and self._validate_response(data):
                logger.info("Fallback analysis successful")
                return data
            
        except Exception as e:
            logger.error(f"Fallback analysis failed: {e}")
        
        return None

class BatchAIAnalyzer:
    """Batch AI analyzer for processing multiple articles efficiently"""
    
    def __init__(self, analyzer: OptimizedAIAnalyzer):
        self.analyzer = analyzer
        self.batch_size = 5  # Limit concurrent AI calls
        self.delay_between_batches = 2  # seconds
    
    def analyze_batch(self, articles: List[Dict]) -> List[Optional[Dict]]:
        """Analyze multiple articles with controlled batching"""
        results = []
        
        for i in range(0, len(articles), self.batch_size):
            batch = articles[i:i + self.batch_size]
            batch_results = []
            
            # Process batch
            for article in batch:
                content = article.get('content', '')
                result = self.analyzer.analyze_article_optimized(content)
                batch_results.append(result)
            
            results.extend(batch_results)
            
            # Delay between batches to avoid overwhelming the AI service
            if i + self.batch_size < len(articles):
                time.sleep(self.delay_between_batches)
            
            logger.info(f"Processed batch {i//self.batch_size + 1}: {sum(1 for r in batch_results if r)} successful")
        
        return results

# Global optimized analyzer instance
optimized_analyzer = OptimizedAIAnalyzer()
batch_analyzer = BatchAIAnalyzer(optimized_analyzer)

# Backwards compatibility function
def analyze_article(text: str) -> Optional[Dict]:
    """Backwards compatibility wrapper"""
    return optimized_analyzer.analyze_article_optimized(text)

if __name__ == "__main__":
    # Test optimized analyzer
    test_text = "Test article content for AI analysis. This is a financial news article about market trends."
    
    import logging
    logger = logging.getLogger(__name__)
    logger.info("🧪 Testing optimized AI analyzer...")
    result = analyze_article(test_text)
    logger.info(f"✅ Test result: {result}")
