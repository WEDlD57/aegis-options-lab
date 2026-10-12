import math
import unittest

from aegis.pricing import implied_vol, price_greeks


class PricingTests(unittest.TestCase):
    def test_known_call_value(self):
        self.assertAlmostEqual(price_greeks(100, 100, 1, .2, rate=.05).price, 10.450583572185565, places=10)

    def test_put_call_parity_with_dividends(self):
        for spot in (65, 100, 135):
            for years in (.02, .5, 2):
                call = price_greeks(spot, 100, years, .35, "C", .03, .015)
                put = price_greeks(spot, 100, years, .35, "P", .03, .015)
                expected = spot * math.exp(-.015 * years) - 100 * math.exp(-.03 * years)
                self.assertAlmostEqual(call.price - put.price, expected, places=11)

    def test_all_greeks_against_finite_differences(self):
        for kind in ("C", "P"):
            for spot in (85, 100, 115):
                s, k, t, v, r, q = spot, 100, .4, .29, .03, .01
                greek = price_greeks(s, k, t, v, kind, r, q)
                def p(s=s, t=t, v=v, r=r):
                    return price_greeks(s, k, t, v, kind, r, q).price
                hs, h = .01, 1e-5
                self.assertAlmostEqual(greek.delta, (p(s=s+hs)-p(s=s-hs))/(2*hs), delta=2e-7)
                self.assertAlmostEqual(greek.gamma, (p(s=s+hs)-2*p()+p(s=s-hs))/(hs*hs), delta=2e-8)
                self.assertAlmostEqual(greek.vega, (p(v=v+h)-p(v=v-h))/(2*h)/100, delta=1e-8)
                self.assertAlmostEqual(greek.theta, -(p(t=t+h)-p(t=t-h))/(2*h)/365, delta=1e-8)
                self.assertAlmostEqual(greek.rho, (p(r=r+h)-p(r=r-h))/(2*h)/100, delta=1e-8)

    def test_iv_recovers_price_over_grid(self):
        for kind in ("C", "P"):
            for vol in (.15, .3, .7, 1.4):
                for strike in (80, 100, 120):
                    premium = price_greeks(100, strike, .75, vol, kind).price
                    self.assertAlmostEqual(implied_vol(premium, 100, strike, .75, kind), vol, delta=1e-7)

    def test_impossible_iv_is_rejected(self):
        for value in (-1, 100, 110, float("nan")):
            with self.assertRaises(ValueError):
                implied_vol(value, 100, 100, 1)
        with self.assertRaises(ValueError):
            implied_vol(1, 100, 100, 0)

    def test_expiry_and_zero_volatility(self):
        self.assertEqual(price_greeks(110, 100, 0, .2).price, 10)
        self.assertEqual(price_greeks(90, 100, 0, .2, "P").price, 10)
        self.assertEqual(price_greeks(100, 100, 0, .2).delta, .5)
        deterministic = price_greeks(110, 100, 1, 0)
        self.assertAlmostEqual(deterministic.price, 110-100*math.exp(-.04), places=12)
        self.assertEqual(deterministic.gamma, 0)
        self.assertEqual(implied_vol(deterministic.price, 110, 100, 1), 0)

    def test_bad_inputs_fail(self):
        for args in [(0,100,1,.2), (100,0,1,.2), (100,100,-1,.2),
                     (100,100,1,-.2), (float("inf"),100,1,.2), (100,100,1,.2,"X")]:
            with self.assertRaises(ValueError):
                price_greeks(*args)
