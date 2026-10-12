import json
from pathlib import Path
import shutil
import subprocess
import unittest

from aegis.engine import Simulator
from aegis.market import make_tape
from aegis.pricing import cdf, price_greeks


@unittest.skipUnless(shutil.which("node"),"Node is optional; needed only to test browser math")
class BrowserMathTests(unittest.TestCase):
    def test_cdf_prices_and_full_stress_match_python(self):
        module=str(Path(__file__).resolve().parents[1]/"src/aegis/templates/math.js")
        inputs=[(s,k,t,v,kind) for s in (75,100,120) for k in (95,100,105)
                for t in (7/365,30/365,1) for v in (.05,.24,.7) for kind in ("C","P")]
        xs=[i/10 for i in range(-100,101)]
        result=Simulator(make_tape(ticks=60,scenario="vol_shock")).run()
        payload={"inputs":inputs,"xs":xs,"snapshot":result["snapshots"][-1],
                 "contracts":[{"id":x.id,"strike":x.strike,"expiry_days":x.expiry_days,"kind":x.kind,"multiplier":x.multiplier}
                              for x in Simulator(make_tape(ticks=20)).contracts.values()]}
        code="const fs=require('fs'),m=require(process.argv[1]),d=JSON.parse(fs.readFileSync(0,'utf8'));process.stdout.write(JSON.stringify({prices:d.inputs.map(a=>m.price(...a)),cdf:d.xs.map(m.cdf),stress:m.stress(d.snapshot,d.contracts)}));"
        process=subprocess.run(["node","-e",code,module],input=json.dumps(payload),text=True,capture_output=True,check=True)
        browser=json.loads(process.stdout)
        for args, actual in zip(inputs,browser["prices"]):
            self.assertAlmostEqual(actual,price_greeks(*args).price,delta=1e-9)
        for x,actual in zip(xs,browser["cdf"]):
            self.assertAlmostEqual(actual,cdf(x),delta=1e-12)
        for row_a,row_b in zip(browser["stress"],result["final_stress"]):
            for a,b in zip(row_a,row_b):self.assertAlmostEqual(a,b,delta=.0002)
