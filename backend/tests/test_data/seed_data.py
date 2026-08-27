"""Test data generation utilities for seeding the test database."""

from datetime import datetime, timedelta

from sqlalchemy.orm import Session

from app.models import Card, Deck, ReviewLog, Setting, User, UserCardSRS, UserSettings
from app.utils.timezone import storage_now


def _build_srs_snapshot(bucket: str, now: datetime) -> dict:
    """Return a native FSRS snapshot payload for the requested test bucket."""
    snapshots = {
        "new": {
            "state": "learning",
            "step": 0,
            "stability": None,
            "difficulty": None,
            "due": now,
            "last_review": None,
        },
        "learning": {
            "state": "learning",
            "step": 1,
            "stability": 1.0,
            "difficulty": 5.0,
            "due": now - timedelta(hours=1),
            "last_review": now - timedelta(hours=2),
        },
        "review": {
            "state": "review",
            "step": None,
            "stability": 7.0,
            "difficulty": 4.0,
            "due": now - timedelta(days=1),
            "last_review": now - timedelta(days=2),
        },
        "relearning": {
            "state": "relearning",
            "step": 0,
            "stability": 2.0,
            "difficulty": 6.0,
            "due": now,
            "last_review": now - timedelta(days=1),
        },
    }

    if bucket not in snapshots:
        raise ValueError(f"Invalid SRS bucket: {bucket}")

    return snapshots[bucket].copy()


def create_full_deck_tree(db: Session) -> dict:
    """
    Create a complete deck tree structure for testing.

    Creates:
    - 1 Source deck (NCE Book 2)
    - 1 Unit deck (Unit 1)
    - 1 Lesson deck (Lesson 1)
    - 5 Cards with corresponding SRS states

    Returns:
        dict: {"source": Deck, "unit": Deck, "lesson": Deck, "cards": [Card, ...]}
    """
    # Create source deck
    source = Deck(
        title="New Concept English Book 2",
        type="source",
        level_index=0,
        parent_id=None
    )
    db.add(source)
    db.flush()

    # Create unit deck
    unit = Deck(
        title="Unit 1: Getting Started",
        type="unit",
        level_index=0,
        parent_id=source.id
    )
    db.add(unit)
    db.flush()

    # Create lesson deck
    lesson = Deck(
        title="Lesson 1: A Private Conversation",
        type="lesson",
        level_index=0,
        parent_id=unit.id
    )
    db.add(lesson)
    db.flush()

    # Create 5 cards
    cards = []
    test_sentences = [
        ("Last week I went to the theatre.", "上周我去了剧院。"),
        ("I had a very good seat.", "我的座位很好。"),
        ("The play was very interesting.", "这出戏很有意思。"),
        ("I did not enjoy it.", "但我却无法欣赏。"),
        ("A young man and a young woman were sitting behind me.", "一青年男子与一青年女子坐在我的身后。")
    ]

    for i, (front, back) in enumerate(test_sentences):
        card = Card(
            deck_id=lesson.id,
            card_index=i,
            front_text=front,
            back_text=back,
            audio_path=f"audio/nce2/unit1/lesson1/{i}.wav"
        )
        db.add(card)
        db.flush()

        # All cards start in the business "new" bucket as native initial snapshots.
        srs = UserCardSRS(
            card_id=card.id,
            **_build_srs_snapshot("new", storage_now() - timedelta(hours=1)),
        )
        db.add(srs)
        cards.append(card)

    db.commit()

    return {
        "source": source,
        "unit": unit,
        "lesson": lesson,
        "cards": cards
    }


def create_test_card_with_srs(
    db: Session,
    lesson_id: int | None = None,
    bucket: str = "new",
) -> dict:
    """
    Create a single test card with SRS state.

    Args:
        db: Database session
        lesson_id: Optional lesson ID to attach the card to (creates new lesson if None)
        bucket: Business bucket / native state preset:
            "new", "learning", "review", "relearning"

    Returns:
        dict: {"card": Card, "srs": UserCardSRS, "lesson": Deck}
    """
    # Create lesson if not provided
    if lesson_id is None:
        source = Deck(title="Test Source", type="source", level_index=0)
        db.add(source)
        db.flush()

        unit = Deck(title="Test Unit", type="unit", level_index=0, parent_id=source.id)
        db.add(unit)
        db.flush()

        lesson = Deck(title="Test Lesson", type="lesson", level_index=0, parent_id=unit.id)
        db.add(lesson)
        db.flush()
        lesson_id = lesson.id
    else:
        lesson = db.query(Deck).filter(Deck.id == lesson_id).first()

    # Create card
    card = Card(
        deck_id=lesson_id,
        card_index=0,
        front_text="Test sentence for review.",
        back_text="测试复习句子。",
        audio_path="audio/test/0.wav"
    )
    db.add(card)
    db.flush()

    snapshot = _build_srs_snapshot(bucket, storage_now())
    srs = UserCardSRS(card_id=card.id, **snapshot)
    db.add(srs)
    db.commit()

    return {
        "card": card,
        "srs": srs,
        "lesson": lesson
    }


def create_test_review_log(
    db: Session,
    card_id: int,
    deck_id: int,
    status: str = "completed",
    rating: str = "good",
    result_type: str = "single"
) -> ReviewLog:
    """
    Create a test review log.

    Args:
        db: Database session
        card_id: Card ID being reviewed (can be None for summary)
        deck_id: Deck/Lesson ID
        status: "processing", "completed", or "failed"
        rating: "again", "hard", "good", or "easy" (None for summary)
        result_type: "single" or "summary"

    Returns:
        ReviewLog: Created review log
    """
    # Base log data
    ai_feedback = {}

    # Add completion data if status is completed
    if status == "completed":
        if result_type == "single":
            ai_feedback = {
                "transcription": {
                    "text": "Test transcription text",
                    "timestamps": [
                        {"word": "Test", "start": 0.0, "end": 0.3},
                        {"word": "transcription", "start": 0.3, "end": 0.9},
                        {"word": "text", "start": 0.9, "end": 1.2}
                    ]
                },
                "feedback": {
                    "pronunciation": "Good pronunciation",
                    "completeness": "Complete sentence",
                    "fluency": "Natural fluency",
                    "suggestions": [
                        {
                            "text": "Keep up the good work!",
                            "target_word": None,
                            "timestamp": None,
                        }
                    ],
                    "issues": [],
                },
                "srs_update": {
                    "state": "review",
                    "due": (datetime.now() + timedelta(days=3)).isoformat(),
                    "stability": 7.0,
                    "difficulty": 4.5
                }
            }
        else:  # summary
            ai_feedback = {
                "overall_performance": "Good progress on this lesson",
                "strengths": ["Clear pronunciation", "Good fluency"],
                "areas_for_improvement": ["Completeness of sentences"],
                "recommendations": ["Practice longer sentences"]
            }

    log = ReviewLog(
        card_id=card_id,
        deck_id=deck_id,
        rating=rating,
        result_type=result_type,
        ai_feedback_json=ai_feedback,
        status=status,
        error_code="ASR_ERROR" if status == "failed" else None,
        error_message="Test error: ASR service unavailable" if status == "failed" else None
    )

    db.add(log)
    db.commit()

    return log


def create_test_settings(db: Session) -> list[Setting]:
    """
    Create test settings entries.

    Returns:
        list[Setting]: Created settings
    """
    settings_data = [
        {"key": "daily_new_limit", "value": 20},
        {"key": "daily_review_limit", "value": 50},
        {"key": "max_interval", "value": 365},
        {"key": "enable_audio", "value": True},
    ]

    settings = []
    for data in settings_data:
        setting = Setting(
            key=data["key"],
            value=data["value"]
        )
        db.add(setting)
        settings.append(setting)

    db.commit()
    return settings


def create_test_user_settings(
    db: Session,
    user_id: int = 1,
) -> UserSettings:
    """Create a default user_settings row for tests."""
    user = db.query(User).filter(User.id == user_id).first()
    if user is None:
        user = User(id=user_id, username=f"user-{user_id}")
        db.add(user)
        db.flush()

    settings = UserSettings(
        user_id=user_id,
        desired_retention=0.9,
        learning_steps_json=[15],
        relearning_steps_json=[15],
        maximum_interval=36500,
        default_source_scope_json=[1, 2],
    )
    db.add(settings)
    db.commit()
    return settings


def create_multiple_review_logs(
    db: Session,
    card_id: int,
    deck_id: int,
    count: int = 5,
    days_ago: int = 7
) -> list[ReviewLog]:
    """
    Create multiple review logs for statistics testing.

    Args:
        db: Database session
        card_id: Card ID
        deck_id: Deck/Lesson ID
        count: Number of logs to create
        days_ago: Create logs starting from this many days ago

    Returns:
        list[ReviewLog]: Created review logs
    """
    logs = []
    ratings = ["again", "hard", "good", "easy"]

    for i in range(count):
        rating = ratings[i % len(ratings)]
        created_at = storage_now() - timedelta(days=days_ago - i)

        log = ReviewLog(
            card_id=card_id,
            deck_id=deck_id,
            rating=rating,
            result_type="single",
            ai_feedback_json={
                "transcription": {"text": f"Review {i} transcription", "timestamps": []},
                "feedback": {
                    "pronunciation": "Good",
                    "completeness": "Complete",
                    "fluency": "Fluent"
                },
                "srs_update": {
                    "state": "review",
                    "due": (created_at + timedelta(days=3)).isoformat(),
                    "stability": 5.0 + i,
                    "difficulty": 5.0
                }
            },
            status="completed",
            created_at=created_at
        )
        db.add(log)
        logs.append(log)

    db.commit()
    return logs
