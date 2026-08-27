"""Integration tests for authentication endpoints."""

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.invitation_code import InvitationCode
from app.models.user import User
from app.utils.timezone import storage_now


def create_invitation_code(db: Session, code: str = "BETA-2026") -> InvitationCode:
    """Create an active invitation code for auth tests."""
    invitation = InvitationCode(
        code=code,
        note="test invite",
        max_uses=1,
        used_count=0,
        created_at=storage_now(),
        updated_at=storage_now(),
    )
    db.add(invitation)
    db.commit()
    db.refresh(invitation)
    return invitation


@pytest.mark.integration
class TestAuthRouter:
    """Test registration, login, and current user endpoints."""

    def test_register_login_and_me(self, client: TestClient, test_db: Session):
        invitation = create_invitation_code(test_db)

        register_response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "learner",
                "password": "strong-password",
                "email": "learner@example.com",
                "invitation_code": invitation.code,
            },
        )

        assert register_response.status_code == 200
        register_data = register_response.json()["data"]
        assert register_data["token_type"] == "bearer"
        assert register_data["access_token"]
        assert register_data["user"]["username"] == "learner"
        assert register_data["user"]["email_verified"] is False
        assert register_data["user"]["email_verified_at"] is None

        test_db.refresh(invitation)
        user = test_db.query(User).filter(User.username == "learner").one()
        assert invitation.used_count == 1
        assert user.invitation_code_id == invitation.id

        login_response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "learner",
                "password": "strong-password",
            },
        )

        assert login_response.status_code == 200
        token = login_response.json()["data"]["access_token"]

        me_response = client.get(
            "/api/v1/auth/me",
            headers={"Authorization": f"Bearer {token}"},
        )

        assert me_response.status_code == 200
        assert me_response.json()["data"]["username"] == "learner"

    def test_register_rejects_short_password(self, client: TestClient, test_db: Session):
        invitation = create_invitation_code(test_db)

        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "learner",
                "password": "short",
                "invitation_code": invitation.code,
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"]["error"]["code"] == "AUTH_REGISTER_FAILED"

    def test_register_requires_invitation_code(self, client: TestClient):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "learner",
                "password": "strong-password",
            },
        )

        assert response.status_code == 422

    def test_register_rejects_invalid_invitation_code(self, client: TestClient):
        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "learner",
                "password": "strong-password",
                "invitation_code": "missing-code",
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"]["error"]["message"] == "Invitation code is invalid"

    def test_register_rejects_used_invitation_code(
        self,
        client: TestClient,
        test_db: Session,
    ):
        invitation = create_invitation_code(test_db)
        client.post(
            "/api/v1/auth/register",
            json={
                "username": "learner-one",
                "password": "strong-password",
                "invitation_code": invitation.code,
            },
        )

        response = client.post(
            "/api/v1/auth/register",
            json={
                "username": "learner-two",
                "password": "strong-password",
                "invitation_code": invitation.code,
            },
        )

        assert response.status_code == 400
        assert response.json()["detail"]["error"]["message"] == "Invitation code has been used"

    def test_login_rejects_bad_password(self, client: TestClient, test_db: Session):
        invitation = create_invitation_code(test_db)

        client.post(
            "/api/v1/auth/register",
            json={
                "username": "learner",
                "password": "strong-password",
                "invitation_code": invitation.code,
            },
        )

        response = client.post(
            "/api/v1/auth/login",
            json={
                "username": "learner",
                "password": "wrong-password",
            },
        )

        assert response.status_code == 401
        assert response.json()["detail"]["error"]["code"] == "AUTH_LOGIN_FAILED"

    def test_me_requires_token(self, client: TestClient):
        response = client.get("/api/v1/auth/me")

        assert response.status_code == 401
