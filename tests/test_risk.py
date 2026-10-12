from dataclasses import replace
import unittest

from aegis.book import Order
from aegis.market import instruments, make_tape
from aegis.portfolio import Portfolio
from aegis.risk import Limits, RiskGate


class RiskTests(unittest.TestCase):
    def setUp(self):
        self.contracts={x.id:x for x in instruments()}
        self.key="SYN-7D-100C"
        frame=make_tape(ticks=20)[0]
        self.marks={key:inst.mark(frame) for key,inst in self.contracts.items()}
        self.portfolio=Portfolio()

    def test_inflight_both_sides_are_reserved_independently(self):
        gate=RiskGate(replace(Limits(),per_instrument=3))
        buy=Order("buy",self.key,"AEGIS",1,100,2)
        sell=Order("sell",self.key,"AEGIS",-1,110,2)
        self.assertIsNone(gate.reserve(buy,self.portfolio,self.marks,self.contracts))
        self.assertEqual(gate.reserve(sell,self.portfolio,self.marks,self.contracts),"POSITION_LIMIT")
        gate.release("buy")
        self.assertIsNone(gate.reserve(sell,self.portfolio,self.marks,self.contracts))

    def test_arrival_rechecks_updated_greeks(self):
        gate=RiskGate(replace(Limits(),delta_shares=100))
        order=Order("x",self.key,"AEGIS",1,100,1)
        self.assertIsNone(gate.reserve(order,self.portfolio,self.marks,self.contracts))
        self.portfolio.shares=80
        self.assertEqual(gate.check(order,self.portfolio,self.marks,self.contracts),"DELTA_LIMIT")

    def test_positions_plus_remaining_reservations(self):
        gate=RiskGate(replace(Limits(),per_instrument=3))
        self.portfolio.positions[self.key]=-2
        order=Order("x",self.key,"AEGIS",1,100,2)
        self.assertEqual(gate.reserve(order,self.portfolio,self.marks,self.contracts),"POSITION_LIMIT")

    def test_pending_hedge_consumes_delta_bound(self):
        gate=RiskGate(replace(Limits(),delta_shares=100))
        order=Order("x",self.key,"AEGIS",1,100,1)
        self.assertEqual(gate.reserve(order,self.portfolio,self.marks,self.contracts,pending_hedge=90),"DELTA_LIMIT")

    def test_latch_cannot_reset_itself(self):
        gate=RiskGate()
        self.assertTrue(gate.trip("STALE_FEED",5000))
        self.assertFalse(gate.trip("OTHER",6000))
        self.assertEqual(gate.trigger_ms,5000)
        self.assertEqual(gate.reserve(Order("x",self.key,"AEGIS",1,100,1),self.portfolio,self.marks,self.contracts),"CIRCUIT_OPEN")

    def test_freshness_and_high_water_drawdown(self):
        gate=RiskGate()
        self.assertIsNone(gate.monitor(100,0,1000))
        self.assertEqual(gate.monitor(200,0,499),"DRAWDOWN")
        self.assertEqual(gate.monitor(2600,0,1000),"STALE_FEED")
