"""Family calendar: settings, the calendar view, conversion suggestions and the ICS feed (ADR-0022).

Everything is evaluated as the reader: a date shows only if they may see it in full (a living
person's birthday follows the birth-date field groups; a redacted date never carries its tithi).
Computed tithi dates appear only for a convention offered at the city (``conventions.offered``).
"""

from __future__ import annotations

import datetime as dt
import hashlib
import secrets
import uuid
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.context import TreeContext, load_tree_context
from app.authz.permissions import Permission
from app.core import audit
from app.core.config import get_settings
from app.core.errors import Forbidden, NotFound, Unprocessable
from app.core.lunar import LunarDate
from app.core.ratelimit import enforce
from app.models import CalendarFeed, Event, User
from app.models.enums import ReminderKind, ReminderRecurrence
from app.modules.calendar import conventions, engine, observance
from app.modules.calendar.schemas import (
    CalendarEntryOut,
    CalendarOut,
    CalendarSettingsIn,
    CalendarSettingsOut,
    CityOut,
    ConventionOut,
    ConvertIn,
    ConvertOut,
    FeedOut,
)
from app.modules.genealogy.schemas import EventOut
from app.modules.notifications import schedule
from app.modules.notifications.service import KIND_FOR_TYPE, _principal_name, label_for

MAX_RANGE_DAYS = 400
FEEDS_PER_MINUTE = 30


def _lang(ctx: TreeContext) -> str:
    lang = (ctx.user.preferred_language if ctx.user else "en") or "en"
    return "hi" if lang.startswith("hi") else "en"


def _require_member(ctx: TreeContext) -> uuid.UUID:
    ctx.require(Permission.TREE_READ)
    if ctx.user_id is None or not ctx.is_member:
        raise NotFound("Tree not found")
    return ctx.user_id


# ---------------------------------------------------------------- settings
def get_calendar_settings(ctx: TreeContext) -> CalendarSettingsOut:
    _require_member(ctx)
    lang = _lang(ctx)
    return CalendarSettingsOut(
        convention=ctx.tree.calendar_convention,
        observance_city=ctx.tree.observance_city,
        conventions=[
            ConventionOut(
                key=c.key,
                label=c.labels[lang],
                golden_verified=conventions.verified(c.key, ctx.tree.observance_city or ""),
                offered=conventions.offered(c.key, ctx.tree.observance_city),
            )
            for c in conventions.all_conventions().values()
        ],
        cities=[
            CityOut(key=c.key, label=c.hi if lang == "hi" else c.en, timezone=c.tz)
            for c in conventions.cities().values()
        ],
        lunar_enabled=conventions.lunar_enabled(),
    )


def set_calendar_settings(ctx: TreeContext, body: CalendarSettingsIn) -> CalendarSettingsOut:
    """The family's convention and observance city: chosen by a tree admin, never inferred."""
    ctx.require(Permission.TREE_MANAGE)
    if body.convention is not None and body.convention not in conventions.all_conventions():
        raise Unprocessable("Unknown calendar convention", code="unknown_convention")
    if body.observance_city is not None and body.observance_city not in conventions.cities():
        raise Unprocessable("Unknown city", code="unknown_city")
    fields = body.model_fields_set
    if "convention" in fields:
        ctx.tree.calendar_convention = body.convention
    if "observance_city" in fields:
        ctx.tree.observance_city = body.observance_city
    ctx.db.flush()
    audit.log(
        ctx,
        "calendar.settings_changed",
        target_type="tree",
        target_id=ctx.tree_id,
        details={"fields": sorted(fields)},
    )
    return get_calendar_settings(ctx)


# ---------------------------------------------------------------- the calendar
def _solar_entries(
    ctx: TreeContext, events: list[EventOut], start: dt.date, end: dt.date
) -> list[CalendarEntryOut]:
    out = []
    lang = _lang(ctx)
    for eo in events:
        kind = KIND_FOR_TYPE.get(eo.type)
        if kind is None:
            continue
        try:
            anchor = schedule.anchor_from_date(eo.date, ReminderRecurrence.ANNUAL)
        except schedule.NotSchedulable:
            continue  # no visible full day and month
        pid, _ = _principal_name(eo)
        for year in range(start.year, end.year + 1):
            day = schedule.occurrence_in(anchor, year)
            if not (start <= day <= end) or (anchor.year and year < anchor.year):
                continue
            nth = year - anchor.year if anchor.year else None
            out.append(
                CalendarEntryOut(
                    day=day,
                    kind=kind,
                    event_id=eo.id,
                    person_id=pid,
                    label=label_for(eo, kind, lang),
                    anniversary=nth if nth and nth > 0 else None,
                    basis="solar",
                )
            )
    return out


def _lunar_entries(
    ctx: TreeContext, events: list[EventOut], start: dt.date, end: dt.date, convention: str, city: str
) -> list[CalendarEntryOut]:
    out = []
    lang = _lang(ctx)
    conv = conventions.all_conventions()[convention]
    for eo in events:
        kind = KIND_FOR_TYPE.get(eo.type)
        raw = eo.date or {}
        if kind is None or not raw.get("lunar") or raw.get("redacted"):
            continue
        lunar = LunarDate.model_validate(raw["lunar"])
        pid, _ = _principal_name(eo)
        for day in observance.cached_days(lunar, convention, kind.value, city, start, end):
            out.append(
                CalendarEntryOut(
                    day=day,
                    kind=kind,
                    event_id=eo.id,
                    person_id=pid,
                    label=label_for(eo, kind, lang),
                    basis="lunar",
                    lunar_label=lunar.label(lang),
                    convention=convention,
                    rule=conv.rule_for(kind.value),
                    city=city,
                )
            )
    return out


def calendar(ctx: TreeContext, start: dt.date, end: dt.date) -> CalendarOut:
    _require_member(ctx)
    if end < start or (end - start).days > MAX_RANGE_DAYS:
        raise Unprocessable(f"Choose a range of at most {MAX_RANGE_DAYS} days", code="range_too_long")
    from app.modules.lifeevents.service import serialize_events

    rows = list(
        ctx.db.scalars(
            select(Event)
            .where(Event.tree_id == ctx.tree_id, Event.type.in_(list(KIND_FOR_TYPE)), Event.date.is_not(None))
            .limit(5000)
        )
    )
    events = serialize_events(ctx, rows)  # privacy-filtered as the reader; redacted dates lose their tithi
    entries = _solar_entries(ctx, events, start, end)
    convention, city = ctx.tree.calendar_convention, ctx.tree.observance_city
    why: Any = None
    if not conventions.lunar_enabled():
        why = "disabled"
    elif not city:
        why = "no_city"
    elif not conventions.offered(convention, city):
        why = "convention_not_offered"  # not signed off, verified and activated for this city
    else:
        entries += _lunar_entries(ctx, events, start, end, str(convention), city)
    entries.sort(key=lambda e: (e.day, e.label))
    return CalendarOut(start=start, end=end, entries=entries, lunar_unavailable=why)


# ---------------------------------------------------------------- conversion (a suggestion)
def convert(ctx: TreeContext, body: ConvertIn) -> ConvertOut:
    """The probable Gregorian day of a lunar date with a samvat year. Nothing is stored."""
    _require_member(ctx)
    convention = body.convention or ctx.tree.calendar_convention
    city = body.observance_city or ctx.tree.observance_city
    if not city or city not in conventions.cities():
        raise Unprocessable("Choose the city where the day is observed", code="observance_place_required")
    if not conventions.offered(convention, city):
        raise Unprocessable(
            "Finding the Gregorian date is not available yet for this convention and city",
            code="lunar_not_available",
        )
    if body.lunar.year is None or body.lunar.samvat is None:
        raise Unprocessable("A samvat year is needed to find a Gregorian date", code="year_required")
    conv = conventions.all_conventions()[str(convention)]
    found = observance.suggest_gregorian(body.lunar, conv, conventions.cities()[city].place())
    return ConvertOut(
        suggestion=found.day if found else None,
        convention=conv.key,
        rule=conv.rule_for("default"),
        city=city,
        engine_version=engine.ENGINE_VERSION,
    )


# ---------------------------------------------------------------- the ICS feed (§7)
def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _active_feed(ctx: TreeContext) -> CalendarFeed | None:
    return ctx.db.scalar(
        select(CalendarFeed).where(
            CalendarFeed.tree_id == ctx.tree_id,
            CalendarFeed.user_id == ctx.user_id,
            CalendarFeed.revoked_at.is_(None),
        )
    )


def _feed_out(f: CalendarFeed | None, url: str | None = None) -> FeedOut:
    if f is None:
        return FeedOut(active=False)
    return FeedOut(
        active=True,
        include_names=f.include_names,
        created_at=f.created_at,
        last_used_at=f.last_used_at,
        url=url,
    )


def feed_status(ctx: TreeContext) -> FeedOut:
    _require_member(ctx)
    return _feed_out(_active_feed(ctx))


def create_feed(ctx: TreeContext, include_names: bool) -> FeedOut:
    """Create (or replace) the member's feed; the URL is shown once."""
    user_id = _require_member(ctx)
    now = dt.datetime.now(dt.UTC)
    old = _active_feed(ctx)
    if old is not None:
        old.revoked_at = now
        ctx.db.flush()
    token = secrets.token_urlsafe(32)  # 256 bits
    feed = CalendarFeed(
        tree_id=ctx.tree_id, user_id=user_id, token_hash=_hash(token), include_names=include_names
    )
    ctx.db.add(feed)
    ctx.db.flush()
    audit.log(
        ctx,
        "calendar.feed_created",
        target_type="calendar_feed",
        target_id=feed.id,
        details={"include_names": include_names, "replaced": old is not None},
    )
    url = f"{get_settings().public_base_url}{get_settings().api_prefix}/calendar-feeds/{token}.ics"
    return _feed_out(feed, url)


def revoke_feed(ctx: TreeContext) -> FeedOut:
    _require_member(ctx)
    f = _active_feed(ctx)
    if f is None:
        raise NotFound("No calendar feed")
    f.revoked_at = dt.datetime.now(dt.UTC)
    ctx.db.flush()
    audit.log(ctx, "calendar.feed_revoked", target_type="calendar_feed", target_id=f.id)
    return _feed_out(None)


_ICS_KIND = {
    "en": {
        ReminderKind.BIRTHDAY: "Birthday",
        ReminderKind.ANNIVERSARY: "Wedding anniversary",
        ReminderKind.MEMORIAL: "Remembrance",
    },
    "hi": {
        ReminderKind.BIRTHDAY: "जन्मदिन",
        ReminderKind.ANNIVERSARY: "विवाह वर्षगाँठ",
        ReminderKind.MEMORIAL: "स्मृति",
    },
}


def _ics_text(value: str) -> str:
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\n", "\\n")


def _fold(line: str) -> str:
    """RFC 5545 §3.1: lines of at most 75 octets, continued with a space."""
    raw = line.encode()
    if len(raw) <= 75:
        return line
    parts: list[str] = []
    cur = b""
    for ch in line:
        b = ch.encode()
        if len(cur) + len(b) > (75 if not parts else 74):
            parts.append(cur.decode())
            cur = b""
        cur += b
    parts.append(cur.decode())
    return "\r\n ".join(parts)


def render_ics(entries: list[CalendarEntryOut], include_names: bool, lang: str, tree_url: str) -> str:
    now = dt.datetime.now(dt.UTC).strftime("%Y%m%dT%H%M%SZ")
    lines = [
        "BEGIN:VCALENDAR",
        "VERSION:2.0",
        "PRODID:-//Vanshavali//Family calendar//EN",
        "CALSCALE:GREGORIAN",
        "X-WR-CALNAME:Vanshavali",
    ]
    for e in entries:
        kind = _ICS_KIND[lang].get(e.kind, "Family day" if lang == "en" else "पारिवारिक दिन")
        summary = e.label if include_names else kind
        if e.basis == "lunar" and e.lunar_label and include_names:
            summary += f" ({e.lunar_label})"
        lines += [
            "BEGIN:VEVENT",
            f"UID:{e.event_id}-{e.day:%Y%m%d}-{e.basis}@vanshavali",
            f"DTSTAMP:{now}",
            f"DTSTART;VALUE=DATE:{e.day:%Y%m%d}",
            f"DTEND;VALUE=DATE:{e.day + dt.timedelta(days=1):%Y%m%d}",
            f"SUMMARY:{_ics_text(summary)}",
            f"URL:{tree_url}",
            "TRANSP:TRANSPARENT",
            "END:VEVENT",
        ]
    lines.append("END:VCALENDAR")
    return "\r\n".join(_fold(x) for x in lines) + "\r\n"


def feed_ics(db: Session, token: str) -> str:
    """The feed body, evaluated as its member right now: empty once they have lost access."""
    h = _hash(token)
    enforce(f"calendar-feed:{h[:16]}", FEEDS_PER_MINUTE)
    feed = db.scalar(
        select(CalendarFeed).where(CalendarFeed.token_hash == h, CalendarFeed.revoked_at.is_(None))
    )
    if feed is None:
        raise NotFound("Not found")
    user = db.get(User, feed.user_id)
    if user is None or not user.is_active:
        raise NotFound("Not found")
    feed.last_used_at = dt.datetime.now(dt.UTC)
    db.commit()
    lang = "hi" if (user.preferred_language or "").startswith("hi") else "en"
    tree_url = f"{get_settings().public_base_url}/t/{feed.tree_id}/calendar"
    try:
        ctx = load_tree_context(db, feed.tree_id, user)
    except NotFound:
        return render_ics([], False, lang, tree_url)
    today = dt.date.today()
    try:
        out = calendar(ctx, today - dt.timedelta(days=30), today + dt.timedelta(days=365))
    except (Forbidden, NotFound):
        return render_ics([], False, lang, tree_url)
    return render_ics(out.entries, feed.include_names, lang, tree_url)
