"""Searches and the request cascade (FR-29..35, D15, D19, D22, D23)."""

from __future__ import annotations

import uuid
from dataclasses import replace
from datetime import datetime, timedelta

from app.domain.matching import aggregate, offered_group
from app.domain.types import Group, RequestStatus, Search, SearchStatus, StudyRequest
from app.services.context import Context
from app.services.errors import conflict, forbidden, not_found, too_many
from app.services.facts import Facts
from app.services.lifecycle import Candidate, LifecycleService, findable_hosts
from app.services.ports import Conflict, Lock, Tx
from app.services.topics import TopicsService
from app.services.views import GroupCountView, PersonView, SearchStatusView, SearchView


def _own(tx: Tx, user_id: str, search_id: str, lock: Lock = Lock.NONE) -> Search:
    search = tx.search(search_id, lock)
    if search is None:
        raise not_found("search_not_found", "No such search")
    if search.seeker_id != user_id:
        raise forbidden("not_your_search", "This search belongs to someone else")
    return search


def _counts(candidates: list[Candidate], group: Group) -> list[GroupCountView]:
    places = [(c.seat.building_id, c.seat.floor) for c in candidates if c.group is group]
    return [GroupCountView(b, f, n) for b, f, n in aggregate(places)]


def _has_real(candidates: list[Candidate], group: Group) -> bool:
    return any(c.group is group and not c.seat.is_simulated for c in candidates)


class SearchService:
    def __init__(self, ctx: Context, lifecycle: LifecycleService, topics: TopicsService) -> None:
        self._ctx = ctx
        self._lifecycle = lifecycle
        self._topics = topics

    def _candidates(self, tx: Tx, now: datetime, search: Search) -> list[Candidate]:
        facts = Facts(tx, now, self._ctx.timers)
        return findable_hosts(facts, search.seeker_id, search.course_code, search.subject)

    def create(self, user_id: str, topic_raw: str, group: Group | None) -> SearchView:
        with self._ctx.repo.read() as tx:
            if tx.live_session_for_user(user_id) is not None:
                raise conflict("already_hosting", "Turn off host mode to search")
        topic = self._topics.normalize(topic_raw)
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            current = tx.active_search_for_user(user_id)
            if current is not None:
                if current.joined_at is not None:
                    raise conflict("already_searching", "Cancel your current search first")
                # An un-joined search is only a preview; a new topic replaces it (FR-34).
                tx.update_search(replace(current, status=SearchStatus.CANCELLED))
            facts = Facts(tx, now, self._ctx.timers)
            candidates = findable_hosts(facts, user_id, topic.course_code, topic.subject)
            same = sum(c.group is Group.SAME_COURSE for c in candidates)
            offered = offered_group(same, group)
            search = Search(
                id=str(uuid.uuid4()),
                seeker_id=user_id,
                topic_raw=topic_raw,
                course_code=topic.course_code,
                subject=topic.subject,
                keywords=topic.keywords,
                label=topic.label,
                offered_group=offered,
                status=SearchStatus.ACTIVE,
                tried_session_ids=(),
                created_at=now,
                joined_at=None,
            )
            try:
                tx.insert_search(search)
            except Conflict as exc:
                raise conflict("already_searching", "You already have an active search") from exc
        return SearchView(
            search_id=search.id,
            label=topic.label,
            course_code=topic.course_code,
            subject=topic.subject,
            offered_group=offered,
            has_real_hosts=_has_real(candidates, offered),
            same_course=_counts(candidates, Group.SAME_COURSE),
            related=_counts(candidates, Group.RELATED),
        )

    def join(self, user_id: str, search_id: str) -> SearchStatusView:
        now = self._ctx.clock.now()
        with self._ctx.repo.tx() as tx:
            search = _own(tx, user_id, search_id, Lock.WAIT)
            if search.status is not SearchStatus.ACTIVE:
                raise conflict("search_not_active", "This search has ended")
            if search.joined_at is None:
                if not _has_real(self._candidates(tx, now, search), search.offered_group):
                    raise conflict("no_real_hosts", "No one in this group can take a request")
                hour_ago = now - timedelta(hours=1)
                if (
                    tx.count_requests_since(user_id, hour_ago)
                    >= self._ctx.timers.max_requests_per_hour
                ):
                    raise too_many("rate_limited", "Too many requests this hour; try again later")
                tx.update_search(replace(search, joined_at=now))
        return self.status(user_id, search_id)

    def status(self, user_id: str, search_id: str) -> SearchStatusView:
        with self._ctx.repo.read() as tx:
            _own(tx, user_id, search_id)
        self._lifecycle.advance_search(search_id)
        now = self._ctx.clock.now()
        with self._ctx.repo.read() as tx:
            search = _own(tx, user_id, search_id)
            pending = tx.pending_request_for_search(search_id)
            left = 0 if pending is None else max(0, int((pending.expires_at - now).total_seconds()))
            match = (
                tx.match_for_search(search_id) if search.status is SearchStatus.MATCHED else None
            )
            return SearchStatusView(
                status=search.status,
                seconds_left=left,
                match_id=match.id if match else None,
                asking=_asking(tx, pending),
                request_id=pending.id if pending else None,
                joined=search.joined_at is not None,
                label=search.label,
                offered_group=search.offered_group,
            )

    def cancel(self, user_id: str, search_id: str) -> SearchStatus:
        with self._ctx.repo.tx() as tx:
            search = _own(tx, user_id, search_id, Lock.WAIT)
            if search.status is not SearchStatus.ACTIVE:
                return search.status
            pending = tx.pending_request_for_search(search_id)
            if pending is not None:
                tx.update_request(replace(pending, status=RequestStatus.CANCELLED))
            tx.update_search(replace(search, status=SearchStatus.CANCELLED))
            return SearchStatus.CANCELLED


def _asking(tx: Tx, pending: StudyRequest | None) -> PersonView | None:
    """The host holding the pending request, as the seeker may see them before accept (D43)."""
    if pending is None:
        return None
    session = tx.session(pending.host_session_id)
    host = tx.user(session.user_id) if session else None
    return PersonView(host.first_name, host.major) if host else None
