from __future__ import annotations

import argparse
import json
import sys

from backend.app.services.storage_hygiene import inspect_storage, migrate_duplicate_uploads


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect or migrate BlueAlpha backend storage hygiene.")
    parser.add_argument(
        "--dedupe-uploads",
        action="store_true",
        help="Migrate legacy duplicate upload files to one canonical physical file per content hash.",
    )
    parser.add_argument(
        "--failed-run-retention-days",
        type=int,
        default=7,
        help="Report failed runs at or above this age in days.",
    )
    parser.add_argument(
        "--workflow-retention-days",
        type=int,
        default=7,
        help="Report unreferenced workflow drafts at or above this age in days.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Apply --dedupe-uploads migration. Without --dedupe-uploads this is refused.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    if args.apply and not args.dedupe_uploads:
        print("--apply is only supported with --dedupe-uploads.", file=sys.stderr)
        return 2
    if args.dedupe_uploads:
        report = migrate_duplicate_uploads(apply=bool(args.apply))
    else:
        report = inspect_storage(
            failed_run_retention_days=max(0, args.failed_run_retention_days),
            workflow_retention_days=max(0, args.workflow_retention_days),
        )
    print(json.dumps(report, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
