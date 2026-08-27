"""Run one or more prompt variants against the local single-feedback eval dataset."""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from app.adapters.gemini_adapter import GenerationConfig
from app.evals.single_feedback import (
    DEFAULT_SINGLE_FEEDBACK_DATASET_ROOT,
    PromptEvalConfig,
    PromptVariant,
    run_single_feedback_eval,
)


def parse_variant(raw: str) -> PromptVariant:
    if "=" not in raw:
        raise argparse.ArgumentTypeError(
            "Variant must be in the form name=prompt_dir"
        )
    name, prompt_dir = raw.split("=", 1)
    if not name.strip() or not prompt_dir.strip():
        raise argparse.ArgumentTypeError(
            "Variant must be in the form name=prompt_dir"
        )
    return PromptVariant(name=name.strip(), prompt_dir=Path(prompt_dir.strip()))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run Gemini single-feedback prompt evals on a fixed local dataset.",
    )
    parser.add_argument(
        "--dataset-root",
        default=str(DEFAULT_SINGLE_FEEDBACK_DATASET_ROOT),
        help="Dataset root directory.",
    )
    parser.add_argument(
        "--variant",
        action="append",
        type=parse_variant,
        default=[],
        help=(
            "Prompt variant in the form name=prompt_dir. "
            "Repeat this flag to compare multiple prompt directories."
        ),
    )
    parser.add_argument(
        "--split",
        default="eval",
        help="Only evaluate samples in this split. Use an empty string to include all splits.",
    )
    parser.add_argument(
        "--sample-id",
        action="append",
        dest="sample_ids",
        default=[],
        help="Only evaluate the listed sample ids.",
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help="Maximum number of samples to run from the selected dataset slice.",
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Override GEMINI_MODEL_ID for this run only.",
    )
    parser.add_argument(
        "--temperature",
        type=float,
        default=0.3,
        help="Generation temperature recorded and used for this run.",
    )
    parser.add_argument(
        "--max-output-tokens",
        type=int,
        default=2048,
        help="Max output tokens recorded and used for this run.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    variants = tuple(args.variant)
    if not variants:
        variants = (
            PromptVariant(
                name="baseline",
                prompt_dir=Path("app/adapters/prompts/v1/single_feedback"),
            ),
        )

    config = PromptEvalConfig(
        dataset_root=Path(args.dataset_root),
        variants=variants,
        split=args.split or None,
        sample_ids=tuple(args.sample_ids),
        limit=args.limit,
        model_id=args.model_id,
        generation_config=GenerationConfig(
            temperature=args.temperature,
            max_output_tokens=args.max_output_tokens,
        ),
    )
    manifest = run_single_feedback_eval(config)
    print(json.dumps(manifest, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
