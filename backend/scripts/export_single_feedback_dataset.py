"""Export completed single-feedback records into a local prompt-eval dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.evals.single_feedback import (
    DEFAULT_SINGLE_FEEDBACK_DATASET_ROOT,
    DatasetExportConfig,
    export_single_feedback_dataset,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Export completed single-feedback review logs into a local eval dataset.",
    )
    parser.add_argument(
        "--dataset-root",
        default=str(DEFAULT_SINGLE_FEEDBACK_DATASET_ROOT),
        help="Dataset root directory.",
    )
    parser.add_argument(
        "--database-url",
        default=None,
        help="Override database URL. Defaults to backend settings.",
    )
    parser.add_argument(
        "--source",
        choices=("review_logs", "cards"),
        default="review_logs",
        help="Export completed review logs or reference-only card records.",
    )
    parser.add_argument(
        "--split",
        default="eval",
        help="Split label written into exported sample metadata.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of completed records to export.",
    )
    parser.add_argument(
        "--deck-id",
        action="append",
        dest="deck_ids",
        type=int,
        default=[],
        help="Restrict export to one or more lesson deck ids.",
    )
    parser.add_argument(
        "--review-log-id",
        action="append",
        dest="review_log_ids",
        type=int,
        default=[],
        help="Restrict export to one or more review_log ids.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Rewrite existing sample directories instead of skipping them.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    default_database_url = DatasetExportConfig().database_url
    config = DatasetExportConfig(
        dataset_root=Path(args.dataset_root),
        database_url=args.database_url or default_database_url,
        source=args.source,
        split=args.split,
        limit=args.limit,
        deck_ids=tuple(args.deck_ids),
        review_log_ids=tuple(args.review_log_ids),
        overwrite=args.overwrite,
    )
    report = export_single_feedback_dataset(config)
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
