"""European Black–Scholes–Merton prices, explicit Greek units, and IV inversion.

Premiums are per underlying unit. Multiply by the contract multiplier for cash.
Vega is dollars per 1 percentage-point IV change; theta is dollars per calendar
day; rho is dollars per 1 percentage-point rate change. Delta and gamma hold IV
fixed. Expiry and deterministic zero-volatility branches are deliberate limits.
"""

from dataclasses import dataclass
from math import erf, exp, isfinite, log, pi, sqrt


@dataclass(frozen=True, slots=True)
class Greeks:
    price: float
    delta: float
    gamma: float
    vega: float
    theta: float
    rho: float


def cdf(x: float) -> float:
    return 0.5 * (1.0 + erf(x / sqrt(2.0)))


def price_greeks(spot: float, strike: float, years: float, vol: float,
                 kind: str = "C", rate: float = 0.04,
                 dividend: float = 0.0) -> Greeks:
    if kind not in ("C", "P"):
        raise ValueError("kind must be C or P")
    if not all(isfinite(x) for x in (spot, strike, years, vol, rate, dividend)):
        raise ValueError("pricing inputs must be finite")
    if spot <= 0 or strike <= 0 or years < 0 or vol < 0:
        raise ValueError("spot/strike must be positive; time/vol nonnegative")
    sign = 1 if kind == "C" else -1
    if years == 0:
        intrinsic = max(sign * (spot - strike), 0.0)
        delta = sign if sign * (spot - strike) > 0 else (sign * 0.5 if spot == strike else 0.0)
        return Greeks(intrinsic, delta, 0.0, 0.0, 0.0, 0.0)
    dq, dr = exp(-dividend * years), exp(-rate * years)
    if vol == 0:
        difference = spot * dq - strike * dr
        weight = 1.0 if sign * difference > 0 else (0.5 if difference == 0 else 0.0)
        theta = sign * (dividend * spot * dq - rate * strike * dr) * weight / 365.0
        return Greeks(max(sign * difference, 0.0), sign * dq * weight, 0.0, 0.0,
                      theta, sign * strike * years * dr * weight / 100.0)
    root = sqrt(years)
    d1 = (log(spot / strike) + (rate - dividend + vol * vol / 2) * years) / (vol * root)
    d2 = d1 - vol * root
    density = exp(-0.5 * d1 * d1) / sqrt(2 * pi)
    nd1, nd2 = cdf(sign * d1), cdf(sign * d2)
    premium = sign * (spot * dq * nd1 - strike * dr * nd2)
    delta = sign * dq * nd1
    gamma = dq * density / (spot * vol * root)
    vega = spot * dq * density * root / 100.0
    theta = (-spot * dq * density * vol / (2 * root)
             - sign * rate * strike * dr * nd2
             + sign * dividend * spot * dq * nd1) / 365.0
    rho = sign * strike * years * dr * nd2 / 100.0
    return Greeks(max(premium, 0.0), delta, gamma, vega, theta, rho)


def implied_vol(premium: float, spot: float, strike: float, years: float,
                kind: str = "C", rate: float = 0.04, dividend: float = 0.0,
                tolerance: float = 1e-9) -> float:
    """Bracketed bisection; never returns an IV for an impossible premium.

    At the deterministic lower bound returns zero. At the upper no-arbitrage
    bound no finite IV exists. The search expands up to vol=32 before rejecting.
    """
    base = price_greeks(spot, strike, years, 0.0, kind, rate, dividend).price
    if years <= 0 or not isfinite(premium) or tolerance <= 0 or not isfinite(tolerance):
        raise ValueError("IV needs positive time, finite premium, and positive tolerance")
    upper = spot * exp(-dividend * years) if kind == "C" else strike * exp(-rate * years)
    if premium < base - tolerance or premium >= upper:
        raise ValueError("premium outside finite-IV no-arbitrage bounds")
    if abs(premium - base) <= tolerance:
        return 0.0
    low, high = 0.0, 1.0
    while price_greeks(spot, strike, years, high, kind, rate, dividend).price < premium and high < 32:
        high *= 2
    if price_greeks(spot, strike, years, high, kind, rate, dividend).price < premium:
        raise ValueError("premium requires IV outside the supported bracket")
    for _ in range(150):
        middle = (low + high) / 2
        value = price_greeks(spot, strike, years, middle, kind, rate, dividend).price
        if abs(value - premium) <= tolerance:
            return middle
        if value < premium:
            low = middle
        else:
            high = middle
    return (low + high) / 2
