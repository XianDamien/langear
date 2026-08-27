"""Unit tests for offline single-feedback dataset export and prompt eval workflow."""

import json
from pathlib import Path
from unittest.mock import Mock

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from app.adapters.gemini_adapter import GenerationConfig, PromptTemplate
from app.database import Base
from app.evals.single_feedback import (
    DatasetExportConfig,
    PromptEvalConfig,
    PromptVariant,
    export_single_feedback_dataset,
    rebuild_single_feedback_dataset_manifest,
    run_single_feedback_eval,
)


def _write_prompt_dir(prompt_dir: Path) -> None:
    prompt_dir.mkdir(parents=True, exist_ok=True)
    (prompt_dir / "system.md").write_text("system", encoding="utf-8")
    (prompt_dir / "user.md").write_text("user", encoding="utf-8")
    (prompt_dir / "metadata.json").write_text(
        json.dumps({"tracking_commit": "test-commit"}),
        encoding="utf-8",
    )


def test_export_single_feedback_dataset_creates_local_sample_archive(
    tmp_path: Path,
):
    from tests.test_data.seed_data import create_test_review_log
    from tests.test_data.seed_data import create_test_card_with_srs

    db_path = tmp_path / "eval.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        sample_card_with_srs = create_test_card_with_srs(session)
        card = sample_card_with_srs["card"]
        lesson = sample_card_with_srs["lesson"]
        review_log = create_test_review_log(
            session,
            card_id=card.id,
            deck_id=lesson.id,
            status="completed",
            rating="good",
        )
        review_log.ai_feedback_json = {
            "transcription": {"text": "sample transcription", "timestamps": []},
            "feedback": {"pronunciation": "ok", "completeness": "ok", "fluency": "ok"},
            "oss_path": "recordings/20260321/user.wav",
            "reference_audio_path": "lessons/20260321/ref.mp3",
            "realtime_session_id": "rt-1",
        }
        session.commit()
        review_log_id = review_log.id
        front_text = card.front_text

    def fake_downloader(audio_ref: str, target_path: Path) -> dict[str, object]:
        target_path.write_bytes(f"bytes:{audio_ref}".encode("utf-8"))
        return {
            "local_file": target_path.name,
            "mime_type": "audio/wav",
            "bytes": target_path.stat().st_size,
            "sha256": "hash-" + target_path.stem,
        }

    report = export_single_feedback_dataset(
        DatasetExportConfig(
            dataset_root=tmp_path / "dataset",
            database_url=f"sqlite:///{db_path}",
        ),
        audio_downloader=fake_downloader,
    )

    sample_id = f"sf-{review_log_id:06d}"
    assert report["exported_sample_ids"] == [sample_id]

    sample_dir = tmp_path / "dataset" / "samples" / sample_id
    metadata = json.loads((sample_dir / "metadata.json").read_text(encoding="utf-8"))
    input_payload = json.loads((sample_dir / "input.json").read_text(encoding="utf-8"))
    source_output = json.loads((sample_dir / "source_output.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (tmp_path / "dataset" / "dataset_manifest.json").read_text(encoding="utf-8")
    )

    assert metadata["source"]["review_log_id"] == review_log_id
    assert input_payload["front_text"] == front_text
    assert source_output["transcription"]["text"] == "sample transcription"
    assert manifest["sample_count"] == 1
    assert manifest["dataset_role"] == "offline_snapshot"
    assert manifest["last_export"]["source_database"]["resolved_url"] == f"sqlite:///{db_path}"
    assert report["source_database"]["sqlite_path"] == str(db_path.resolve())


def test_export_single_feedback_dataset_from_cards_creates_reference_only_samples(
    tmp_path: Path,
):
    from tests.test_data.seed_data import create_test_card_with_srs

    db_path = tmp_path / "cards.sqlite3"
    engine = create_engine(f"sqlite:///{db_path}")
    SessionLocal = sessionmaker(bind=engine)
    Base.metadata.create_all(bind=engine)

    with SessionLocal() as session:
        sample_card_with_srs = create_test_card_with_srs(session)
        card = sample_card_with_srs["card"]
        lesson = sample_card_with_srs["lesson"]
        card.audio_path = "lessons/ref-audio.mp3"
        session.commit()
        card_id = card.id
        deck_id = lesson.id
        front_text = card.front_text

    def fake_downloader(audio_ref: str, target_path: Path) -> dict[str, object]:
        target_path.write_bytes(f"bytes:{audio_ref}".encode("utf-8"))
        return {
            "local_file": target_path.name,
            "mime_type": "audio/mpeg",
            "bytes": target_path.stat().st_size,
            "sha256": "hash-" + target_path.stem,
        }

    report = export_single_feedback_dataset(
        DatasetExportConfig(
            dataset_root=tmp_path / "dataset",
            database_url=f"sqlite:///{db_path}",
            source="cards",
        ),
        audio_downloader=fake_downloader,
    )

    sample_id = f"card-{card_id:06d}"
    assert report["exported_sample_ids"] == [sample_id]

    sample_dir = tmp_path / "dataset" / "samples" / sample_id
    metadata = json.loads((sample_dir / "metadata.json").read_text(encoding="utf-8"))
    input_payload = json.loads((sample_dir / "input.json").read_text(encoding="utf-8"))
    manifest = json.loads(
        (tmp_path / "dataset" / "dataset_manifest.json").read_text(encoding="utf-8")
    )

    assert metadata["ready_for_eval"] is False
    assert metadata["source"]["record_source"] == "cards"
    assert metadata["source"]["card_id"] == card_id
    assert metadata["source"]["deck_id"] == deck_id
    assert input_payload["front_text"] == front_text
    assert input_payload["user_audio_file"] is None
    assert manifest["readiness_counts"]["reference_only"] == 1
    assert report["dataset_role"] == "offline_snapshot"


def test_run_single_feedback_eval_records_variant_outputs(tmp_path: Path):
    dataset_root = tmp_path / "dataset"
    sample_dir = dataset_root / "samples" / "sf-000001"
    sample_dir.mkdir(parents=True, exist_ok=True)
    (sample_dir / "user_audio.wav").write_bytes(b"user-audio")
    (sample_dir / "reference_audio.mp3").write_bytes(b"ref-audio")
    (sample_dir / "input.json").write_text(
        json.dumps(
            {
                "task": "single_feedback",
                "front_text": "Hello world.",
                "user_audio_file": "user_audio.wav",
                "reference_audio_file": "reference_audio.mp3",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    (sample_dir / "source_output.json").write_text(
        json.dumps({"feedback": {"pronunciation": "历史输出"}}) + "\n",
        encoding="utf-8",
    )
    (sample_dir / "metadata.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "sample_id": "sf-000001",
                "task": "single_feedback",
                "split": "eval",
                "ready_for_eval": True,
                "source": {"review_log_id": 1, "deck_id": 2, "card_id": 3},
                "input_fingerprint": "sample-hash",
            }
        )
        + "\n",
        encoding="utf-8",
    )
    rebuild_single_feedback_dataset_manifest(dataset_root)

    prompt_dir = tmp_path / "prompt-baseline"
    _write_prompt_dir(prompt_dir)

    fake_adapter = Mock()
    fake_adapter.model_id = "gemini-test-model"
    fake_adapter.load_prompt_from_dir.return_value = PromptTemplate(
        system="system",
        user="user",
        metadata={"tracking_commit": "test-commit"},
    )
    fake_adapter.generate_single_feedback.return_value = {
        "transcription_text": "Hello world",
        "pronunciation": "ok",
        "completeness": "ok",
        "fluency": "ok",
        "suggestions": [],
        "issues": [],
    }

    manifest = run_single_feedback_eval(
        PromptEvalConfig(
            dataset_root=dataset_root,
            variants=(PromptVariant(name="baseline", prompt_dir=prompt_dir),),
            generation_config=GenerationConfig(
                temperature=0.1,
                max_output_tokens=512,
            ),
        ),
        adapter_factory=lambda: fake_adapter,
    )

    run_root = dataset_root / "runs" / manifest["run_id"]
    sample_result = json.loads(
        (
            run_root / "variants" / "baseline" / "samples" / "sf-000001.json"
        ).read_text(encoding="utf-8")
    )
    comparison = json.loads((run_root / "comparison.json").read_text(encoding="utf-8"))

    assert manifest["sample_count"] == 1
    assert sample_result["status"] == "completed"
    assert sample_result["output"]["transcription_text"] == "Hello world"
    assert comparison["sf-000001"]["baseline"].endswith("sf-000001.json")
    fake_adapter.generate_single_feedback.assert_called_once()
