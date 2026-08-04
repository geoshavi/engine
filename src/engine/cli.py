import argparse
import sys
from pathlib import Path

from engine.config import load_config
from engine.orchestrator.engine import run_task
from engine.reporting.report import generate_report
from engine.runtime.gateway import LLMGateway


def main() -> None:
    parser = argparse.ArgumentParser(prog="engine")
    subparsers = parser.add_subparsers(dest="command", required=True)

    run_parser = subparsers.add_parser("run", help="Run a coding task through the engine")
    run_parser.add_argument("task", help="Natural-language description of the task")
    run_parser.add_argument(
        "--workspace", default=None, help="Directory to write generated code into"
    )
    run_parser.add_argument("--provider", default="anthropic", help="Provider to use")

    serve_parser = subparsers.add_parser(
        "serve", help="Run the code-review HTTP API (for n8n or other automation)"
    )
    serve_parser.add_argument("--port", type=int, default=8000)
    serve_parser.add_argument("--provider", default="anthropic", help="Provider to use")

    bench_parser = subparsers.add_parser(
        "bench", help="Run the evaluation benchmark against the review flow"
    )
    bench_parser.add_argument(
        "--category",
        default=None,
        choices=["security", "correctness", "quality", "edge_case"],
        help="Run only this category instead of the full 40-case benchmark",
    )
    bench_parser.add_argument(
        "--compare",
        type=int,
        default=None,
        metavar="EVAL_RUN_ID",
        help="After running, compare results against a previous eval_run_id",
    )
    bench_parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate the dataset and budget, print the plan, make zero LLM calls",
    )
    bench_parser.add_argument("--provider", default="anthropic", help="Provider to use")

    args = parser.parse_args()

    if args.command == "run":
        config = load_config()
        gateway = LLMGateway.from_config(args.provider, config)
        workspace = Path(args.workspace) if args.workspace else Path(".engine/workspace")

        result = run_task(args.task, workspace, gateway, config, provider_name=args.provider)

        report = generate_report(result)
        print(report)
        report_path = workspace.parent / "report.md"
        report_path.write_text(report)

        sys.exit(0 if result.passed else 1)
    elif args.command == "serve":
        from engine.api import serve

        serve(port=args.port, provider_name=args.provider)
    elif args.command == "bench":
        from engine.eval.report import (
            format_benchmark_report,
            format_comparison,
            format_dry_run_plan,
        )
        from engine.eval.runner import run_benchmark, select_cases
        from engine.providers.registry import DEFAULT_MODELS
        from engine.state import db

        config = load_config()
        judge_model = DEFAULT_MODELS[args.provider]["judge"]
        cases = select_cases(args.category)

        if args.dry_run:
            if args.compare is not None:
                print(
                    f"WARNING: --compare {args.compare} is ignored with --dry-run -- "
                    "dry-run makes zero LLM calls, so there are no new results to compare. "
                    "Run without --dry-run to actually compare against a previous eval run.\n"
                )
            plan_text, errors = format_dry_run_plan(cases, judge_model)
            print(plan_text)
            sys.exit(1 if errors else 0)

        eval_run, results = run_benchmark(
            config=config, provider_name=args.provider, judge_model=judge_model, category=args.category
        )
        print(format_benchmark_report(eval_run, results))

        if args.compare is not None:
            with db.connect(config.db_path) as conn:
                previous = db.get_eval_run(conn, args.compare)
                if previous is None:
                    print(f"\nERROR: no eval run #{args.compare} found -- cannot compare.")
                    sys.exit(1)
                previous_results = db.get_eval_case_results(conn, args.compare)
            print()
            print(format_comparison(eval_run, results, previous, previous_results))

        # false_pass (the judge wrongly approving bad code) is the failure
        # mode this benchmark exists to catch -- treat it as a CI-style gate.
        sys.exit(0 if eval_run.false_pass == 0 else 1)


if __name__ == "__main__":
    main()
