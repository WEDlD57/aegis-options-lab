"""Generate the complete offline replay and transparent experiment exports."""

import argparse
import csv
from dataclasses import asdict
import json
from pathlib import Path
import platform
from time import perf_counter

from . import __version__
from .benchmark import benchmark_matching
from .engine import POLICIES, Simulator, canonical_hash
from .market import SCENARIOS, instruments, make_tape


def _write_json(path: Path, value: object) -> None:
    path.write_text(json.dumps(value, indent=2, allow_nan=False) + "\n", encoding="utf-8")


def replay_run(result: dict) -> dict:
    kinds = {"FILL", "HEDGE_FILL", "KILL_SWITCH", "REGIME", "SESSION_END", "HEDGE_REJECT"}
    selected = [row for row in result["audit"] if row["kind"] in kinds]
    diagnostic = [row for row in result["audit"] if row["kind"] in ("REJECT", "CANCEL_MISS")]
    # Keep both ends of the diagnostic log. Complete audit is exported separately.
    by_sequence = {row["seq"]: row for row in selected + diagnostic[:80] + diagnostic[-80:]}
    events = sorted(by_sequence.values(), key=lambda row: row["seq"])
    return {key: result[key] for key in ("policy", "limits", "summary", "snapshots", "trades",
                                         "tape_hash", "result_hash", "final_stress")} | {
        "events": events, "audit_total": len(result["audit"]), "replay_events": len(events)}


def generate(out: Path, seed: int, ticks: int, scenario_names: tuple[str, ...],
             policy_names: tuple[str, ...], benchmark_iterations: int = 20_000) -> dict:
    out.mkdir(parents=True, exist_ok=True)
    replay = {"version": __version__, "seed": seed, "ticks": ticks,
              "data_kind": "SYNTHETIC", "initial_capital": 100_000,
              "instruments": [asdict(inst) for inst in instruments()], "experiments": []}
    audit_file = out / "audit.jsonl"
    trades_file = out / "trades.csv"
    timings = []
    fields = ["scenario", "policy", "ms", "instrument", "side", "qty", "price", "fair", "fee",
              "source", "quote_age_ms", "order_id", "markout_5s_per_contract"]
    with audit_file.open("w", encoding="utf-8") as audit, trades_file.open("w", newline="", encoding="utf-8") as ledger:
        writer = csv.DictWriter(ledger, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for scenario in scenario_names:
            tape = make_tape(seed, ticks, scenario)
            experiment = {"scenario": scenario, "runs": []}
            for name in policy_names:
                start = perf_counter()
                result = Simulator(tape, POLICIES[name]).run()
                elapsed = perf_counter() - start
                timings.append({"scenario": scenario, "policy": name, "wall_seconds": elapsed,
                                "processed_events": result["summary"]["processed_events"],
                                "events_per_second": result["summary"]["processed_events"] / elapsed})
                experiment["runs"].append(replay_run(result))
                for event in result["audit"]:
                    audit.write(json.dumps({"scenario": scenario, "policy": name, **event}, separators=(",", ":"), allow_nan=False) + "\n")
                for trade in result["trades"]:
                    writer.writerow({"scenario": scenario, "policy": name, **trade})
                summary = result["summary"]
                print(f"{scenario:12s} {name:10s} P&L={summary['pnl']:9.2f} "
                      f"fills={summary['contracts_filled']:5d} circuit={summary['circuit']:10s} "
                      f"hash={result['result_hash'][:12]}", flush=True)
            if len({run["tape_hash"] for run in experiment["runs"]}) != 1:
                raise AssertionError("policies used different exogenous tapes")
            replay["experiments"].append(experiment)
    replay["suite_hash"] = canonical_hash(replay)
    _write_json(out / "replay.json", replay)
    summaries = {"version": __version__, "seed": seed, "ticks": ticks, "suite_hash": replay["suite_hash"],
                 "results": [{"scenario": exp["scenario"], "policy": run["policy"]["name"],
                              "tape_hash": run["tape_hash"], "result_hash": run["result_hash"], **run["summary"]}
                             for exp in replay["experiments"] for run in exp["runs"]]}
    _write_json(out / "summary.json", summaries)
    measurements = {"python": platform.python_version(), "platform": platform.platform(),
                    "suite_timings": timings, "matching": benchmark_matching(benchmark_iterations)}
    _write_json(out / "benchmark.json", measurements)
    template_dir = Path(__file__).with_name("templates")
    # No fetch/CDN: report opens from a file, with everything embedded.
    payload = json.dumps(replay, separators=(",", ":"), allow_nan=False).replace("<", "\\u003c")
    template = (template_dir / "report.html").read_text(encoding="utf-8")
    rendered = template.replace("/*__MATH__*/", (template_dir / "math.js").read_text(encoding="utf-8"))
    rendered = rendered.replace("/*__DATA__*/{}", payload)
    (out / "report.html").write_text(rendered, encoding="utf-8")
    print(f"\nOpen {out / 'report.html'} — self-contained, no server or account needed.")
    return replay


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="AEGIS — options market microstructure lab")
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("demo", "simulate"):
        p = sub.add_parser(command)
        p.add_argument("--seed", type=int, default=42)
        p.add_argument("--ticks", type=int, default=600)
        p.add_argument("--out", type=Path, default=Path("artifacts"))
        p.add_argument("--benchmark-iterations", type=int, default=20_000)
        if command == "simulate":
            p.add_argument("--scenario", choices=SCENARIOS, default="vol_shock")
            p.add_argument("--policy", choices=tuple(POLICIES), default="aegis")
    p = sub.add_parser("benchmark")
    p.add_argument("--iterations", type=int, default=20_000)
    args = parser.parse_args(argv)
    if args.command == "benchmark":
        print(json.dumps(benchmark_matching(args.iterations), indent=2))
    else:
        if args.ticks < 20 or args.benchmark_iterations < 1:
            parser.error("ticks must be >=20 and benchmark-iterations >=1")
        scenarios = SCENARIOS if args.command == "demo" else (args.scenario,)
        policies = tuple(POLICIES) if args.command == "demo" else (args.policy,)
        generate(args.out, args.seed, args.ticks, scenarios, policies, args.benchmark_iterations)


if __name__ == "__main__":
    main()
