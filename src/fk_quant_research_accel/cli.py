"""CLI for running quant research batches on top of FK PINN backend."""

from __future__ import annotations

import argparse
from typing import Iterable

from .client import FKPinnClient
from .orchestrator import BatchConfig, generate_black_scholes_scenarios, run_batch
from .reporting import write_csv


def _parse_int_list(raw: str) -> list[int]:
    return [int(item.strip()) for item in raw.split(",") if item.strip()]


def _parse_float_list(raw: str) -> list[float]:
    return [float(item.strip()) for item in raw.split(",") if item.strip()]


def _print_top(rows: Iterable[dict], n: int = 10) -> None:
    print("Top scenarios by score (lower is better):")
    for idx, row in enumerate(rows):
        if idx >= n:
            break
        print(
            f"{idx + 1:>2}. score={row['score']:.6f} "
            f"dim={row['dim']} vol={row['volatility']} corr={row['correlation']} "
            f"status={row['status']} train_loss={row['train_loss']}"
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run quant scenario batches on FK PINN backend")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run = subparsers.add_parser("run-batch", help="Submit a Black-Scholes scenario grid")
    run.add_argument("--base-url", required=True, help="FK PINN backend base URL")
    run.add_argument("--dimensions", default="5,10", help="Comma-separated integer dims")
    run.add_argument("--volatilities", default="0.15,0.2", help="Comma-separated vol values")
    run.add_argument("--correlations", default="0.0,0.3", help="Comma-separated corr values")
    run.add_argument("--option-types", default="call", help="Comma-separated option types")
    run.add_argument("--n-steps", type=int, default=40)
    run.add_argument("--batch-size", type=int, default=64)
    run.add_argument("--n-mc-paths", type=int, default=256)
    run.add_argument("--learning-rate", type=float, default=1e-3)
    run.add_argument("--poll-seconds", type=float, default=1.5)
    run.add_argument("--max-wait-seconds", type=float, default=1800.0)
    run.add_argument("--output", default="artifacts/batch_results.csv")

    return parser


def main() -> int:
    parser = build_parser()
    args = parser.parse_args()

    if args.command == "run-batch":
        client = FKPinnClient(base_url=args.base_url)
        scenarios = generate_black_scholes_scenarios(
            dimensions=_parse_int_list(args.dimensions),
            volatilities=_parse_float_list(args.volatilities),
            correlations=_parse_float_list(args.correlations),
            option_types=[item.strip() for item in args.option_types.split(",") if item.strip()],
        )
        config = BatchConfig(
            n_steps=args.n_steps,
            batch_size=args.batch_size,
            n_mc_paths=args.n_mc_paths,
            learning_rate=args.learning_rate,
        )
        rows = run_batch(
            client=client,
            scenarios=scenarios,
            batch_config=config,
            poll_seconds=args.poll_seconds,
            max_wait_seconds=args.max_wait_seconds,
        )
        output = write_csv(rows, args.output)
        _print_top(rows)
        print(f"Wrote {len(rows)} rows to {output}")
        return 0

    parser.error("Unknown command")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
