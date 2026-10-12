from dataclasses import replace
import unittest

from aegis.engine import POLICIES, Simulator
from aegis.market import make_tape, tape_hash


class EngineTests(unittest.TestCase):
    def test_exact_seeded_reproduction(self):
        tape=make_tape(seed=17,ticks=45,scenario="normal")
        a,b=Simulator(tape).run(),Simulator(tape).run()
        self.assertEqual(a["result_hash"],b["result_hash"])
        self.assertEqual(a,b)
        self.assertNotEqual(tape_hash(tape),tape_hash(make_tape(seed=18,ticks=45,scenario="normal")))

    def test_future_changes_cannot_change_earlier_decisions(self):
        tape=make_tape(ticks=80,scenario="normal")
        modified=tuple(replace(f,spot=f.spot*1.08,iv=f.iv+.12) if f.ms>=40000 else f for f in tape)
        a,b=Simulator(tape).run(),Simulator(modified).run()
        for key in ("snapshots","audit"):
            self.assertEqual([x for x in a[key] if x["ms"]<40000],[x for x in b[key] if x["ms"]<40000])

    def test_data_domain_is_delayed_and_excludes_future_flows(self):
        sim=Simulator(make_tape(ticks=50),POLICIES["delayed"])
        result=sim.run()
        self.assertFalse(hasattr(sim.observed,"flows"))
        for row in result["audit"]:
            if row["kind"] in ("QUOTE_SENT","HEDGE_SENT"):
                self.assertGreaterEqual(row["ms"]-row["observed_ms"],300)
            if row["kind"]=="FILL":
                self.assertGreaterEqual(row["quote_age_ms"],1900)

    def test_attribution_matches_cash_and_model_value(self):
        for policy in ("aegis","unhedged","symmetric","delayed"):
            result=Simulator(make_tape(ticks=70,scenario="normal"),POLICIES[policy]).run()
            s=result["summary"]
            self.assertAlmostEqual(s["pnl"],sum(s["attribution"].values()),delta=5e-6)
            self.assertLess(abs(s["reconciliation_error"]),1e-6)
            self.assertEqual(result["snapshots"][-1]["live_orders"],0)
            self.assertEqual(result["snapshots"][-1]["inflight_orders"],0)
            self.assertGreater(s["contracts_filled"],0)

    def test_outage_trips_and_new_orders_stop(self):
        result=Simulator(make_tape(ticks=80,scenario="feed_outage")).run()
        self.assertEqual(result["summary"]["circuit"],"STALE_FEED")
        trigger=result["summary"]["circuit_ms"]
        self.assertGreater(trigger,40000)
        self.assertFalse(any(e["kind"]=="QUOTE_SENT" and e["ms"]>trigger for e in result["audit"]))
        self.assertEqual(result["snapshots"][-1]["live_orders"],0)

    def test_late_orders_are_rejected_after_kill(self):
        policy=replace(POLICIES["aegis"],order_latency_ms=4000)
        result=Simulator(make_tape(ticks=80,scenario="feed_outage"),policy).run()
        self.assertTrue(any(e["kind"]=="REJECT" and e["reason"]=="CIRCUIT_OPEN" for e in result["audit"]))
        self.assertEqual(result["snapshots"][-1]["inflight_orders"],0)

    def test_gap_can_exceed_loss_trigger_and_leaves_inventory(self):
        result=Simulator(make_tape(ticks=180,scenario="vol_shock")).run()
        self.assertEqual(result["summary"]["circuit"],"DRAWDOWN")
        self.assertGreater(result["summary"]["max_drawdown"],result["limits"]["drawdown_dollars"])
        self.assertGreater(result["summary"]["final_gross"],0)

    def test_five_second_markouts_are_censored_at_session_end(self):
        result=Simulator(make_tape(ticks=35,scenario="normal")).run()
        late=[t for t in result["trades"] if t["instrument"]!="SYN" and t["ms"]>=30000]
        self.assertTrue(late)
        self.assertTrue(all(t["markout_5s_per_contract"] is None for t in late))

    def test_policies_share_same_exogenous_tape(self):
        tape=make_tape(ticks=30)
        outputs=[Simulator(tape,p).run() for p in POLICIES.values()]
        self.assertEqual(len({r["tape_hash"] for r in outputs}),1)

    def test_single_use_and_invalid_clock(self):
        sim=Simulator(make_tape(ticks=20));sim.run()
        with self.assertRaises(RuntimeError):sim.run()
        with self.assertRaises(ValueError):Simulator((replace(make_tape(ticks=20)[0],ms=1000),))
