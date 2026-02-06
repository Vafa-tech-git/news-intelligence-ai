"""
Position Sizing Engine
Calculate optimal position sizes based on risk parameters and portfolio constraints.

Methods included:
- Kelly Criterion: Optimal position size based on win rate and payoff ratio
- Volatility-Adjusted: Size based on ATR/volatility with risk percentage
- Fixed Fractional: Simple percentage of portfolio
- Portfolio Heat: Total risk exposure tracking
"""

import math
from typing import Dict, List, Optional
from statistics import mean, stdev

import database


class PositionSizer:
    """Calculate optimal position sizes based on various risk models."""

    def __init__(self, max_position_pct: float = 0.25, max_portfolio_heat: float = 0.10):
        """
        Initialize position sizer.

        Args:
            max_position_pct: Maximum single position size (default 25%)
            max_portfolio_heat: Maximum total portfolio risk (default 10%)
        """
        self.max_position_pct = max_position_pct
        self.max_portfolio_heat = max_portfolio_heat

    def kelly_criterion(
        self,
        win_rate: float,
        avg_win: float,
        avg_loss: float,
        kelly_fraction: float = 0.5
    ) -> Dict:
        """
        Calculate Kelly Criterion position size.

        Kelly % = W - [(1-W) / R]
        Where:
            W = Win probability
            R = Win/Loss ratio (avg_win / avg_loss)

        Args:
            win_rate: Historical win rate (0.0 to 1.0)
            avg_win: Average winning trade return
            avg_loss: Average losing trade return (as positive number)
            kelly_fraction: Fraction of Kelly to use (0.5 = Half-Kelly, safer)

        Returns:
            Dict with kelly_pct, recommended_size, reasoning
        """
        if avg_loss <= 0:
            return {
                'kelly_pct': 0,
                'recommended_size': 0,
                'reasoning': 'Invalid avg_loss (must be positive)',
                'method': 'kelly_criterion'
            }

        # Win/Loss ratio
        win_loss_ratio = avg_win / avg_loss

        # Full Kelly
        full_kelly = win_rate - ((1 - win_rate) / win_loss_ratio)

        # Apply Kelly fraction (Half-Kelly is common for safety)
        kelly_pct = full_kelly * kelly_fraction

        # Cap at maximum position size
        recommended_size = max(0, min(kelly_pct, self.max_position_pct))

        # Reasoning
        if full_kelly <= 0:
            reasoning = "Negative edge - strategy is unprofitable, no position recommended"
        elif kelly_pct > 0.20:
            reasoning = f"Strong edge detected. Full Kelly: {full_kelly:.1%}, using {kelly_fraction:.0%} Kelly for safety"
        elif kelly_pct > 0.10:
            reasoning = f"Moderate edge. Using {kelly_fraction:.0%} Kelly"
        else:
            reasoning = f"Small edge. Conservative sizing recommended"

        return {
            'full_kelly_pct': round(full_kelly, 4),
            'kelly_pct': round(kelly_pct, 4),
            'recommended_size': round(recommended_size, 4),
            'recommended_size_pct': f"{round(recommended_size * 100, 1)}%",
            'win_rate': win_rate,
            'win_loss_ratio': round(win_loss_ratio, 2),
            'kelly_fraction_used': kelly_fraction,
            'reasoning': reasoning,
            'method': 'kelly_criterion'
        }

    def volatility_adjusted(
        self,
        portfolio_value: float,
        current_price: float,
        atr: float,
        risk_percent: float = 0.02,
        atr_multiplier: float = 2.0,
        signal_confidence: float = 1.0
    ) -> Dict:
        """
        Calculate position size based on volatility (ATR).

        Position Size = (Portfolio × Risk%) / (ATR × Multiplier)

        Args:
            portfolio_value: Total portfolio value
            current_price: Current price of the asset
            atr: Average True Range (volatility measure)
            risk_percent: Max risk per trade (default 2%)
            atr_multiplier: Stop loss distance in ATRs (default 2.0)
            signal_confidence: Confidence multiplier (0.0 to 1.0)

        Returns:
            Dict with shares, position_value, stop_loss, risk_amount
        """
        if atr <= 0 or current_price <= 0:
            return {
                'shares': 0,
                'position_value': 0,
                'reasoning': 'Invalid ATR or price',
                'method': 'volatility_adjusted'
            }

        # Calculate risk amount
        risk_amount = portfolio_value * risk_percent

        # Stop loss distance
        stop_distance = atr * atr_multiplier
        stop_loss_price = current_price - stop_distance

        # Position size (shares)
        shares = risk_amount / stop_distance

        # Adjust by confidence
        adjusted_shares = shares * signal_confidence

        # Calculate position value
        position_value = adjusted_shares * current_price

        # Check against max position limit
        max_position_value = portfolio_value * self.max_position_pct
        if position_value > max_position_value:
            adjusted_shares = max_position_value / current_price
            position_value = max_position_value

        return {
            'shares': int(adjusted_shares),
            'shares_exact': round(adjusted_shares, 2),
            'position_value': round(position_value, 2),
            'position_pct': round(position_value / portfolio_value * 100, 2),
            'risk_amount': round(risk_amount, 2),
            'stop_loss_price': round(stop_loss_price, 2),
            'stop_distance': round(stop_distance, 2),
            'stop_distance_pct': round(stop_distance / current_price * 100, 2),
            'atr': atr,
            'atr_multiplier': atr_multiplier,
            'signal_confidence': signal_confidence,
            'risk_percent': risk_percent,
            'method': 'volatility_adjusted'
        }

    def fixed_fractional(
        self,
        portfolio_value: float,
        current_price: float,
        fraction: float = 0.05
    ) -> Dict:
        """
        Simple fixed fractional position sizing.

        Position Size = Portfolio Value × Fraction / Price

        Args:
            portfolio_value: Total portfolio value
            current_price: Current price of the asset
            fraction: Fraction of portfolio (default 5%)

        Returns:
            Dict with shares, position_value
        """
        if current_price <= 0:
            return {
                'shares': 0,
                'position_value': 0,
                'method': 'fixed_fractional'
            }

        # Cap at max position
        fraction = min(fraction, self.max_position_pct)

        position_value = portfolio_value * fraction
        shares = position_value / current_price

        return {
            'shares': int(shares),
            'shares_exact': round(shares, 2),
            'position_value': round(position_value, 2),
            'position_pct': round(fraction * 100, 2),
            'fraction': fraction,
            'method': 'fixed_fractional'
        }

    def portfolio_heat(self, positions: List[Dict], portfolio_value: float) -> Dict:
        """
        Calculate total portfolio risk exposure (heat).

        Heat = Sum of all position risks / Portfolio Value

        Args:
            positions: List of position dicts with 'risk_amount' or 'position_value' and 'stop_pct'
            portfolio_value: Total portfolio value

        Returns:
            Dict with total_heat, position_count, warnings
        """
        total_risk = 0
        position_details = []

        for pos in positions:
            if 'risk_amount' in pos:
                risk = pos['risk_amount']
            elif 'position_value' in pos and 'stop_pct' in pos:
                risk = pos['position_value'] * pos['stop_pct']
            else:
                risk = pos.get('position_value', 0) * 0.10  # Assume 10% risk if not specified

            total_risk += risk
            position_details.append({
                'ticker': pos.get('ticker', 'Unknown'),
                'risk_amount': round(risk, 2),
                'risk_pct': round(risk / portfolio_value * 100, 2) if portfolio_value > 0 else 0
            })

        total_heat = total_risk / portfolio_value if portfolio_value > 0 else 0

        # Generate warnings
        warnings = []
        if total_heat > self.max_portfolio_heat:
            warnings.append(f"Portfolio heat ({total_heat:.1%}) exceeds maximum ({self.max_portfolio_heat:.1%})")
        if total_heat > self.max_portfolio_heat * 0.8:
            warnings.append(f"Portfolio heat approaching limit")
        if len(positions) > 20:
            warnings.append("High position count may indicate over-diversification")

        # Check position concentration
        if positions:
            max_position = max(pos.get('position_value', 0) for pos in positions)
            max_concentration = max_position / portfolio_value if portfolio_value > 0 else 0
            if max_concentration > 0.20:
                warnings.append(f"Largest position is {max_concentration:.1%} of portfolio")

        return {
            'total_heat': round(total_heat, 4),
            'total_heat_pct': f"{round(total_heat * 100, 2)}%",
            'total_risk_amount': round(total_risk, 2),
            'position_count': len(positions),
            'positions': position_details,
            'max_allowed_heat': self.max_portfolio_heat,
            'remaining_heat': round(max(0, self.max_portfolio_heat - total_heat), 4),
            'can_add_position': total_heat < self.max_portfolio_heat,
            'warnings': warnings
        }

    def calculate_recommended_size(
        self,
        portfolio_value: float,
        current_price: float,
        signal: Dict,
        historical_trades: List[float] = None,
        atr: float = None
    ) -> Dict:
        """
        Calculate recommended position size based on signal and multiple methods.

        Args:
            portfolio_value: Total portfolio value
            current_price: Current asset price
            signal: Signal dict with 'confidence', 'signal' type
            historical_trades: List of historical trade returns for Kelly
            atr: Average True Range for volatility sizing

        Returns:
            Dict with recommendations from multiple methods
        """
        results = {
            'ticker': signal.get('ticker', 'Unknown'),
            'signal_type': signal.get('signal', 'hold'),
            'signal_confidence': signal.get('signal_confidence', 0.5),
            'current_price': current_price,
            'portfolio_value': portfolio_value,
            'methods': {}
        }

        confidence = signal.get('signal_confidence', 0.5)

        # 1. Fixed Fractional (baseline)
        base_fraction = 0.05  # 5% baseline
        adjusted_fraction = base_fraction * confidence

        results['methods']['fixed_fractional'] = self.fixed_fractional(
            portfolio_value, current_price, adjusted_fraction
        )

        # 2. Volatility-Adjusted (if ATR available)
        if atr and atr > 0:
            results['methods']['volatility_adjusted'] = self.volatility_adjusted(
                portfolio_value, current_price, atr,
                risk_percent=0.02,
                signal_confidence=confidence
            )

        # 3. Kelly Criterion (if historical data available)
        if historical_trades and len(historical_trades) >= 10:
            wins = [t for t in historical_trades if t > 0]
            losses = [abs(t) for t in historical_trades if t < 0]

            if wins and losses:
                win_rate = len(wins) / len(historical_trades)
                avg_win = mean(wins)
                avg_loss = mean(losses)

                results['methods']['kelly'] = self.kelly_criterion(
                    win_rate, avg_win, avg_loss, kelly_fraction=0.5
                )

        # Calculate final recommendation
        sizes = []
        for method_name, method_result in results['methods'].items():
            if method_result.get('position_value'):
                sizes.append(method_result['position_value'])

        if sizes:
            # Use conservative approach: minimum of all methods
            recommended_value = min(sizes)
            recommended_shares = int(recommended_value / current_price)

            results['recommendation'] = {
                'shares': recommended_shares,
                'position_value': round(recommended_value, 2),
                'position_pct': round(recommended_value / portfolio_value * 100, 2),
                'approach': 'conservative_min'
            }
        else:
            results['recommendation'] = {
                'shares': 0,
                'position_value': 0,
                'position_pct': 0,
                'approach': 'insufficient_data'
            }

        return results


# Convenience functions
_sizer = PositionSizer()


def calculate_position_size(
    portfolio_value: float,
    price: float,
    atr: float = None,
    confidence: float = 1.0,
    method: str = 'volatility'
) -> Dict:
    """
    Quick position size calculation.

    Args:
        portfolio_value: Portfolio value
        price: Current price
        atr: ATR for volatility method
        confidence: Signal confidence
        method: 'volatility', 'fixed', or 'kelly'

    Returns:
        Position sizing recommendation
    """
    if method == 'volatility' and atr:
        return _sizer.volatility_adjusted(portfolio_value, price, atr, signal_confidence=confidence)
    elif method == 'fixed':
        return _sizer.fixed_fractional(portfolio_value, price, fraction=0.05 * confidence)
    else:
        return _sizer.fixed_fractional(portfolio_value, price, fraction=0.05 * confidence)


def get_portfolio_heat(positions: List[Dict], portfolio_value: float) -> Dict:
    """Calculate portfolio heat from positions."""
    return _sizer.portfolio_heat(positions, portfolio_value)
