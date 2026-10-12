/* Browser-side full repricing. Tests compare these values with Python.
 * Normal CDF: integrate its Taylor series for |x|<=4; use the Laplace
 * continued fraction for the Gaussian tail beyond 4. No remote libraries.
 */
(function (root) {
  'use strict';
  function cdf(x) {
    const a = Math.abs(x);
    let positive;
    if (a <= 4) {
      let term = a, sum = a;
      for (let n = 1; n < 90; n++) {
        term *= -a * a / (2 * n);
        const add = term / (2 * n + 1);
        sum += add;
        if (Math.abs(add) < 1e-16) break;
      }
      positive = 0.5 + sum / Math.sqrt(2 * Math.PI);
    } else {
      let tail = 0;
      for (let n = 100; n >= 1; n--) tail = n / (a + tail);
      positive = 1 - Math.exp(-a * a / 2) / (Math.sqrt(2 * Math.PI) * (a + tail));
    }
    return x >= 0 ? positive : 1 - positive;
  }
  function price(spot, strike, years, vol, kind, rate = 0.04) {
    const sign = kind === 'C' ? 1 : -1;
    if (years <= 0) return Math.max(sign * (spot - strike), 0);
    if (vol <= 0) return Math.max(sign * (spot - strike * Math.exp(-rate * years)), 0);
    const d1 = (Math.log(spot / strike) + (rate + vol * vol / 2) * years) / (vol * Math.sqrt(years));
    const d2 = d1 - vol * Math.sqrt(years);
    return Math.max(sign * (spot * cdf(sign * d1) - strike * Math.exp(-rate * years) * cdf(sign * d2)), 0);
  }
  const SPOT_SHOCKS = [-0.06, -0.04, -0.02, 0, 0.02, 0.04, 0.06];
  const VOL_SHOCKS = [0.15, 0.10, 0.05, 0, -0.05, -0.10, -0.15];
  function stress(snapshot, contracts) {
    return VOL_SHOCKS.map(v => SPOT_SHOCKS.map(s => {
      const spot = snapshot.spot * (1 + s);
      let change = snapshot.shares * (spot - snapshot.spot);
      for (const row of snapshot.chain) {
        if (!row.position) continue;
        const inst = contracts.find(x => x.id === row.id);
        const years = Math.max(inst.expiry_days / 365 - snapshot.market_ms / (365 * 86400000), 0);
        const before = price(snapshot.spot, inst.strike, years, snapshot.iv, inst.kind);
        const after = price(spot, inst.strike, years, Math.max(snapshot.iv + v, 0.01), inst.kind);
        change += row.position * inst.multiplier * (after - before);
      }
      return change;
    }));
  }
  const api = {cdf, price, stress, SPOT_SHOCKS, VOL_SHOCKS};
  if (typeof module !== 'undefined' && module.exports) module.exports = api;
  else root.AegisMath = api;
})(typeof globalThis !== 'undefined' ? globalThis : this);
