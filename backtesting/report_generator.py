"""HTML backtest report with equity and drawdown charts."""

from __future__ import annotations

import base64
import io
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from backtesting.models import BacktestResult
from backtesting.walk_forward import WalkForwardReport


def _fig_to_base64(fig: plt.Figure) -> str:
    buf = io.BytesIO()
    fig.savefig(buf, format="png", dpi=100, bbox_inches="tight")
    plt.close(fig)
    buf.seek(0)
    return base64.b64encode(buf.read()).decode("ascii")


def _equity_chart(result: BacktestResult) -> str:
    times = [t for t, _ in result.equity_curve]
    equity = [e for _, e in result.equity_curve]
    fig, ax = plt.subplots(figsize=(10, 4))
    ax.plot(times, equity, color="#2563eb", linewidth=1.5)
    ax.set_title(f"Equity Curve - {result.symbol} ({result.timeframe})")
    ax.set_ylabel("USDT")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    return _fig_to_base64(fig)


def _drawdown_chart(result: BacktestResult) -> str:
    equity = np.array([e for _, e in result.equity_curve], dtype=float)
    times = [t for t, _ in result.equity_curve]
    peak = np.maximum.accumulate(equity)
    dd = (peak - equity) / peak * 100
    fig, ax = plt.subplots(figsize=(10, 3))
    ax.fill_between(times, dd, color="#dc2626", alpha=0.4)
    ax.set_title("Drawdown %")
    ax.set_ylabel("%")
    ax.grid(True, alpha=0.3)
    fig.autofmt_xdate()
    return _fig_to_base64(fig)


def generate_html_report(result: BacktestResult, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)

    equity_b64 = _equity_chart(result)
    dd_b64 = _drawdown_chart(result)
    m = result.metrics
    gate_status = "PASSED" if result.passed_gate else "FAILED"
    gate_color = "#16a34a" if result.passed_gate else "#dc2626"
    reasons = "".join(f"<li>{r}</li>" for r in result.gate_reasons) or "<li>All gates passed</li>"

    rows = ""
    for t in result.trades[-20:]:
        rows += (
            f"<tr><td>{t.entry_time}</td><td>{t.exit_time}</td>"
            f"<td>{t.pnl_usdt:.2f}</td><td>{t.pnl_pct:.2f}%</td><td>{t.bars_held}</td></tr>"
        )

    cards = [
        ("Total Return", f"{m.get('total_return_pct', 0):.2f}%"),
        ("Sharpe", f"{m.get('sharpe_ratio', 0):.2f}"),
        ("Max DD", f"{m.get('max_drawdown_pct', 0):.2f}%"),
        ("Win Rate", f"{m.get('win_rate_pct', 0):.1f}%"),
        ("Profit Factor", f"{m.get('profit_factor', 0):.2f}"),
        ("Trades", str(int(m.get("trade_count", 0)))),
    ]
    metrics_html = "\n".join(
        f'<div class="metric">{label}<span>{val}</span></div>' for label, val in cards
    )

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>PulsarAI Backtest - {result.symbol}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }}
  h1, h2 {{ color: #f8fafc; }}
  .gate {{ font-size: 1.2rem; font-weight: bold; color: {gate_color}; }}
  table {{ border-collapse: collapse; width: 100%; margin-top: 1rem; }}
  th, td {{ border: 1px solid #334155; padding: 0.5rem; text-align: left; }}
  th {{ background: #1e293b; }}
  img {{ max-width: 100%; margin: 1rem 0; border-radius: 8px; }}
  .metrics {{ display: grid; grid-template-columns: repeat(auto-fill, minmax(180px, 1fr)); gap: 1rem; }}
  .metric {{ background: #1e293b; padding: 1rem; border-radius: 8px; }}
  .metric span {{ display: block; font-size: 1.4rem; font-weight: 600; }}
</style></head><body>
<h1>PulsarAI Backtest Report</h1>
<p>{result.symbol} | {result.timeframe} | {result.start_time} to {result.end_time}</p>
<p class="gate">Gate: {gate_status}</p>
<ul>{reasons}</ul>
<div class="metrics">{metrics_html}</div>
<h2>Equity</h2>
<img src="data:image/png;base64,{equity_b64}" alt="equity"/>
<h2>Drawdown</h2>
<img src="data:image/png;base64,{dd_b64}" alt="drawdown"/>
<h2>Recent Trades (last 20)</h2>
<table><tr><th>Entry</th><th>Exit</th><th>PnL USDT</th><th>PnL %</th><th>Bars</th></tr>{rows}</table>
</body></html>"""

    path.write_text(html, encoding="utf-8")
    return path


def generate_walk_forward_html(report: WalkForwardReport, output_path: str | Path) -> Path:
    path = Path(output_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    status = "PASSED" if report.passed else "FAILED"
    color = "#16a34a" if report.passed else "#dc2626"
    agg = report.aggregate_metrics
    period_rows = ""
    for p in report.periods:
        pm = p.result.metrics
        period_rows += (
            f"<tr><td>{p.period_index}</td>"
            f"<td>{p.test_start.date()} - {p.test_end.date()}</td>"
            f"<td>{pm.get('total_return_pct', 0):.2f}%</td>"
            f"<td>{pm.get('sharpe_ratio', 0):.2f}</td>"
            f"<td>{'PASS' if p.result.passed_gate else 'FAIL'}</td></tr>"
        )
    reasons = "".join(f"<li>{r}</li>" for r in report.failure_reasons) or "<li>All checks passed</li>"

    html = f"""<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Walk-Forward - {report.symbol}</title>
<style>
  body {{ font-family: system-ui, sans-serif; margin: 2rem; background: #0f172a; color: #e2e8f0; }}
  .gate {{ color: {color}; font-weight: bold; font-size: 1.2rem; }}
  table {{ border-collapse: collapse; width: 100%; }}
  th, td {{ border: 1px solid #334155; padding: 0.5rem; }}
  th {{ background: #1e293b; }}
</style></head><body>
<h1>Walk-Forward Report - {report.symbol}</h1>
<p class="gate">{status}</p>
<ul>{reasons}</ul>
<p>Periods: {int(agg.get('periods', 0))} | Mean Sharpe: {agg.get('mean_sharpe', 0):.2f} |
   Worst DD: {agg.get('worst_drawdown_pct', 0):.2f}%</p>
<table>
<tr><th>#</th><th>Test window</th><th>Return</th><th>Sharpe</th><th>Gate</th></tr>
{period_rows}
</table>
</body></html>"""
    path.write_text(html, encoding="utf-8")
    return path
