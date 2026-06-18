import json
from backtest.backtest import run_backtest

result = run_backtest(top_n=3, initial_capital=10_000)

print(f"Period  : {result['period']['start']} → {result['period']['end']} ({result['period']['days']} days)")
print(f"Return  : {result['metrics']['total_return_pct']:+.2f}%")
print(f"BTC B&H : {result['metrics']['benchmark_btc_return_pct']:+.2f}%")
print(f"Sharpe  : {result['metrics']['sharpe_ratio']:.3f}")
print(f"Max DD  : {result['metrics']['max_drawdown_pct']:.2f}%")
print(f"Win Rate: {result['metrics']['win_rate_pct']:.1f}%")
print()
print("Daily breakdown (last 7 days):")
for row in result["daily"][-7:]:
    print(f"  {row['date']}  {row['regime']:14s}  F&G={row['fg']:2d}  ret={row['daily_return']:+.2f}%  {row['holdings']}")
