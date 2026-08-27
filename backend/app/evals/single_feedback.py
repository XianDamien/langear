"""Offline dataset export and prompt eval workflow for Gemini single feedback."""

from __future__ import annotations

import hashlib
import json
import shutil
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any, Callable
from urllib.parse import urlparse
from urllib.request import urlopen

from sqlalchemy import create_engine, select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import Session

from app.database_url import build_default_sqlite_database_url, resolve_database_url
from app.models.card import Card
from app.models.deck import Deck
from app.models.review_log import ReviewLog
from app.utils.timezone import app_now, from_storage_local, to_utc

if TYPE_CHECKING:
    from app.adapters.gemini_adapter import GeminiAdapter

BACKEND_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DATABASE_URL = build_default_sqlite_database_url(BACKEND_ROOT)
DATASET_SCHEMA_VERSION = 1
RUN_SCHEMA_VERSION = 1
DEFAULT_SINGLE_FEEDBACK_DATASET_ROOT = (
    BACKEND_ROOT / "datasets" / "gemini_single_feedback_eval"
)


class EvalWorkflowError(RuntimeError):
    """Raised when dataset export or prompt eval setup is invalid."""


@dataclass(frozen=True)
class DatasetExportConfig:
    """Configuration for exporting single-feedback records into a local dataset."""

    dataset_root: Path = DEFAULT_SINGLE_FEEDBACK_DATASET_ROOT
    database_url: str = DEFAULT_DATABASE_URL
    source: str = "review_logs"
    split: str = "eval"
    limit: int | None = None
    deck_ids: tuple[int, ...] = ()
    review_log_ids: tuple[int, ...] = ()
    overwrite: bool = False


@dataclass(frozen=True)
class PromptVariant:
    """Named prompt variant for an offline eval run."""

    name: str
    prompt_dir: Path


@dataclass(frozen=True)
class PromptEvalConfig:
    """Configuration for running prompt evals on the local dataset."""

    dataset_root: Path = DEFAULT_SINGLE_FEEDBACK_DATASET_ROOT
    variants: tuple[PromptVariant, ...] = ()
    split: str | None = "eval"
    sample_ids: tuple[str, ...] = ()
    limit: int | None = None
    model_id: str | None = None
    generation_config: Any = None


@dataclass(frozen=True)
class DatasetSample:
    """Materialized dataset sample used by the runner."""

    sample_id: str
    sample_dir: Path
    metadata: dict[str, Any]
    input_payload: dict[str, Any]
    source_output: dict[str, Any] | None

    @property
    def front_text(self) -> str:
        return str(self.input_payload["front_text"])

    @property
    def user_audio_path(self) -> Path:
        return self.sample_dir / str(self.input_payload["user_audio_file"])

    @property
    def reference_audio_path(self) -> Path:
        return self.sample_dir / str(self.input_payload["reference_audio_file"])


AudioDownloader = Callable[[str, Path], dict[str, Any]]
AdapterFactory = Callable[[], "GeminiAdapter"]


def export_single_feedback_dataset(
    config: DatasetExportConfig,
    *,
    audio_downloader: AudioDownloader | None = None,
) -> dict[str, Any]:
    """Export completed single-feedback review logs into a local eval dataset."""
    dataset_root = config.dataset_root.resolve()
    _ensure_dataset_layout(dataset_root)

    downloader = audio_downloader or _download_audio_reference
    database_url = resolve_database_url(config.database_url, base_dir=BACKEND_ROOT)

    exported_sample_ids: list[str] = []
    skipped_existing: list[str] = []
    errors: list[dict[str, Any]] = []
    selected_count = 0

    engine = create_engine(database_url)
    try:
        with Session(engine) as db:
            if config.source == "review_logs":
                selected_count = _export_from_review_logs(
                    db=db,
                    config=config,
                    downloader=downloader,
                    dataset_root=dataset_root,
                    exported_sample_ids=exported_sample_ids,
                    skipped_existing=skipped_existing,
                    errors=errors,
                )
            elif config.source == "cards":
                selected_count = _export_from_cards(
                    db=db,
                    config=config,
                    downloader=downloader,
                    dataset_root=dataset_root,
                    exported_sample_ids=exported_sample_ids,
                    skipped_existing=skipped_existing,
                    errors=errors,
                )
            else:
                raise EvalWorkflowError(f"Unsupported export source: {config.source}")
    finally:
        engine.dispose()

    manifest = rebuild_single_feedback_dataset_manifest(dataset_root)
    provenance = _build_dataset_provenance(
        configured_database_url=config.database_url,
        resolved_database_url=database_url,
    )
    export_report = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_role": "offline_snapshot",
        "source_of_truth": "review_log/user_card_srs tables in the configured runtime database",
        "exported_at": _utc_now_iso(),
        "selected_records": selected_count,
        "exported_sample_ids": exported_sample_ids,
        "skipped_existing": skipped_existing,
        "errors": errors,
        "dataset_manifest_fingerprint": manifest["dataset_fingerprint"],
        "source_database": provenance,
    }
    report_path = dataset_root / "exports" / f"{_timestamp_slug()}_export.json"
    _write_json(report_path, export_report)
    manifest["dataset_role"] = "offline_snapshot"
    manifest["source_of_truth"] = (
        "review_log/user_card_srs tables in the configured runtime database"
    )
    manifest["last_export"] = {
        "export_report_file": str(report_path.relative_to(dataset_root)),
        "source_database": provenance,
    }
    _write_json(dataset_root / "dataset_manifest.json", manifest)
    return export_report


def rebuild_single_feedback_dataset_manifest(dataset_root: Path) -> dict[str, Any]:
    """Rebuild dataset index and manifest from sample metadata on disk."""
    dataset_root = dataset_root.resolve()
    _ensure_dataset_layout(dataset_root)

    sample_entries: list[dict[str, Any]] = []
    for metadata_path in sorted((dataset_root / "samples").glob("*/metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        sample_id = str(metadata["sample_id"])
        entry = {
            "sample_id": sample_id,
            "task": metadata["task"],
            "split": metadata["split"],
            "sample_dir": f"samples/{sample_id}",
            "ready_for_eval": metadata.get("ready_for_eval", False),
            "record_source": metadata["source"].get("record_source", "review_logs"),
            "review_log_id": metadata["source"].get("review_log_id"),
            "deck_id": metadata["source"]["deck_id"],
            "card_id": metadata["source"]["card_id"],
            "input_fingerprint": metadata["input_fingerprint"],
        }
        sample_entries.append(entry)

    sample_entries.sort(key=lambda item: item["sample_id"])

    sample_index_path = dataset_root / "sample_index.jsonl"
    lines = [json.dumps(entry, ensure_ascii=False) for entry in sample_entries]
    sample_index_path.write_text("\n".join(lines) + ("\n" if lines else ""), encoding="utf-8")

    split_counts: dict[str, int] = {}
    ready_counts = {"ready": 0, "reference_only": 0}
    for entry in sample_entries:
        split_counts[entry["split"]] = split_counts.get(entry["split"], 0) + 1
        if entry["ready_for_eval"]:
            ready_counts["ready"] += 1
        else:
            ready_counts["reference_only"] += 1

    manifest = {
        "schema_version": DATASET_SCHEMA_VERSION,
        "dataset_name": "gemini_single_feedback_eval",
        "task": "single_feedback",
        "updated_at": _utc_now_iso(),
        "sample_count": len(sample_entries),
        "split_counts": split_counts,
        "readiness_counts": ready_counts,
        "sample_index_file": sample_index_path.name,
        "dataset_fingerprint": _sha256_json(sample_entries),
    }
    _write_json(dataset_root / "dataset_manifest.json", manifest)
    return manifest


def run_single_feedback_eval(
    config: PromptEvalConfig,
    *,
    adapter_factory: AdapterFactory | None = None,
) -> dict[str, Any]:
    """Run one or more prompt variants against a fixed local dataset."""
    from app.adapters.gemini_adapter import GenerationConfig, GeminiAdapter

    dataset_root = config.dataset_root.resolve()
    manifest_path = dataset_root / "dataset_manifest.json"
    if not manifest_path.exists():
        raise EvalWorkflowError(
            f"Dataset manifest not found: {manifest_path}. Run export first."
        )
    if not config.variants:
        raise EvalWorkflowError("At least one prompt variant is required")

    samples = _load_dataset_samples(
        dataset_root=dataset_root,
        split=config.split,
        sample_ids=config.sample_ids,
        limit=config.limit,
    )
    if not samples:
        raise EvalWorkflowError("No dataset samples matched the current eval filters")

    generation_config = config.generation_config or GenerationConfig()

    adapter = adapter_factory() if adapter_factory else GeminiAdapter()
    if config.model_id:
        adapter.model_id = config.model_id

    selected_sample_fingerprint = _sha256_json(
        [
            {
                "sample_id": sample.sample_id,
                "input_fingerprint": sample.metadata["input_fingerprint"],
            }
            for sample in samples
        ]
    )

    run_id = _timestamp_slug()
    run_root = dataset_root / "runs" / run_id
    (run_root / "variants").mkdir(parents=True, exist_ok=True)

    variant_summaries: list[dict[str, Any]] = []
    comparison: dict[str, dict[str, str]] = {}

    for variant in config.variants:
        prompt_dir = variant.prompt_dir.resolve()
        prompt_template = adapter.load_prompt_from_dir(prompt_dir)
        variant_dir = run_root / "variants" / variant.name
        prompt_snapshot_dir = variant_dir / "prompt_snapshot"
        sample_outputs_dir = variant_dir / "samples"
        prompt_snapshot_dir.mkdir(parents=True, exist_ok=True)
        sample_outputs_dir.mkdir(parents=True, exist_ok=True)

        _snapshot_prompt_dir(prompt_dir, prompt_snapshot_dir)
        prompt_fingerprint = _fingerprint_prompt_dir(prompt_dir)
        results: list[dict[str, Any]] = []

        for sample in samples:
            started = time.perf_counter()
            sample_record: dict[str, Any] = {
                "sample_id": sample.sample_id,
                "variant": variant.name,
                "status": "completed",
                "input_fingerprint": sample.metadata["input_fingerprint"],
                "input": {
                    "front_text": sample.front_text,
                    "user_audio_file": str(sample.user_audio_path.relative_to(sample.sample_dir)),
                    "reference_audio_file": str(
                        sample.reference_audio_path.relative_to(sample.sample_dir)
                    ),
                },
                "source_output": sample.source_output,
            }
            try:
                output = adapter.generate_single_feedback(
                    front_text=sample.front_text,
                    user_audio_url=sample.user_audio_path.resolve().as_uri(),
                    reference_audio_url=sample.reference_audio_path.resolve().as_uri(),
                    prompt_template=prompt_template,
                    generation_config=generation_config,
                )
                sample_record["output"] = output
                sample_record["output_fingerprint"] = _sha256_json(output)
            except Exception as exc:
                sample_record["status"] = "failed"
                sample_record["error"] = str(exc)

            duration_ms = int((time.perf_counter() - started) * 1000)
            sample_record["duration_ms"] = duration_ms

            output_path = sample_outputs_dir / f"{sample.sample_id}.json"
            _write_json(output_path, sample_record)
            results.append(
                {
                    "sample_id": sample.sample_id,
                    "status": sample_record["status"],
                    "duration_ms": duration_ms,
                    "output_fingerprint": sample_record.get("output_fingerprint"),
                    "output_file": str(output_path.relative_to(run_root)),
                }
            )
            comparison.setdefault(sample.sample_id, {})[variant.name] = str(
                output_path.relative_to(run_root)
            )

        _write_jsonl(variant_dir / "results.jsonl", results)
        variant_summary = {
            "name": variant.name,
            "prompt_dir": str(prompt_dir),
            "prompt_fingerprint": prompt_fingerprint,
            "prompt_metadata": prompt_template.metadata,
            "results_file": str((variant_dir / "results.jsonl").relative_to(run_root)),
            "sample_count": len(results),
        }
        _write_json(variant_dir / "variant_manifest.json", variant_summary)
        variant_summaries.append(variant_summary)

    run_manifest = {
        "schema_version": RUN_SCHEMA_VERSION,
        "run_id": run_id,
        "task": "single_feedback",
        "created_at": _utc_now_iso(),
        "dataset_root": str(dataset_root),
        "dataset_manifest_fingerprint": json.loads(
            manifest_path.read_text(encoding="utf-8")
        )["dataset_fingerprint"],
        "selected_sample_fingerprint": selected_sample_fingerprint,
        "sample_count": len(samples),
        "model_id": adapter.model_id,
        "generation_config": {
            key: value
            for key, value in {
                "temperature": generation_config.temperature,
                "max_output_tokens": generation_config.max_output_tokens,
            }.items()
            if value is not None
        },
        "variants": variant_summaries,
    }
    _write_json(run_root / "run_manifest.json", run_manifest)
    _write_json(run_root / "comparison.json", comparison)
    return run_manifest


def _load_dataset_samples(
    dataset_root: Path,
    *,
    split: str | None,
    sample_ids: tuple[str, ...],
    limit: int | None,
) -> list[DatasetSample]:
    sample_id_filter = set(sample_ids)
    samples: list[DatasetSample] = []
    for metadata_path in sorted((dataset_root / "samples").glob("*/metadata.json")):
        metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
        if split and metadata.get("split") != split:
            continue
        if not metadata.get("ready_for_eval", False):
            continue
        sample_id = str(metadata["sample_id"])
        if sample_id_filter and sample_id not in sample_id_filter:
            continue

        sample_dir = metadata_path.parent
        input_payload = json.loads((sample_dir / "input.json").read_text(encoding="utf-8"))
        source_output_path = sample_dir / "source_output.json"
        source_output = None
        if source_output_path.exists():
            source_output = json.loads(source_output_path.read_text(encoding="utf-8"))

        samples.append(
            DatasetSample(
                sample_id=sample_id,
                sample_dir=sample_dir,
                metadata=metadata,
                input_payload=input_payload,
                source_output=source_output,
            )
        )
        if limit is not None and len(samples) >= limit:
            break
    return samples


def _download_audio_reference(audio_ref: str, target_path: Path) -> dict[str, Any]:
    from app.adapters.oss_adapter import OSSAdapter

    source_url = audio_ref.strip()
    if not source_url:
        raise EvalWorkflowError("Audio reference is empty")

    if source_url.startswith(("http://", "https://", "file://")):
        resolved_url = source_url
    else:
        oss_adapter = OSSAdapter()
        object_name = _normalize_object_name(source_url)
        resolved_url = oss_adapter.generate_signed_url(object_name, expires=3600)

    with urlopen(resolved_url, timeout=30) as response:
        payload = response.read()
        if not payload:
            raise EvalWorkflowError(f"Downloaded empty audio payload from {audio_ref}")
        target_path.write_bytes(payload)
        mime_type = response.headers.get_content_type()

    return {
        "local_file": target_path.name,
        "mime_type": mime_type,
        "bytes": target_path.stat().st_size,
        "sha256": _sha256_file(target_path),
    }


def _export_from_review_logs(
    *,
    db: Session,
    config: DatasetExportConfig,
    downloader: AudioDownloader,
    dataset_root: Path,
    exported_sample_ids: list[str],
    skipped_existing: list[str],
    errors: list[dict[str, Any]],
) -> int:
    statement = (
        select(ReviewLog, Card, Deck)
        .join(Card, ReviewLog.card_id == Card.id)
        .join(Deck, ReviewLog.deck_id == Deck.id)
        .where(
            ReviewLog.result_type == "single",
            ReviewLog.status == "completed",
        )
        .order_by(ReviewLog.id)
    )

    if config.deck_ids:
        statement = statement.where(ReviewLog.deck_id.in_(config.deck_ids))
    if config.review_log_ids:
        statement = statement.where(ReviewLog.id.in_(config.review_log_ids))
    if config.limit is not None:
        statement = statement.limit(config.limit)

    rows = db.execute(statement).all()
    for review_log, card, deck in rows:
        sample_id = _build_review_log_sample_id(review_log.id)
        sample_dir = dataset_root / "samples" / sample_id
        metadata_path = sample_dir / "metadata.json"

        if metadata_path.exists() and not config.overwrite:
            skipped_existing.append(sample_id)
            continue

        ai_feedback_json = review_log.ai_feedback_json or {}
        user_audio_ref = ai_feedback_json.get("oss_path")
        reference_audio_ref = ai_feedback_json.get("reference_audio_path") or card.audio_path

        if not user_audio_ref or not reference_audio_ref:
            errors.append(
                {
                    "sample_id": sample_id,
                    "review_log_id": review_log.id,
                    "error": "Missing user or reference audio reference",
                }
            )
            continue

        try:
            sample_dir.mkdir(parents=True, exist_ok=True)
            user_target = sample_dir / f"user_audio{_infer_audio_suffix(user_audio_ref)}"
            ref_target = sample_dir / (
                f"reference_audio{_infer_audio_suffix(reference_audio_ref)}"
            )

            user_audio_meta = downloader(user_audio_ref, user_target)
            reference_audio_meta = downloader(reference_audio_ref, ref_target)

            input_payload = {
                "task": "single_feedback",
                "front_text": card.front_text,
                "user_audio_file": user_target.name,
                "reference_audio_file": ref_target.name,
            }
            source_output = {
                "transcription": ai_feedback_json.get("transcription", {}),
                "feedback": ai_feedback_json.get("feedback", {}),
                "realtime_session_id": ai_feedback_json.get("realtime_session_id"),
            }
            metadata = {
                "schema_version": DATASET_SCHEMA_VERSION,
                "sample_id": sample_id,
                "task": "single_feedback",
                "split": config.split,
                "created_at": _utc_now_iso(),
                "ready_for_eval": True,
                "source": {
                    "record_source": "review_logs",
                    "review_log_id": review_log.id,
                    "card_id": card.id,
                    "deck_id": deck.id,
                    "deck_title": deck.title,
                    "review_created_at": from_storage_local(review_log.created_at).isoformat(),
                },
                "text": {
                    "front_text": card.front_text,
                    "back_text": card.back_text,
                },
                "audio": {
                    "user": {
                        "source_ref": user_audio_ref,
                        **user_audio_meta,
                    },
                    "reference": {
                        "source_ref": reference_audio_ref,
                        **reference_audio_meta,
                    },
                },
                "reference_output_file": "source_output.json",
                "input_file": "input.json",
            }
            metadata["input_fingerprint"] = _sha256_json(
                {
                    "front_text": card.front_text,
                    "user_audio_sha256": user_audio_meta["sha256"],
                    "reference_audio_sha256": reference_audio_meta["sha256"],
                }
            )

            _write_json(sample_dir / "input.json", input_payload)
            _write_json(sample_dir / "source_output.json", source_output)
            _write_json(metadata_path, metadata)
            exported_sample_ids.append(sample_id)
        except Exception as exc:
            errors.append(
                {
                    "sample_id": sample_id,
                    "review_log_id": review_log.id,
                    "error": str(exc),
                }
            )
    return len(rows)


def _export_from_cards(
    *,
    db: Session,
    config: DatasetExportConfig,
    downloader: AudioDownloader,
    dataset_root: Path,
    exported_sample_ids: list[str],
    skipped_existing: list[str],
    errors: list[dict[str, Any]],
) -> int:
    statement = (
        select(Card, Deck)
        .join(Deck, Card.deck_id == Deck.id)
        .where(Card.audio_path.is_not(None))
        .order_by(Card.id)
    )

    if config.deck_ids:
        statement = statement.where(Card.deck_id.in_(config.deck_ids))
    if config.limit is not None:
        statement = statement.limit(config.limit)

    rows = db.execute(statement).all()
    for card, deck in rows:
        audio_path = (card.audio_path or "").strip()
        if not audio_path:
            continue

        sample_id = _build_card_sample_id(card.id)
        sample_dir = dataset_root / "samples" / sample_id
        metadata_path = sample_dir / "metadata.json"

        if metadata_path.exists() and not config.overwrite:
            skipped_existing.append(sample_id)
            continue

        try:
            sample_dir.mkdir(parents=True, exist_ok=True)
            ref_target = sample_dir / f"reference_audio{_infer_audio_suffix(audio_path)}"
            reference_audio_meta = downloader(audio_path, ref_target)
            input_payload = {
                "task": "single_feedback",
                "front_text": card.front_text,
                "user_audio_file": None,
                "reference_audio_file": ref_target.name,
            }
            metadata = {
                "schema_version": DATASET_SCHEMA_VERSION,
                "sample_id": sample_id,
                "task": "single_feedback",
                "split": config.split,
                "created_at": _utc_now_iso(),
                "ready_for_eval": False,
                "source": {
                    "record_source": "cards",
                    "review_log_id": None,
                    "card_id": card.id,
                    "deck_id": deck.id,
                    "deck_title": deck.title,
                },
                "text": {
                    "front_text": card.front_text,
                    "back_text": card.back_text,
                },
                "audio": {
                    "user": None,
                    "reference": {
                        "source_ref": audio_path,
                        **reference_audio_meta,
                    },
                },
                "reference_output_file": None,
                "input_file": "input.json",
            }
            metadata["input_fingerprint"] = _sha256_json(
                {
                    "front_text": card.front_text,
                    "reference_audio_sha256": reference_audio_meta["sha256"],
                }
            )
            _write_json(sample_dir / "input.json", input_payload)
            _write_json(metadata_path, metadata)
            exported_sample_ids.append(sample_id)
        except Exception as exc:
            errors.append(
                {
                    "sample_id": sample_id,
                    "card_id": card.id,
                    "error": str(exc),
                }
            )
    return len(rows)


def _normalize_object_name(audio_ref: str) -> str:
    parsed = urlparse(audio_ref)
    if parsed.scheme == "oss":
        object_name = parsed.path.lstrip("/")
        if not object_name:
            raise EvalWorkflowError(f"Invalid OSS reference: {audio_ref}")
        return object_name
    return audio_ref


def _build_dataset_provenance(
    *,
    configured_database_url: str,
    resolved_database_url: str,
) -> dict[str, Any]:
    url = make_url(resolved_database_url)
    sqlite_path = None
    if url.drivername == "sqlite" and url.database and url.database != ":memory:":
        sqlite_path = str(Path(url.database).resolve())

    return {
        "configured_url": configured_database_url,
        "resolved_url": resolved_database_url,
        "sqlite_path": sqlite_path,
    }


def _ensure_dataset_layout(dataset_root: Path) -> None:
    for subdir in ("samples", "runs", "exports"):
        (dataset_root / subdir).mkdir(parents=True, exist_ok=True)


def _snapshot_prompt_dir(prompt_dir: Path, target_dir: Path) -> None:
    for filename in ("system.md", "user.md", "metadata.json"):
        source = prompt_dir / filename
        if source.exists():
            shutil.copy2(source, target_dir / filename)


def _fingerprint_prompt_dir(prompt_dir: Path) -> str:
    payload = {}
    for filename in ("system.md", "user.md", "metadata.json"):
        path = prompt_dir / filename
        payload[filename] = path.read_text(encoding="utf-8") if path.exists() else ""
    return _sha256_json(payload)


def _build_review_log_sample_id(review_log_id: int) -> str:
    return f"sf-{review_log_id:06d}"


def _build_card_sample_id(card_id: int) -> str:
    return f"card-{card_id:06d}"


def _infer_audio_suffix(audio_ref: str) -> str:
    path = urlparse(audio_ref).path or audio_ref
    suffix = Path(path).suffix.lower()
    if suffix in {".wav", ".webm", ".mp3", ".m4a", ".ogg"}:
        return suffix
    return ".bin"


def _utc_now_iso() -> str:
    return to_utc(app_now()).isoformat()


def _timestamp_slug() -> str:
    return to_utc(app_now()).strftime("%Y%m%dT%H%M%SZ")


def _sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _sha256_json(payload: Any) -> str:
    serialized = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(serialized.encode("utf-8")).hexdigest()


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")
