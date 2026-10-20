"""Dashboard aggregates over core Attempts plus imported daily history.

A "study day" is the same unit Review uses for due days and daily quotas: the
local date in the Collection timezone, shifted back one day for hours before
`study_day_rollover_hour`. Live Attempts are counted in study days. Imported
legacy aggregates were recorded per local calendar date, so they are mapped one
calendar date to one study day.

A day covered by live Attempts never also consumes an imported aggregate, so a
legacy history row cannot double count a card that already has core Attempts.
"""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from sqlalchemy import select

from core.models import Attempt, DailyActivity, Deck, utcnow
from core.scheduling import effective, study_day

DAY = timedelta(days=1)
EPOCH = date(1970, 1, 1)
MAX_STREAK_DAYS = 3650
EMPTY = {"reviews": 0, "new_cards": 0}


def day_number(value):
    return (value - EPOCH).days


def day_date(number):
    return EPOCH + timedelta(days=number)


def local_date(now, collection):
    return now.astimezone(ZoneInfo(collection.timezone)).date()


def live_daily_counts(db, collection):
    """Group rated Attempts by the Collection's study day."""
    counts = {}
    for rated_at, quota_kind in db.execute(
        select(Attempt.rated_at, Attempt.quota_kind).where(
            Attempt.collection_id == collection.id,
            Attempt.rating.is_not(None),
            Attempt.rated_at.is_not(None),
        )
    ):
        bucket = counts.setdefault(
            study_day(rated_at, collection.timezone), {"reviews": 0, "new_cards": 0}
        )
        bucket["reviews"] += 1
        bucket["new_cards"] += int(quota_kind == "new")
    return counts


def imported_daily_counts(db, collection):
    counts = {}
    for row in db.scalars(
        select(DailyActivity).where(DailyActivity.collection_id == collection.id)
    ):
        bucket = counts.setdefault(
            day_number(row.activity_date), {"reviews": 0, "new_cards": 0}
        )
        bucket["reviews"] += row.reviews
        bucket["new_cards"] += row.new_cards
    return counts


def merged_days(db, collection, days):
    live = live_daily_counts(db, collection)
    imported = imported_daily_counts(db, collection)
    return {day: live.get(day) or imported.get(day) or dict(EMPTY) for day in days}


def current_streak(daily, today, lookback=MAX_STREAK_DAYS):
    """Consecutive days with activity ending today or yesterday.

    A learner who has not started today yet keeps the streak they built through
    yesterday; only a fully skipped day breaks it.
    """
    def run(end):
        streak, day = 0, end
        while streak < lookback and daily.get(day, EMPTY)["reviews"] > 0:
            streak, day = streak + 1, day - 1
        return streak

    today_run = run(today)
    return today_run or run(today - 1)


def due_counts(db, collection):
    """Reuse Review eligibility so Dashboard and Review never disagree."""
    from core.review import ReviewService

    review = ReviewService(db, collection)
    decks = {deck.id: deck for deck in review.decks.values() if deck.kind == "standard"}
    roots = [deck_id for deck_id, deck in decks.items() if deck.parent_id is None]
    usage = review.usage()
    result = {"new_due": 0, "review_due": 0, "learning_due": 0}
    for deck_id in roots:
        review._card_content.clear()
        cards = review.in_scope(
            {
                "deck_id": deck_id,
                "include_descendants": True,
                "exclude_imported": True,
            }
        )
        for card in cards:
            if card.queue == "new":
                # Due counts report today's remaining allowed work, matching the
                # quota the learner will actually be given in Review.
                result["new_due"] += int(review.capacity(card, usage))
            elif card.queue == "review" and card.due_day <= review.day:
                result["review_due"] += int(review.capacity(card, usage))
            elif card.queue in ("learning", "day_learning") and (
                (card.due_at is not None and card.due_at <= review.now)
                or (card.due_day is not None and card.due_day <= review.day)
            ):
                result["learning_due"] += 1
    return result


def dashboard_data(db, collection):
    from core.config import get_settings

    settings = get_settings()
    now = utcnow()
    today = study_day(now, collection.timezone)
    heatmap_days = settings.dashboard_heatmap_days
    trend_days = settings.dashboard_trend_days
    window = [today - offset for offset in range(heatmap_days - 1, -1, -1)]
    daily = merged_days(db, collection, window)
    config = effective(
        collection,
        None,
        {d.id: d for d in db.scalars(select(Deck).where(Deck.collection_id == collection.id))},
    )
    completed = daily.get(today, dict(EMPTY))
    due = due_counts(db, collection)
    return {
        "stats": {
            "points": completed["reviews"],
            "reviewsPending": due["new_due"] + due["review_due"] + due["learning_due"],
            "streakDays": current_streak(daily, today),
            "dailyGoal": config["new_limit"] + config["review_limit"],
            "dailyDone": completed["reviews"],
            "todayNew": completed["new_cards"],
            "todayReview": completed["reviews"] - completed["new_cards"],
            "todayDone": completed["reviews"],
            "newDue": due["new_due"],
            "reviewDue": due["review_due"],
            "learningDue": due["learning_due"],
            "localDate": local_date(now, collection).isoformat(),
        },
        "weeklyTrend": [
            {
                "name": day_date(day).isoformat(),
                "sentences": daily.get(day, EMPTY)["reviews"],
            }
            for day in window[-trend_days:]
        ],
        "heatmap": [
            {"date": day_date(day).isoformat(), "count": daily.get(day, EMPTY)["reviews"]}
            for day in window
        ],
        # Ranking rules are a later task; the slot stays so the UI can render
        # an explicit empty state instead of hard-coded leaders.
        "leaderboard": [],
    }
