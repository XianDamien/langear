"""Retired-route telemetry records counts only, without authentication or content."""

import logging


def test_legacy_route_hits_are_logged_without_user_content(client, caplog):
    with caplog.at_level(logging.INFO, logger="core.telemetry"):
        response = client.post(
            "/api/v1/telemetry/legacy-route-hits",
            json={
                "route": "Study",
                "date": "2026-10-20",
                "release_sha": "a" * 40,
                "user_id": "must-not-be-logged",
                "card": "secret",
            },
        )
    assert response.status_code == 204
    message = caplog.text
    assert "legacy_route_hit" in message
    assert "route=Study" in message
    assert "date=2026-10-20" in message
    assert "release_sha=" + "a" * 40 in message
    assert "must-not-be-logged" not in message
    assert "secret" not in message


def test_legacy_route_hits_reject_unexpected_values(client, caplog):
    with caplog.at_level(logging.INFO, logger="core.telemetry"):
        response = client.post(
            "/api/v1/telemetry/legacy-route-hits",
            json={"route": "../etc", "date": "today", "release_sha": "not-a-sha"},
        )
    assert response.status_code == 204
    assert "route=invalid" in caplog.text
    assert "date=invalid" in caplog.text
    assert "release_sha=invalid" in caplog.text
