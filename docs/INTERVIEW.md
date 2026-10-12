# Understand and present AEGIS

Use the replay to demonstrate engineering choices and failure behavior. The strongest presentation explains one decision, one invariant, and one limitation in concrete terms.

## A two-minute demonstration

**0:00 — Show the system.** Open `artifacts/report.html`. Explain that this is a synthetic options exchange with delayed trader observations, price/time matching, and a cash ledger. The 12 contracts and four policies are experiments you can reproduce.

**0:20 — Establish the comparison.** Choose Volatility shock. Drag the scrubber to a frame before the halfway mark, select an at-the-money contract, and inspect its bids, asks, and own outlined orders. Policies receive the same external tape and use the same limits.

**0:45 — Reveal the race.** Jump to the event. The exchange sees the price/IV change before the trader's delayed feed. A rival reprice or customer IOC can execute against stale quotes. An order cancellation is a message that arrives later.

**1:10 — Explain the control.** Filter the audit to Risk. The drawdown latch prevents new submissions and schedules cancels. The $500 threshold is not a guaranteed loss cap. Remaining option and hedge positions continue to change in value.

**1:35 — Demonstrate accountability.** Show the P&L components and stress heatmap. Export trades. Explain that cash is integer cents, the component sum is checked against the ledger, and future-mark diagnostics never feed back into quote decisions.

**1:55 — State a concrete next extension.** Execution-report latency, multi-seed policy distributions, or a calibrated historical data adapter would address a real limitation. Do not claim that these are already implemented.

## Concepts to be able to explain

**What is a market maker?** It posts bids and asks, potentially earning execution edge while accumulating inventory. A fill can be adverse: the option's fair value may have moved against the stale quote.

**Why use an event queue?** Market updates, observations, quote arrivals, cancels, and fills do not occur in one synchronous loop. Ordering them on an integer clock makes the races visible and reproducible. A sequence number resolves equal-time events.

**Why does price/time priority matter?** Better-priced orders execute first; at equal prices, earlier arrivals execute first. A strategy can have an attractive quote and still receive no fill because other orders are ahead. Partial fills preserve the remaining quantity's priority.

**Why reserve in-flight orders?** A quote may arrive and fill before its cancel. Releasing exposure when a cancel is merely requested would let the strategy send more orders than its limit permits. Both sides also cannot be assumed to fill in a helpful offsetting sequence.

**What does delta hedging do?** It offsets the first-order sensitivity of the portfolio to spot changes using underlying shares. It incurs fees and slippage, and it does not eliminate gamma, vega, jump risk, or latency risk. A hedge can become inappropriate before arrival.

**How do you know there is no future-data dependency in this experiment?** The strategy's observation object excludes customer-flow schedules. Tests alter future market frames and compare all earlier audit entries and snapshots. Markouts are calculated only after the run.

**Why reconcile P&L?** A chart can look plausible while cash accounting is wrong. Every premium transfer and fee changes integer-cent cash. Valuation plus cash must independently agree with execution edge, revaluation, hedge slippage, and fees within the chosen tolerance.

**Why can Symmetric earn more in the shock run?** It can carry different inventory into a particular shock and benefit from that realization. One profitable path does not establish lower risk or policy superiority. Compare exposure, drawdown, open inventory, and multiple seeds before making broader claims.

**What does the benchmark demonstrate?** The matching primitive's local computational cost under one exact workload. It excludes a network, serialization, venue connectivity, realistic book sizes, and production reliability. Tail samples depend on hardware and process scheduling.

## Read these first

1. `market.Observation` and `Simulator._observe`: understand exactly what the strategy knows.
2. `OrderBook.submit`: trace an incoming order through price priority, partial fill, and IOC handling.
3. `RiskGate.check` and `Simulator._cancel`: explain when exposure is reserved and released.
4. `Portfolio.option_fill`, `hedge_fill`, and `attribution`: work through one buy, one sell, and their fees on paper.
5. `test_future_changes_cannot_change_earlier_decisions` and `test_late_orders_are_rejected_after_kill`: explain the failure each test prevents.

## Resume wording

After you can run and explain the system, a factual project entry is:

> **AEGIS — Options Market Microstructure Lab** · Python, JavaScript  
> Developed an AI-assisted, deterministic options exchange simulator with price/time matching, delayed order execution, inventory-aware quoting, delta hedging, and pre-trade exposure reservations. Built an offline interactive replay and 33 automated tests covering pricing, matching invariants, future-data independence, and P&L reconciliation.

Describe the development honestly. Avoid claiming real trading returns, production exchange latency, professional trading experience, or features absent from the source.
