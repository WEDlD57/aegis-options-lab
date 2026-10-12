"""Integer-time discrete-event exchange and options market-making experiment.

Venue truth and delayed trader observations are separate. Strategy decisions,
risk checks, and hedges use ONLY delivered observations. True venue marks are
used for execution, post-run markouts, and evaluation. Common exogenous tapes
make policy comparisons reproducible, without asserting real-market validity.
"""

from dataclasses import asdict, dataclass
from hashlib import sha256
from heapq import heappop, heappush
import json
from math import ceil, floor, fsum
from typing import Any

from .book import Fill, Order, OrderBook
from .market import Flow, Frame, Observation, instruments, tape_hash
from .portfolio import Portfolio, stress_grid
from .risk import Limits, RiskGate


@dataclass(frozen=True, slots=True)
class Policy:
    name: str
    label: str
    inventory_skew: bool = True
    hedge: bool = True
    order_latency_ms: int = 80
    feed_latency_ms: int = 60
    half_spread: float = 0.06
    hedge_threshold: float = 65.0


POLICIES = {
    "aegis": Policy("aegis", "AEGIS"),
    "unhedged": Policy("unhedged", "No hedge", hedge=False),
    "symmetric": Policy("symmetric", "Symmetric", inventory_skew=False, hedge=False),
    "delayed": Policy("delayed", "Delayed", order_latency_ms=1600, feed_latency_ms=300),
}


def canonical_hash(value: Any) -> str:
    return sha256(json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False).encode()).hexdigest()


class Simulator:
    def __init__(self, tape: tuple[Frame, ...], policy: Policy | None = None,
                 limits: Limits | None = None, sample_every: int = 5):
        if not tape or sample_every < 1:
            raise ValueError("nonempty tape and positive sampling interval required")
        if any(frame.ms != i * 1000 for i, frame in enumerate(tape)):
            raise ValueError("tape must contain contiguous one-second frames starting at zero")
        self.tape = tape
        self.policy = policy or POLICIES["aegis"]
        if self.policy.order_latency_ms < 0 or self.policy.feed_latency_ms < 0:
            raise ValueError("latencies must be nonnegative")
        self.sample_every = sample_every
        self.contracts = {inst.id: inst for inst in instruments()}
        self.books = {key: OrderBook(key) for key in self.contracts}
        self.portfolio = Portfolio()
        self.risk = RiskGate(limits)
        self.now = 0
        self.world = tape[0]
        self.marks = {key: inst.mark(self.world) for key, inst in self.contracts.items()}
        self.observed: Observation | None = None
        self.observed_marks = self.marks
        self.cancel_pending: set[str] = set()
        self.pending_hedge = 0
        self.running = True
        self._events: list[tuple[int, int, str, Any]] = []
        self._event_sequence = 0
        self._order_sequence = 0
        self.audit: list[dict[str, Any]] = []
        self.trades: list[dict[str, Any]] = []
        self.snapshots: list[dict[str, Any]] = []
        self.counts = {"processed_events": 0, "quotes_sent": 0, "quotes_accepted": 0,
                       "rejects": 0, "cancels": 0, "cancel_misses": 0, "option_fills": 0,
                       "contracts_filled": 0, "hedges": 0}
        self.peak_delta = self.peak_gross = self.high_water = self.max_drawdown = 0.0
        self._has_run = False

    def _schedule(self, ms: int, kind: str, payload: Any = None) -> None:
        if ms < self.now:
            raise ValueError("cannot schedule in the past")
        self._event_sequence += 1
        heappush(self._events, (ms, self._event_sequence, kind, payload))

    def _id(self, prefix: str) -> str:
        self._order_sequence += 1
        return f"{prefix}-{self._order_sequence:08d}"

    def _log(self, kind: str, **detail: Any) -> None:
        self.audit.append({"seq": len(self.audit) + 1, "ms": self.now, "kind": kind, **detail})

    def _peaks(self) -> None:
        exposure = self.portfolio.exposures(self.marks, self.contracts)
        pnl = self.portfolio.value(self.world.spot, self.marks, self.contracts) - self.portfolio.initial_cents / 100
        self.peak_delta = max(self.peak_delta, abs(exposure["delta"]))
        self.peak_gross = max(self.peak_gross, sum(abs(q) for q in self.portfolio.positions.values()))
        self.high_water = max(self.high_water, pnl)
        self.max_drawdown = max(self.max_drawdown, self.high_water - pnl)

    def _account(self, fills: list[Fill], source: str) -> None:
        for fill in fills:
            if fill.maker_owner != "AEGIS":
                continue
            inst = self.contracts[fill.instrument]
            order = self.risk.holds[fill.maker_id]
            fair = self.marks[fill.instrument].price
            self.portfolio.option_fill(inst, fill.maker_side, fill.ticks, fill.quantity, fair)
            self.counts["option_fills"] += 1
            self.counts["contracts_filled"] += fill.quantity
            trade = {"ms": self.now, "instrument": fill.instrument,
                     "side": "BUY" if fill.maker_side == 1 else "SELL", "sign": fill.maker_side,
                     "qty": fill.quantity, "price": fill.ticks / 100, "fair": round(fair, 8),
                     "fee": 0.65 * fill.quantity, "source": source,
                     "quote_age_ms": self.now - order.observed_ms, "order_id": fill.maker_id}
            self.trades.append(trade)
            self._log("FILL", **{k: v for k, v in trade.items() if k != "ms"})
            if not order.remaining:
                self.risk.release(order.id)
            self._peaks()

    def _market(self, frame: Frame) -> None:
        old_marks, old_spot = self.marks, self.world.spot
        self.world = frame
        self.marks = {key: inst.mark(frame) for key, inst in self.contracts.items()}
        for key, quantity in self.portfolio.positions.items():
            self.portfolio.option_revaluation += quantity * self.contracts[key].multiplier * (self.marks[key].price - old_marks[key].price)
        self.portfolio.underlying_revaluation += self.portfolio.shares * (frame.spot - old_spot)
        self._peaks()
        if frame.regime != self.tape[max(frame.ms // 1000 - 1, 0)].regime or frame.ms == 0:
            self._log("REGIME", regime=frame.regime, spot=round(frame.spot, 4), iv=round(frame.iv, 6))
        # Rival cancels and replaces at venue time. If a fresh aggressive limit
        # crosses a stale AEGIS quote, it must trade; books never stay crossed.
        for key, book in self.books.items():
            book.remove_owner("RIVAL")
            fair = self.marks[key].price
            for level, quantity in enumerate((3, 5, 8)):
                for side in (1, -1):
                    offset = frame.rival_half_spread + 0.04 * level
                    raw = (fair - side * offset) * 100
                    ticks = floor(raw) if side == 1 else ceil(raw)
                    if ticks <= 0:
                        continue
                    order = Order(self._id("R"), key, "RIVAL", side, ticks, quantity, self.now, frame.ms)
                    fills, _ = book.submit(order)
                    self._account(fills, "RIVAL_REPRICE")

    def _observed_pnl(self) -> float:
        if self.observed is None:
            return 0.0
        return self.portfolio.value(self.observed.spot, self.observed_marks, self.contracts) - self.portfolio.initial_cents / 100

    def _check_risk(self) -> None:
        if not self.running or self.observed is None or self.risk.reason:
            return
        reason = self.risk.monitor(self.now, self.observed.ms, self._observed_pnl())
        exposure = self.portfolio.exposures(self.observed_marks, self.contracts)
        if not reason and abs(exposure["delta"]) > self.risk.limits.delta_shares:
            reason = "DELTA_BREACH"
        if not reason and abs(exposure["vega"]) > self.risk.limits.vega_per_point:
            reason = "VEGA_BREACH"
        if reason and self.risk.trip(reason, self.now):
            self._log("KILL_SWITCH", reason=reason, observed_pnl=round(self._observed_pnl(), 6),
                      data_age_ms=self.now - self.observed.ms, reserved_orders=len(self.risk.holds))
            self._cancel_all()

    def _cancel_all(self) -> None:
        for key in list(self.risk.holds):
            if key not in self.cancel_pending:
                self.cancel_pending.add(key)
                self._schedule(self.now + self.policy.order_latency_ms, "cancel", key)

    def _observe(self, frame: Observation) -> None:
        if self.observed and frame.ms <= self.observed.ms:
            return
        self.observed = frame
        self.observed_marks = {key: inst.mark(frame) for key, inst in self.contracts.items()}
        self._check_risk()
        if not self.running or self.risk.reason:
            return
        self._cancel_all()
        exposure = self.portfolio.exposures(self.observed_marks, self.contracts)
        for key, inst in self.contracts.items():
            mark = self.observed_marks[key]
            quantity = self.portfolio.positions.get(key, 0)
            center = mark.price
            half = self.policy.half_spread * (1 + 2 * max(frame.iv - 0.24, 0))
            if self.policy.inventory_skew:
                center -= 0.015 * quantity + 0.00025 * exposure["delta"] * mark.delta
                half += 0.003 * abs(quantity) + 0.000015 * abs(exposure["delta"])
            for side in (1, -1):
                raw = 100 * (center - side * half)
                ticks = floor(raw) if side == 1 else ceil(raw)
                if ticks <= 0:
                    continue
                order = Order(self._id("Q"), key, "AEGIS", side, ticks, 1, self.now, frame.ms)
                reason = self.risk.reserve(order, self.portfolio, self.observed_marks,
                                           self.contracts, self.pending_hedge)
                if reason:
                    self.counts["rejects"] += 1
                    self._log("REJECT", stage="PRE_TRADE", reason=reason, instrument=key, order_id=order.id)
                else:
                    self.counts["quotes_sent"] += 1
                    self._log("QUOTE_SENT", instrument=key, order_id=order.id, side=side,
                              ticks=ticks, observed_ms=frame.ms)
                    self._schedule(self.now + self.policy.order_latency_ms, "quote", order)
        if self.policy.hedge and not self.pending_hedge and abs(exposure["delta"]) >= self.policy.hedge_threshold:
            limit = self.risk.limits.max_hedge_shares
            quantity = max(-limit, min(limit, -round(exposure["delta"])))
            self.pending_hedge = quantity
            self._log("HEDGE_SENT", qty=quantity, observed_ms=frame.ms)
            self._schedule(self.now + self.policy.order_latency_ms, "hedge", quantity)

    def _quote(self, order: Order) -> None:
        self._check_risk()
        reason = "SESSION_END" if not self.running else self.risk.check(
            order, self.portfolio, self.observed_marks, self.contracts, self.pending_hedge)
        if not reason:
            fills, reason = self.books[order.instrument].submit(order, post_only=True)
            assert not fills, "post-only order cannot take liquidity"
        if reason:
            self.counts["rejects"] += 1
            self.risk.release(order.id)
            self._log("REJECT", stage="ARRIVAL", reason=reason, instrument=order.instrument, order_id=order.id)
        else:
            self.counts["quotes_accepted"] += 1
            self._log("QUOTE_ACCEPTED", instrument=order.instrument, order_id=order.id)

    def _cancel(self, order_id: str) -> None:
        self.cancel_pending.discard(order_id)
        order = self.risk.holds.get(order_id)
        if order is None:
            self.counts["cancel_misses"] += 1
            self._log("CANCEL_MISS", order_id=order_id)
            return
        cancelled = self.books[order.instrument].cancel(order_id)
        # A pending order has a quote-arrival time earlier than this cancel's
        # arrival (both use the same link latency). It cannot reappear afterward.
        self.risk.release(order_id)
        if cancelled:
            self.counts["cancels"] += 1
            self._log("CANCELLED", order_id=order_id)
        else:
            self.counts["cancel_misses"] += 1
            self._log("CANCEL_MISS", order_id=order_id)

    def _flow(self, flow: Flow) -> None:
        key = tuple(self.contracts)[flow.instrument_index]
        fair = self.marks[key].price
        raw = 100 * (fair + flow.side * flow.aggression)
        ticks = floor(raw) if flow.side == 1 else ceil(raw)
        if ticks <= 0:
            return
        order = Order(self._id("T"), key, "TAKER", flow.side, ticks, flow.quantity, self.now, self.world.ms)
        fills, _ = self.books[key].submit(order, immediate_or_cancel=True)
        self._account(fills, "EXOGENOUS_FLOW")

    def _hedge(self, quantity: int) -> None:
        self.pending_hedge = 0
        self._check_risk()
        delta = self.portfolio.exposures(self.observed_marks, self.contracts)["delta"]
        reason = "SESSION_END" if not self.running else ("CIRCUIT_OPEN" if self.risk.reason else None)
        if not reason and abs(delta + quantity) >= abs(delta):
            reason = "HEDGE_NO_LONGER_REDUCES_DELTA"
        if reason:
            self._log("HEDGE_REJECT", reason=reason, qty=quantity)
            return
        sign = 1 if quantity > 0 else -1
        execution = round(100 * (self.world.spot + sign * (0.01 + 0.00005 * abs(quantity))))
        self.portfolio.hedge_fill(quantity, execution, self.world.spot)
        self.counts["hedges"] += 1
        trade = {"ms": self.now, "instrument": "SYN", "side": "BUY" if sign == 1 else "SELL",
                 "sign": sign, "qty": abs(quantity), "price": execution / 100,
                 "fair": round(self.world.spot, 8), "fee": abs(quantity) / 100,
                 "source": "DELTA_HEDGE", "quote_age_ms": self.now - self.observed.ms,
                 "order_id": self._id("H")}
        self.trades.append(trade)
        self._log("HEDGE_FILL", **{k: v for k, v in trade.items() if k != "ms"})
        self._peaks()

    def _snapshot(self) -> None:
        exposure = self.portfolio.exposures(self.marks, self.contracts)
        risk_exposure = self.portfolio.exposures(self.observed_marks, self.contracts)
        pnl = self.portfolio.value(self.world.spot, self.marks, self.contracts) - self.portfolio.initial_cents / 100
        chain = []
        for key, inst in self.contracts.items():
            mark = self.marks[key]
            chain.append({"id": key, "price": round(mark.price, 6), "delta": round(mark.delta, 6),
                          "gamma": round(mark.gamma, 6), "vega": round(mark.vega, 6),
                          "position": self.portfolio.positions.get(key, 0)})
        live_ids = {key for book in self.books.values() for key, order in book.orders.items() if order.owner == "AEGIS"}
        state = self.risk.reason or ("CLOSED" if not self.running else ("ACTIVE" if self.observed else "WARMUP"))
        self.snapshots.append({
            "ms": self.now, "market_ms": self.world.ms, "spot": round(self.world.spot, 8),
            "iv": round(self.world.iv, 8), "regime": self.world.regime, "state": state,
            "observed_ms": self.observed.ms if self.observed else None,
            "observed_spot": round(self.observed.spot, 8) if self.observed else None,
            "data_age_ms": self.now - self.observed.ms if self.observed else 0,
            "pnl": round(pnl, 6), "observed_pnl": round(self._observed_pnl(), 6),
            "cash": self.portfolio.cash_cents / 100, "fees": self.portfolio.fees_cents / 100,
            "shares": self.portfolio.shares, "exposure": {k: round(v, 6) for k, v in exposure.items()},
            "risk_exposure": {k: round(v, 6) for k, v in risk_exposure.items()},
            "gross": sum(abs(q) for q in self.portfolio.positions.values()),
            "live_orders": len(live_ids), "inflight_orders": len(self.risk.holds) - len(live_ids),
            "chain": chain, "books": {key: book.depth(3) for key, book in self.books.items()},
            "attribution": {k: round(v, 6) for k, v in self.portfolio.attribution().items()},
        })

    def _session_end(self) -> None:
        self.running = False
        self._log("SESSION_END", message="Stop submissions; drain delayed cancels. Inventory remains marked.")
        self._cancel_all()

    def run(self) -> dict[str, Any]:
        if self._has_run:
            raise RuntimeError("simulator instances are single-use")
        self._has_run = True
        self._snapshot()
        for index, frame in enumerate(self.tape):
            self._schedule(frame.ms, "market", frame)
            if frame.feed_available:
                self._schedule(frame.ms + self.policy.feed_latency_ms, "observe",
                               Observation(frame.ms, frame.spot, frame.iv, frame.regime))
            for flow in frame.flows:
                self._schedule(frame.ms + flow.offset_ms, "flow", flow)
            self._schedule(frame.ms + 700, "risk")
            if (index + 1) % self.sample_every == 0 or index == len(self.tape) - 1:
                self._schedule(frame.ms + 900, "snapshot")
        self._schedule(len(self.tape) * 1000, "end")
        handlers = {"market": self._market, "observe": self._observe, "quote": self._quote,
                    "cancel": self._cancel, "flow": self._flow, "hedge": self._hedge}
        while self._events:
            self.now, _, kind, payload = heappop(self._events)
            self.counts["processed_events"] += 1
            if kind in handlers:
                handlers[kind](payload)
            elif kind == "risk":
                self._check_risk()
            elif kind == "snapshot":
                self._snapshot()
            elif kind == "end":
                self._session_end()
        self._snapshot()
        markout_sum = markout_quantity = 0.0
        for trade in self.trades:
            if trade["instrument"] == "SYN":
                continue
            future_index = trade["ms"] // 1000 + 5
            if future_index < len(self.tape):
                future = self.contracts[trade["instrument"]].mark(self.tape[future_index]).price
                markout = trade["sign"] * (future - trade["price"]) * 100
                trade["markout_5s_per_contract"] = round(markout, 6)
                markout_sum += markout * trade["qty"]
                markout_quantity += trade["qty"]
            else:
                trade["markout_5s_per_contract"] = None
        final = self.snapshots[-1]
        attribution = self.portfolio.attribution()
        raw_pnl = self.portfolio.value(self.world.spot, self.marks, self.contracts) - self.portfolio.initial_cents / 100
        reconciliation = raw_pnl - fsum(attribution.values())
        if abs(reconciliation) > 1e-6:
            raise AssertionError(f"cash/mark attribution mismatch: {reconciliation}")
        if self.risk.holds or any(order.owner == "AEGIS" for book in self.books.values() for order in book.orders.values()):
            raise AssertionError("session drain left outstanding AEGIS orders")
        summary = {**self.counts, "pnl": final["pnl"], "max_drawdown": round(self.max_drawdown, 6),
                   "max_abs_delta": round(self.peak_delta, 6), "max_gross_contracts": int(self.peak_gross),
                   "fees": self.portfolio.fees_cents / 100, "final_gross": final["gross"],
                   "final_shares": self.portfolio.shares, "circuit": self.risk.reason or "NONE",
                   "circuit_ms": self.risk.trigger_ms,
                   "mean_5s_markout_per_contract": round(markout_sum / markout_quantity, 6) if markout_quantity else None,
                   "markout_contracts": int(markout_quantity),
                   "reconciliation_error": reconciliation,
                   "estimated_exit_cost": round(final["gross"] * (self.world.rival_half_spread * 100 + 0.65)
                                                + abs(self.portfolio.shares) * 0.01, 2),
                   "attribution": {k: round(v, 6) for k, v in attribution.items()}}
        result = {"policy": asdict(self.policy), "limits": asdict(self.risk.limits),
                  "tape_hash": tape_hash(self.tape), "summary": summary,
                  "snapshots": self.snapshots, "trades": self.trades,
                  "audit": self.audit, "final_stress": stress_grid(self.portfolio, self.world, self.contracts, self.marks)}
        result["result_hash"] = canonical_hash(result)
        return result
