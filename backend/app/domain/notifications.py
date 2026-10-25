"""Push payloads (FR-52, FR-53): no names before accept, location only as building/floor/table."""

from __future__ import annotations

from app.domain.types import OutboxKind, OutboxMessage, User


def person_label(user: User) -> str:
    """What either side may see before accept: first name and major only (D43)."""
    return f"{user.first_name} · {user.major}" if user.major else user.first_name


def request_received(
    host_user_id: str, seeker: User, course_label: str, table_label: str
) -> OutboxMessage:
    return OutboxMessage(
        host_user_id,
        OutboxKind.REQUEST_RECEIVED,
        {
            "title": "New study request",
            "body": (
                f"{person_label(seeker)} wants to study {course_label} with you at {table_label}."
            ),
            "url": "/host",
        },
    )


def request_accepted(
    seeker_id: str, host_first_name: str, table_label: str, match_id: str
) -> OutboxMessage:
    return OutboxMessage(
        seeker_id,
        OutboxKind.REQUEST_ACCEPTED,
        {
            "title": "Request accepted",
            "body": f"{host_first_name} is expecting you at {table_label}.",
            "url": f"/match/{match_id}",
        },
    )


def match_cancelled(user_id: str, match_id: str) -> OutboxMessage:
    return OutboxMessage(
        user_id,
        OutboxKind.MATCH_CANCELLED,
        {
            "title": "Match cancelled",
            "body": "This study match was cancelled.",
            "url": f"/match/{match_id}",
        },
    )


def match_expired(user_id: str, match_id: str) -> OutboxMessage:
    return OutboxMessage(
        user_id,
        OutboxKind.MATCH_EXPIRED,
        {
            "title": "Match expired",
            "body": "This study match timed out.",
            "url": f"/match/{match_id}",
        },
    )


def search_exhausted(seeker_id: str, search_id: str) -> OutboxMessage:
    return OutboxMessage(
        seeker_id,
        OutboxKind.SEARCH_EXHAUSTED,
        {
            "title": "No one's free right now",
            "body": "Here are the best open seats instead.",
            "url": f"/search/{search_id}",
        },
    )


def confirm_needed(host_user_id: str) -> OutboxMessage:
    return OutboxMessage(
        host_user_id,
        OutboxKind.CONFIRM_NEEDED,
        {
            "title": "Still open to study partners?",
            "body": "Confirm now to stay findable, or host mode ends shortly.",
            "url": "/host",
        },
    )


def session_ended(host_user_id: str) -> OutboxMessage:
    return OutboxMessage(
        host_user_id,
        OutboxKind.SESSION_ENDED,
        {"title": "Host mode ended", "body": "You're no longer findable.", "url": "/host"},
    )
