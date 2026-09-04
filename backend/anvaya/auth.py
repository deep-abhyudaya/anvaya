"""Better Auth session validation and tenant access control for FastAPI."""

from __future__ import annotations

import base64
import hashlib
import hmac
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import unquote

from fastapi import HTTPException, Request
from sqlalchemy import text
from sqlmodel import Session

from anvaya.config import settings


def _safe_unquote(value: str) -> str:
    return unquote(value.replace("+", " "))


def _base64url_decode(value: str) -> bytes:
    value = _safe_unquote(value)
    padding = 4 - len(value) % 4
    if padding != 4:
        value += "=" * padding
    return base64.urlsafe_b64decode(value)


def verify_session_token(session_token: str) -> str | None:
    """Verify a Better Auth signed session token and return the raw DB token.

    Better Auth session cookies have the format `token.signature`. The signature
    is HMAC-SHA256 over the token, base64url encoded, using `BETTER_AUTH_SECRET`.
    """
    if not session_token:
        return None

    if "." not in session_token:
        return session_token

    parts = session_token.split(".")
    if len(parts) != 2:
        return None

    data_part, sig_part = parts
    try:
        raw_token = _safe_unquote(data_part)
        expected_sig = _base64url_decode(sig_part)
    except Exception:
        return None

    secret = (
        os.environ.get("BETTER_AUTH_SECRET") or settings.better_auth_secret or ""
    ).encode("utf-8")
    if not secret:
        return None

    actual_sig = hmac.new(secret, raw_token.encode("utf-8"), hashlib.sha256).digest()
    if not hmac.compare_digest(actual_sig, expected_sig):
        return None

    return raw_token


def _extract_bearer_token(request: Request) -> str | None:
    auth_header = request.headers.get("authorization")
    if auth_header and auth_header.lower().startswith("bearer "):
        return auth_header[7:].strip()
    return None


def _extract_cookie_token(request: Request) -> str | None:
    cookie = request.cookies.get("better-auth.session_token") or request.cookies.get(
        "better_auth_session_token"
    )
    if cookie:
        return cookie
    return request.cookies.get("better_auth.session_token")


def _get_session_token(request: Request) -> str | None:
    return _extract_bearer_token(request) or _extract_cookie_token(request)


@dataclass
class AuthContext:
    user_id: str
    email: str
    name: str
    image: str | None
    session_token: str
    session_expires_at: datetime
    active_organization_id: str | None
    organization: dict[str, Any] | None
    member_role: str | None

    def is_member(self) -> bool:
        return self.organization is not None and self.member_role is not None

    def require_org(self) -> dict[str, Any]:
        if not self.organization:
            raise HTTPException(status_code=403, detail="Active organization required")
        return self.organization

    def require_role(self, *allowed: str) -> None:
        if self.member_role not in allowed:
            raise HTTPException(status_code=403, detail="Insufficient organization permissions")


def get_auth_context(request: Request, session: Session) -> AuthContext:
    """Validate the incoming request against the Better Auth session store."""
    raw_token = _get_session_token(request)
    if not raw_token:
        raise HTTPException(status_code=401, detail="Not authenticated")

    verified_token = verify_session_token(raw_token) or raw_token

    row = session.execute(
        text(
            """
            SELECT s."id", s."token", s."expiresAt", s."activeOrganizationId", s."userId",
                   u."name", u."email", u."image"
            FROM "session" s
            JOIN "user" u ON u."id" = s."userId"
            WHERE s."token" = :token AND s."expiresAt" > :now
            """
        ).bindparams(token=verified_token, now=datetime.now(timezone.utc))
    ).first()

    if not row:
        raise HTTPException(status_code=401, detail="Invalid or expired session")

    (
        session_id,
        _,
        expires_at,
        active_org_id,
        user_id,
        user_name,
        email,
        image,
    ) = row

    organization = None
    member_role = None

    org_row = None
    if active_org_id:
        org_row = session.execute(
            text(
                """
                SELECT o."id", o."name", o."slug", o."logo", o."metadata",
                       m."role"
                FROM "organization" o
                JOIN "member" m ON m."organizationId" = o."id" AND m."userId" = :user_id
                WHERE o."id" = :org_id
                """
            ).bindparams(user_id=user_id, org_id=active_org_id)
        ).first()

    if not org_row:
        org_row = session.execute(
            text(
                """
                SELECT o."id", o."name", o."slug", o."logo", o."metadata",
                       m."role"
                FROM "member" m
                JOIN "organization" o ON o."id" = m."organizationId"
                WHERE m."userId" = :user_id
                ORDER BY m."createdAt" DESC
                LIMIT 1
                """
            ).bindparams(user_id=user_id)
        ).first()

    if org_row:
        org_id, name, slug, logo, meta, role = org_row
        active_org_id = org_id
        organization = {
            "id": org_id,
            "name": name,
            "slug": slug,
            "logo": logo,
            "metadata": meta,
        }
        member_role = role

    return AuthContext(
        user_id=user_id,
        email=email,
        name=user_name,
        image=image,
        session_token=verified_token,
        session_expires_at=expires_at,
        active_organization_id=active_org_id,
        organization=organization,
        member_role=member_role,
    )
