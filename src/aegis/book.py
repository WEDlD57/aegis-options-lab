"""Small price/time-priority CLOB with integer cent ticks and partial fills.

    Heap keys provide price and arrival priority. Cancellations remove the order
    from the live index; stale heap entries are discarded lazily. Order IDs are
    unique for the life of the book. This is a simulator, not a venue protocol.
"""

from dataclasses import dataclass
from heapq import heappop, heappush


@dataclass(slots=True)
class Order:
    id: str
    instrument: str
    owner: str
    side: int
    ticks: int
    remaining: int
    sent_ms: int = 0
    observed_ms: int = 0


@dataclass(frozen=True, slots=True)
class Fill:
    maker_id: str
    taker_id: str
    maker_owner: str
    taker_owner: str
    maker_side: int
    ticks: int
    quantity: int
    instrument: str


class OrderBook:
    def __init__(self, instrument: str):
        self.instrument = instrument
        self.orders: dict[str, Order] = {}
        self._seen: set[str] = set()
        self._heaps: dict[int, list[tuple[int, int, str]]] = {1: [], -1: []}
        self._sequence = 0

    def _top(self, side: int) -> Order | None:
        heap = self._heaps[side]
        while heap and heap[0][2] not in self.orders:
            heappop(heap)
        return self.orders[heap[0][2]] if heap else None

    def best(self, side: int) -> int | None:
        top = self._top(side)
        return top.ticks if top else None

    def submit(self, order: Order, post_only: bool = False,
               immediate_or_cancel: bool = False) -> tuple[list[Fill], str | None]:
        if (order.instrument != self.instrument or order.side not in (-1, 1)
                or type(order.ticks) is not int or type(order.remaining) is not int
                or order.ticks <= 0 or order.remaining <= 0):
            raise ValueError("invalid order: use positive integer ticks/quantity and side +/-1")
        if order.id in self._seen:
            raise ValueError("duplicate order ID")
        self._seen.add(order.id)
        top = self._top(-order.side)
        crosses = top is not None and order.side * (order.ticks - top.ticks) >= 0
        if post_only and crosses:
            return [], "POST_ONLY_CROSS"
        fills: list[Fill] = []
        while order.remaining:
            top = self._top(-order.side)
            if top is None or order.side * (order.ticks - top.ticks) < 0:
                break
            # Self-match prevention cancels the incoming remainder.
            if top.owner == order.owner:
                return fills, "SELF_MATCH_PREVENTED"
            quantity = min(order.remaining, top.remaining)
            fills.append(Fill(top.id, order.id, top.owner, order.owner, top.side,
                              top.ticks, quantity, self.instrument))
            order.remaining -= quantity
            top.remaining -= quantity
            if not top.remaining:
                self.orders.pop(top.id)
        if order.remaining and not immediate_or_cancel:
            self._sequence += 1
            self.orders[order.id] = order
            heappush(self._heaps[order.side], (-order.side * order.ticks, self._sequence, order.id))
        return fills, None

    def cancel(self, order_id: str) -> Order | None:
        return self.orders.pop(order_id, None)

    def remove_owner(self, owner: str) -> None:
        for order_id in [key for key, order in self.orders.items() if order.owner == owner]:
            self.cancel(order_id)

    def depth(self, levels: int = 5) -> dict[str, list[dict[str, int]]]:
        result = {}
        for side, label in [(1, "bids"), (-1, "asks")]:
            aggregated: dict[int, dict[str, int]] = {}
            for order in self.orders.values():
                if order.side != side:
                    continue
                level = aggregated.setdefault(order.ticks, {"ticks": order.ticks, "qty": 0, "own": 0})
                level["qty"] += order.remaining
                if order.owner == "AEGIS":
                    level["own"] += order.remaining
            result[label] = [aggregated[p] for p in sorted(aggregated, reverse=side == 1)[:levels]]
        return result
