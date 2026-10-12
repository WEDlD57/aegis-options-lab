"""Integer-cent cash ledger; model marks stay unrounded for valuation."""

from dataclasses import dataclass, field

from .market import Frame, Instrument
from .pricing import Greeks, price_greeks


@dataclass(slots=True)
class Portfolio:
    initial_cents: int = 10_000_000
    cash_cents: int = 10_000_000
    shares: int = 0
    positions: dict[str, int] = field(default_factory=dict)
    fees_cents: int = 0
    edge: float = 0.0
    option_revaluation: float = 0.0
    underlying_revaluation: float = 0.0
    hedge_slippage: float = 0.0

    def option_fill(self, instrument: Instrument, side: int, ticks: int,
                    quantity: int, fair: float) -> None:
        self.positions[instrument.id] = self.positions.get(instrument.id, 0) + side * quantity
        fee = 65 * quantity
        self.cash_cents -= side * ticks * instrument.multiplier * quantity + fee
        self.fees_cents += fee
        self.edge += side * (fair - ticks / 100) * quantity * instrument.multiplier

    def hedge_fill(self, quantity: int, execution_cents: int, spot: float) -> None:
        self.shares += quantity
        fee = abs(quantity)
        self.cash_cents -= quantity * execution_cents + fee
        self.fees_cents += fee
        self.hedge_slippage += quantity * (execution_cents / 100 - spot)

    def value(self, spot: float, marks: dict[str, Greeks], contracts: dict[str, Instrument]) -> float:
        return (self.cash_cents / 100 + self.shares * spot
                + sum(qty * contracts[key].multiplier * marks[key].price for key, qty in self.positions.items()))

    def exposures(self, marks: dict[str, Greeks], contracts: dict[str, Instrument]) -> dict[str, float]:
        result = {"delta": float(self.shares), "gamma": 0.0, "vega": 0.0, "theta": 0.0}
        for key, quantity in self.positions.items():
            for greek in result:
                result[greek] += quantity * contracts[key].multiplier * getattr(marks[key], greek)
        return result

    def attribution(self) -> dict[str, float]:
        return {"execution_edge": self.edge, "option_revaluation": self.option_revaluation,
                "underlying_revaluation": self.underlying_revaluation,
                "hedge_slippage": -self.hedge_slippage, "fees": -self.fees_cents / 100}


def stress_grid(portfolio: Portfolio, frame: Frame, contracts: dict[str, Instrument],
                marks: dict[str, Greeks]) -> list[list[float]]:
    """Full repricing, fixed time, flat IV shocked by absolute volatility points."""
    result = []
    for vol_change in (0.15, 0.10, 0.05, 0.0, -0.05, -0.10, -0.15):
        row = []
        for spot_change in (-0.06, -0.04, -0.02, 0.0, 0.02, 0.04, 0.06):
            spot = frame.spot * (1 + spot_change)
            pnl_change = portfolio.shares * (spot - frame.spot)
            for key, quantity in portfolio.positions.items():
                inst = contracts[key]
                value = price_greeks(spot, inst.strike, inst.years(frame.ms), max(frame.iv + vol_change, 0.01), inst.kind).price
                pnl_change += quantity * inst.multiplier * (value - marks[key].price)
            row.append(round(pnl_change, 4))
        result.append(row)
    return result
