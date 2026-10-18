from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime, timedelta
from uuid import UUID

import pytest
from core.models import Attempt, Card, Deck, MediaAsset, ProcessingOutbox
from core.review import QUEUES, dictation
from core.scheduling import ORDERS, day_start, study_day
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from uuid6 import uuid7


def make_note(
    client, account, fields=None, template="vocabulary_english_to_chinese", deck_id=None
):
    response = client.post(
        "/api/v1/notes",
        json={
            "note_type_key": "sentence"
            if template.startswith("sentence")
            else "vocabulary",
            "card_template_key": template,
            "fields": fields or {"word": "apple", "meaning": "苹果"},
            "deck_id": deck_id or account["deck_id"],
        },
    )
    assert response.status_code == 201, response.text
    return response.json()


def queue(client, account, deck_id=None):
    response = client.post(
        "/api/v1/review/queues",
        json={"scope": {"deck_id": deck_id or account["deck_id"]}},
    )
    assert response.status_code == 200, response.text
    return response.json()["queue_id"]


def next_card(client, q):
    response = client.get(f"/api/v1/review/queues/{q}/next")
    assert response.status_code == 200, response.text
    return response.json()


def flip(client, q, current, data=None, key=None):
    return client.post(
        f"/api/v1/review/queues/{q}/flip",
        headers={"Idempotency-Key": str(key or uuid7())},
        json={
            "card_id": current["card"]["id"],
            "review_token": current["review_token"],
            "input": data or {"type": "none"},
        },
    )


def rate(client, q, flipped, rating="good", key=None):
    return client.put(
        f"/api/v1/review/queues/{q}/attempts/{flipped['attempt']['id']}/rating",
        headers={"Idempotency-Key": str(key or uuid7())},
        json={
            "rating": rating,
            "card_schedule_revision": flipped["card_schedule_revision"],
        },
    )


def test_next_flip_rating_undo_and_receipts(client, account, engine):
    make_note(client, account)
    q = queue(client, account)
    current = next_card(client, q)
    assert current == next_card(client, q)
    assert "back" not in current["card"] and "answer" not in current["card"]
    key = uuid7()
    response = flip(client, q, current, key=key)
    assert response.status_code == 200, response.text
    flipped = response.json()
    assert len(flipped["rating_options"]) == 4
    assert flipped == flip(client, q, current, key=key).json()
    assert next_card(client, q)["attempt"]["id"] == flipped["attempt"]["id"]
    key = uuid7()
    response = rate(client, q, flipped, "good", key)
    assert response.status_code == 200, response.text
    rated = response.json()
    assert "next" not in rated and rated["card"]["reps"] == 1
    assert rate(client, q, flipped, "good", key).json() == rated
    assert rate(client, q, flipped, "good").json() == rated
    assert (
        rate(client, q, flipped, "easy", key).json()["error"]["code"]
        == "IDEMPOTENCY_KEY_REUSED"
    )
    assert (
        rate(client, q, flipped, "easy").json()["error"]["code"] == "RATING_ALREADY_SET"
    )
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Attempt)) == 1
        assert db.get(Card, UUID(current["card"]["id"])).reps == 1
    undo = client.post(f"/api/v1/review/queues/{q}/undo")
    assert undo.status_code == 200, undo.text
    restored = undo.json()
    assert restored["attempt"]["id"] == flipped["attempt"]["id"]
    assert restored["card_schedule_revision"] > flipped["card_schedule_revision"]
    assert restored["attempt"]["back_snapshot"] == flipped["attempt"]["back_snapshot"]
    assert rate(client, q, restored, "easy").status_code == 200
    with Session(engine) as db:
        assert db.get(Card, UUID(current["card"]["id"])).reps == 1
    assert next_card(client, q)["card"] is None


def test_restart_recovers_pending_only_in_its_own_scope(client, account):
    make_note(client, account)
    q = queue(client, account)
    original = flip(client, q, next_card(client, q)).json()
    QUEUES.clear()
    assert client.get(f"/api/v1/review/queues/{q}/next").json()["error"]["code"] == "QUEUE_EXPIRED"
    other = client.post("/api/v1/decks", json={"name": "Other"}).json()["id"]
    blocked = client.post("/api/v1/review/queues", json={"scope": {"deck_id": other}})
    assert blocked.status_code == 409
    assert blocked.json()["error"]["code"] == "PENDING_REVIEW_OUTSIDE_SCOPE"
    assert blocked.json()["error"]["details"]["deck_id"] == account["deck_id"]
    q2 = queue(client, account)
    recovered = next_card(client, q2)
    assert recovered["attempt"]["id"] == original["attempt"]["id"]
    assert recovered["review_token"] == original["attempt"]["review_token"]
    assert rate(client, q2, original, "easy").status_code == 200
    assert next_card(client, queue(client, account, other))["card"] is None


def test_input_snapshots_outbox_and_independent_status(client, account, engine):
    make_note(
        client,
        account,
        {"english": "I came home.", "chinese": "我回家了。"},
        "sentence_translation",
    )
    q = queue(client, account)
    current = next_card(client, q)
    assert current["card"]["front"] == {"chinese": "我回家了。"}
    assert flip(client, q, current).status_code == 422
    assert flip(client, q, current, {"type": "text", "text": "  \n"}).status_code == 422
    flipped = flip(
        client, q, current, {"type": "text", "text": "  I came home.  "}
    ).json()
    assert flipped["attempt"]["input_snapshot"]["text"] == "  I came home.  "
    assert (
        flipped["attempt"]["asr_status"] == "skipped"
        and flipped["attempt"]["ai_status"] == "pending"
    )
    assert flipped["attempt"]["ai_feedback"] is None
    with Session(engine) as db:
        assert list(db.scalars(select(ProcessingOutbox.kind))) == ["ai"]
    assert rate(client, q, flipped, "easy").status_code == 200


def test_audio_claim_is_atomic_and_scoped(client, account, engine):
    with Session(engine) as db, db.begin():
        collection = UUID(account["collection"]["id"])
        reference = MediaAsset(
            collection_id=collection, object_key="reference.mp3", kind="audio"
        )
        recording = MediaAsset(
            collection_id=collection,
            object_key="recording.mp3",
            uploaded_at=datetime.now(UTC),
            kind="audio",
            lifecycle="temporary",
        )
        db.add_all([reference, recording])
        db.flush()
        ref, media = str(reference.id), str(recording.id)
    make_note(
        client,
        account,
        {"english": "Hello.", "reference_audio": ref},
        "sentence_retelling",
    )
    q = queue(client, account)
    current = next_card(client, q)
    assert (
        flip(
            client, q, current, {"type": "audio", "temporary_media_asset_id": ref}
        ).status_code
        == 409
    )
    flipped = flip(
        client, q, current, {"type": "audio", "temporary_media_asset_id": media}
    )
    assert flipped.status_code == 200, flipped.text
    with Session(engine) as db:
        assert db.get(MediaAsset, UUID(media)).lifecycle == "ready"
        assert set(db.scalars(select(ProcessingOutbox.kind))) == {"asr", "ai"}
    assert rate(client, q, flipped.json(), "easy").status_code == 200


def test_sibling_bury_undo_limits_and_rollover(client, account, engine):
    note = make_note(client, account)
    client.post(
        f"/api/v1/notes/{note['id']}/generate-cards",
        json={"deck_id": account["deck_id"]},
    )
    client.patch(
        f"/api/v1/decks/{account['deck_id']}/scheduling",
        json={"overrides": {"new_limit": 1}},
    )
    q = queue(client, account)
    current = next_card(client, q)
    flipped = flip(client, q, current).json()
    assert rate(client, q, flipped, "easy").status_code == 200
    with Session(engine) as db:
        siblings = list(
            db.scalars(select(Card).where(Card.id != UUID(current["card"]["id"])))
        )
        assert len(siblings) == 1 and siblings[0].queue == "buried_sibling"
        sibling_id = siblings[0].id
    assert next_card(client, q)["card"] is None
    restored = client.post(f"/api/v1/review/queues/{q}/undo").json()
    with Session(engine) as db:
        assert db.get(Card, sibling_id).queue == "new"
    assert rate(client, q, restored, "easy").status_code == 200
    with Session(engine) as db, db.begin():
        db.get(Card, sibling_id).buried_on_day -= 1
    queue(client, account)
    with Session(engine) as db:
        assert db.get(Card, sibling_id).queue == "new"


def test_hierarchical_limits_and_inheritance(client, account):
    parent = account["deck_id"]
    child = client.post(
        "/api/v1/decks", json={"name": "Child", "parent_id": parent}
    ).json()["id"]
    for i in range(2):
        make_note(client, account, {"word": f"word{i}", "meaning": "词"}, deck_id=child)
    client.patch(
        f"/api/v1/decks/{parent}/scheduling",
        json={
            "overrides": {"new_limit": 1, "review_limit": 1, "desired_retention": 0.85}
        },
    )
    client.patch(
        f"/api/v1/decks/{child}/scheduling",
        json={"overrides": {"new_limit": 50, "review_limit": 50}},
    )
    assert (
        client.get(f"/api/v1/decks/{child}/scheduling").json()["effective"][
            "desired_retention"
        ]
        == 0.85
    )
    q = queue(client, account, child)
    flipped = flip(client, q, next_card(client, q)).json()
    assert rate(client, q, flipped, "easy").status_code == 200
    assert next_card(client, q)["card"] is None
    restored = client.post(f"/api/v1/review/queues/{q}/undo").json()
    assert restored["attempt"]["rating"] is None
    assert next_card(client, q)["new_remaining"] >= 1
    result = client.patch(
        f"/api/v1/decks/{child}/scheduling",
        json={"overrides": {"desired_retention": None}},
    )
    assert result.json()["effective"]["desired_retention"] == 0.85
    assert (
        client.get(f"/api/v1/review/queues/{q}/next").json()["error"]["code"]
        == "QUEUE_EXPIRED"
    )


@pytest.mark.parametrize("field,values", list(ORDERS.items()))
def test_display_order_enums_and_queue_invalidation(client, account, field, values):
    for value in values:
        q = queue(client, account)
        response = client.patch(
            f"/api/v1/decks/{account['deck_id']}/scheduling",
            json={"overrides": {field: value}},
        )
        assert response.status_code == 200, response.text
        assert (
            client.get(f"/api/v1/review/queues/{q}/next").json()["error"]["code"]
            == "QUEUE_EXPIRED"
        )
    assert (
        client.patch(
            f"/api/v1/decks/{account['deck_id']}/scheduling",
            json={"overrides": {field: "invalid"}},
        ).status_code
        == 422
    )
    assert (
        client.patch(
            f"/api/v1/decks/{account['deck_id']}/scheduling",
            json={"overrides": {"learning_steps": [1]}},
        ).status_code
        == 422
    )


def test_schedule_conflict_suspend_and_ownership(client, account):
    make_note(client, account)
    q = queue(client, account)
    current = next_card(client, q)
    flipped = flip(client, q, current).json()
    path = f"/api/v1/cards/{current['card']['id']}/schedule"
    result = client.post(path, json={"action": "suspend", "card_schedule_revision": 0})
    assert result.status_code == 200, result.text
    assert result.json()["queue"] == "suspended"
    assert (
        client.post(
            path, json={"action": "unsuspend", "card_schedule_revision": 1}
        ).json()["queue"]
        == "new"
    )
    q = queue(client, account)
    assert (
        rate(client, q, flipped, "easy").json()["error"]["code"]
        == "CARD_SCHEDULE_CONFLICT"
    )
    attempt_id = flipped["attempt"]["id"]
    result = client.post(
        "/api/v1/auth/register",
        json={"email": "other@example.com", "password": "another strong password"},
    )
    client.headers["X-CSRF-Token"] = result.json()["csrf_token"]
    assert client.get(f"/api/v1/attempts/{attempt_id}").status_code == 404
    assert (
        client.get(f"/api/v1/review/queues/{q}/next").json()["error"]["code"]
        == "QUEUE_EXPIRED"
    )


def test_concurrent_flip_and_rating_do_not_duplicate(client, account, engine):
    make_note(client, account)
    q = queue(client, account)
    current = next_card(client, q)
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: flip(client, q, current), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    assert responses[0].json()["attempt"]["id"] == responses[1].json()["attempt"]["id"]
    flipped = responses[0].json()
    with ThreadPoolExecutor(max_workers=2) as pool:
        responses = list(pool.map(lambda _: rate(client, q, flipped, "easy"), range(2)))
    assert [r.status_code for r in responses] == [200, 200]
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(Attempt)) == 1
        assert db.get(Card, UUID(current["card"]["id"])).reps == 1


@pytest.mark.parametrize(
    "tz,instant,expected",
    [
        ("Asia/Shanghai", "2026-10-17T19:59:59+00:00", "2026-10-17"),
        ("Asia/Shanghai", "2026-10-17T20:00:00+00:00", "2026-10-18"),
        ("America/New_York", "2026-03-08T07:59:59+00:00", "2026-03-07"),
        ("America/New_York", "2026-03-08T08:00:00+00:00", "2026-03-08"),
        ("America/New_York", "2026-11-01T08:59:59+00:00", "2026-10-31"),
        ("America/New_York", "2026-11-01T09:00:00+00:00", "2026-11-01"),
    ],
)
def test_study_day_dst(tz, instant, expected):
    from datetime import date

    now = datetime.fromisoformat(instant)
    assert study_day(now, tz) == (date.fromisoformat(expected) - date(1970, 1, 1)).days
    assert day_start(study_day(now, tz), tz) <= now


def test_dictation_evaluator_preserves_semantic_writing():
    assert dictation("“Hello.”", '"Hello."')["exact_match"]
    for expected, actual, category in [
        ("Hello", "hello", "capitalization"),
        ("a b", "a  b", "spacing"),
        ("Hi!", "Hi", "punctuation"),
        ("cat", "dog", "word"),
    ]:
        result = dictation(expected, actual)
        assert not result["exact_match"]
        assert category in {d["category"] for d in result["differences"]}


def test_dictation_flip_creates_no_async_work(client, account, engine):
    with Session(engine) as db, db.begin():
        reference = MediaAsset(
            collection_id=UUID(account["collection"]["id"]),
            object_key="dictation.mp3",
            kind="audio",
        )
        db.add(reference)
        db.flush()
        ref = str(reference.id)
    make_note(
        client,
        account,
        {"english": "Hello, world!", "reference_audio": ref},
        "sentence_dictation",
    )
    q = queue(client, account)
    current = next_card(client, q)
    result = flip(client, q, current, {"type": "text", "text": "hello, world!"})
    assert result.status_code == 200, result.text
    attempt = result.json()["attempt"]
    assert (
        attempt["deterministic_result"]["differences"][0]["category"]
        == "capitalization"
    )
    assert attempt["asr_status"] == attempt["ai_status"] == "skipped"
    with Session(engine) as db:
        assert db.scalar(select(func.count()).select_from(ProcessingOutbox)) == 0


def test_stable_order_actual_positions_and_limits(client, account, engine):
    for i in range(5):
        make_note(client, account, {"word": f"w{i}", "meaning": "词"})
    path = f"/api/v1/decks/{account['deck_id']}/scheduling"
    client.patch(
        path,
        json={
            "overrides": {"new_card_gather_order": "lowest_position", "new_limit": 2}
        },
    )
    q = queue(client, account)
    assert next_card(client, q)["new_remaining"] == 2
    with Session(engine) as db:
        first = db.scalar(select(Card).order_by(Card.new_position)).id
    assert next_card(client, q)["card"]["id"] == str(first)
    client.patch(
        path, json={"overrides": {"new_card_gather_order": "highest_position"}}
    )
    q = queue(client, account)
    with Session(engine) as db:
        last = db.scalar(select(Card).order_by(Card.new_position.desc())).id
    assert next_card(client, q)["card"]["id"] == str(last)
    client.patch(path, json={"overrides": {"new_card_gather_order": "random_cards"}})
    q = queue(client, account)
    random_first = next_card(client, q)["card"]["id"]
    assert next_card(client, queue(client, account))["card"]["id"] == random_first


def test_fsrs_conversion_options_and_intraday_reinsertion(client, account, engine):
    from core.models import Collection
    from core.scheduling import effective, options, schedule

    make_note(client, account)
    with Session(engine) as db, db.begin():
        card = db.scalar(select(Card))
        collection = db.get(Collection, UUID(account["collection"]["id"]))
        decks = {
            d.id: d
            for d in db.scalars(select(Deck).where(Deck.collection_id == collection.id))
        }
        config = effective(collection, card.deck_id, decks)
        now = datetime(2026, 10, 17, 19, 55, tzinfo=UTC)  # 03:55 Shanghai
        result = schedule(card, "again", now, collection, config)
        assert result["type"] == "learning" and result["queue"] == "day_learning"
        assert (
            result["due_at"] is None
            and result["due_day"] == study_day(now, collection.timezone) + 1
        )
        now = datetime(2026, 10, 17, 10, tzinfo=UTC)
        opts = options(card, now, collection, config)
        assert [o["rating"] for o in opts] == ["again", "hard", "good", "easy"]
        result = schedule(card, "again", now, collection, config)
        assert result["queue"] == "learning" and result["due_at"] == now + timedelta(
            minutes=15
        )
        easy = schedule(card, "easy", now, collection, config)
        for key, value in easy.items():
            setattr(card, key, value)
        result = schedule(card, "again", now + timedelta(days=10), collection, config)
        assert result["type"] == "relearning" and result["lapses"] == 1
    q = queue(client, account)
    # Make a short-step Card become due without rebuilding the queue.
    with Session(engine) as db, db.begin():
        card = db.scalar(select(Card))
        collection = db.get(Collection, UUID(account["collection"]["id"]))
        result = schedule(
            card,
            "again",
            datetime.now(UTC) - timedelta(minutes=30),
            collection,
            config,
        )
        for key, value in result.items():
            setattr(card, key, value)
    assert next_card(client, q)["card"] is not None


def test_rollback_restores_runtime_and_does_not_claim_recording(
    client, account, engine, monkeypatch
):
    from core.review import ReviewService

    make_note(client, account)
    q = queue(client, account)
    current = next_card(client, q)
    flipped = flip(client, q, current).json()
    original = ReviewService.receipt

    def fail(*args, **kwargs):
        raise DomainError(503, "TEST_FAILURE", "Simulated transaction failure")

    from core.errors import DomainError

    monkeypatch.setattr(ReviewService, "receipt", fail)
    assert rate(client, q, flipped, "easy").status_code == 503
    monkeypatch.setattr(ReviewService, "receipt", original)
    assert next_card(client, q)["attempt"]["rating"] is None
    with Session(engine) as db:
        assert db.get(Card, UUID(current["card"]["id"])).reps == 0
    assert rate(client, q, flipped, "easy").status_code == 200


def test_new_token_after_learning_and_review_sort_default(client, account, engine):
    make_note(client, account)
    q = queue(client, account)
    current = next_card(client, q)
    flipped = flip(client, q, current).json()
    assert rate(client, q, flipped, "again").status_code == 200
    with Session(engine) as db, db.begin():
        card = db.get(Card, UUID(current["card"]["id"]))
        card.queue = "learning"
        card.due_day = None
        card.due_at = datetime.now(UTC) - timedelta(seconds=1)
    later = next_card(client, q)
    assert later["card"]["id"] == current["card"]["id"]
    assert later["review_token"] != current["review_token"]
    settings = client.get(f"/api/v1/decks/{account['deck_id']}/scheduling").json()
    assert settings["effective"]["review_sort_order"] == "retrievability_descending"


def test_all_display_orders_on_mixed_card_fixture(client, account, engine):
    from core.models import Collection
    from core.scheduling import effective, ordered, schedule

    for i in range(6):
        make_note(client, account, {"word": f"item{i}", "meaning": "词"})
    with Session(engine) as db, db.begin():
        collection = db.get(Collection, UUID(account["collection"]["id"]))
        decks = {
            d.id: d
            for d in db.scalars(select(Deck).where(Deck.collection_id == collection.id))
        }
        cards = list(db.scalars(select(Card).order_by(Card.new_position)))
        config = effective(collection, UUID(account["deck_id"]), decks)
        now = datetime.now(UTC)
        day = study_day(now, collection.timezone)
        for i, card in enumerate(cards[2:]):
            state = schedule(
                card, "easy", now - timedelta(days=i + 2), collection, config
            )
            for key, value in state.items():
                setattr(card, key, value)
            card.due_day = day - i
        # Two new, two reviews, one interday, one intraday learning.
        for card in cards[4:]:
            card.type = "learning"
            card.queue = "day_learning"
            card.due_day = day
        cards[5].queue = "learning"
        cards[5].due_day = None
        cards[5].due_at = now - timedelta(minutes=1)
        db.flush()
        for name, values in ORDERS.items():
            for value in values:
                changed = {**config, name: value}
                first = ordered(cards, collection, changed, now, decks)
                second = ordered(cards, collection, changed, now, decks)
                assert [c.id for c in first] == [c.id for c in second]
                assert len(first) == len(cards) and first[0].id == cards[5].id
        config["new_review_order"] = "before_reviews"
        config["interday_learning_review_order"] = "after_reviews"
        result = ordered(cards, collection, config, now, decks)
        assert [c.queue for c in result] == [
            "learning",
            "new",
            "new",
            "review",
            "review",
            "day_learning",
        ]
        # Default retrievability descending is the same order calculated by FSRS.
        from core.scheduling import engine as scheduler
        from core.scheduling import native

        reviews = [c for c in result if c.queue == "review"]
        retrievabilities = [
            scheduler(config).get_card_retrievability(
                native(c, now, collection.timezone), current_datetime=now
            )
            for c in reviews
        ]
        assert retrievabilities == sorted(retrievabilities, reverse=True)


@pytest.mark.parametrize("protected_queue", ["learning", "suspended", "buried_user"])
def test_sibling_bury_respects_protected_queues(
    client, account, engine, protected_queue
):
    note = make_note(client, account)
    client.post(
        f"/api/v1/notes/{note['id']}/generate-cards",
        json={"deck_id": account["deck_id"]},
    )
    client.patch(
        f"/api/v1/decks/{account['deck_id']}/scheduling",
        json={"overrides": {"new_card_gather_order": "lowest_position"}},
    )
    q = queue(client, account)
    current = next_card(client, q)
    with Session(engine) as db, db.begin():
        sibling = db.scalar(select(Card).where(Card.id != UUID(current["card"]["id"])))
        sibling.queue = protected_queue
        if protected_queue == "learning":
            sibling.type = "learning"
            sibling.new_position = None
            sibling.due_at = datetime.now(UTC) + timedelta(minutes=5)
        sibling_id = sibling.id
    flipped = flip(client, q, current).json()
    assert rate(client, q, flipped, "easy").status_code == 200
    with Session(engine) as db:
        assert db.get(Card, sibling_id).queue == protected_queue


def test_pending_snapshot_and_receipt_survive_queue_rebuild(client, account):
    note = make_note(client, account)
    q = queue(client, account)
    current = next_card(client, q)
    key = uuid7()
    original = flip(client, q, current, key=key).json()
    response = client.put(
        f"/api/v1/notes/{note['id']}",
        json={
            "revision": note["revision"],
            "fields": {"word": "changed", "meaning": "变化"},
        },
    )
    assert response.status_code == 200, response.text
    QUEUES.clear()
    q2 = queue(client, account)
    recovered = next_card(client, q2)
    assert recovered["card"]["front"] == original["attempt"]["front_snapshot"]
    assert recovered["attempt"]["back_snapshot"] == original["attempt"]["back_snapshot"]
    assert len(recovered["rating_options"]) == 4
    assert flip(client, q2, current, key=key).json() == original
    assert rate(client, q2, recovered, "easy").status_code == 200


def test_undo_old_key_is_superseded_without_reapplying(client, account, engine):
    make_note(client, account)
    q = queue(client, account)
    flipped = flip(client, q, next_card(client, q)).json()
    key = uuid7()
    result = rate(client, q, flipped, "easy", key)
    assert result.status_code == 200, result.text
    attempt_id = flipped["attempt"]["id"]
    audit = client.get(f"/api/v1/attempts/{attempt_id}").json()
    assert audit["previous_interval_days"] == 0
    assert audit["scheduled_interval_days"] > 0
    assert audit["fsrs_algorithm_version"] == "py-fsrs/6.3.0"
    restored = client.post(f"/api/v1/review/queues/{q}/undo").json()
    replay = rate(client, q, flipped, "easy", key)
    assert replay.status_code == 200 and replay.json()["superseded"] is True
    assert next_card(client, q)["attempt"]["rating"] is None
    assert rate(client, q, restored, "good").status_code == 200
    with Session(engine) as db:
        assert db.get(Card, UUID(flipped["attempt"]["card_id"])).reps == 1
