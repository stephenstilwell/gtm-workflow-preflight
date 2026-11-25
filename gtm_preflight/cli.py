import argparse
import sys
from pathlib import Path

from .config import load_policy
from .inputs import InputError, load_suite
from .report import write_reports
from .runner import run_suite


def main(argv=None):
    parser = argparse.ArgumentParser(prog="gtm-preflight", description="Test proposed GTM workflow decisions offline.")
    commands = parser.add_subparsers(dest="command", required=True)
    run = commands.add_parser("run", help="validate a fixture suite and write JSON and HTML reports")
    run.add_argument("suite", type=Path, help="directory containing suite.json and its records")
    run.add_argument("--output", type=Path, help="report directory (default: reports/<suite directory>)")
    run.add_argument("--policy", type=Path, help="policy JSON file (overrides the suite's optional policy.json)")
    run.add_argument("--junit", action="store_true", help="also write report.junit.xml for CI test reporting")
    run.add_argument("--allow-inconclusive", action="store_true", help="exit 0 if only inconclusive checks remain")
    args = parser.parse_args(argv)

    try:
        suite_directory = args.suite.resolve()
    except (OSError, RuntimeError) as exc:
        print(f"gtm-preflight: {exc}", file=sys.stderr)
        return 2
    try:
        directory = args.output or Path("reports") / suite_directory.name
        suite = load_suite(suite_directory)
        local_policy = suite_directory / "policy.json"
        policy_path = args.policy or (local_policy if local_policy.exists() else None)
        config = load_policy(policy_path) if policy_path else None
        report = run_suite(suite, config)
        write_reports(directory, report, junit=args.junit)
    except (InputError, OSError) as exc:
        print(f"gtm-preflight: {exc}", file=sys.stderr)
        return 2

    counts = report["summary"]
    print(f'{report["status"].upper()} | {counts["pass"]} pass, {counts["fail"]} fail, '
          f'{counts["inconclusive"]} inconclusive')
    print(f"Reports written to {directory}")
    if report["status"] == "fail":
        return 1
    if report["status"] == "inconclusive" and not args.allow_inconclusive:
        return 3
    return 0
