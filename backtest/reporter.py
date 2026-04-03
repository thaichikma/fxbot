"""Format BacktestResult for console / Telegram."""

from __future__ import annotations

from backtest.result import BacktestResult


class BacktestReporter:
    """Human-readable backtest report."""

    def generate_report(self, result: BacktestResult) -> str:
        ch = result.challenge or {}
        lines = [
            f"📊 *BACKTEST* `{result.symbol}`",
            "─────────────────",
            f"📅 {result.start.date()} → {result.end.date()}",
            f"💰 ${result.initial_balance:,.0f} → ${result.final_balance:,.0f} ({result.total_return_pct:+.2f}%)",
        ]
        if result.costs_enabled:
            lines.append(
                f"💸 Costs (model): ${result.total_transaction_costs_usd:,.2f} "
                "(spread+commission+swap — not tick-perfect)",
            )
        lines += [
            f"📈 Trades: {result.total_trades} | Win rate: {result.win_rate*100:.1f}% | PF: {result.profit_factor:.2f}",
            f"📉 Max DD: {result.max_drawdown_pct:.2f}% | Max daily loss: {result.max_daily_loss_pct:.2f}%",
            f"⭐ Best day: ${result.best_day_profit:.0f} ({result.best_day_ratio*100:.0f}% of +days)",
            f"🛡️ FTMO check: {'✅' if result.ftmo_compliant else '❌'} {result.ftmo_fail_reason or ''}",
            "",
            "🏆 *Challenge (simplified)*",
            f"`{ch.get('final_phase', '?')}` | days traded: {ch.get('trading_days', 0)}",
            "",
            "Note: costs are modeled; live FTMO differs (slippage, gaps, swap table).",
        ]
        return "\n".join(lines)

    def generate_plain(self, result: BacktestResult) -> str:
        """Markdown off — plain text."""
        return self.generate_report(result).replace("*", "")
