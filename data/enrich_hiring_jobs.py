"""Run one bounded, company-scoped persisted hiring-enrichment batch."""

import argparse
import asyncio
from collections import Counter
import json
from pathlib import Path
import sys

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from backend.app.application.hiring import HiringBatchEnrichmentRequest  # noqa: E402
from backend.app.infrastructure.composition.hiring_batch_enrichment import (
    create_hiring_batch_enrichment_service,
)  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a controlled persisted hiring-enrichment batch."
    )
    parser.add_argument("--organization", required=True)
    parser.add_argument("--max-jobs", required=True, type=int, choices=range(1, 26))
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true")
    mode.add_argument(
        "--execute",
        action="store_true",
        help="Call the configured provider and persist validated results.",
    )
    parser.add_argument(
        "--stop-on-error",
        action="store_true",
        help="Stop after the first provider, validation, or persistence failure.",
    )
    return parser.parse_args()


async def run() -> int:
    args = parse_args()
    service = create_hiring_batch_enrichment_service()
    result = await service.execute(
        HiringBatchEnrichmentRequest(
            organization=args.organization,
            max_jobs=args.max_jobs,
            dry_run=args.dry_run,
            continue_on_error=not args.stop_on_error,
        )
    )
    summary = result.model_dump(exclude={"outcomes"})
    summary["outcome_counts"] = dict(
        sorted(Counter(item.status.value for item in result.outcomes).items())
    )
    summary["attempted_outcomes"] = [
        {
            "job_id": str(item.job_id),
            "evidence_id": str(item.evidence_id),
            "status": item.status.value,
            "failure_code": item.failure_code,
            "message": item.message,
        }
        for item in result.outcomes
        if item.status.value not in {"deferred_limit", "skipped_existing"}
    ]
    print(json.dumps(summary, indent=2))
    return 0 if result.failed_jobs == 0 else 1


if __name__ == "__main__":
    raise SystemExit(asyncio.run(run()))
