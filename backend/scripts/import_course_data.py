#!/usr/bin/env python3
"""
Import course data from processed JSON files and audio to database + OSS.

Stages:
1. Discovery: Scan data directory and validate files
2. Database: Import deck hierarchy and cards
3. Upload: Upload audio files to OSS
4. Verify: Verify import completeness

Usage:
    # Full import
    uv run python scripts/import_course_data.py --data-dir /path/to/data --all

    # Stage-specific execution
    uv run python scripts/import_course_data.py --phase discover
    uv run python scripts/import_course_data.py --phase database
    uv run python scripts/import_course_data.py --phase upload
    uv run python scripts/import_course_data.py --phase verify

    # Resume from checkpoint
    uv run python scripts/import_course_data.py --resume

    # Dry run (no actual changes)
    uv run python scripts/import_course_data.py --dry-run
"""

import argparse
import json
import os
import re
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy.orm import Session

from app.adapters.oss_adapter import OSSAdapter
from app.database import SessionLocal
from app.models.card import Card
from app.models.deck import Deck
from app.models.user_card_srs import UserCardSRS
from app.repositories.card_repo import CardRepository
from app.repositories.deck_repo import DeckRepository
from app.repositories.srs_repo import SRSRepository
from app.utils.timezone import app_now, storage_now

# Progress tracking file
PROGRESS_FILE = ".import_progress.json"


class ImportProgress:
    """Track import progress for resume capability."""

    def __init__(self, filepath: str = PROGRESS_FILE):
        self.filepath = filepath
        self.data: dict[str, Any] = self._load()

    def _load(self) -> dict[str, Any]:
        """Load progress from file."""
        if os.path.exists(self.filepath):
            with open(self.filepath) as f:
                return json.load(f)
        return {
            "completed_lessons": [],
            "uploaded_cards": [],
            "source_ids": {},
            "unit_ids": {},
            "lesson_ids": {},
            "timestamp": None,
        }

    def save(self):
        """Save progress to file."""
        self.data["timestamp"] = app_now().isoformat()
        with open(self.filepath, "w") as f:
            json.dump(self.data, f, indent=2)

    def is_lesson_completed(self, lesson_tag: str) -> bool:
        """Check if lesson is already imported."""
        return lesson_tag in self.data["completed_lessons"]

    def mark_lesson_completed(self, lesson_tag: str):
        """Mark lesson as imported."""
        if lesson_tag not in self.data["completed_lessons"]:
            self.data["completed_lessons"].append(lesson_tag)

    def is_card_uploaded(self, card_id: int) -> bool:
        """Check if card audio is already uploaded."""
        return card_id in self.data["uploaded_cards"]

    def mark_card_uploaded(self, card_id: int):
        """Mark card audio as uploaded."""
        if card_id not in self.data["uploaded_cards"]:
            self.data["uploaded_cards"].append(card_id)

    def get_source_id(self, source_name: str) -> int | None:
        """Get cached source deck ID."""
        return self.data["source_ids"].get(source_name)

    def set_source_id(self, source_name: str, deck_id: int):
        """Cache source deck ID."""
        self.data["source_ids"][source_name] = deck_id

    def get_unit_id(self, unit_key: str) -> int | None:
        """Get cached unit deck ID."""
        return self.data["unit_ids"].get(unit_key)

    def set_unit_id(self, unit_key: str, deck_id: int):
        """Cache unit deck ID."""
        self.data["unit_ids"][unit_key] = deck_id

    def get_lesson_id(self, lesson_tag: str) -> int | None:
        """Get cached lesson deck ID."""
        return self.data["lesson_ids"].get(lesson_tag)

    def set_lesson_id(self, lesson_tag: str, deck_id: int):
        """Cache lesson deck ID."""
        self.data["lesson_ids"][lesson_tag] = deck_id

    def reset(self):
        """Reset all progress."""
        self.data = {
            "completed_lessons": [],
            "uploaded_cards": [],
            "source_ids": {},
            "unit_ids": {},
            "lesson_ids": {},
            "timestamp": None,
        }
        if os.path.exists(self.filepath):
            os.remove(self.filepath)


class CourseDataImporter:
    """Import course data from processed files."""

    def __init__(self, data_dir: str, dry_run: bool = False):
        """Initialize importer.

        Args:
            data_dir: Path to processed course data directory
            dry_run: If True, don't make actual changes
        """
        self.data_dir = Path(data_dir)
        self.dry_run = dry_run
        self.progress = ImportProgress()

        # Statistics
        self.stats = {
            "lessons_found": 0,
            "lessons_with_json": 0,
            "lessons_audio_only": 0,
            "total_audio_files": 0,
            "sources_created": 0,
            "units_created": 0,
            "lessons_created": 0,
            "cards_created": 0,
            "srs_states_created": 0,
            "files_uploaded": 0,
            "upload_failed": 0,
        }

        # Source name mapping
        self.source_names = {
            "C18": "C18 English Conversation",
            "C19": "C19 English Conversation",
            "C20": "C20 English Conversation",
            "NCE2": "New Concept English Book 2",
        }

    def parse_lesson_tag(self, lesson_tag: str) -> dict[str, Any] | None:
        """Parse lesson tag into components.

        Args:
            lesson_tag: e.g., "NCE2_01-03" or "C18_01-01"

        Returns:
            Dict with source, unit, lesson, or None if invalid
        """
        match = re.match(r"^(C18|C19|C20|NCE2)_(\d+)-(\d+)$", lesson_tag)
        if not match:
            return None

        source, unit, lesson = match.groups()
        return {
            "source": source,
            "unit": int(unit),
            "lesson": int(lesson),
            "tag": lesson_tag,
        }

    def discover(self) -> dict[str, Any]:
        """Stage 1: Discover and validate course data.

        Returns:
            Discovery manifest with all lesson metadata
        """
        print("\n" + "=" * 60)
        print("STAGE 1: DISCOVERY & VALIDATION")
        print("=" * 60)

        if not self.data_dir.exists():
            raise FileNotFoundError(f"Data directory not found: {self.data_dir}")

        manifest = {
            "lessons": [],
            "sources": defaultdict(lambda: {"units": defaultdict(list)}),
        }

        # Scan all lesson directories
        lesson_dirs = sorted([d for d in self.data_dir.iterdir() if d.is_dir()])

        for lesson_dir in lesson_dirs:
            lesson_tag = lesson_dir.name
            parsed = self.parse_lesson_tag(lesson_tag)

            if not parsed:
                print(f"⚠️  Skipping invalid lesson tag: {lesson_tag}")
                continue

            self.stats["lessons_found"] += 1

            # Check for JSON metadata
            json_file = lesson_dir / f"{lesson_tag}_data.json"
            has_json = json_file.exists()

            if has_json:
                self.stats["lessons_with_json"] += 1
            else:
                self.stats["lessons_audio_only"] += 1

            # Find audio files
            audio_files = []
            audio_dir = lesson_dir / "audio"
            if audio_dir.exists():
                audio_files = sorted(list(audio_dir.glob("*.mp3")))
            else:
                # Audio files might be directly in lesson dir
                audio_files = sorted(list(lesson_dir.glob("*.mp3")))

            self.stats["total_audio_files"] += len(audio_files)

            lesson_info = {
                **parsed,
                "dir": str(lesson_dir),
                "has_json": has_json,
                "json_file": str(json_file) if has_json else None,
                "audio_files": [str(f) for f in audio_files],
                "audio_count": len(audio_files),
            }

            manifest["lessons"].append(lesson_info)

            # Group by source and unit
            source = parsed["source"]
            unit = parsed["unit"]
            manifest["sources"][source]["units"][unit].append(lesson_info)

        # Print summary
        print(f"\n✓ Found {self.stats['lessons_found']} lessons")
        print(f"  • {self.stats['lessons_with_json']} with JSON metadata")
        print(f"  • {self.stats['lessons_audio_only']} audio-only")
        print(f"  • {self.stats['total_audio_files']} total audio files")

        print(f"\n✓ Found {len(manifest['sources'])} sources:")
        for source_code, source_data in sorted(manifest["sources"].items()):
            unit_count = len(source_data["units"])
            lesson_count = sum(
                len(lessons) for lessons in source_data["units"].values()
            )
            print(f"  • {source_code}: {unit_count} units, {lesson_count} lessons")

        return manifest

    def import_database(
        self, manifest: dict[str, Any], db: Session
    ) -> dict[str, int]:
        """Stage 2: Import deck hierarchy and cards to database.

        Args:
            manifest: Discovery manifest from stage 1
            db: Database session

        Returns:
            Mapping of lesson tags to card IDs
        """
        print("\n" + "=" * 60)
        print("STAGE 2: DATABASE IMPORT")
        print("=" * 60)

        deck_repo = DeckRepository(db)
        card_repo = CardRepository(db)
        srs_repo = SRSRepository(db)

        card_mapping = {}  # {lesson_tag: [card_ids]}

        # Create sources
        print("\n[1/4] Creating source decks...")
        source_decks = {}
        for idx, (source_code, source_data) in enumerate(
            sorted(manifest["sources"].items())
        ):
            # Check if source already exists
            existing_id = self.progress.get_source_id(source_code)
            if existing_id:
                existing = deck_repo.get_by_id(existing_id)
                if existing:
                    source_decks[source_code] = existing
                    print(f"  ✓ Reusing existing source: {source_code}")
                    continue

            source_name = self.source_names.get(source_code, source_code)

            if not self.dry_run:
                # Check if already exists by title
                existing_sources = deck_repo.get_all_sources()
                existing = next(
                    (s for s in existing_sources if s.title == source_name), None
                )

                if existing:
                    source_decks[source_code] = existing
                    print(f"  ✓ Reusing existing source: {source_code}")
                else:
                    source_deck = deck_repo.create(
                        title=source_name,
                        type="source",
                        level_index=idx,
                    )
                    db.flush()
                    source_decks[source_code] = source_deck
                    self.stats["sources_created"] += 1
                    print(f"  ✓ Created source: {source_code}")

                self.progress.set_source_id(source_code, source_decks[source_code].id)
                self.progress.save()

        # Create units
        print("\n[2/4] Creating unit decks...")
        unit_decks = {}  # {(source, unit): Deck}
        for source_code, source_data in sorted(manifest["sources"].items()):
            source_deck = source_decks.get(source_code)

            for unit_num in sorted(source_data["units"].keys()):
                unit_key = f"{source_code}_U{unit_num}"
                existing_id = self.progress.get_unit_id(unit_key)

                if existing_id:
                    existing = deck_repo.get_by_id(existing_id)
                    if existing:
                        unit_decks[(source_code, unit_num)] = existing
                        continue

                unit_title = f"Unit {unit_num}"

                if not self.dry_run:
                    # Check if already exists
                    existing_units = deck_repo.get_children(source_deck.id)
                    existing = next(
                        (u for u in existing_units if u.title == unit_title), None
                    )

                    if existing:
                        unit_decks[(source_code, unit_num)] = existing
                    else:
                        unit_deck = deck_repo.create(
                            title=unit_title,
                            type="unit",
                            parent_id=source_deck.id,
                            level_index=unit_num,
                        )
                        db.flush()
                        unit_decks[(source_code, unit_num)] = unit_deck
                        self.stats["units_created"] += 1

                    self.progress.set_unit_id(
                        unit_key, unit_decks[(source_code, unit_num)].id
                    )
                    self.progress.save()

        print(f"  ✓ Created {self.stats['units_created']} units")

        # Create lessons and cards
        print("\n[3/4] Creating lessons and cards...")
        for lesson_info in manifest["lessons"]:
            lesson_tag = lesson_info["tag"]

            # Skip if already completed
            if self.progress.is_lesson_completed(lesson_tag):
                print(f"  ⏭️  Skipping completed: {lesson_tag}")
                continue

            source = lesson_info["source"]
            unit = lesson_info["unit"]
            lesson_num = lesson_info["lesson"]

            unit_deck = unit_decks.get((source, unit))
            if not unit_deck:
                print(f"  ⚠️  Unit deck not found for {lesson_tag}")
                continue

            try:
                if not self.dry_run:
                    # Check if lesson already exists
                    existing_id = self.progress.get_lesson_id(lesson_tag)
                    if existing_id:
                        lesson_deck = deck_repo.get_by_id(existing_id)
                    else:
                        lesson_title = f"Lesson {lesson_num}"
                        lesson_deck = deck_repo.create(
                            title=lesson_title,
                            type="lesson",
                            parent_id=unit_deck.id,
                            level_index=lesson_num,
                        )
                        db.flush()
                        self.stats["lessons_created"] += 1
                        self.progress.set_lesson_id(lesson_tag, lesson_deck.id)

                    # Create cards
                    cards_created = []

                    if lesson_info["has_json"]:
                        # Import from JSON
                        with open(lesson_info["json_file"]) as f:
                            data = json.load(f)

                        for idx, sentence in enumerate(data["sentences"]):
                            audio_filename = sentence["audio_file"]
                            audio_path = f"lessons/{source}/{unit:02d}-{lesson_num:02d}/{audio_filename}"

                            card = Card(
                                deck_id=lesson_deck.id,
                                card_index=idx,
                                front_text=sentence["english_text"],
                                back_text=sentence.get("chinese_translation"),
                                audio_path=audio_path,
                            )
                            db.add(card)
                            db.flush()

                            # Create SRS state
                            srs = UserCardSRS(
                                card_id=card.id,
                                state="learning",
                                step=0,
                                stability=None,
                                difficulty=None,
                                due=storage_now(),
                                last_review=None,
                            )
                            db.add(srs)

                            cards_created.append(card.id)
                            self.stats["cards_created"] += 1
                            self.stats["srs_states_created"] += 1

                    else:
                        # Audio-only lesson - create placeholder cards
                        for idx, audio_file in enumerate(lesson_info["audio_files"]):
                            audio_filename = Path(audio_file).name
                            audio_path = f"lessons/{source}/{unit:02d}-{lesson_num:02d}/{audio_filename}"

                            card = Card(
                                deck_id=lesson_deck.id,
                                card_index=idx,
                                front_text=f"[Audio {idx + 1}]",
                                back_text=None,
                                audio_path=audio_path,
                            )
                            db.add(card)
                            db.flush()

                            # Create SRS state
                            srs = UserCardSRS(
                                card_id=card.id,
                                state="learning",
                                step=0,
                                stability=None,
                                difficulty=None,
                                due=storage_now(),
                                last_review=None,
                            )
                            db.add(srs)

                            cards_created.append(card.id)
                            self.stats["cards_created"] += 1
                            self.stats["srs_states_created"] += 1

                    db.commit()
                    card_mapping[lesson_tag] = cards_created

                    self.progress.mark_lesson_completed(lesson_tag)
                    self.progress.save()

                    print(
                        f"  ✓ {lesson_tag}: {len(cards_created)} cards "
                        f"({'JSON' if lesson_info['has_json'] else 'audio-only'})"
                    )

            except Exception as e:
                db.rollback()
                print(f"  ❌ Failed to import {lesson_tag}: {e}")
                continue

        print(
            f"\n✓ Created {self.stats['lessons_created']} lessons, "
            f"{self.stats['cards_created']} cards, "
            f"{self.stats['srs_states_created']} SRS states"
        )

        return card_mapping

    def upload_audio(self, manifest: dict[str, Any], db: Session):
        """Stage 3: Upload audio files to OSS.

        Args:
            manifest: Discovery manifest from stage 1
            db: Database session
        """
        print("\n" + "=" * 60)
        print("STAGE 3: OSS AUDIO UPLOAD")
        print("=" * 60)

        if self.dry_run:
            print("⚠️  Dry run mode - skipping actual upload")
            return

        oss = OSSAdapter()

        # Collect all audio files to upload
        upload_tasks = []  # [(local_path, oss_path, card_id)]

        for lesson_info in manifest["lessons"]:
            lesson_tag = lesson_info["tag"]
            source = lesson_info["source"]
            unit = lesson_info["unit"]
            lesson_num = lesson_info["lesson"]

            # Get cards for this lesson
            lesson_id = self.progress.get_lesson_id(lesson_tag)
            if not lesson_id:
                continue

            cards = (
                db.query(Card)
                .filter(Card.deck_id == lesson_id)
                .order_by(Card.card_index)
                .all()
            )

            for card in cards:
                # Skip if already uploaded
                if self.progress.is_card_uploaded(card.id):
                    continue

                # Find corresponding audio file
                audio_filename = Path(card.audio_path).name

                # Try audio/ subdirectory first
                audio_path = Path(lesson_info["dir"]) / "audio" / audio_filename
                if not audio_path.exists():
                    # Try lesson directory
                    audio_path = Path(lesson_info["dir"]) / audio_filename

                if not audio_path.exists():
                    print(f"  ⚠️  Audio file not found: {audio_filename}")
                    continue

                oss_path = card.audio_path
                upload_tasks.append((str(audio_path), oss_path, card.id))

        total = len(upload_tasks)
        print(f"\n✓ Found {total} audio files to upload")

        if total == 0:
            return

        # Upload in batches
        batch_size = 50
        for i in range(0, total, batch_size):
            batch = upload_tasks[i : i + batch_size]
            batch_num = i // batch_size + 1
            total_batches = (total + batch_size - 1) // batch_size

            print(f"\n[Batch {batch_num}/{total_batches}] Uploading {len(batch)} files...")

            # Prepare batch
            files_to_upload = [(local, oss) for local, oss, _ in batch]

            # Upload batch
            results = oss.batch_upload_files(files_to_upload, max_workers=10)

            # Update database and progress
            for local_path, oss_path, card_id in batch:
                if results.get(oss_path):
                    self.progress.mark_card_uploaded(card_id)
                    self.stats["files_uploaded"] += 1
                else:
                    self.stats["upload_failed"] += 1
                    print(f"  ❌ Failed to upload: {Path(local_path).name}")

            # Save progress after each batch
            self.progress.save()

            uploaded = i + len(batch)
            percentage = (uploaded / total) * 100
            print(f"  Progress: {uploaded}/{total} ({percentage:.1f}%)")

        print(
            f"\n✓ Upload complete: {self.stats['files_uploaded']} succeeded, "
            f"{self.stats['upload_failed']} failed"
        )

    def verify(self, db: Session) -> dict[str, Any]:
        """Stage 4: Verify import completeness.

        Args:
            db: Database session

        Returns:
            Verification report
        """
        print("\n" + "=" * 60)
        print("STAGE 4: VERIFICATION")
        print("=" * 60)

        report = {
            "sources": 0,
            "units": 0,
            "lessons": 0,
            "cards": 0,
            "srs_states": 0,
            "cards_with_audio": 0,
            "issues": [],
        }

        # Count decks
        report["sources"] = db.query(Deck).filter_by(type="source").count()
        report["units"] = db.query(Deck).filter_by(type="unit").count()
        report["lessons"] = db.query(Deck).filter_by(type="lesson").count()

        # Count cards and SRS states
        report["cards"] = db.query(Card).count()
        report["srs_states"] = db.query(UserCardSRS).count()
        report["cards_with_audio"] = (
            db.query(Card).filter(Card.audio_path.isnot(None)).count()
        )

        # Check for issues
        expected_sources = len(self.source_names)
        if report["sources"] != expected_sources:
            report["issues"].append(
                f"Expected {expected_sources} sources, found {report['sources']}"
            )

        if report["lessons"] != self.stats["lessons_found"]:
            report["issues"].append(
                f"Expected {self.stats['lessons_found']} lessons, "
                f"found {report['lessons']}"
            )

        if report["cards"] != self.stats["cards_created"]:
            report["issues"].append(
                f"Expected {self.stats['cards_created']} cards, "
                f"found {report['cards']}"
            )

        if report["srs_states"] != report["cards"]:
            report["issues"].append(
                f"SRS state count ({report['srs_states']}) "
                f"doesn't match card count ({report['cards']})"
            )

        if report["cards_with_audio"] != report["cards"]:
            report["issues"].append(
                f"Only {report['cards_with_audio']}/{report['cards']} "
                "cards have audio paths"
            )

        # Print report
        print("\n" + "-" * 60)
        print("VERIFICATION REPORT")
        print("-" * 60)
        print(f"Sources:           {report['sources']}")
        print(f"Units:             {report['units']}")
        print(f"Lessons:           {report['lessons']}")
        print(f"Cards:             {report['cards']}")
        print(f"SRS States:        {report['srs_states']}")
        print(f"Cards with Audio:  {report['cards_with_audio']}")

        if report["issues"]:
            print("\n⚠️  Issues found:")
            for issue in report["issues"]:
                print(f"  • {issue}")
        else:
            print("\n✓ All checks passed!")

        return report

    def run_all(self):
        """Run all import stages."""
        start_time = time.perf_counter()

        # Stage 1: Discovery
        manifest = self.discover()

        # Stage 2: Database import
        db = SessionLocal()
        try:
            card_mapping = self.import_database(manifest, db)
        finally:
            db.close()

        # Stage 3: OSS upload
        db = SessionLocal()
        try:
            self.upload_audio(manifest, db)
        finally:
            db.close()

        # Stage 4: Verification
        db = SessionLocal()
        try:
            report = self.verify(db)
        finally:
            db.close()

        # Print summary
        duration = time.perf_counter() - start_time
        print("\n" + "=" * 60)
        print("IMPORT COMPLETE")
        print("=" * 60)
        print(f"Duration: {duration:.1f}s")
        print(f"\nStatistics:")
        for key, value in self.stats.items():
            print(f"  {key}: {value}")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(description="Import course data to database and OSS")
    parser.add_argument(
        "--data-dir",
        default="/Users/damien/Desktop/LanProject/LanGear/2_processed_output/new_processed",
        help="Path to processed course data directory",
    )
    parser.add_argument(
        "--phase",
        choices=["discover", "database", "upload", "verify"],
        help="Run specific phase only",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help="Run all phases",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Dry run (no actual changes)",
    )
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Resume from previous checkpoint",
    )
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Reset progress and start fresh",
    )

    args = parser.parse_args()

    # Validate arguments
    if not args.phase and not args.all and not args.reset:
        parser.error("Must specify --phase, --all, or --reset")

    importer = CourseDataImporter(args.data_dir, dry_run=args.dry_run)

    # Handle reset
    if args.reset:
        print("Resetting import progress...")
        importer.progress.reset()
        print("✓ Progress reset complete")
        return

    # Run requested phases
    if args.all:
        importer.run_all()
    elif args.phase == "discover":
        importer.discover()
    elif args.phase == "database":
        manifest = importer.discover()
        db = SessionLocal()
        try:
            importer.import_database(manifest, db)
        finally:
            db.close()
    elif args.phase == "upload":
        manifest = importer.discover()
        db = SessionLocal()
        try:
            importer.upload_audio(manifest, db)
        finally:
            db.close()
    elif args.phase == "verify":
        db = SessionLocal()
        try:
            importer.verify(db)
        finally:
            db.close()


if __name__ == "__main__":
    main()
