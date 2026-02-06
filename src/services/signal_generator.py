"""
Signal Generator Module
Generates buy/sell signals based on sentiment, market context, and timing factors.
"""

from datetime import datetime
from config import SIGNAL_THRESHOLDS
import database
from modules.economic_health import get_economic_health


class SignalGenerator:
    """Generates trading signals from sentiment data."""

    def __init__(self, thresholds=None):
        """
        Initialize signal generator with thresholds.

        Args:
            thresholds: Dict of signal thresholds
        """
        self.thresholds = thresholds or SIGNAL_THRESHOLDS

    def generate_signal(self, ticker, sentiment_data, market_context=None):
        """
        Generate a trading signal for a ticker.

        Args:
            ticker: Stock symbol
            sentiment_data: Dict with composite sentiment data
            market_context: Optional market context data

        Returns:
            dict with signal type, confidence, reasons, risks
        """
        if not sentiment_data:
            return None

        score = sentiment_data.get('composite_score', 0)
        confidence = sentiment_data.get('confidence', 0)
        consensus = sentiment_data.get('consensus_strength', 0)
        momentum = sentiment_data.get('momentum', 'stable')

        # Determine base signal
        signal, signal_confidence = self._determine_signal(
            score, confidence, consensus, momentum
        )

        # Generate reasons
        reasons = self._generate_reasons(sentiment_data, market_context)

        # Generate risk factors
        risks = self._generate_risks(sentiment_data, market_context)

        # Calculate timing score
        timing_score = self._calculate_timing_score(
            sentiment_data, market_context
        )

        # Check for buy-low / sell-high opportunities
        opportunity_flags = self._check_opportunities(
            sentiment_data, market_context
        )

        result = {
            'ticker': ticker,
            'signal': signal,
            'signal_confidence': round(signal_confidence, 4),
            'timing_score': timing_score,
            'reasons': reasons,
            'risk_factors': risks,
            'time_horizon': self._suggest_horizon(timing_score, momentum),
            'opportunities': opportunity_flags
        }

        # Update ticker_sentiment with signal
        database.save_ticker_sentiment(
            ticker=ticker,
            composite_score=score,
            composite_direction=sentiment_data.get('composite_direction'),
            confidence=confidence,
            consensus_strength=consensus,
            momentum=momentum,
            velocity=sentiment_data.get('velocity'),
            source_breakdown=sentiment_data.get('source_breakdown'),
            signal=signal,
            signal_confidence=signal_confidence,
            signal_reasons=reasons,
            risk_factors=risks,
            timing_score=timing_score
        )

        return result

    def _determine_signal(self, score, confidence, consensus, momentum):
        """
        Determine signal type based on thresholds.

        Returns:
            tuple of (signal_type, signal_confidence)
        """
        th = self.thresholds

        # Strong Buy: High sentiment + high confidence + high consensus + rising momentum
        if (score >= th['strong_buy']['sentiment'] and
            confidence >= th['strong_buy']['confidence'] and
            consensus >= th['strong_buy']['consensus'] and
            momentum == 'rising'):
            return 'strong_buy', min(1.0, confidence * consensus)

        # Strong Sell: Low sentiment + high confidence + high consensus + falling momentum
        if (score <= th['strong_sell']['sentiment'] and
            confidence >= th['strong_sell']['confidence'] and
            consensus >= th['strong_sell']['consensus'] and
            momentum == 'falling'):
            return 'strong_sell', min(1.0, confidence * consensus)

        # Buy: Positive sentiment + decent confidence
        if (score >= th['buy']['sentiment'] and
            confidence >= th['buy']['confidence']):
            return 'buy', confidence * 0.8

        # Sell: Negative sentiment + decent confidence
        if (score <= th['sell']['sentiment'] and
            confidence >= th['sell']['confidence']):
            return 'sell', confidence * 0.8

        # Hold: Everything else
        return 'hold', 0.5

    def _generate_reasons(self, sentiment_data, market_context=None):
        """Generate human-readable reasons for the signal."""
        reasons = []

        score = sentiment_data.get('composite_score', 0)
        consensus = sentiment_data.get('consensus_strength', 0)
        momentum = sentiment_data.get('momentum', 'stable')
        sources = sentiment_data.get('source_breakdown', {})

        # Sentiment-based reasons
        if score >= 0.6:
            reasons.append("Strong positive sentiment across sources")
        elif score >= 0.3:
            reasons.append("Positive sentiment trend")
        elif score <= -0.6:
            reasons.append("Strong negative sentiment across sources")
        elif score <= -0.3:
            reasons.append("Negative sentiment trend")

        # Consensus-based reasons
        if consensus >= 0.7:
            reasons.append("High agreement between sentiment sources")
        elif consensus < 0.3:
            reasons.append("Mixed signals from different sources")

        # Momentum-based reasons
        if momentum == 'rising':
            reasons.append("Sentiment momentum is rising")
        elif momentum == 'falling':
            reasons.append("Sentiment momentum is falling")

        # Source-specific reasons
        if 'alphavantage' in sources:
            av = sources['alphavantage']
            if av.get('score', 0) >= 0.3:
                reasons.append("Professional news sentiment positive")
            elif av.get('score', 0) <= -0.3:
                reasons.append("Professional news sentiment negative")

        if 'stocktwits' in sources:
            st = sources['stocktwits']
            if st.get('score', 0) >= 0.3:
                reasons.append("Strong retail bullish sentiment")
            elif st.get('score', 0) <= -0.3:
                reasons.append("Strong retail bearish sentiment")

        if 'reddit' in sources:
            rd = sources['reddit']
            if rd.get('volume', 0) >= 50:
                reasons.append("High social media activity")

        # Market context reasons
        if market_context:
            regime = market_context.get('regime', '')
            if regime == 'bull' and score > 0:
                reasons.append("Bullish in bull market regime")
            elif regime == 'bear' and score < 0:
                reasons.append("Bearish in bear market regime")
            elif regime == 'bear' and score > 0.3:
                reasons.append("Contrarian bullish signal in bear market")

        return reasons[:5]  # Limit to top 5 reasons

    def _generate_risks(self, sentiment_data, market_context=None):
        """Generate risk factors for the signal."""
        risks = []

        confidence = sentiment_data.get('confidence', 0)
        consensus = sentiment_data.get('consensus_strength', 0)
        sources = sentiment_data.get('source_breakdown', {})

        # Confidence-based risks
        if confidence < 0.5:
            risks.append("Low overall confidence in signal")

        # Coverage-based risks
        if len(sources) < 2:
            risks.append("Limited source coverage")

        # Consensus-based risks
        if consensus < 0.3:
            risks.append("Conflicting signals from sources")

        # Check for divergence between sources
        if sources:
            scores = [s.get('score', 0) for s in sources.values()]
            if scores:
                max_score = max(scores)
                min_score = min(scores)
                if max_score - min_score > 0.5:
                    risks.append("High divergence between sources")

        # Market context risks
        if market_context:
            volatility = market_context.get('volatility_level', 0)
            if volatility >= 25:
                risks.append("High market volatility")
            elif volatility >= 20:
                risks.append("Elevated market volatility")

            regime = market_context.get('regime', '')
            if regime == 'volatile':
                risks.append("Unstable market conditions")

        # Economic health risks
        try:
            economic_health = get_economic_health()
            if economic_health:
                econ_regime = economic_health.get('regime', '')
                if econ_regime in ('contraction', 'trough'):
                    risks.append(f"Economic {econ_regime} regime")
                if economic_health.get('recession_warning'):
                    risks.append("Yield curve recession warning active")
                recession_prob = economic_health.get('recession_probability', 0)
                if recession_prob >= 50:
                    risks.append(f"Elevated recession risk ({recession_prob:.0f}%)")
        except Exception:
            pass  # Continue without economic data

        return risks[:5]  # Limit to top 5 risks

    def _calculate_timing_score(self, sentiment_data, market_context=None):
        """
        Calculate timing favorability score (1-10).

        Factors:
        - Sentiment momentum (25%)
        - Market context (25%)
        - Relative strength (20%)
        - Volume trend (15%)
        - Catalyst proximity (15%)
        """
        score = 5.0  # Start at neutral

        momentum = sentiment_data.get('momentum', 'stable')
        velocity = sentiment_data.get('velocity', 0)
        composite = sentiment_data.get('composite_score', 0)
        consensus = sentiment_data.get('consensus_strength', 0)

        # Sentiment momentum factor (25%)
        if momentum == 'rising' and composite > 0:
            score += 1.25  # Good for buying
        elif momentum == 'falling' and composite < 0:
            score += 1.25  # Good for selling
        elif momentum == 'rising' and composite < 0:
            score += 0.5  # Potential reversal
        elif momentum == 'falling' and composite > 0:
            score -= 0.5  # Weakening

        # Strong velocity bonus
        if abs(velocity) > 0.05:
            score += 0.5

        # Market context factor (25%)
        if market_context:
            regime = market_context.get('regime', '')
            volatility = market_context.get('volatility_level', 15)

            # Regime alignment
            if regime == 'bull' and composite > 0:
                score += 1.0
            elif regime == 'bear' and composite < 0:
                score += 1.0
            elif regime == 'volatile':
                score -= 0.5

            # Volatility factor (elevated VIX = opportunity but risky)
            if volatility >= 25 and composite > 0:
                score += 0.5  # Buy in fear
            elif volatility < 15 and composite > 0.5:
                score -= 0.25  # Complacency risk

        # Consensus factor (20%)
        if consensus >= 0.7:
            score += 1.0
        elif consensus >= 0.5:
            score += 0.5
        elif consensus < 0.3:
            score -= 0.5

        # Volume/activity factor (15%)
        sources = sentiment_data.get('source_breakdown', {})
        total_volume = sum(s.get('volume', 0) for s in sources.values())
        if total_volume >= 100:
            score += 0.75
        elif total_volume >= 50:
            score += 0.5

        # Economic health factor (bonus/penalty)
        try:
            economic_health = get_economic_health()
            if economic_health:
                econ_regime = economic_health.get('regime', '')
                overall_score = economic_health.get('overall_score', 50)

                # Adjust timing based on economic conditions
                if econ_regime == 'expansion' and composite > 0:
                    score += 0.5  # Favorable for bullish signals
                elif econ_regime == 'contraction' and composite < 0:
                    score += 0.5  # Favorable for bearish signals
                elif econ_regime in ('contraction', 'trough') and composite > 0:
                    score -= 0.5  # Risky for bullish signals in weak economy

                # Recession warning penalty
                if economic_health.get('recession_warning'):
                    if composite > 0:
                        score -= 0.75  # Extra caution for bullish signals
        except Exception:
            pass  # Continue without economic data

        # Clamp to 1-10 range
        return round(max(1, min(10, score)), 1)

    def _suggest_horizon(self, timing_score, momentum):
        """Suggest time horizon based on signal characteristics."""
        if timing_score >= 8 and momentum in ('rising', 'falling'):
            return 'short_term'  # 1-5 days
        elif timing_score >= 6:
            return 'medium_term'  # 1-4 weeks
        else:
            return 'long_term'  # 1-3 months

    def _check_opportunities(self, sentiment_data, market_context=None):
        """
        Check for special buy-low / sell-high opportunities.

        Returns:
            dict with opportunity flags
        """
        opportunities = {
            'buy_low': False,
            'sell_high': False,
            'contrarian': False
        }

        score = sentiment_data.get('composite_score', 0)
        momentum = sentiment_data.get('momentum', 'stable')
        velocity = sentiment_data.get('velocity', 0)

        if not market_context:
            return opportunities

        regime = market_context.get('regime', '')
        volatility = market_context.get('volatility_level', 15)
        sp500_change = market_context.get('sp500_pct_change', 0)

        # Buy Low: Market correction + improving sentiment
        if (sp500_change <= -5 and  # Market down 5%+
            volatility >= 20 and     # Elevated fear
            velocity > 0 and         # Sentiment improving
            score > -0.3):           # Not deeply negative
            opportunities['buy_low'] = True

        # Sell High: Extended rally + euphoric sentiment + weakening momentum
        if (regime == 'bull' and
            score >= 0.6 and          # Euphoric
            momentum in ('stable', 'falling') and
            velocity < 0):            # Starting to weaken
            opportunities['sell_high'] = True

        # Contrarian: Sentiment diverging from market
        if (regime == 'bear' and score >= 0.3):
            opportunities['contrarian'] = True
        elif (regime == 'bull' and score <= -0.3):
            opportunities['contrarian'] = True

        return opportunities


def generate_signal(ticker, sentiment_data, market_context=None):
    """
    Convenience function to generate a signal.

    Args:
        ticker: Stock symbol
        sentiment_data: Aggregated sentiment data
        market_context: Optional market context

    Returns:
        dict with signal data
    """
    generator = SignalGenerator()
    return generator.generate_signal(ticker, sentiment_data, market_context)


def generate_signals_for_all():
    """
    Generate signals for all tickers with sentiment data.

    Returns:
        list of signal dicts
    """
    all_sentiments = database.get_all_ticker_sentiments()
    market_context = database.get_latest_market_context()

    generator = SignalGenerator()
    signals = []

    for sentiment in all_sentiments:
        ticker = sentiment.get('ticker')
        if ticker:
            signal = generator.generate_signal(ticker, sentiment, market_context)
            if signal:
                signals.append(signal)

    return signals


def get_actionable_signals(signal_types=None):
    """
    Get all actionable signals (excluding 'hold').

    Args:
        signal_types: Optional list of signal types to include

    Returns:
        list of signals
    """
    if signal_types is None:
        signal_types = ['strong_buy', 'buy', 'sell', 'strong_sell']

    return database.get_signals_by_type(signal_types)
