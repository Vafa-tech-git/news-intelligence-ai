"""
Risk Metrics Module
Professional trading risk metrics for signal evaluation and portfolio analysis.

Metrics included:
- Sharpe Ratio: Risk-adjusted return (excess return / volatility)
- Sortino Ratio: Downside risk-adjusted return
- Maximum Drawdown (MDD): Largest peak-to-trough decline
- Calmar Ratio: Annual return / Maximum Drawdown
- Profit Factor: Gross profit / Gross loss
- Win Rate: Percentage of profitable trades
- Risk/Reward Ratio: Average win / Average loss
"""

import math
from typing import List, Dict, Optional, Tuple
from datetime import datetime, timedelta
from statistics import mean, stdev

import database


class RiskMetricsCalculator:
    """Calculate professional trading risk metrics."""

    def __init__(self, risk_free_rate: float = 0.05):
        """
        Initialize calculator.

        Args:
            risk_free_rate: Annual risk-free rate (default 5% for 2024/2025)
        """
        self.risk_free_rate = risk_free_rate
        self.daily_rf = risk_free_rate / 252  # Trading days per year

    def sharpe_ratio(self, returns: List[float], annualize: bool = True) -> float:
        """
        Calculate Sharpe Ratio.

        Sharpe Ratio = (Portfolio Return - Risk-Free Rate) / Portfolio StdDev

        Args:
            returns: List of period returns (e.g., daily returns as decimals)
            annualize: Whether to annualize the ratio

        Returns:
            Sharpe ratio (higher is better, > 2.0 is excellent)
        """
        if not returns or len(returns) < 2:
            return 0.0

        # Calculate excess returns (return - risk-free rate)
        excess_returns = [r - self.daily_rf for r in returns]

        avg_excess = mean(excess_returns)
        std_dev = stdev(excess_returns) if len(excess_returns) > 1 else 0.0001

        if std_dev == 0:
            return 0.0

        sharpe = avg_excess / std_dev

        if annualize:
            sharpe *= math.sqrt(252)

        return round(sharpe, 3)

    def sortino_ratio(self, returns: List[float], annualize: bool = True) -> float:
        """
        Calculate Sortino Ratio.

        Like Sharpe but uses only downside deviation (negative returns),
        which better reflects risk of loss.

        Sortino Ratio = (Portfolio Return - Risk-Free Rate) / Downside Deviation

        Args:
            returns: List of period returns
            annualize: Whether to annualize the ratio

        Returns:
            Sortino ratio (higher is better)
        """
        if not returns or len(returns) < 2:
            return 0.0

        excess_returns = [r - self.daily_rf for r in returns]
        avg_excess = mean(excess_returns)

        # Calculate downside deviation (only negative returns)
        downside_returns = [r for r in excess_returns if r < 0]

        if not downside_returns:
            return float('inf') if avg_excess > 0 else 0.0

        # Downside deviation
        squared_downside = [r ** 2 for r in downside_returns]
        downside_variance = sum(squared_downside) / len(returns)  # Use all returns count
        downside_deviation = math.sqrt(downside_variance) if downside_variance > 0 else 0.0001

        sortino = avg_excess / downside_deviation

        if annualize:
            sortino *= math.sqrt(252)

        return round(sortino, 3)

    def maximum_drawdown(self, equity_curve: List[float]) -> Dict:
        """
        Calculate Maximum Drawdown (MDD).

        MDD is the largest peak-to-trough decline in portfolio value.
        A lower MDD indicates better capital preservation.

        Args:
            equity_curve: List of portfolio values over time

        Returns:
            Dict with max_drawdown (as decimal), peak_idx, trough_idx, recovery info
        """
        if not equity_curve or len(equity_curve) < 2:
            return {
                'max_drawdown': 0.0,
                'max_drawdown_pct': 0.0,
                'peak_idx': 0,
                'trough_idx': 0,
                'recovery_idx': None,
                'recovery_periods': None,
                'underwater_periods': 0
            }

        peak = equity_curve[0]
        peak_idx = 0
        max_dd = 0.0
        max_dd_peak_idx = 0
        max_dd_trough_idx = 0
        trough_value = peak

        underwater_periods = 0

        for i, value in enumerate(equity_curve):
            if value > peak:
                peak = value
                peak_idx = i

            drawdown = (peak - value) / peak if peak > 0 else 0

            if drawdown > 0:
                underwater_periods += 1

            if drawdown > max_dd:
                max_dd = drawdown
                max_dd_peak_idx = peak_idx
                max_dd_trough_idx = i
                trough_value = value

        # Find recovery point (when equity returns to peak level)
        recovery_idx = None
        if max_dd_trough_idx < len(equity_curve) - 1:
            peak_value = equity_curve[max_dd_peak_idx]
            for i in range(max_dd_trough_idx + 1, len(equity_curve)):
                if equity_curve[i] >= peak_value:
                    recovery_idx = i
                    break

        recovery_periods = recovery_idx - max_dd_trough_idx if recovery_idx else None

        return {
            'max_drawdown': round(max_dd, 4),
            'max_drawdown_pct': round(max_dd * 100, 2),
            'peak_idx': max_dd_peak_idx,
            'trough_idx': max_dd_trough_idx,
            'peak_value': equity_curve[max_dd_peak_idx],
            'trough_value': trough_value,
            'recovery_idx': recovery_idx,
            'recovery_periods': recovery_periods,
            'underwater_periods': underwater_periods,
            'underwater_pct': round(underwater_periods / len(equity_curve) * 100, 1)
        }

    def calmar_ratio(self, returns: List[float], equity_curve: List[float] = None) -> float:
        """
        Calculate Calmar Ratio.

        Calmar Ratio = Annualized Return / Maximum Drawdown

        Args:
            returns: List of period returns
            equity_curve: Optional equity curve (will be computed from returns if not provided)

        Returns:
            Calmar ratio (higher is better)
        """
        if not returns or len(returns) < 2:
            return 0.0

        # Annualized return
        total_return = 1.0
        for r in returns:
            total_return *= (1 + r)

        periods = len(returns)
        annualized_return = (total_return ** (252 / periods)) - 1

        # Build equity curve if not provided
        if equity_curve is None:
            equity_curve = [1.0]
            for r in returns:
                equity_curve.append(equity_curve[-1] * (1 + r))

        mdd_result = self.maximum_drawdown(equity_curve)
        max_dd = mdd_result['max_drawdown']

        if max_dd == 0:
            return float('inf') if annualized_return > 0 else 0.0

        calmar = annualized_return / max_dd

        return round(calmar, 3)

    def profit_factor(self, trades: List[float]) -> float:
        """
        Calculate Profit Factor.

        Profit Factor = Gross Profit / Gross Loss

        A profit factor > 1.0 means the strategy is profitable.
        > 1.5 is good, > 2.0 is excellent.

        Args:
            trades: List of trade returns (positive for wins, negative for losses)

        Returns:
            Profit factor
        """
        if not trades:
            return 0.0

        gross_profit = sum(t for t in trades if t > 0)
        gross_loss = abs(sum(t for t in trades if t < 0))

        if gross_loss == 0:
            return float('inf') if gross_profit > 0 else 0.0

        return round(gross_profit / gross_loss, 3)

    def win_rate(self, trades: List[float]) -> float:
        """
        Calculate Win Rate.

        Win Rate = Number of Winning Trades / Total Trades

        Args:
            trades: List of trade returns

        Returns:
            Win rate as decimal (0.0 to 1.0)
        """
        if not trades:
            return 0.0

        winners = sum(1 for t in trades if t > 0)
        return round(winners / len(trades), 4)

    def risk_reward_ratio(self, trades: List[float]) -> float:
        """
        Calculate Risk/Reward Ratio.

        R/R Ratio = Average Win / Average Loss

        Args:
            trades: List of trade returns

        Returns:
            Risk/reward ratio
        """
        if not trades:
            return 0.0

        wins = [t for t in trades if t > 0]
        losses = [abs(t) for t in trades if t < 0]

        if not wins or not losses:
            return 0.0

        avg_win = mean(wins)
        avg_loss = mean(losses)

        if avg_loss == 0:
            return float('inf')

        return round(avg_win / avg_loss, 3)

    def expectancy(self, trades: List[float]) -> float:
        """
        Calculate Trade Expectancy.

        Expectancy = (Win Rate × Average Win) - (Loss Rate × Average Loss)

        This tells you how much you can expect to make per trade on average.

        Args:
            trades: List of trade returns

        Returns:
            Expectancy per trade
        """
        if not trades:
            return 0.0

        wins = [t for t in trades if t > 0]
        losses = [abs(t) for t in trades if t < 0]

        win_rate = len(wins) / len(trades) if trades else 0
        loss_rate = len(losses) / len(trades) if trades else 0

        avg_win = mean(wins) if wins else 0
        avg_loss = mean(losses) if losses else 0

        expectancy = (win_rate * avg_win) - (loss_rate * avg_loss)

        return round(expectancy, 6)

    def calculate_all_metrics(self, returns: List[float] = None, trades: List[float] = None) -> Dict:
        """
        Calculate all risk metrics at once.

        Args:
            returns: Time series of returns (for Sharpe, Sortino, MDD, Calmar)
            trades: List of individual trade P&L (for Profit Factor, Win Rate, etc.)

        Returns:
            Dict with all calculated metrics
        """
        result = {
            'calculated_at': datetime.now().isoformat(),
            'periods': len(returns) if returns else 0,
            'trades_count': len(trades) if trades else 0
        }

        if returns and len(returns) >= 2:
            # Build equity curve
            equity = [1.0]
            for r in returns:
                equity.append(equity[-1] * (1 + r))

            result['sharpe_ratio'] = self.sharpe_ratio(returns)
            result['sortino_ratio'] = self.sortino_ratio(returns)
            result['max_drawdown'] = self.maximum_drawdown(equity)
            result['calmar_ratio'] = self.calmar_ratio(returns, equity)

            # Total return
            total_return = (equity[-1] / equity[0]) - 1
            result['total_return'] = round(total_return * 100, 2)
            result['total_return_pct'] = f"{result['total_return']}%"

            # Annualized return
            if len(returns) > 20:
                ann_return = (equity[-1] ** (252 / len(returns))) - 1
                result['annualized_return'] = round(ann_return * 100, 2)
                result['annualized_return_pct'] = f"{result['annualized_return']}%"

        if trades and len(trades) > 0:
            result['profit_factor'] = self.profit_factor(trades)
            result['win_rate'] = self.win_rate(trades)
            result['win_rate_pct'] = f"{round(result['win_rate'] * 100, 1)}%"
            result['risk_reward_ratio'] = self.risk_reward_ratio(trades)
            result['expectancy'] = self.expectancy(trades)

            # Additional trade stats
            wins = [t for t in trades if t > 0]
            losses = [t for t in trades if t < 0]
            result['winning_trades'] = len(wins)
            result['losing_trades'] = len(losses)
            result['avg_win'] = round(mean(wins), 4) if wins else 0
            result['avg_loss'] = round(mean(losses), 4) if losses else 0
            result['largest_win'] = round(max(trades), 4) if trades else 0
            result['largest_loss'] = round(min(trades), 4) if trades else 0

        # Quality ratings
        result['ratings'] = self._rate_metrics(result)

        return result

    def _rate_metrics(self, metrics: Dict) -> Dict:
        """Rate the quality of each metric."""
        ratings = {}

        # Sharpe Ratio rating
        sharpe = metrics.get('sharpe_ratio', 0)
        if sharpe >= 3.0:
            ratings['sharpe'] = {'rating': 'Excellent', 'color': '#22c55e'}
        elif sharpe >= 2.0:
            ratings['sharpe'] = {'rating': 'Very Good', 'color': '#84cc16'}
        elif sharpe >= 1.0:
            ratings['sharpe'] = {'rating': 'Good', 'color': '#eab308'}
        elif sharpe >= 0.5:
            ratings['sharpe'] = {'rating': 'Acceptable', 'color': '#f97316'}
        else:
            ratings['sharpe'] = {'rating': 'Poor', 'color': '#ef4444'}

        # Max Drawdown rating
        mdd = metrics.get('max_drawdown', {}).get('max_drawdown_pct', 0)
        if mdd <= 10:
            ratings['max_drawdown'] = {'rating': 'Excellent', 'color': '#22c55e'}
        elif mdd <= 15:
            ratings['max_drawdown'] = {'rating': 'Good', 'color': '#84cc16'}
        elif mdd <= 25:
            ratings['max_drawdown'] = {'rating': 'Acceptable', 'color': '#eab308'}
        elif mdd <= 35:
            ratings['max_drawdown'] = {'rating': 'Risky', 'color': '#f97316'}
        else:
            ratings['max_drawdown'] = {'rating': 'Dangerous', 'color': '#ef4444'}

        # Profit Factor rating
        pf = metrics.get('profit_factor', 0)
        if pf >= 2.5:
            ratings['profit_factor'] = {'rating': 'Excellent', 'color': '#22c55e'}
        elif pf >= 1.75:
            ratings['profit_factor'] = {'rating': 'Good', 'color': '#84cc16'}
        elif pf >= 1.25:
            ratings['profit_factor'] = {'rating': 'Acceptable', 'color': '#eab308'}
        elif pf >= 1.0:
            ratings['profit_factor'] = {'rating': 'Marginal', 'color': '#f97316'}
        else:
            ratings['profit_factor'] = {'rating': 'Unprofitable', 'color': '#ef4444'}

        # Win Rate rating
        wr = metrics.get('win_rate', 0)
        if wr >= 0.6:
            ratings['win_rate'] = {'rating': 'High', 'color': '#22c55e'}
        elif wr >= 0.5:
            ratings['win_rate'] = {'rating': 'Good', 'color': '#84cc16'}
        elif wr >= 0.4:
            ratings['win_rate'] = {'rating': 'Acceptable', 'color': '#eab308'}
        else:
            ratings['win_rate'] = {'rating': 'Low', 'color': '#f97316'}

        return ratings


def get_signal_risk_metrics(ticker: str = None, days: int = 90) -> Dict:
    """
    Calculate risk metrics for signals from the database.

    Args:
        ticker: Optional ticker filter
        days: Number of days to analyze

    Returns:
        Dict with risk metrics
    """
    # Get signal performance data from database
    performance = database.get_signal_performance_history(ticker=ticker, days=days)

    if not performance:
        return {'error': 'No performance data available'}

    calculator = RiskMetricsCalculator()

    # Extract returns and trades
    returns = []
    trades = []

    for p in performance:
        if p.get('return_1d') is not None:
            returns.append(p['return_1d'] / 100)  # Convert percentage to decimal

        # Use 5-day return as "trade" outcome
        if p.get('return_5d') is not None:
            trades.append(p['return_5d'] / 100)

    return calculator.calculate_all_metrics(returns=returns, trades=trades)


# Convenience instance
_calculator = RiskMetricsCalculator()


def sharpe_ratio(returns: List[float]) -> float:
    return _calculator.sharpe_ratio(returns)


def sortino_ratio(returns: List[float]) -> float:
    return _calculator.sortino_ratio(returns)


def maximum_drawdown(equity_curve: List[float]) -> Dict:
    return _calculator.maximum_drawdown(equity_curve)


def calmar_ratio(returns: List[float]) -> float:
    return _calculator.calmar_ratio(returns)


def profit_factor(trades: List[float]) -> float:
    return _calculator.profit_factor(trades)
