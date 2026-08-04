import argparse
import sys
from pathlib import Path

from engine.config import load_config
from engine.orchestrator.engine import run_task
from engine.providers.registry import build_provider
from engine.reporting.report import generate_report


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

    args = parser.parse_args()

    if args.command == "run":
        config = load_config()
        provider = build_provider(args.provider, config)
        workspace = Path(args.workspace) if args.workspace else Path(".engine/workspace")

        result = run_task(args.task, workspace, provider, config, provider_name=args.provider)

        report = generate_report(result)
        print(report)
        report_path = workspace.parent / "report.md"
        report_path.write_text(report)

        sys.exit(0 if result.passed else 1)
    elif args.command == "serve":
        from engine.api import serve

        serve(port=args.port, provider_name=args.provider)


if __name__ == "__main__":
    main()
