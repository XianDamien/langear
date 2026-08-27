"""
Unit tests for CardRepository.

Tests card repository operations including:
- Getting cards by lesson
- Getting card by ID
- Creating cards
- Counting cards
- Card ordering
"""

import pytest
from sqlalchemy.orm import Session
from app.repositories.card_repo import CardRepository
from app.models.deck import Deck
from app.models.card import Card


@pytest.mark.unit
class TestCardRepository:
    """Test CardRepository operations."""

    def test_get_by_id_found(self, test_db: Session):
        """Test getting a card by ID when it exists."""
        repo = CardRepository(test_db)

        # Create lesson and card
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        card = Card(
            deck_id=lesson.id,
            card_index=0,
            front_text="Hello",
            back_text="你好",
            audio_path="audio/test.wav"
        )
        test_db.add(card)
        test_db.commit()

        # Get by ID
        result = repo.get_by_id(card.id)

        assert result is not None
        assert result.id == card.id
        assert result.front_text == "Hello"
        assert result.back_text == "你好"

    def test_get_by_id_not_found(self, test_db: Session):
        """Test getting a card by ID when it doesn't exist."""
        repo = CardRepository(test_db)

        result = repo.get_by_id(99999)

        assert result is None

    def test_get_by_lesson_empty(self, test_db: Session):
        """Test getting cards from a lesson with no cards."""
        repo = CardRepository(test_db)

        # Create lesson without cards
        lesson = Deck(title="Empty Lesson", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.commit()

        cards = repo.get_by_lesson(lesson.id)

        assert cards == []

    def test_get_by_lesson_single_card(self, test_db: Session):
        """Test getting a single card from a lesson."""
        repo = CardRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        # Create card
        card = Card(
            deck_id=lesson.id,
            card_index=0,
            front_text="Good morning",
            back_text="早上好",
            audio_path="audio/card0.wav"
        )
        test_db.add(card)
        test_db.commit()

        cards = repo.get_by_lesson(lesson.id)

        assert len(cards) == 1
        assert cards[0].front_text == "Good morning"
        assert cards[0].deck_id == lesson.id

    def test_get_by_lesson_multiple_cards_ordered(self, test_db: Session):
        """Test getting multiple cards ordered by card_index."""
        repo = CardRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        # Create cards out of order
        card2 = Card(
            deck_id=lesson.id,
            card_index=2,
            front_text="Goodbye",
            back_text="再见"
        )
        card0 = Card(
            deck_id=lesson.id,
            card_index=0,
            front_text="Hello",
            back_text="你好"
        )
        card1 = Card(
            deck_id=lesson.id,
            card_index=1,
            front_text="Thank you",
            back_text="谢谢"
        )

        test_db.add_all([card2, card0, card1])
        test_db.commit()

        cards = repo.get_by_lesson(lesson.id)

        assert len(cards) == 3
        assert cards[0].front_text == "Hello"
        assert cards[1].front_text == "Thank you"
        assert cards[2].front_text == "Goodbye"
        assert cards[0].card_index == 0
        assert cards[1].card_index == 1
        assert cards[2].card_index == 2

    def test_get_by_lesson_only_correct_lesson(self, test_db: Session):
        """Test that get_by_lesson only returns cards from the specified lesson."""
        repo = CardRepository(test_db)

        # Create two lessons
        lesson1 = Deck(title="Lesson 1", type="lesson", level_index=0)
        lesson2 = Deck(title="Lesson 2", type="lesson", level_index=1)
        test_db.add_all([lesson1, lesson2])
        test_db.flush()

        # Create cards in both lessons
        card1 = Card(deck_id=lesson1.id, card_index=0, front_text="Card 1", back_text="卡片1")
        card2 = Card(deck_id=lesson2.id, card_index=0, front_text="Card 2", back_text="卡片2")
        test_db.add_all([card1, card2])
        test_db.commit()

        # Get cards from lesson1
        cards = repo.get_by_lesson(lesson1.id)

        assert len(cards) == 1
        assert cards[0].front_text == "Card 1"
        assert cards[0].deck_id == lesson1.id

    def test_create_card_minimal(self, test_db: Session):
        """Test creating a card with minimal fields."""
        repo = CardRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        # Create card with only required fields
        card = repo.create(
            deck_id=lesson.id,
            card_index=0,
            front_text="Hello world"
        )

        assert card.id is not None
        assert card.deck_id == lesson.id
        assert card.card_index == 0
        assert card.front_text == "Hello world"
        assert card.back_text is None
        assert card.audio_path is None

    def test_create_card_complete(self, test_db: Session):
        """Test creating a card with all fields."""
        repo = CardRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        # Create card with all fields
        card = repo.create(
            deck_id=lesson.id,
            card_index=5,
            front_text="How are you?",
            back_text="你好吗？",
            audio_path="audio/nce2/unit1/lesson1/5.wav"
        )

        assert card.id is not None
        assert card.deck_id == lesson.id
        assert card.card_index == 5
        assert card.front_text == "How are you?"
        assert card.back_text == "你好吗？"
        assert card.audio_path == "audio/nce2/unit1/lesson1/5.wav"
        assert card.created_at is not None

    def test_create_multiple_cards(self, test_db: Session):
        """Test creating multiple cards in sequence."""
        repo = CardRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        # Create multiple cards
        sentences = [
            ("I am a student.", "我是学生。"),
            ("This is a book.", "这是一本书。"),
            ("Nice to meet you.", "很高兴见到你。")
        ]

        for i, (front, back) in enumerate(sentences):
            card = repo.create(
                deck_id=lesson.id,
                card_index=i,
                front_text=front,
                back_text=back,
                audio_path=f"audio/card{i}.wav"
            )
            assert card.card_index == i

        # Verify all cards created
        cards = repo.get_by_lesson(lesson.id)
        assert len(cards) == 3

    def test_count_by_lesson_empty(self, test_db: Session):
        """Test counting cards in an empty lesson."""
        repo = CardRepository(test_db)

        # Create lesson without cards
        lesson = Deck(title="Empty Lesson", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.commit()

        count = repo.count_by_lesson(lesson.id)

        assert count == 0

    def test_count_by_lesson_with_cards(self, test_db: Session):
        """Test counting cards in a lesson with cards."""
        repo = CardRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        # Create cards
        for i in range(10):
            card = Card(
                deck_id=lesson.id,
                card_index=i,
                front_text=f"Sentence {i}",
                back_text=f"句子{i}"
            )
            test_db.add(card)
        test_db.commit()

        count = repo.count_by_lesson(lesson.id)

        assert count == 10

    def test_count_by_lesson_only_counts_correct_lesson(self, test_db: Session):
        """Test that count_by_lesson only counts cards from the specified lesson."""
        repo = CardRepository(test_db)

        # Create two lessons
        lesson1 = Deck(title="Lesson 1", type="lesson", level_index=0)
        lesson2 = Deck(title="Lesson 2", type="lesson", level_index=1)
        test_db.add_all([lesson1, lesson2])
        test_db.flush()

        # Create cards in lesson1
        for i in range(5):
            card = Card(deck_id=lesson1.id, card_index=i, front_text=f"Card {i}")
            test_db.add(card)

        # Create cards in lesson2
        for i in range(3):
            card = Card(deck_id=lesson2.id, card_index=i, front_text=f"Card {i}")
            test_db.add(card)

        test_db.commit()

        # Count should be correct for each lesson
        assert repo.count_by_lesson(lesson1.id) == 5
        assert repo.count_by_lesson(lesson2.id) == 3

    def test_card_with_long_text(self, test_db: Session):
        """Test creating a card with long text content."""
        repo = CardRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        # Create card with long text
        long_text = "This is a very long sentence that contains multiple clauses and demonstrates that the system can handle longer text content without any issues."

        card = repo.create(
            deck_id=lesson.id,
            card_index=0,
            front_text=long_text,
            back_text="这是一个非常长的句子，包含多个从句，并证明系统可以处理较长的文本内容而不会出现任何问题。"
        )

        assert card.front_text == long_text
        assert len(card.front_text) > 100

    def test_card_with_special_characters(self, test_db: Session):
        """Test creating a card with special characters."""
        repo = CardRepository(test_db)

        # Create lesson
        lesson = Deck(title="Lesson 1", type="lesson", level_index=0)
        test_db.add(lesson)
        test_db.flush()

        # Create card with special characters
        card = repo.create(
            deck_id=lesson.id,
            card_index=0,
            front_text="Hello! How are you? I'm fine, thanks.",
            back_text="你好！你好吗？我很好，谢谢。"
        )

        assert "!" in card.front_text
        assert "?" in card.front_text
        assert "'" in card.front_text
        assert "！" in card.back_text
