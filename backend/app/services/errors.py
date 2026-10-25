"""Domain-level failures that the interface turns into `{error, message}` responses."""

from __future__ import annotations


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


def not_found(code: str, message: str) -> DomainError:
    return DomainError(code, message, 404)


def conflict(code: str, message: str) -> DomainError:
    return DomainError(code, message, 409)


def forbidden(code: str, message: str) -> DomainError:
    return DomainError(code, message, 403)


def unauthorized(code: str, message: str) -> DomainError:
    return DomainError(code, message, 401)


def too_many(code: str, message: str) -> DomainError:
    return DomainError(code, message, 429)
