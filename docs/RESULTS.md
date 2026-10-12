# Bundled experiment results

These are synthetic, seed-42, 600-frame engineering experiments with $100,000 initial capital. The results are mark-to-model dollars after fees, with inventory still open. Favorable flow makes ordinary-scenario gains large; do not infer real returns or annualize them.

## All 16 runs

| Scenario | Policy | P&L ($) | Max drawdown ($) | Peak absolute delta (shares) | Option contracts filled | Circuit |
| --- | --- | ---: | ---: | ---: | ---: | --- |
| normal | AEGIS | 9,268.53 | 43.03 | 368.8 | 1,972 | NONE |
| normal | No hedge | 10,067.74 | 21.51 | 424.0 | 1,918 | NONE |
| normal | Symmetric | 8,585.34 | 476.78 | 2,351.1 | 1,331 | NONE |
| normal | Delayed | 8,863.04 | 38.94 | 514.6 | 1,905 | NONE |
| trend | AEGIS | 9,609.54 | 28.34 | 382.2 | 2,037 | NONE |
| trend | No hedge | 10,405.59 | 20.88 | 437.4 | 1,986 | NONE |
| trend | Symmetric | 391.36 | 4,301.71 | 2,248.4 | 921 | DRAWDOWN |
| trend | Delayed | 9,262.80 | 49.36 | 561.8 | 1,972 | NONE |
| vol_shock | AEGIS | 2,139.48 | 3,050.55 | 632.5 | 1,014 | DRAWDOWN |
| vol_shock | No hedge | 2,568.67 | 2,999.49 | 600.0 | 996 | DRAWDOWN |
| vol_shock | Symmetric | 12,432.91 | 1,484.45 | 2,399.2 | 1,266 | DRAWDOWN |
| vol_shock | Delayed | 1,853.84 | 3,204.83 | 653.6 | 972 | DRAWDOWN |
| feed_outage | AEGIS | 4,886.99 | 75.81 | 368.8 | 1,011 | STALE_FEED |
| feed_outage | No hedge | 5,375.96 | 110.36 | 387.2 | 993 | STALE_FEED |
| feed_outage | Symmetric | 6,119.69 | 856.49 | 2,209.3 | 904 | STALE_FEED |
| feed_outage | Delayed | 4,925.19 | 90.38 | 514.6 | 972 | STALE_FEED |

## Read the failure modes

In the shock scenario, the AEGIS latch fires at 300.060 seconds; Delayed reacts at 300.300 seconds. Both retain open positions. AEGIS ends with 20 gross option contracts and 173 underlying shares. Its $3,050.55 full-run drawdown exceeds the $500 trigger because observed controls cannot prevent an earlier jump or freeze subsequent inventory valuation.

Symmetric happens to make the most marked dollars in this particular shock path. That is not evidence of overall superiority: its inventory, timing, and exposures differ. In the trend run its latch fires and remaining positions produce a $4,301.71 drawdown. Evaluate risk and multiple independent seeds, rather than selecting the largest number in this table.

In the outage scenario, all gates latch for stale data and remain latched after observations resume. Delayed messages drain. No automatic liquidation follows.

## Accounting and reproduction

- Suite hash: `f6e5baa5be4596d8a05a8aff76614ab889ac57949107c6f8d7d9022df5e97bd9`.
- Each scenario has one common tape hash across all four policies.
- Largest absolute final ledger reconciliation error: $2.91e-11 (required tolerance: $0.000001).
- The full JSON summary includes final inventory, fees, markout censoring counts, attribution, estimated exit cost, and run hashes.

## Local-process measurements

Python 3.12.14 on `Linux-6.18.44-x86_64-with-glibc2.39`. One recorded run; timings are machine-dependent and not deterministic.

| Measurement | Recorded value |
| --- | ---: |
| IOC operation iterations | 20,000 |
| Warm-up iterations | 200 |
| Median one-match IOC | 1.632 µs |
| 95th percentile | 1.793 µs |
| 99th percentile | 2.294 µs |
| Matching loop wall time including setup | 0.0615 s |
| Total processed simulator events | 376,003 |

The per-operation sample measures one IOC taker matching one previously inserted resting order. It excludes construction/setup, network transport, broker/exchange connections, serialization, realistic book populations, and operational controls. Garbage collection was enabled. Full-simulation timings include much more work and are recorded separately in `benchmark.json`. Do not label these numbers end-to-end trading latency.

## Reproduce

```bash
python scripts/run.py demo --seed 42 --ticks 600
python scripts/run.py benchmark --iterations 20000
```

The audit, trade ledger, and replay payload are included in this ZIP. Git ignores those larger generated exports; the source command recreates them.
