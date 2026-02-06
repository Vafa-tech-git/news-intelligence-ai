"""
Enhanced Financial Analysis Service with yfinance and Finnhub Integration
Provides market sentiment validation for buy/sell/hold recommendations
"""

import yfinance as yf
import requests
import logging
import time
from typing import Dict, List, Optional, Tuple
from datetime import datetime, timedelta
import sys
import os

# Add project root to path
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from src.core.config import FINNHUB_TOKEN

logger = logging.getLogger(__name__)

class FinancialAnalysisService:
    """Enhanced financial analysis with real-time market data"""
    
    def __init__(self):
        self.finnhub_token = FINNHUB_TOKEN
        self.cache = {}  # Simple cache for API responses
        self.cache_ttl = 300  # 5 minutes cache
        
    def get_market_sentiment(self, symbols: List[str]) -> Dict:
        """
        Get comprehensive market sentiment for multiple financial symbols
        
        Returns:
            Dict with sentiment analysis and recommendation validation
        """
        if not symbols:
            return self._get_neutral_sentiment()
            
        sentiments = []
        valid_symbols = []
        
        for symbol in symbols:
            try:
                # Get data from both sources
                yfinance_data = self._get_yfinance_sentiment(symbol)
                finnhub_data = self._get_finnhub_sentiment(symbol)
                
                if yfinance_data or finnhub_data:
                    combined_sentiment = self._combine_sentiments(yfinance_data, finnhub_data)
                    sentiments.append(combined_sentiment)
                    valid_symbols.append(symbol)
                    
            except Exception as e:
                logger.warning(f"Error getting sentiment for {symbol}: {e}")
                continue
        
        if not sentiments:
            return self._get_neutral_sentiment()
            
        # Aggregate all sentiments
        return self._aggregate_sentiments(sentiments, valid_symbols)
    
    def _get_yfinance_sentiment(self, symbol: str) -> Optional[Dict]:
        """Get market sentiment from yfinance data"""
        try:
            cache_key = f"yf_{symbol}_{int(time.time() // self.cache_ttl)}"
            if cache_key in self.cache:
                return self.cache[cache_key]
                
            # Get stock data
            ticker = yf.Ticker(symbol)
            
            # Try multiple market data points
            info = ticker.info
            hist = ticker.history(period="5d")
            
            if info is None or hist.empty:
                return None
                
            # Calculate sentiment indicators
            current_price = info.get('currentPrice') or info.get('regularMarketPrice')
            previous_close = info.get('previousClose')
            
            if not current_price or not previous_close:
                # Use last available price from history
                if len(hist) >= 2:
                    current_price = hist['Close'].iloc[-1]
                    previous_close = hist['Close'].iloc[-2]
                else:
                    return None
            
            price_change = ((current_price - previous_close) / previous_close) * 100
            
            # Volume analysis
            volume = info.get('volume') or 0
            avg_volume = info.get('averageVolume') or 1
            volume_ratio = volume / avg_volume if avg_volume > 0 else 1
            
            # RSI and other indicators (if available)
            rsi = info.get('rsi') or 50  # Default neutral
            
            # Determine sentiment
            sentiment_score = 0
            
            # Price change impact
            if price_change > 2:
                sentiment_score += 2
            elif price_change > 0.5:
                sentiment_score += 1
            elif price_change < -2:
                sentiment_score -= 2
            elif price_change < -0.5:
                sentiment_score -= 1
                
            # Volume impact (unusual volume indicates strong sentiment)
            if volume_ratio > 2:
                sentiment_score += 1 if price_change > 0 else -1
            elif volume_ratio < 0.5:
                sentiment_score += 0.5 if price_change > 0 else -0.5
                
            # RSI impact
            if rsi > 70:
                sentiment_score -= 0.5  # Overbought
            elif rsi < 30:
                sentiment_score += 0.5  # Oversold
                
            sentiment_data = {
                'source': 'yfinance',
                'symbol': symbol,
                'price_change': price_change,
                'volume_ratio': volume_ratio,
                'rsi': rsi,
                'current_price': current_price,
                'sentiment_score': sentiment_score,
                'recommendation': self._score_to_recommendation(sentiment_score)
            }
            
            # Cache the result
            self.cache[cache_key] = sentiment_data
            return sentiment_data
            
        except Exception as e:
            logger.warning(f"yfinance error for {symbol}: {e}")
            return None
    
    def _get_finnhub_sentiment(self, symbol: str) -> Optional[Dict]:
        """Get insider sentiment from Finnhub"""
        try:
            if not self.finnhub_token:
                return None
                
            cache_key = f"fh_{symbol}_{int(time.time() // self.cache_ttl)}"
            if cache_key in self.cache:
                return self.cache[cache_key]
            
            # Get company profile
            profile_url = f"https://finnhub.io/api/v1/stock/profile2?symbol={symbol}&token={self.finnhub_token}"
            profile_response = requests.get(profile_url, timeout=5)
            
            if profile_response.status_code != 200:
                return None
                
            profile = profile_response.json()
            
            # Get insider sentiment
            sentiment_url = f"https://finnhub.io/api/v1/stock/insider-sentiment?symbol={symbol}&token={self.finnhub_token}"
            sentiment_response = requests.get(sentiment_url, timeout=5)
            
            sentiment_data = {
                'source': 'finnhub',
                'symbol': symbol,
                'company_name': profile.get('name', ''),
                'sector': profile.get('sector', ''),
                'market_cap': profile.get('marketCapitalization', 0)
            }
            
            if sentiment_response.status_code == 200:
                insider_data = sentiment_response.json()
                if insider_data.get('data'):
                    latest = insider_data['data'][0]  # Most recent month
                    
                    sentiment_data.update({
                        'mspr': latest.get('mspr', 0),  # Monthly share purchase ratio
                        'change': latest.get('change', 0),
                        'sentiment_score': self._calculate_insider_score(latest),
                        'recommendation': self._insider_to_recommendation(latest)
                    })
            
            # Cache the result
            self.cache[cache_key] = sentiment_data
            return sentiment_data
            
        except Exception as e:
            logger.warning(f"Finnhub error for {symbol}: {e}")
            return None
    
    def _combine_sentiments(self, yfinance_data: Optional[Dict], finnhub_data: Optional[Dict]) -> Dict:
        """Combine data from both sources"""
        combined = {
            'symbol': yfinance_data.get('symbol') if yfinance_data else finnhub_data.get('symbol'),
            'yfinance_score': yfinance_data.get('sentiment_score', 0) if yfinance_data else 0,
            'finnhub_score': finnhub_data.get('sentiment_score', 0) if finnhub_data else 0,
            'has_price_data': bool(yfinance_data),
            'has_insider_data': bool(finnhub_data and finnhub_data.get('mspr') is not None)
        }
        
        # Weight the scores (yfinance 60%, finnhub 40% if both available)
        if combined['has_price_data'] and combined['has_insider_data']:
            combined['combined_score'] = (combined['yfinance_score'] * 0.6 + combined['finnhub_score'] * 0.4)
        elif combined['has_price_data']:
            combined['combined_score'] = combined['yfinance_score']
        elif combined['has_insider_data']:
            combined['combined_score'] = combined['finnhub_score']
        else:
            combined['combined_score'] = 0
            
        combined['recommendation'] = self._score_to_recommendation(combined['combined_score'])
        combined['confidence'] = self._calculate_confidence(combined)
        
        return combined
    
    def _aggregate_sentiments(self, sentiments: List[Dict], symbols: List[str]) -> Dict:
        """Aggregate multiple symbol sentiments into overall market sentiment"""
        if not sentiments:
            return self._get_neutral_sentiment()
        
        # Calculate weighted average
        total_score = sum(s['combined_score'] for s in sentiments)
        avg_score = total_score / len(sentiments)
        
        # Count recommendations
        recommendations = [s['recommendation'] for s in sentiments]
        rec_counts = {
            'strong_buy': recommendations.count('strong_buy'),
            'buy': recommendations.count('buy'),
            'hold': recommendations.count('hold'),
            'sell': recommendations.count('sell'),
            'strong_sell': recommendations.count('strong_sell')
        }
        
        # Determine dominant recommendation
        if rec_counts['strong_buy'] + rec_counts['buy'] > rec_counts['sell'] + rec_counts['strong_sell']:
            if rec_counts['strong_buy'] > rec_counts['buy']:
                final_rec = 'strong_buy'
            else:
                final_rec = 'buy'
        elif rec_counts['strong_sell'] + rec_counts['sell'] > rec_counts['buy'] + rec_counts['strong_buy']:
            if rec_counts['strong_sell'] > rec_counts['sell']:
                final_rec = 'strong_sell'
            else:
                final_rec = 'sell'
        else:
            final_rec = 'hold'
        
        return {
            'overall_sentiment_score': avg_score,
            'final_recommendation': final_rec,
            'analyzed_symbols': symbols,
            'recommendation_counts': rec_counts,
            'confidence': self._calculate_overall_confidence(sentiments),
            'market_outlook': self._get_market_outlook(avg_score),
            'individual_sentiments': sentiments,
            'analysis_timestamp': datetime.now().isoformat()
        }
    
    def _score_to_recommendation(self, score: float) -> str:
        """Convert sentiment score to recommendation"""
        if score >= 2:
            return 'strong_buy'
        elif score >= 0.5:
            return 'buy'
        elif score > -0.5:
            return 'hold'
        elif score > -2:
            return 'sell'
        else:
            return 'strong_sell'
    
    def _calculate_insider_score(self, insider_data: Dict) -> float:
        """Calculate sentiment score from insider data"""
        mspr = insider_data.get('mspr', 0)  # Monthly share purchase ratio
        change = insider_data.get('change', 0)
        
        # MSPR > 1 indicates buying, < 1 indicates selling
        if mspr > 1.5:
            score = 2
        elif mspr > 1.1:
            score = 1
        elif mspr < 0.5:
            score = -2
        elif mspr < 0.9:
            score = -1
        else:
            score = 0
            
        # Adjust for change magnitude
        if abs(change) > 1000:  # Large insider activity
            score *= 1.5
            
        return score
    
    def _insider_to_recommendation(self, insider_data: Dict) -> str:
        """Convert insider data to recommendation"""
        score = self._calculate_insider_score(insider_data)
        return self._score_to_recommendation(score)
    
    def _calculate_confidence(self, sentiment_data: Dict) -> float:
        """Calculate confidence level for the sentiment"""
        confidence = 0.5  # Base confidence
        
        if sentiment_data.get('has_price_data'):
            confidence += 0.3
            
        if sentiment_data.get('has_insider_data'):
            confidence += 0.2
            
        # Additional confidence for strong signals
        score = sentiment_data.get('combined_score', 0)
        if abs(score) > 2:
            confidence += 0.1
            
        return min(confidence, 1.0)
    
    def _calculate_overall_confidence(self, sentiments: List[Dict]) -> float:
        """Calculate confidence for aggregated sentiment"""
        if not sentiments:
            return 0.0
            
        avg_confidence = sum(s.get('confidence', 0) for s in sentiments) / len(sentiments)
        
        # Boost confidence if multiple symbols agree
        recommendations = [s['recommendation'] for s in sentiments]
        if len(set(recommendations)) <= 2:  # Most symbols have similar recommendations
            avg_confidence += 0.1
            
        return min(avg_confidence, 1.0)
    
    def _get_market_outlook(self, score: float) -> str:
        """Get market outlook description"""
        if score >= 2:
            return "Bullish trend with strong positive momentum"
        elif score >= 0.5:
            return "Modestly positive outlook"
        elif score > -0.5:
            return "Neutral market conditions"
        elif score > -2:
            return "Modestly negative outlook"
        else:
            return "Bearish trend with significant downward pressure"
    
    def _get_neutral_sentiment(self) -> Dict:
        """Return neutral sentiment when no data is available"""
        return {
            'overall_sentiment_score': 0.0,
            'final_recommendation': 'hold',
            'analyzed_symbols': [],
            'recommendation_counts': {'strong_buy': 0, 'buy': 0, 'hold': 0, 'sell': 0, 'strong_sell': 0},
            'confidence': 0.0,
            'market_outlook': 'Insufficient data for market analysis',
            'individual_sentiments': [],
            'analysis_timestamp': datetime.now().isoformat()
        }

# Global instance
financial_analyzer = FinancialAnalysisService()

def get_enhanced_recommendation(ai_recommendation: str, symbols: List[str]) -> Tuple[str, float, str]:
    """
    Enhance AI recommendation with market data
    
    Returns:
        Tuple of (final_recommendation, confidence_score, reasoning)
    """
    try:
        market_sentiment = financial_analyzer.get_market_sentiment(symbols)
        market_rec = market_sentiment['final_recommendation']
        confidence = market_sentiment['confidence']
        
        # If no market data, return AI recommendation with low confidence
        if confidence == 0:
            return ai_recommendation, 0.3, "Based on article content only"
        
        # Combine AI and market recommendations
        rec_map = {'strong_buy': 2, 'buy': 1, 'hold': 0, 'sell': -1, 'strong_sell': -2}
        ai_score = rec_map.get(ai_recommendation, 0)
        market_score = rec_map.get(market_rec, 0)
        
        # Weight: 40% AI, 60% market data (market data is more objective)
        combined_score = (ai_score * 0.4 + market_score * 0.6)
        final_rec = financial_analyzer._score_to_recommendation(combined_score)
        
        reasoning = f"AI: {ai_recommendation}, Market: {market_rec}, Combined: {final_rec}"
        
        return final_rec, confidence, reasoning
        
    except Exception as e:
        logger.error(f"Error enhancing recommendation: {e}")
        return ai_recommendation, 0.2, "Error in market analysis, using AI recommendation only"
