"""Conservative reservations include live AND in-flight option orders.

Limits are checked in the trader's observed-data domain, not with future/venue
marks. They bound single-snapshot fill exposure, not subsequent market moves.
Both sides reserve independently (no assumed cancellation or fill netting).
"""

from dataclasses import dataclass

from .book import Order
from .market import Instrument
from .portfolio import Portfolio
from .pricing import Greeks


@dataclass(frozen=True, slots=True)
class Limits:
    per_instrument: int = 12
    gross_contracts: int = 100
    delta_shares: float = 6000.0
    vega_per_point: float = 1000.0
    drawdown_dollars: float = 500.0
    stale_ms: int = 2500
    max_hedge_shares: int = 500


class RiskGate:
    def __init__(self, limits: Limits | None = None):
        self.limits = limits or Limits()
        self.holds: dict[str, Order] = {}
        self.reason: str | None = None
        self.trigger_ms: int | None = None
        self.high_water = 0.0

    def reserve(self, order: Order, portfolio: Portfolio, marks: dict[str, Greeks],
                contracts: dict[str, Instrument], pending_hedge: int = 0) -> str | None:
        if order.id in self.holds:
            raise ValueError("duplicate risk reservation")
        reason = self.check(order, portfolio, marks, contracts, pending_hedge)
        if not reason:
            self.holds[order.id] = order
        return reason

    def check(self, order: Order, portfolio: Portfolio, marks: dict[str, Greeks],
              contracts: dict[str, Instrument], pending_hedge: int = 0) -> str | None:
        if self.reason:
            return "CIRCUIT_OPEN"
        pending = [x for key, x in self.holds.items() if key != order.id] + [order]
        quantity_bound = abs(portfolio.positions.get(order.instrument, 0)) + sum(
            candidate.remaining for candidate in pending if candidate.instrument == order.instrument)
        if quantity_bound > self.limits.per_instrument:
            return "POSITION_LIMIT"
        gross = sum(abs(q) for q in portfolio.positions.values()) + sum(x.remaining for x in pending)
        if gross > self.limits.gross_contracts:
            return "GROSS_LIMIT"
        exposure = portfolio.exposures(marks, contracts)
        delta_bound = abs(exposure["delta"]) + abs(pending_hedge)
        vega_bound = abs(exposure["vega"])
        for candidate in pending:
            factor = candidate.remaining * contracts[candidate.instrument].multiplier
            delta_bound += factor * abs(marks[candidate.instrument].delta)
            vega_bound += factor * abs(marks[candidate.instrument].vega)
        if delta_bound > self.limits.delta_shares:
            return "DELTA_LIMIT"
        if vega_bound > self.limits.vega_per_point:
            return "VEGA_LIMIT"
        return None

    def release(self, order_id: str) -> None:
        self.holds.pop(order_id, None)

    def trip(self, reason: str, ms: int) -> bool:
        if self.reason:
            return False
        self.reason, self.trigger_ms = reason, ms
        return True

    def monitor(self, ms: int, observed_ms: int | None, observed_pnl: float) -> str | None:
        if self.reason or observed_ms is None:
            return None
        self.high_water = max(self.high_water, observed_pnl)
        if ms - observed_ms > self.limits.stale_ms:
            return "STALE_FEED"
        if self.high_water - observed_pnl >= self.limits.drawdown_dollars:
            return "DRAWDOWN"
        return None
