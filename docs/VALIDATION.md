# Validation record

Validated for this downloadable source bundle on 2026-10-07 using Python 3.12.14 on Linux. This record distinguishes completed checks from supplied checks that could not run here.

## Passed

- **33 standard-library tests:** order priority, partial fills, IOC/post-only semantics, self-match prevention, cancellation, randomized quantity conservation, finite-difference Greeks, put/call parity, IV inversion, pricing edge cases, conservative reservations, delayed shutdowns, future-data independence, deterministic repetition, export parsing, and P&L reconciliation.
- **JavaScript pricing/stress parity:** the test suite ran the browser math functions with Node and compared CDFs, option prices, and a full stress grid with Python. This validates the math, not the HTML layout.
- **Full default generation:** 16 runs with seed 42 and 600 one-second market frames per run. Each run asserts ledger reconciliation and drainage of AEGIS orders/reservations. All policies within a scenario share one tape hash.
- **Prebuilt payload/export consistency:** the HTML embeds the same generated suite, with no unresolved template tokens, external JavaScript dependencies, or data fetch requirement.
- **Package and documentation checks:** source packaging, links, required files, generated data-summary animation, and ZIP integrity were checked before delivery.

## Browser verification limitation

The supplied `scripts/verify_ui.cjs` uses Playwright to check all 16 scenario/policy switches, displayed P&L, contract selection, the stress grid, risk filters, the guide, CSV download, play/pause, scrubbing, event jump, and page overflow at 1500 × 1100 and 390 × 844 viewports. It also requires zero page exceptions and zero remote requests.

These browser checks **did not run successfully in this environment**: Playwright was available, but no browser executable was installed, and the browser download returned an unusable archive. Desktop/mobile rendering and interactions therefore remain unverified here. The GitHub workflow includes this check for execution in a runner with browser-install network access; that workflow has not been run on GitHub as part of this bundle.

To run it locally:

```bash
npm install --no-save --package-lock=false playwright
npx playwright install chromium
node scripts/verify_ui.cjs
```

On Linux, system browser dependencies may also require `npx playwright install --with-deps chromium`. Browser tools are optional development dependencies; ordinary simulation and report viewing do not require them.

## Reproduce

```bash
python scripts/test.py
python scripts/run.py demo --seed 42 --ticks 600
```

Hashes identify deterministic run data, not machine timing. The raw benchmark metadata accompanies every generation. None of these tests establish live-market profitability or production readiness.
