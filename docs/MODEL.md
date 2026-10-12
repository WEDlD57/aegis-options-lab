# Model assumptions and units

This file defines how to interpret the outputs. All markets, option symbols, flow, and price paths are generated locally; the project makes no live-performance claim.

## Instruments and prices

The underlying starts near $100. The universe has strikes 95, 100, and 105, expiries of 7 and 30 calendar days, and both calls and puts. Each contract represents 100 underlying units. Option premiums are per underlying unit, with a $0.01 tick. A $1 premium therefore represents $100 per contract.

The pricing API implements European Black–Scholes–Merton with continuously compounded rates and dividend yields. Simulation marks default to a 4% annual rate and zero dividend yield. IV is a decimal fraction; 0.24 means 24%. Time is calendar years with a 365-day denominator. Expiry and zero-volatility limits have separate branches. IV inversion uses bisection within no-arbitrage bounds rather than an unstable unrestricted Newton iteration.

| Greek | Per-unit pricing API convention | Portfolio convention |
| --- | --- | --- |
| Delta | Price derivative with respect to spot | Equivalent underlying shares; includes hedge shares |
| Gamma | Delta derivative with respect to spot | Multiplied by signed contracts × 100 |
| Vega | Dollars for a 1-percentage-point IV change | Dollars per IV point across signed inventory |
| Theta | Dollars per calendar day | Dollars per day across signed inventory |
| Rho | Dollars for a 1-percentage-point rate change | Pricing API only; not used in the risk gate |

The heatmap fully reprices the current inventory at spot changes from −6% to +6% and IV changes from −15 to +15 percentage points. IV is floored at 1%. Time and cash stay fixed, with no hypothetical fees or liquidation. It is a scenario matrix, not a probability distribution or VaR estimate.

## Market and customer flow

A separate random stream generates spot/IV evolution and another generates five customer orders per second. AEGIS does not inspect those scheduled orders when deciding quotes. The synthetic flow intentionally provides regular opportunities to earn spread; its parameters are not estimated from real option data.

Spot evolves with Gaussian log-return increments using a trading-second scale. IV follows a simple noisy mean-reverting process. The trend scenario adds positive drift. The shock scenario applies a 4% down gap and an 18-point IV jump at the halfway frame, increases subsequent realized variability, and creates current-mark-informed customer flow at that frame. The outage suppresses observation delivery for 15 frames while venue activity continues.

The rival knows the current venue mark, cancels immediately, and refreshes three levels with fixed quantities of 3, 5, and 8 contracts. The model has one rival, one venue, no queue calibration, no endogenous spot impact, and no feedback from one policy experiment into another experiment's tape.

## Execution and costs

AEGIS option quotes are post-only, one contract per side. Customer flow is IOC. Price/time priority determines fills. Rival repricing can also execute against stale resting quotes. Order and cancel link latency is fixed by policy; jitter, packet loss, duplicate messages, and delayed fill acknowledgments are not simulated.

Option fills charge $0.65 per contract. Hedge fills charge $0.01 per share, with an execution-price offset of $0.01 plus $0.00005 per share in the request, rounded to cents. Hedge liquidity is assumed available at that price, without a separate underlying order book.

## Risk limits

Defaults are 12 contracts per instrument, 100 gross option contracts, 6,000 delta-equivalent shares, $1,000 vega per IV point, a $500 observed high-water drawdown trigger, 2,500 ms maximum feed age, and 500 shares per hedge request.

Checks reserve both sides independently, including in-flight and cancellation-pending orders. Limits constrain exposure evaluated at observed marks. A gap, changing Greeks, or delayed observation can produce larger venue exposure or losses before a control responds. The kill switch blocks submissions and schedules cancellations; it does not hedge or flatten after activation.

## Metrics

- **P&L:** cash plus marked option and underlying inventory minus $100,000 initial capital. Fees are included. Closing trades are not performed.
- **Max drawdown:** maximum venue-mark peak-to-trough drop, including market updates and fills. The trigger uses a different, delayed observed-data domain.
- **Five-second markout:** signed future model premium minus execution premium, multiplied by 100. The future mark is the one-second tape frame at `floor(fill_ms / 1000) + 5`, so the actual horizon is approximately 4–5 seconds for within-second fills. Last-session fills lacking that future frame are censored. It is a quantity-weighted post-run diagnostic, not information available to the strategy.
- **Estimated exit cost:** a rough half-spread plus option fees and $0.01 per hedge share. It excludes depth constraints, market impact, and full hedge slippage, and is not charged to P&L.
- **Benchmark latency:** time for one in-process IOC taker to match one resting order. Setup is excluded from per-operation samples but included in the separate wall-time field. It is not end-to-end exchange or broker latency.

The ordinary scenarios are intentionally favorable and short. Their simulated gains cannot be annualized or used to infer live profitability. A multi-seed, calibrated study and richer execution model would be separate extensions.
