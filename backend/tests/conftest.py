"""
Core pytest configuration for LanGear backend tests.

Provides test database setup, FastAPI TestClient, and mock fixtures
for all external services (OSS, ASR, Gemini, FSRS).
"""

import os
from typing import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

os.environ.setdefault("DATABASE_URL", "sqlite:///:memory:")
os.environ.setdefault("APP_TIMEZONE", "Asia/Shanghai")
os.environ.setdefault("GEMINI_API_KEY", "test-gemini-key")
os.environ.setdefault("GEMINI_MODEL_ID", "gemini-test-model")
os.environ.setdefault("OSS_ACCESS_KEY_ID", "test-oss-key")
os.environ.setdefault("OSS_ACCESS_KEY_SECRET", "test-oss-secret")
os.environ.setdefault("OSS_ENDPOINT", "oss-cn-test.aliyuncs.com")
os.environ.setdefault("OSS_BUCKET_NAME", "test-bucket")
os.environ.setdefault("DASHSCOPE_API_KEY", "test-dashscope-key")

from app.database import Base, get_db
from app.main import app


# ============================================================================
# Test Database Configuration
# ============================================================================

test_engine = create_engine(
    "sqlite:///:memory:",
    connect_args={"check_same_thread": False},
)

TestSessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=test_engine
)


@pytest.fixture(scope="session", autouse=True)
def setup_test_database():
    """Create all tables before any tests run."""
    Base.metadata.create_all(bind=test_engine)
    yield
    Base.metadata.drop_all(bind=test_engine)


@pytest.fixture(scope="function")
def test_db() -> Generator[Session, None, None]:
    """
    Provide a test database session with transaction isolation.

    Each test function gets a fresh session in a transaction that's
    automatically rolled back after the test completes, ensuring
    complete data isolation between tests.
    """
    connection = test_engine.connect()
    transaction = connection.begin()
    session = TestSessionLocal(bind=connection)

    yield session

    session.close()
    transaction.rollback()
    connection.close()


@pytest.fixture(scope="function")
def client(test_db: Session) -> Generator[TestClient, None, None]:
    """Provide a FastAPI TestClient with test database dependency override."""
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db

    with TestClient(app) as test_client:
        yield test_client

    app.dependency_overrides.clear()


# ============================================================================
# Mock Fixtures for External Services
# ============================================================================

@pytest.fixture
def mock_oss_adapter(monkeypatch):
    """Mock OSSAdapter to avoid real Aliyun OSS API calls."""

    def mock_generate_signed_url(self, object_name: str, expires: int = 3600) -> str:
        return f"https://mocked-oss-url.com/{object_name}?expires={expires}&signed=true"

    def mock_upload_file_from_path(self, local_path: str, object_path: str) -> bool:
        return True

    def mock_generate_sts_token(self, duration: int = 3600) -> dict:
        return {
            "access_key_id": "STS.MockAccessKeyId",
            "access_key_secret": "MockAccessKeySecret",
            "security_token": "MockSecurityToken",
            "expiration": "2026-12-31T23:59:59Z",
            "bucket": "mock-bucket",
            "region": "oss-cn-shanghai",
            "upload_prefix": "recordings",
        }

    monkeypatch.setattr("app.adapters.oss_adapter.OSSAdapter.generate_signed_url", mock_generate_signed_url)
    monkeypatch.setattr("app.adapters.oss_adapter.OSSAdapter.upload_file_from_path", mock_upload_file_from_path)
    monkeypatch.setattr("app.adapters.oss_adapter.OSSAdapter.generate_sts_token", mock_generate_sts_token)


@pytest.fixture
def mock_asr_adapter(monkeypatch):
    """Mock ASRAdapter to avoid real Dashscope API calls."""

    def mock_transcribe(self, audio_url: str, timeout: int = 60) -> dict:
        return {
            "text": "This is a test transcription from the mocked ASR service",
            "timestamps": [
                {"word": "This", "start": 0.0, "end": 0.3},
                {"word": "is", "start": 0.3, "end": 0.45},
                {"word": "a", "start": 0.45, "end": 0.55},
                {"word": "test", "start": 0.55, "end": 0.85},
                {"word": "transcription", "start": 0.85, "end": 1.5},
                {"word": "from", "start": 1.5, "end": 1.7},
                {"word": "the", "start": 1.7, "end": 1.85},
                {"word": "mocked", "start": 1.85, "end": 2.2},
                {"word": "ASR", "start": 2.2, "end": 2.5},
                {"word": "service", "start": 2.5, "end": 2.9}
            ]
        }

    monkeypatch.setattr("app.adapters.asr_adapter.ASRAdapter.transcribe", mock_transcribe)


@pytest.fixture
def mock_gemini_adapter(monkeypatch):
    """Mock GeminiAdapter to avoid real Google Gemini API calls."""

    def mock_generate_single_feedback(
        self,
        front_text: str,
        user_audio_url: str,
        reference_audio_url: str,
    ) -> dict:
        _ = user_audio_url, reference_audio_url
        return {
            "transcription_text": "This is a mocked transcription text.",
            "pronunciation": "Your pronunciation is clear and accurate.",
            "completeness": "You covered all the key points in the sentence.",
            "fluency": "Your speech flows naturally with good pacing.",
            "suggestions": [
                {
                    "text": "Try to emphasize key words for better clarity",
                    "target_word": "clarity",
                    "timestamp": 0.8,
                },
                {
                    "text": "Consider adding slight pauses between phrases",
                    "target_word": None,
                    "timestamp": 1.4,
                },
            ],
            "issues": [
                {
                    "problem": "Final consonant is dropped on one key word.",
                    "timestamp": 1.1,
                }
            ],
        }

    monkeypatch.setattr(
        "app.adapters.gemini_adapter.GeminiAdapter.generate_single_feedback",
        mock_generate_single_feedback
    )


@pytest.fixture
def mock_fsrs_adapter(monkeypatch):
    """Mock FSRSAdapter for deterministic SRS calculations."""
    from datetime import datetime, timedelta, timezone

    RATING_PARAMS = {
        "again": ("learning", 0, 0, 1.3),
        "hard": ("review", None, 1, 1.5),
        "good": ("review", None, 3, 2.0),
        "easy": ("review", None, 7, 2.5),
    }

    def mock_schedule_card(self, current_srs, rating_str: str, **kwargs) -> dict:
        state, step, interval_days, ease_factor = RATING_PARAMS.get(
            rating_str,
            ("review", None, 1, 1.5),
        )
        now = datetime.now(timezone.utc)
        return {
            "state": state,
            "step": step,
            "due": now + timedelta(days=interval_days),
            "last_review": now,
            "stability": None if interval_days == 0 else interval_days * 1.5,
            "difficulty": max(1, min(10, 5 - (ease_factor - 1.5) * 2)),
            "review_log": {
                "card_id": kwargs.get("card_id") or getattr(current_srs, "card_id", 0) or 0,
                "rating": {"again": 1, "hard": 2, "good": 3, "easy": 4}[rating_str],
                "review_datetime": now,
                "review_duration": None,
            },
        }

    monkeypatch.setattr(
        "app.adapters.fsrs_adapter.FSRSAdapter.schedule_card",
        mock_schedule_card
    )


@pytest.fixture
def all_adapters_mocked(mock_oss_adapter, mock_asr_adapter, mock_gemini_adapter, mock_fsrs_adapter):
    """Activate all external service mocks at once."""


# ============================================================================
# Test Data Fixtures
# ============================================================================

@pytest.fixture
def sample_deck_tree(test_db: Session):
    """Provide a complete deck tree (source -> unit -> lesson -> 5 cards)."""
    from tests.test_data.seed_data import create_full_deck_tree
    return create_full_deck_tree(test_db)


@pytest.fixture
def sample_card_with_srs(test_db: Session):
    """Provide a single card in the business new-card bucket."""
    from tests.test_data.seed_data import create_test_card_with_srs
    return create_test_card_with_srs(test_db)


@pytest.fixture
def sample_card_due_for_review(test_db: Session):
    """Provide a card that's due for review."""
    from tests.test_data.seed_data import create_test_card_with_srs
    return create_test_card_with_srs(test_db, bucket="review")


@pytest.fixture
def sample_settings(test_db: Session):
    """Provide default test settings."""
    from tests.test_data.seed_data import create_test_settings
    return create_test_settings(test_db)


@pytest.fixture
def sample_user_settings(test_db: Session):
    """Provide default user settings."""
    from tests.test_data.seed_data import create_test_user_settings
    return create_test_user_settings(test_db)


@pytest.fixture
def sample_review_log_completed(test_db: Session, sample_card_with_srs):
    """Provide a completed review log."""
    from tests.test_data.seed_data import create_test_review_log
    card = sample_card_with_srs["card"]
    lesson = sample_card_with_srs["lesson"]
    return create_test_review_log(test_db, card.id, lesson.id, status="completed", rating="good")


@pytest.fixture
def sample_review_log_failed(test_db: Session, sample_card_with_srs):
    """Provide a failed review log."""
    from tests.test_data.seed_data import create_test_review_log
    card = sample_card_with_srs["card"]
    lesson = sample_card_with_srs["lesson"]
    return create_test_review_log(test_db, card.id, lesson.id, status="failed", rating="good")


@pytest.fixture
def sample_multiple_reviews(test_db: Session, sample_card_with_srs):
    """Provide multiple review logs for statistics testing."""
    from tests.test_data.seed_data import create_multiple_review_logs
    card = sample_card_with_srs["card"]
    lesson = sample_card_with_srs["lesson"]
    return create_multiple_review_logs(test_db, card.id, lesson.id, count=7, days_ago=6)


# ============================================================================
# Pytest Configuration
# ============================================================================

def pytest_configure(config):
    """Add custom markers for test categorization."""
    config.addinivalue_line(
        "markers", "unit: Unit tests for individual components"
    )
    config.addinivalue_line(
        "markers", "integration: Integration tests for API endpoints"
    )
    config.addinivalue_line(
        "markers", "e2e: End-to-end tests for complete workflows"
    )
    config.addinivalue_line(
        "markers", "slow: Tests that take more than 1 second"
    )
