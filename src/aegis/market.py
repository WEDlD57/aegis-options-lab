"""Seeded, exogenous market/flow tape shared across strategy experiments."""

from dataclasses import asdict, dataclass
from hashlib import sha256
import json
from math import exp, sqrt
from random import Random

from .pricing import Greeks, price_greeks

SCENARIOS = ("normal", "trend", "vol_shock", "feed_outage")
YEAR_MS = 365 * 24 * 60 * 60 * 1000


@dataclass(frozen=True, slots=True)
class Instrument:
    id: str
    strike: float
    expiry_days: int
    kind: str
    multiplier: int = 100

    def years(self, timestamp_ms: int) -> float:
        return max(self.expiry_days / 365 - timestamp_ms / YEAR_MS, 0.0)

    def mark(self, frame: "Frame") -> Greeks:
        return price_greeks(frame.spot, self.strike, self.years(frame.ms), frame.iv, self.kind)


def instruments() -> tuple[Instrument, ...]:
    return tuple(Instrument(f"SYN-{days}D-{strike}{kind}", float(strike), days, kind)
                 for days in (7, 30) for strike in (95, 100, 105) for kind in ("C", "P"))


@dataclass(frozen=True, slots=True)
class Flow:
    instrument_index: int
    side: int
    quantity: int
    aggression: float
    offset_ms: int


@dataclass(frozen=True, slots=True)
class Frame:
    ms: int
    spot: float
    iv: float
    regime: str
    feed_available: bool
    rival_half_spread: float
    flows: tuple[Flow, ...]


@dataclass(frozen=True, slots=True)
class Observation:
    """Strategy-facing data deliberately excludes the scheduled customer flows."""
    ms: int
    spot: float
    iv: float
    regime: str


def make_tape(seed: int = 42, ticks: int = 600, scenario: str = "vol_shock") -> tuple[Frame, ...]:
    if scenario not in SCENARIOS or ticks < 20:
        raise ValueError(f"scenario must be one of {SCENARIOS}; ticks must be >= 20")
    world, flow_rng = Random(seed), Random(seed + 1_000_003)
    spot, iv = 100.0, 0.24
    tape: list[Frame] = []
    shock_at = ticks // 2
    outage_at = ticks // 2
    for tick in range(ticks):
        old_spot, old_iv = spot, iv
        regime = "NORMAL"
        drift = 0.000065 if scenario == "trend" else 0.0
        realized = 0.60 if scenario != "vol_shock" or tick < shock_at else 1.15
        spot *= exp(drift + realized * sqrt(1 / (252 * 23_400)) * world.gauss(0, 1))
        target = 0.42 if scenario == "vol_shock" and tick >= shock_at else 0.24
        iv = max(0.05, min(1.5, iv + 0.012 * (target - iv) + world.gauss(0, 0.00065)))
        if scenario == "vol_shock" and tick == shock_at:
            spot *= 0.96
            iv += 0.18
        if scenario == "vol_shock" and tick >= shock_at:
            regime = "VOL SHOCK"
        if scenario == "trend":
            regime = "TREND"
        unavailable = scenario == "feed_outage" and outage_at <= tick < outage_at + 15
        if unavailable:
            regime = "FEED OUTAGE"
        flows = []
        for _ in range(5):
            index = flow_rng.randrange(12)
            side = flow_rng.choice((-1, 1))
            offset = flow_rng.choice((25, 500, 650))
            if scenario == "vol_shock" and tick == shock_at:
                # Exogenous informed flow knows the current venue mark, not future frames.
                inst = instruments()[index]
                before = price_greeks(old_spot, inst.strike, inst.years(tick * 1000), old_iv, inst.kind).price
                after = price_greeks(spot, inst.strike, inst.years(tick * 1000), iv, inst.kind).price
                side, offset = (1 if after > before else -1), 25
            flows.append(Flow(index, side, flow_rng.randint(1, 5), flow_rng.uniform(0.045, 0.32), offset))
        half = 0.095 if regime not in ("VOL SHOCK", "FEED OUTAGE") else 0.18
        tape.append(Frame(tick * 1000, spot, iv, regime, not unavailable, half, tuple(flows)))
    return tuple(tape)


def tape_hash(tape: tuple[Frame, ...]) -> str:
    canonical = json.dumps([asdict(frame) for frame in tape], sort_keys=True, separators=(",", ":"), allow_nan=False)
    return sha256(canonical.encode()).hexdigest()
