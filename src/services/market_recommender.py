"""
Market Recommender Module
Statistical recommendation engine: "Is now a good time to buy?"

Weighted composite:
- 60% Price/Technical (MAs, RSI, MACD, 52-week range, volume)
- 20% News Sentiment (aggregated from all sources)
- 20% Macro/Economic (FRED indicators, economic health)
"""

import math
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple
from statistics import mean, stdev

import database
from modules.economic_health import get_economic_health


class MarketRecommender:
    """Statistical recommendation: Is now a good time to buy?"""

    WEIGHTS = {
        'price_technical': 0.60,
        'news_sentiment': 0.20,
        'macro_economic': 0.20
    }

    RECOMMENDATION_THRESHOLDS = {
        'strong_buy': 60,
        'buy': 30,
        'hold_upper': 30,
        'hold_lower': -30,
        'caution': -60,
        'avoid': -100
    }

    def __init__(self):
        self.indices = ['^GSPC', '^IXIC', '^DJI']

    def calculate_recommendation(self, ticker: str = None) -> Dict:
        """
        Calculate buy/sell recommendation with breakdown.

        Args:
            ticker: Optional specific stock ticker. If None, analyzes overall market.

        Returns:
            Dict with recommendation, composite_score, breakdown, confidence, reasons
        """
        # 1. PRICE/TECHNICAL SCORE (60%)
        technical_result = self._calculate_technical_score(ticker)
        technical_score = technical_result['score']
        technical_reasons = technical_result['reasons']

        # 2. NEWS SENTIMENT SCORE (20%)
        sentiment_result = self._calculate_sentiment_score(ticker)
        sentiment_score = sentiment_result['score']
        sentiment_reasons = sentiment_result['reasons']

        # 3. MACRO/ECONOMIC SCORE (20%)
        macro_result = self._calculate_macro_score()
        macro_score = macro_result['score']
        macro_reasons = macro_result['reasons']

        # Calculate weighted composite
        composite = (
            technical_score * self.WEIGHTS['price_technical'] +
            sentiment_score * self.WEIGHTS['news_sentiment'] +
            macro_score * self.WEIGHTS['macro_economic']
        )

        # Calculate confidence based on data availability and agreement
        confidence = self._calculate_confidence(
            technical_result, sentiment_result, macro_result
        )

        # Combine all reasons
        all_reasons = []
        if technical_reasons:
            all_reasons.extend([f"[Technical] {r}" for r in technical_reasons[:3]])
        if sentiment_reasons:
            all_reasons.extend([f"[Sentiment] {r}" for r in sentiment_reasons[:2]])
        if macro_reasons:
            all_reasons.extend([f"[Economic] {r}" for r in macro_reasons[:2]])

        return {
            'ticker': ticker or 'MARKET',
            'recommendation': self._score_to_recommendation(composite),
            'composite_score': round(composite, 1),
            'breakdown': {
                'technical': {
                    'score': round(technical_score, 1),
                    'weight': '60%',
                    'data_quality': technical_result.get('data_quality', 'unknown')
                },
                'sentiment': {
                    'score': round(sentiment_score, 1),
                    'weight': '20%',
                    'data_quality': sentiment_result.get('data_quality', 'unknown')
                },
                'macro': {
                    'score': round(macro_score, 1),
                    'weight': '20%',
                    'data_quality': macro_result.get('data_quality', 'unknown')
                }
            },
            'confidence': confidence,
            'reasons': all_reasons[:7],
            'timestamp': datetime.now().isoformat()
        }

    def _calculate_technical_score(self, ticker: str = None) -> Dict:
        """
        Score from -100 to +100 based on price action.

        Factors:
        - Price vs 20/50/200 day MAs (-30 to +30)
        - RSI overbought/oversold (-20 to +20)
        - MACD signal (-15 to +15)
        - Distance from 52-week high/low (-15 to +15)
        - Volume trend (-10 to +10)
        - Recent momentum (-10 to +10)
        """
        score = 0
        reasons = []
        data_quality = 'good'

        if ticker:
            data = self._get_ticker_technicals(ticker)
        else:
            data = self._get_market_technicals()

        if not data or not data.get('price'):
            return {'score': 0, 'reasons': ['Insufficient price data'], 'data_quality': 'poor'}

        # === MOVING AVERAGE ANALYSIS (30 points max) ===
        ma_score = 0
        if data.get('ma_200'):
            if data['price'] > data['ma_200']:
                ma_score += 15
                reasons.append(f"Price above 200-day MA (bullish trend)")
            else:
                ma_score -= 15
                reasons.append(f"Price below 200-day MA (bearish trend)")

        if data.get('ma_50'):
            if data['price'] > data['ma_50']:
                ma_score += 10
            else:
                ma_score -= 10

        if data.get('ma_20'):
            if data['price'] > data['ma_20']:
                ma_score += 5
            else:
                ma_score -= 5

        score += ma_score

        # === RSI ANALYSIS (20 points max) ===
        rsi = data.get('rsi')
        if rsi is not None:
            if rsi < 30:
                score += 20
                reasons.append(f"RSI oversold ({rsi:.0f}) - buying opportunity")
            elif rsi < 40:
                score += 10
                reasons.append(f"RSI approaching oversold ({rsi:.0f})")
            elif rsi > 70:
                score -= 20
                reasons.append(f"RSI overbought ({rsi:.0f}) - risky to buy")
            elif rsi > 60:
                score -= 10

        # === MACD ANALYSIS (15 points max) ===
        macd_hist = data.get('macd_histogram')
        macd_signal = data.get('macd_signal')
        if macd_hist is not None:
            if macd_hist > 0:
                if macd_signal == 'bullish_cross':
                    score += 15
                    reasons.append("MACD bullish crossover")
                else:
                    score += 8
            else:
                if macd_signal == 'bearish_cross':
                    score -= 15
                    reasons.append("MACD bearish crossover")
                else:
                    score -= 8

        # === 52-WEEK RANGE (15 points max) ===
        if data.get('high_52w') and data.get('low_52w'):
            range_size = data['high_52w'] - data['low_52w']
            if range_size > 0:
                range_position = (data['price'] - data['low_52w']) / range_size
                if range_position < 0.2:
                    score += 15
                    reasons.append(f"Near 52-week low ({range_position*100:.0f}% of range)")
                elif range_position < 0.35:
                    score += 10
                elif range_position > 0.9:
                    score -= 10
                    reasons.append(f"Near 52-week high ({range_position*100:.0f}% of range)")
                elif range_position > 0.8:
                    score -= 5

        # === VOLUME TREND (10 points max) ===
        vol_trend = data.get('volume_trend')
        price_trend = data.get('price_trend')
        if vol_trend and price_trend:
            if vol_trend == 'increasing' and price_trend == 'up':
                score += 10
                reasons.append("Strong volume on uptrend")
            elif vol_trend == 'increasing' and price_trend == 'down':
                score -= 10
                reasons.append("High volume selling pressure")
            elif vol_trend == 'decreasing' and price_trend == 'up':
                score += 3  # Weak uptrend
            elif vol_trend == 'decreasing' and price_trend == 'down':
                score -= 3

        # === RECENT MOMENTUM (10 points max) ===
        momentum_5d = data.get('momentum_5d', 0)
        momentum_20d = data.get('momentum_20d', 0)
        if momentum_5d > 3:
            score += 5
        elif momentum_5d < -3:
            score -= 5
        if momentum_20d > 5:
            score += 5
        elif momentum_20d < -5:
            score -= 5

        # Clamp score
        score = max(-100, min(100, score))

        return {
            'score': score,
            'reasons': reasons,
            'data_quality': data_quality,
            'raw_data': {
                'price': data.get('price'),
                'rsi': rsi,
                'ma_position': 'above' if ma_score > 0 else 'below' if ma_score < 0 else 'mixed'
            }
        }

    def _calculate_sentiment_score(self, ticker: str = None) -> Dict:
        """
        Score from -100 to +100 based on news sentiment.
        Uses existing sentiment aggregation normalized to -100 to +100.
        """
        score = 0
        reasons = []
        data_quality = 'good'

        if ticker:
            sentiment = database.get_ticker_sentiment(ticker)
        else:
            sentiment = self._get_market_sentiment()

        if not sentiment:
            return {'score': 0, 'reasons': ['No sentiment data available'], 'data_quality': 'poor'}

        # Convert -1.0 to 1.0 scale to -100 to +100
        composite = sentiment.get('composite_score', 0)
        base_score = composite * 100

        # Consensus strength adjustment
        consensus = sentiment.get('consensus_strength', 0.5)
        if consensus > 0.7:
            base_score *= 1.2
            reasons.append(f"High sentiment consensus ({consensus:.0%})")
        elif consensus < 0.3:
            base_score *= 0.7
            reasons.append(f"Low sentiment consensus ({consensus:.0%})")
            data_quality = 'moderate'

        # Momentum adjustment
        momentum = sentiment.get('momentum', 'stable')
        if momentum == 'rising':
            base_score += 10
            reasons.append("Sentiment momentum improving")
        elif momentum == 'falling':
            base_score -= 10
            reasons.append("Sentiment momentum weakening")

        # Direction label
        direction = sentiment.get('composite_direction', 'neutral')
        if direction in ['strong_bullish', 'bullish']:
            reasons.append(f"Overall sentiment: {direction.replace('_', ' ')}")
        elif direction in ['strong_bearish', 'bearish']:
            reasons.append(f"Overall sentiment: {direction.replace('_', ' ')}")

        score = max(-100, min(100, base_score))

        return {
            'score': score,
            'reasons': reasons,
            'data_quality': data_quality,
            'raw_data': {
                'composite': composite,
                'direction': direction,
                'momentum': momentum
            }
        }

    def _calculate_macro_score(self) -> Dict:
        """
        Score from -100 to +100 based on economic conditions.
        Uses FRED indicators and economic health composite.
        """
        score = 0
        reasons = []
        data_quality = 'good'

        health = database.get_latest_economic_health()
        if not health:
            return {'score': 0, 'reasons': ['No economic data available'], 'data_quality': 'poor'}

        # === OVERALL HEALTH (40 points max) ===
        health_score = health.get('overall_score', 50)
        health_contribution = (health_score - 50) * 0.8
        score += health_contribution

        if health_score >= 70:
            reasons.append(f"Strong economic health ({health_score:.0f}/100)")
        elif health_score <= 40:
            reasons.append(f"Weak economic health ({health_score:.0f}/100)")

        # === REGIME (30 points max) ===
        regime = health.get('regime', 'unknown')
        regime_scores = {
            'expansion': 30,
            'peak': 10,
            'contraction': -20,
            'trough': -30
        }
        regime_contribution = regime_scores.get(regime, 0)
        score += regime_contribution

        if regime == 'expansion':
            reasons.append("Economy in expansion phase")
        elif regime == 'contraction':
            reasons.append("Economy in contraction phase")
        elif regime == 'trough':
            reasons.append("Economy near trough - potential recovery")

        # === RECESSION PROBABILITY (30 points max penalty) ===
        recession_prob = health.get('recession_probability', 0.1)
        if recession_prob > 0.5:
            score -= 30
            reasons.append(f"High recession probability ({recession_prob:.0%})")
            data_quality = 'concerning'
        elif recession_prob > 0.3:
            score -= 15
            reasons.append(f"Elevated recession risk ({recession_prob:.0%})")
        elif recession_prob < 0.1:
            score += 10

        # === YIELD CURVE ===
        if health.get('yield_curve_inverted'):
            inversion_months = health.get('inversion_months', 0)
            if inversion_months >= 3:
                score -= 15
                reasons.append(f"Yield curve inverted {inversion_months} months (recession warning)")
            else:
                score -= 5

        score = max(-100, min(100, score))

        return {
            'score': score,
            'reasons': reasons,
            'data_quality': data_quality,
            'raw_data': {
                'health_score': health_score,
                'regime': regime,
                'recession_probability': recession_prob
            }
        }

    def _get_market_technicals(self) -> Dict:
        """Get aggregated technical indicators for major indices."""
        all_data = []

        for symbol in self.indices:
            data = database.get_market_data(symbol)
            if data and len(data) >= 20:
                all_data.append(self._compute_technicals(data, symbol))

        if not all_data:
            return {}

        # Average across indices
        avg_data = {
            'price': mean([d['price'] for d in all_data if d.get('price')]),
            'ma_20': self._safe_mean([d.get('ma_20') for d in all_data]),
            'ma_50': self._safe_mean([d.get('ma_50') for d in all_data]),
            'ma_200': self._safe_mean([d.get('ma_200') for d in all_data]),
            'rsi': self._safe_mean([d.get('rsi') for d in all_data]),
            'macd_histogram': self._safe_mean([d.get('macd_histogram') for d in all_data]),
            'macd_signal': self._get_consensus_signal([d.get('macd_signal') for d in all_data]),
            'high_52w': self._safe_mean([d.get('high_52w') for d in all_data]),
            'low_52w': self._safe_mean([d.get('low_52w') for d in all_data]),
            'volume_trend': self._get_consensus_signal([d.get('volume_trend') for d in all_data]),
            'price_trend': self._get_consensus_signal([d.get('price_trend') for d in all_data]),
            'momentum_5d': self._safe_mean([d.get('momentum_5d') for d in all_data]),
            'momentum_20d': self._safe_mean([d.get('momentum_20d') for d in all_data])
        }

        return avg_data

    def _get_ticker_technicals(self, ticker: str) -> Dict:
        """Get technical indicators for a specific ticker."""
        # Try to get from market_indices first (for indices)
        data = database.get_market_data(ticker)
        if data and len(data) >= 20:
            return self._compute_technicals(data, ticker)

        # For individual stocks, we'd need yfinance or another source
        # For now, return empty if not in our tracked indices
        return {}

    def _compute_technicals(self, ohlcv_data: List[Dict], symbol: str) -> Dict:
        """Compute technical indicators from OHLCV data."""
        if not ohlcv_data or len(ohlcv_data) < 20:
            return {}

        # Sort by date
        data = sorted(ohlcv_data, key=lambda x: x.get('date', ''))
        closes = [d['close'] for d in data if d.get('close')]

        if len(closes) < 20:
            return {}

        current_price = closes[-1]
        result = {'price': current_price, 'symbol': symbol}

        # Moving Averages
        if len(closes) >= 20:
            result['ma_20'] = mean(closes[-20:])
        if len(closes) >= 50:
            result['ma_50'] = mean(closes[-50:])
        if len(closes) >= 200:
            result['ma_200'] = mean(closes[-200:])

        # RSI (14-period)
        if len(closes) >= 15:
            result['rsi'] = self._calculate_rsi(closes, 14)

        # MACD
        if len(closes) >= 26:
            macd_data = self._calculate_macd(closes)
            result['macd_histogram'] = macd_data['histogram']
            result['macd_signal'] = macd_data['signal']

        # 52-week high/low
        if len(closes) >= 252:
            result['high_52w'] = max(closes[-252:])
            result['low_52w'] = min(closes[-252:])
        elif len(closes) >= 60:
            result['high_52w'] = max(closes)
            result['low_52w'] = min(closes)

        # Volume trend
        volumes = [d.get('volume', 0) for d in data[-20:] if d.get('volume')]
        if len(volumes) >= 10:
            recent_vol = mean(volumes[-5:]) if len(volumes) >= 5 else volumes[-1]
            older_vol = mean(volumes[:10])
            if older_vol > 0:
                vol_ratio = recent_vol / older_vol
                result['volume_trend'] = 'increasing' if vol_ratio > 1.2 else 'decreasing' if vol_ratio < 0.8 else 'stable'

        # Price trend
        if len(closes) >= 5:
            pct_5d = ((closes[-1] - closes[-5]) / closes[-5]) * 100
            result['momentum_5d'] = pct_5d
            result['price_trend'] = 'up' if pct_5d > 1 else 'down' if pct_5d < -1 else 'flat'

        if len(closes) >= 20:
            pct_20d = ((closes[-1] - closes[-20]) / closes[-20]) * 100
            result['momentum_20d'] = pct_20d

        return result

    def _calculate_rsi(self, closes: List[float], period: int = 14) -> float:
        """Calculate RSI indicator."""
        if len(closes) < period + 1:
            return 50.0

        deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
        recent_deltas = deltas[-(period):]

        gains = [d for d in recent_deltas if d > 0]
        losses = [-d for d in recent_deltas if d < 0]

        avg_gain = mean(gains) if gains else 0
        avg_loss = mean(losses) if losses else 0.001

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    def _calculate_macd(self, closes: List[float]) -> Dict:
        """Calculate MACD indicator."""
        if len(closes) < 26:
            return {'histogram': 0, 'signal': 'neutral'}

        # EMA calculations
        ema_12 = self._calculate_ema(closes, 12)
        ema_26 = self._calculate_ema(closes, 26)

        macd_line = ema_12 - ema_26

        # Signal line (9-period EMA of MACD)
        # Simplified: use recent MACD values
        recent_macd_values = []
        for i in range(min(9, len(closes) - 26)):
            idx = len(closes) - 1 - i
            if idx >= 26:
                e12 = self._calculate_ema(closes[:idx+1], 12)
                e26 = self._calculate_ema(closes[:idx+1], 26)
                recent_macd_values.append(e12 - e26)

        signal_line = mean(recent_macd_values) if recent_macd_values else macd_line
        histogram = macd_line - signal_line

        # Detect crossover
        signal = 'neutral'
        if len(recent_macd_values) >= 2:
            prev_hist = recent_macd_values[0] - signal_line if recent_macd_values else 0
            if histogram > 0 and prev_hist <= 0:
                signal = 'bullish_cross'
            elif histogram < 0 and prev_hist >= 0:
                signal = 'bearish_cross'

        return {'histogram': histogram, 'signal': signal}

    def _calculate_ema(self, closes: List[float], period: int) -> float:
        """Calculate Exponential Moving Average."""
        if len(closes) < period:
            return closes[-1] if closes else 0

        multiplier = 2 / (period + 1)
        ema = mean(closes[:period])  # Start with SMA

        for price in closes[period:]:
            ema = (price - ema) * multiplier + ema

        return ema

    def _get_market_sentiment(self) -> Optional[Dict]:
        """Get aggregated market-wide sentiment."""
        all_sentiments = database.get_all_ticker_sentiments()
        if not all_sentiments:
            return None

        scores = [s.get('composite_score', 0) for s in all_sentiments if s.get('composite_score') is not None]
        if not scores:
            return None

        # Aggregate
        avg_score = mean(scores)

        # Count directions
        bullish = sum(1 for s in all_sentiments if s.get('composite_direction') in ['bullish', 'strong_bullish'])
        bearish = sum(1 for s in all_sentiments if s.get('composite_direction') in ['bearish', 'strong_bearish'])
        total = len(all_sentiments)

        # Determine consensus
        if total > 0:
            consensus_strength = abs(bullish - bearish) / total
        else:
            consensus_strength = 0

        # Determine direction
        if avg_score > 0.3:
            direction = 'strong_bullish' if avg_score > 0.6 else 'bullish'
        elif avg_score < -0.3:
            direction = 'strong_bearish' if avg_score < -0.6 else 'bearish'
        else:
            direction = 'neutral'

        return {
            'composite_score': avg_score,
            'composite_direction': direction,
            'consensus_strength': consensus_strength,
            'momentum': 'stable',  # Would need historical data to determine
            'ticker_count': total
        }

    def _calculate_confidence(self, technical: Dict, sentiment: Dict, macro: Dict) -> Dict:
        """Calculate confidence level based on data quality and score agreement."""
        # Data quality scores
        quality_map = {'good': 1.0, 'moderate': 0.7, 'poor': 0.3, 'concerning': 0.5, 'unknown': 0.5}

        tech_quality = quality_map.get(technical.get('data_quality', 'unknown'), 0.5)
        sent_quality = quality_map.get(sentiment.get('data_quality', 'unknown'), 0.5)
        macro_quality = quality_map.get(macro.get('data_quality', 'unknown'), 0.5)

        # Weighted average quality
        avg_quality = (
            tech_quality * 0.5 +
            sent_quality * 0.25 +
            macro_quality * 0.25
        )

        # Score agreement (do all factors point same direction?)
        scores = [technical['score'], sentiment['score'], macro['score']]
        directions = [1 if s > 10 else -1 if s < -10 else 0 for s in scores]

        # Count agreement
        positive = sum(1 for d in directions if d > 0)
        negative = sum(1 for d in directions if d < 0)
        agreement = max(positive, negative) / 3

        # Final confidence
        confidence_score = avg_quality * 0.6 + agreement * 0.4

        if confidence_score >= 0.8:
            level = 'high'
        elif confidence_score >= 0.5:
            level = 'medium'
        else:
            level = 'low'

        return {
            'level': level,
            'score': round(confidence_score, 2),
            'data_quality': round(avg_quality, 2),
            'signal_agreement': round(agreement, 2)
        }

    def _score_to_recommendation(self, score: float) -> Dict:
        """Convert composite score to actionable recommendation."""
        if score >= 60:
            return {
                'action': 'STRONG_BUY',
                'color': '#22c55e',
                'bg_color': '#dcfce7',
                'description': 'Excellent conditions to buy',
                'short_desc': 'Very favorable'
            }
        elif score >= 30:
            return {
                'action': 'BUY',
                'color': '#84cc16',
                'bg_color': '#ecfccb',
                'description': 'Favorable conditions for buying',
                'short_desc': 'Favorable'
            }
        elif score >= -30:
            return {
                'action': 'HOLD',
                'color': '#eab308',
                'bg_color': '#fef9c3',
                'description': 'Neutral - wait for better entry',
                'short_desc': 'Neutral'
            }
        elif score >= -60:
            return {
                'action': 'CAUTION',
                'color': '#f97316',
                'bg_color': '#ffedd5',
                'description': 'Unfavorable conditions - proceed carefully',
                'short_desc': 'Unfavorable'
            }
        else:
            return {
                'action': 'AVOID',
                'color': '#ef4444',
                'bg_color': '#fee2e2',
                'description': 'Poor conditions - high risk of loss',
                'short_desc': 'High risk'
            }

    def _safe_mean(self, values: List) -> Optional[float]:
        """Calculate mean of non-None values."""
        filtered = [v for v in values if v is not None]
        return mean(filtered) if filtered else None

    def _get_consensus_signal(self, signals: List) -> Optional[str]:
        """Get most common signal from list."""
        filtered = [s for s in signals if s is not None]
        if not filtered:
            return None
        # Simple majority
        from collections import Counter
        counts = Counter(filtered)
        return counts.most_common(1)[0][0]


# Convenience functions
def get_recommendation(ticker: str = None) -> Dict:
    """Get buy/sell recommendation for ticker or market."""
    recommender = MarketRecommender()
    return recommender.calculate_recommendation(ticker)


def get_market_recommendation() -> Dict:
    """Get overall market recommendation."""
    return get_recommendation(None)


def get_ticker_recommendation(ticker: str) -> Dict:
    """Get recommendation for specific ticker."""
    return get_recommendation(ticker)
