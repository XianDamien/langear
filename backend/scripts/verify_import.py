#!/usr/bin/env python3
"""
Verify course data import completeness.

Usage:
    uv run python scripts/verify_import.py
"""

import sys
from pathlib import Path

# Add parent directory to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import func

from app.database import SessionLocal
from app.models.card import Card
from app.models.deck import Deck
from app.models.user_card_srs import UserCardSRS


def verify_import() -> dict:
    """Comprehensive verification after import.

    Returns:
        Verification report with counts and issues
    """
    db = SessionLocal()
    try:
        report = {
            "sources": 0,
            "units": 0,
            "lessons": 0,
            "cards": 0,
            "srs_states": 0,
            "cards_with_audio": 0,
            "orphaned_cards": 0,
            "cards_without_srs": 0,
            "issues": [],
        }

        # Count decks by type
        report["sources"] = db.query(Deck).filter_by(type="source").count()
        report["units"] = db.query(Deck).filter_by(type="unit").count()
        report["lessons"] = db.query(Deck).filter_by(type="lesson").count()

        # Count cards
        report["cards"] = db.query(Card).count()
        report["srs_states"] = db.query(UserCardSRS).count()
        report["cards_with_audio"] = (
            db.query(Card).filter(Card.audio_path.isnot(None)).count()
        )

        # Check for orphaned cards (cards without valid deck)
        orphaned = (
            db.query(Card)
            .outerjoin(Deck, Card.deck_id == Deck.id)
            .filter(Deck.id.is_(None))
            .count()
        )
        report["orphaned_cards"] = orphaned

        # Check for cards without SRS state
        cards_without_srs = (
            db.query(Card)
            .outerjoin(UserCardSRS, Card.id == UserCardSRS.card_id)
            .filter(UserCardSRS.card_id.is_(None))
            .count()
        )
        report["cards_without_srs"] = cards_without_srs

        # Expected values
        expected_sources = 4
        expected_lessons = 72

        # Validate counts
        if report["sources"] != expected_sources:
            report["issues"].append(
                f"Expected {expected_sources} sources, found {report['sources']}"
            )

        if report["lessons"] != expected_lessons:
            report["issues"].append(
                f"Expected {expected_lessons} lessons, found {report['lessons']}"
            )

        if report["cards"] == 0:
            report["issues"].append("No cards found in database")

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

        if report["orphaned_cards"] > 0:
            report["issues"].append(f"Found {orphaned} orphaned cards (no valid deck)")

        if report["cards_without_srs"] > 0:
            report["issues"].append(
                f"Found {cards_without_srs} cards without SRS state"
            )

        # Get source details
        sources = db.query(Deck).filter_by(type="source").all()
        report["source_details"] = []

        for source in sources:
            # Count units directly under this source
            units = db.query(Deck).filter_by(type="unit", parent_id=source.id).count()

            # Count lessons under units of this source
            unit_ids = [
                u.id
                for u in db.query(Deck.id)
                .filter_by(type="unit", parent_id=source.id)
                .all()
            ]
            lessons = (
                db.query(Deck)
                .filter(Deck.type == "lesson", Deck.parent_id.in_(unit_ids))
                .count()
            )

            # Count cards in lessons of this source
            lesson_ids = [
                l.id
                for l in db.query(Deck.id)
                .filter(Deck.type == "lesson", Deck.parent_id.in_(unit_ids))
                .all()
            ]
            cards = db.query(Card).filter(Card.deck_id.in_(lesson_ids)).count()

            report["source_details"].append(
                {
                    "name": source.title,
                    "units": units,
                    "lessons": lessons,
                    "cards": cards,
                }
            )

        return report

    finally:
        db.close()


def print_report(report: dict):
    """Print verification report.

    Args:
        report: Verification report dictionary
    """
    print("\n" + "=" * 60)
    print("IMPORT VERIFICATION REPORT")
    print("=" * 60)

    print("\nOverall Statistics:")
    print(f"  Sources:           {report['sources']} ✓")
    print(f"  Units:             {report['units']} ✓")
    print(f"  Lessons:           {report['lessons']} ✓")
    print(f"  Cards:             {report['cards']} ✓")
    print(f"  SRS States:        {report['srs_states']} ✓")
    print(f"  Cards with Audio:  {report['cards_with_audio']} ✓")

    if report.get("source_details"):
        print("\nSource Breakdown:")
        for source in report["source_details"]:
            print(f"\n  {source['name']}:")
            print(f"    Units:   {source['units']}")
            print(f"    Lessons: {source['lessons']}")
            print(f"    Cards:   {source['cards']}")

    if report["issues"]:
        print("\n" + "⚠️  " * 20)
        print("ISSUES FOUND:")
        for issue in report["issues"]:
            print(f"  ❌ {issue}")
        print("⚠️  " * 20)
        print("\nStatus: ❌ Issues detected")
        return False
    else:
        print("\n" + "✓" * 60)
        print("Status: ✓ All checks passed")
        print("✓" * 60)
        return True


def main():
    """Main entry point."""
    try:
        report = verify_import()
        success = print_report(report)
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Verification failed: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
