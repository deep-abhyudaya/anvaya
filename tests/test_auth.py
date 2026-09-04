"""Tests for the Better Auth context and organization fallback."""

from __future__ import annotations

from types import SimpleNamespace

import pytest
from anvaya.auth import get_auth_context
from fastapi import HTTPException
from sqlmodel import Session, create_engine, text


@pytest.fixture
def auth_session():
    engine = create_engine("sqlite:///:memory:")
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                CREATE TABLE "user" (
                    "id" TEXT NOT NULL PRIMARY KEY,
                    "name" TEXT NOT NULL,
                    "email" TEXT NOT NULL,
                    "emailVerified" INTEGER NOT NULL,
                    "image" TEXT,
                    "createdAt" DATE NOT NULL,
                    "updatedAt" DATE NOT NULL
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE "session" (
                    "id" TEXT NOT NULL PRIMARY KEY,
                    "expiresAt" DATE NOT NULL,
                    "token" TEXT NOT NULL UNIQUE,
                    "createdAt" DATE NOT NULL,
                    "updatedAt" DATE NOT NULL,
                    "ipAddress" TEXT,
                    "userAgent" TEXT,
                    "userId" TEXT NOT NULL,
                    "activeOrganizationId" TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE "organization" (
                    "id" TEXT NOT NULL PRIMARY KEY,
                    "name" TEXT NOT NULL,
                    "slug" TEXT NOT NULL,
                    "logo" TEXT,
                    "createdAt" DATE NOT NULL,
                    "metadata" TEXT
                )
                """
            )
        )
        conn.execute(
            text(
                """
                CREATE TABLE "member" (
                    "id" TEXT NOT NULL PRIMARY KEY,
                    "organizationId" TEXT NOT NULL,
                    "userId" TEXT NOT NULL,
                    "role" TEXT NOT NULL,
                    "createdAt" DATE NOT NULL
                )
                """
            )
        )
    with Session(engine) as session:
        yield session


def _request(auth: str | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        headers={"authorization": auth} if auth else {},
        cookies={},
    )


def _seed_user_and_org(
    session: Session,
    user_id: str = "u-1",
    org_id: str = "o-1",
    active_org_id: str | None = "o-1",
    token: str = "testtoken",
) -> None:
    session.execute(
        text(
            """
            INSERT INTO "user" (
                "id", "name", "email", "emailVerified", "image", "createdAt", "updatedAt"
            )
            VALUES (:id, 'Test User', 'test@example.com', 1, NULL, '2024-01-01', '2024-01-01')
            """
        ).bindparams(id=user_id)
    )
    session.execute(
        text(
            """
            INSERT INTO "organization" ("id", "name", "slug", "logo", "createdAt", "metadata")
            VALUES (:id, 'Test Org', 'test-org', NULL, '2024-01-01', NULL)
            """
        ).bindparams(id=org_id)
    )
    session.execute(
        text(
            """
            INSERT INTO "member" ("id", "organizationId", "userId", "role", "createdAt")
            VALUES ('m-1', :org_id, :user_id, 'owner', '2024-01-01')
            """
        ).bindparams(org_id=org_id, user_id=user_id)
    )
    session.execute(
        text(
            """
            INSERT INTO "session" (
                "id", "expiresAt", "token", "createdAt", "updatedAt",
                "ipAddress", "userAgent", "userId", "activeOrganizationId"
            )
            VALUES (
                's-1', '2099-01-01 00:00:00', :token, '2024-01-01',
                '2024-01-01', NULL, NULL, :user_id, :active_org_id
            )
            """
        ).bindparams(user_id=user_id, token=token, active_org_id=active_org_id)
    )
    session.commit()


def test_get_auth_context_requires_token(auth_session: Session):
    request = _request()
    with pytest.raises(HTTPException, match="Not authenticated"):
        get_auth_context(request, auth_session)


def test_get_auth_context_uses_active_organization(auth_session: Session):
    _seed_user_and_org(auth_session, active_org_id="o-1")
    request = _request("Bearer testtoken")
    auth = get_auth_context(request, auth_session)
    assert auth.active_organization_id == "o-1"
    assert auth.organization["id"] == "o-1"
    assert auth.member_role == "owner"


def test_get_auth_context_falls_back_when_active_organization_missing(auth_session: Session):
    _seed_user_and_org(auth_session, active_org_id=None)
    request = _request("Bearer testtoken")
    auth = get_auth_context(request, auth_session)
    assert auth.active_organization_id == "o-1"
    assert auth.organization["id"] == "o-1"
    assert auth.member_role == "owner"


def test_get_auth_context_falls_back_when_active_organization_not_a_member(auth_session: Session):
    _seed_user_and_org(auth_session, active_org_id="o-missing")
    request = _request("Bearer testtoken")
    auth = get_auth_context(request, auth_session)
    assert auth.active_organization_id == "o-1"
    assert auth.organization["id"] == "o-1"
    assert auth.member_role == "owner"


def test_get_auth_context_still_requires_organization_membership(auth_session: Session):
    user_id = "u-2"
    auth_session.execute(
        text(
            """
            INSERT INTO "user" (
                "id", "name", "email", "emailVerified", "image", "createdAt", "updatedAt"
            )
            VALUES (:id, 'No Org User', 'noorg@example.com', 1, NULL, '2024-01-01', '2024-01-01')
            """
        ).bindparams(id=user_id)
    )
    auth_session.execute(
        text(
            """
            INSERT INTO "session" (
                "id", "expiresAt", "token", "createdAt", "updatedAt",
                "ipAddress", "userAgent", "userId", "activeOrganizationId"
            )
            VALUES (
                's-2', '2099-01-01 00:00:00', 'notoken', '2024-01-01',
                '2024-01-01', NULL, NULL, :user_id, NULL
            )
            """
        ).bindparams(user_id=user_id)
    )
    auth_session.commit()
    request = _request("Bearer notoken")
    auth = get_auth_context(request, auth_session)
    assert auth.organization is None
    with pytest.raises(HTTPException, match="Active organization required"):
        auth.require_org()
