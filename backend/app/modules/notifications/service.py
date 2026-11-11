"""Event reminders: preferences, subscriptions, scheduling, delivery and history (ADR-0016).

Reminders are **per user and opt-in**: a member subscribes themself to an event they can see. Nobody
can subscribe someone else. At send time the reminder is re-evaluated *as the recipient* (still a
member? event and full date still visible?), so a revoked permission stops reminders at once.

The scheduler (:func:`tick`) walks trees one at a time with the tree bound for row-level security,
materialises due deliveries idempotently (unique per reminder, channel, occurrence and lead time),
and enqueues one job per delivery. :func:`deliver` records the provider's outcome: ``sent``,
``retrying`` (with back-off) or ``failed``; deliveries that must not go out are ``cancelled`` with a
reason. Delivery rows never hold message bodies or addresses.
"""

from __future__ import annotations

import base64
import datetime as dt
import hashlib
import hmac
import logging
import secrets
import uuid
from dataclasses import dataclass
from typing import Any

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.authz.context import TreeContext, load_tree_context
from app.core import audit, events
from app.core.config import get_settings
from app.core.db import bind_tree, get_sessionmaker
from app.core.errors import Conflict, Forbidden, NotFound, Unprocessable
from app.core.jobs import enqueue
from app.core.ratelimit import enforce
from app.core.storage import decrypt, encrypt
from app.models import (
    Event,
    EventReminder,
    NotificationContact,
    NotificationDelivery,
    NotificationPreference,
    Tree,
    User,
)
from app.models.enums import (
    DeliveryStatus,
    EventType,
    NotificationChannel,
    ParticipantRole,
    ReminderDateRule,
    ReminderKind,
    ReminderRecurrence,
)
from app.modules.genealogy.schemas import EventOut
from app.modules.genealogy.service import get_event_checked
from app.modules.notifications import channels as ch
from app.modules.notifications import schedule
from app.modules.notifications.schemas import (
    ContactIn,
    ContactOut,
    DeliveryOut,
    PreferenceIn,
    PreferenceOut,
    ReminderIn,
    ReminderOut,
    ReminderUpdate,
    UpcomingOut,
)

log = logging.getLogger("app.notifications")

# retry back-off after the 1st, 2nd and 3rd failed attempt; the 4th failure is final
RETRY_BACKOFF_S = (120, 900, 3600)
MAX_ATTEMPTS = len(RETRY_BACKOFF_S) + 1
TEST_SENDS_PER_HOUR = 5
CODE_TTL = dt.timedelta(minutes=10)
MAX_CODE_ATTEMPTS = 5

KIND_FOR_TYPE = {
    EventType.BIRTH: ReminderKind.BIRTHDAY,
    EventType.MARRIAGE: ReminderKind.ANNIVERSARY,
    EventType.DEATH: ReminderKind.MEMORIAL,
    EventType.MEMORIAL: ReminderKind.MEMORIAL,
    EventType.CREMATION: ReminderKind.MEMORIAL,
    EventType.BURIAL: ReminderKind.MEMORIAL,
}
ANNUAL_KINDS = {ReminderKind.BIRTHDAY, ReminderKind.ANNIVERSARY, ReminderKind.MEMORIAL}


def _now() -> dt.datetime:
    return dt.datetime.now(dt.UTC)


# ---------------------------------------------------------------- labels and messages
_LABELS = {
    "en": {
        ReminderKind.BIRTHDAY: "{name}'s birthday",
        ReminderKind.ANNIVERSARY: "{name}'s wedding anniversary",
        ReminderKind.MEMORIAL: "Remembering {name}",
        "event": "{title}",
        "someone": "a family member",
        "subject": "Reminder: {label} — {when}",
        "today": "today",
        "in_days": "in {n} days",
        "tomorrow": "tomorrow",
        "nth": "{n} years",
        "open": "Open in Vanshavali",
        "why": "You asked Vanshavali to remind you about this. Change or stop reminders: {url}",
        "short": "Vanshavali: family reminder ({kind}) {when}, {date}. {url}",
        ReminderKind.ONE_TIME: "event",
        ReminderKind.CUSTOM: "event",
        "kind_birthday": "birthday",
        "kind_anniversary": "anniversary",
        "kind_memorial": "remembrance",
        "kind_event": "event",
        "test": "[Test] ",
    },
    "hi": {
        ReminderKind.BIRTHDAY: "{name} का जन्मदिन",
        ReminderKind.ANNIVERSARY: "{name} की विवाह वर्षगाँठ",
        ReminderKind.MEMORIAL: "{name} की पुण्यतिथि / स्मृति",
        "event": "{title}",
        "someone": "परिवार के एक सदस्य",
        "subject": "अनुस्मारक: {label} — {when}",
        "today": "आज",
        "in_days": "{n} दिन में",
        "tomorrow": "कल",
        "nth": "{n} वर्ष",
        "open": "वंशावली में खोलें",
        "why": "आपने वंशावली से यह याद दिलाने को कहा था। अनुस्मारक बदलें या बंद करें: {url}",
        "short": "वंशावली: पारिवारिक अनुस्मारक ({kind}) {when}, {date}। {url}",
        ReminderKind.ONE_TIME: "event",
        ReminderKind.CUSTOM: "event",
        "kind_birthday": "जन्मदिन",
        "kind_anniversary": "वर्षगाँठ",
        "kind_memorial": "स्मृति",
        "kind_event": "आयोजन",
        "test": "[परीक्षण] ",
    },
}


def _lang(user: User) -> str:
    return "hi" if (user.preferred_language or "").startswith("hi") else "en"


def _principal_name(eo: EventOut) -> tuple[uuid.UUID | None, str | None]:
    p = next((p for p in eo.participants if p.role == ParticipantRole.PRINCIPAL), None)
    return (p.person_id, p.display_name) if p else (None, None)


def label_for(eo: EventOut, kind: ReminderKind, lang: str = "en") -> str:
    t = _LABELS[lang]
    _pid, name = _principal_name(eo)
    if kind in ANNUAL_KINDS and not eo.title:
        return str(t[kind]).format(name=name or t["someone"])
    if eo.title:
        return eo.title
    if kind in ANNUAL_KINDS:
        return str(t[kind]).format(name=name or t["someone"])
    base = (eo.category.value if eo.category else eo.type.value).replace("_", " ")
    return f"{base.capitalize()} — {name}" if name else base.capitalize()


def _when(days: int, lang: str) -> str:
    t = _LABELS[lang]
    if days <= 0:
        return t["today"]
    if days == 1:
        return t["tomorrow"]
    return t["in_days"].format(n=days)


# ---------------------------------------------------------------- preferences
def _pref(ctx: TreeContext) -> NotificationPreference | None:
    return ctx.db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.tree_id == ctx.tree_id, NotificationPreference.user_id == ctx.user_id
        )
    )


def _pref_out(p: NotificationPreference | None) -> PreferenceOut:
    if p is None:
        return PreferenceOut(
            enabled=False,
            channels=[NotificationChannel.EMAIL],
            timezone="Asia/Kolkata",
            send_hour=8,
            default_lead_days=[0],
            exists=False,
        )
    return PreferenceOut(
        enabled=p.enabled,
        channels=[NotificationChannel(c) for c in p.channels],
        timezone=p.timezone,
        send_hour=p.send_hour,
        default_lead_days=list(p.default_lead_days),
    )


def get_preferences(ctx: TreeContext) -> PreferenceOut:
    return _pref_out(_pref(ctx))


def _require_member(ctx: TreeContext) -> uuid.UUID:
    if ctx.public or ctx.user_id is None:
        raise Forbidden()
    return ctx.user_id


def _check_channels(ctx: TreeContext, channels: list[NotificationChannel]) -> None:
    for c in channels:
        if not ch.channel_available(c):
            raise Unprocessable(
                f"{c.value} reminders are not available on this server", code="channel_unavailable"
            )
        if c != NotificationChannel.EMAIL and _verified_contact(ctx.db, ctx.user_id, c) is None:
            raise Unprocessable(
                f"Add and verify a phone number for {c.value} first", code="contact_not_verified"
            )


def set_preferences(ctx: TreeContext, body: PreferenceIn) -> PreferenceOut:
    user_id = _require_member(ctx)
    if body.enabled:
        _check_channels(ctx, body.channels)
    p = _pref(ctx)
    if p is None:
        p = NotificationPreference(tree_id=ctx.tree_id, user_id=user_id, created_by=user_id)
        ctx.db.add(p)
    p.enabled = body.enabled
    p.channels = [c.value for c in body.channels]
    p.timezone = body.timezone
    p.send_hour = body.send_hour
    p.default_lead_days = list(body.default_lead_days)
    p.updated_by = user_id
    ctx.db.flush()
    _reschedule_all(ctx, p)
    audit.log(
        ctx,
        "notifications.preferences_changed",
        target_type="notification_preference",
        target_id=p.id,
        details={"enabled": p.enabled, "channels": p.channels},
    )
    return _pref_out(p)


# ---------------------------------------------------------------- reminders
def _visible_event(ctx: TreeContext, event_id: uuid.UUID) -> EventOut:
    from app.modules.lifeevents.service import serialize_events

    e, _ = get_event_checked(ctx, event_id)
    out = serialize_events(ctx, [e])
    if not out:
        raise NotFound("Event not found")
    return out[0]


def _anchor(
    eo: EventOut, recurrence: ReminderRecurrence, r: EventReminder | None = None
) -> schedule.AnyAnchor:
    try:
        return _anchor_raw(eo.date, recurrence, r)
    except schedule.NotSchedulable as exc:
        raise Unprocessable(str(exc), code=exc.code)


def _anchor_raw(
    raw: dict[str, Any] | None, recurrence: ReminderRecurrence, r: EventReminder | None
) -> schedule.AnyAnchor:
    """The reminder's own rule (ADR-0022 §5): the Gregorian day, or the tithi at its city."""
    if r is None:
        return schedule.anchor_from_date(raw, recurrence)
    return schedule.anchor_for(raw, recurrence, r.date_rule, r.convention, r.observance_city, r.kind.value)


def _compute_next(
    r: EventReminder, pref: NotificationPreference, anchor: schedule.AnyAnchor, after: dt.datetime
) -> None:
    r.next_fire_at = schedule.next_fire(
        anchor, r.recurrence, r.lead_days, pref.send_hour, pref.timezone, after
    )


def _reschedule_all(ctx: TreeContext, pref: NotificationPreference) -> None:
    for r in ctx.db.scalars(
        select(EventReminder).where(
            EventReminder.tree_id == ctx.tree_id, EventReminder.user_id == pref.user_id
        )
    ):
        try:
            anchor = _anchor(_visible_event(ctx, r.event_id), r.recurrence, r)
        except (NotFound, Unprocessable):
            r.next_fire_at = None
            continue
        _compute_next(r, pref, anchor, max(_now(), r.last_fired_at or _now()))


def _get_reminder(ctx: TreeContext, reminder_id: uuid.UUID) -> EventReminder:
    r = ctx.db.scalar(
        select(EventReminder).where(
            EventReminder.tree_id == ctx.tree_id,
            EventReminder.id == reminder_id,
            EventReminder.user_id == ctx.user_id,  # only your own reminders exist for you
        )
    )
    if r is None:
        raise NotFound("Reminder not found")
    return r


def create_reminder(ctx: TreeContext, body: ReminderIn) -> EventReminder:
    user_id = _require_member(ctx)
    eo = _visible_event(ctx, body.event_id)
    kind = body.kind or KIND_FOR_TYPE.get(eo.type, ReminderKind.ONE_TIME)
    recurrence = body.recurrence or (
        ReminderRecurrence.ANNUAL if kind in ANNUAL_KINDS else ReminderRecurrence.NONE
    )
    lunar = body.date_rule == ReminderDateRule.LUNAR
    draft = EventReminder(
        kind=kind,
        recurrence=recurrence,
        date_rule=body.date_rule,
        # a lunar reminder follows the tree's convention and city unless the member chose their own
        convention=(body.convention or ctx.tree.calendar_convention) if lunar else None,
        observance_city=(body.observance_city or ctx.tree.observance_city) if lunar else None,
    )
    anchor = _anchor(eo, recurrence, draft)
    pref = _pref(ctx)
    if pref is None:
        # subscribing to a reminder is the explicit opt-in for this tree (email unless chosen)
        pref = NotificationPreference(
            tree_id=ctx.tree_id,
            user_id=user_id,
            enabled=True,
            channels=[c.value for c in (body.channels or [NotificationChannel.EMAIL])],
            created_by=user_id,
        )
        ctx.db.add(pref)
        ctx.db.flush()
    channels = body.channels or [NotificationChannel(c) for c in pref.channels] or [NotificationChannel.EMAIL]
    _check_channels(ctx, channels)
    lead = body.lead_days or list(pref.default_lead_days) or [0]
    if (
        recurrence == ReminderRecurrence.NONE
        and schedule.next_occurrence(anchor, recurrence, _now().date()) is None
    ):
        raise Unprocessable(
            "This date has passed; choose a yearly reminder to remember it every year", code="date_in_past"
        )
    r = EventReminder(
        tree_id=ctx.tree_id,
        event_id=eo.id,
        user_id=user_id,
        kind=kind,
        recurrence=recurrence,
        date_rule=draft.date_rule,
        convention=draft.convention,
        observance_city=draft.observance_city,
        lead_days=lead,
        channels=[c.value for c in channels],
        note=(body.note or "").strip() or None,
        created_by=user_id,
    )
    _compute_next(r, pref, anchor, _now())
    ctx.db.add(r)
    try:
        ctx.db.flush()
    except IntegrityError:
        ctx.db.rollback()
        raise Conflict("You already have a reminder for this event", code="duplicate_reminder")
    audit.log(
        ctx,
        "reminder.created",
        target_type="event_reminder",
        target_id=r.id,
        details={
            "event_id": str(eo.id),
            "kind": kind.value,
            "channels": r.channels,
            "lead_days": lead,
            "date_rule": r.date_rule.value,
        },
    )
    return r


def update_reminder(ctx: TreeContext, reminder_id: uuid.UUID, body: ReminderUpdate) -> EventReminder:
    _require_member(ctx)
    r = _get_reminder(ctx, reminder_id)
    if body.channels is not None:
        _check_channels(ctx, body.channels)
        r.channels = [c.value for c in body.channels]
    if body.lead_days is not None:
        r.lead_days = body.lead_days
    if body.recurrence is not None:
        r.recurrence = body.recurrence
    if "note" in body.model_fields_set:
        r.note = (body.note or "").strip() or None
    if body.active is not None:
        r.active = body.active
    if body.date_rule is not None:
        r.date_rule = body.date_rule
    if "convention" in body.model_fields_set:
        r.convention = body.convention
    if "observance_city" in body.model_fields_set:
        r.observance_city = body.observance_city
    if r.date_rule == ReminderDateRule.LUNAR:
        r.convention = r.convention or ctx.tree.calendar_convention
        r.observance_city = r.observance_city or ctx.tree.observance_city
    eo = _visible_event(ctx, r.event_id)
    anchor = _anchor(eo, r.recurrence, r)
    pref = _pref(ctx)
    if pref is None:  # a reminder implies a preference row; recreate defaults if it was removed
        pref = NotificationPreference(
            tree_id=ctx.tree_id, user_id=ctx.user_id, enabled=True, channels=r.channels
        )
        ctx.db.add(pref)
        ctx.db.flush()
    _compute_next(r, pref, anchor, max(_now(), r.last_fired_at or _now()))
    r.updated_by = ctx.user_id
    ctx.db.flush()
    audit.log(
        ctx,
        "reminder.changed",
        target_type="event_reminder",
        target_id=r.id,
        details={"fields": sorted(body.model_fields_set)},
    )
    return r


def delete_reminder(ctx: TreeContext, reminder_id: uuid.UUID) -> None:
    _require_member(ctx)
    r = _get_reminder(ctx, reminder_id)
    # pending deliveries for it will not go out
    for d in ctx.db.scalars(
        select(NotificationDelivery).where(
            NotificationDelivery.tree_id == ctx.tree_id,
            NotificationDelivery.reminder_id == r.id,
            NotificationDelivery.status.in_([DeliveryStatus.PENDING, DeliveryStatus.RETRYING]),
        )
    ):
        d.status, d.cancelled_reason = DeliveryStatus.CANCELLED, "reminder_deleted"
    ctx.db.delete(r)
    audit.log(ctx, "reminder.deleted", target_type="event_reminder", target_id=r.id)


def reminder_out(ctx: TreeContext, r: EventReminder, eo: EventOut | None = None) -> ReminderOut:
    out = ReminderOut.model_validate(r)
    if eo is None:
        try:
            eo = _visible_event(ctx, r.event_id)
        except NotFound:
            eo = None
    if eo is None:
        return out.model_copy(update={"deliverable": False, "next_fire_at": None})
    pid, name = _principal_name(eo)
    nxt = None
    deliverable = True
    try:
        nxt = schedule.next_occurrence(_anchor(eo, r.recurrence, r), r.recurrence, _now().date())
    except Unprocessable:
        deliverable = False
    return out.model_copy(
        update={
            "label": label_for(eo, r.kind, _lang(ctx.user) if ctx.user else "en"),
            "person_id": pid,
            "person_name": name,
            "next_occurrence": nxt,
            "deliverable": deliverable,
        }
    )


def list_reminders(ctx: TreeContext, event_id: uuid.UUID | None = None) -> list[ReminderOut]:
    _require_member(ctx)
    stmt = select(EventReminder).where(
        EventReminder.tree_id == ctx.tree_id, EventReminder.user_id == ctx.user_id
    )
    if event_id is not None:
        stmt = stmt.where(EventReminder.event_id == event_id)
    rows = list(ctx.db.scalars(stmt.order_by(EventReminder.next_fire_at.asc().nulls_last())))
    from app.modules.lifeevents.service import serialize_events

    events_by_id = (
        {
            eo.id: eo
            for eo in serialize_events(
                ctx,
                list(
                    ctx.db.scalars(
                        select(Event).where(
                            Event.tree_id == ctx.tree_id, Event.id.in_([r.event_id for r in rows])
                        )
                    )
                ),
            )
        }
        if rows
        else {}
    )
    return [
        reminder_out(ctx, r, events_by_id.get(r.event_id))
        if r.event_id in events_by_id
        else reminder_out(ctx, r, None)
        for r in rows
    ]


# ---------------------------------------------------------------- upcoming dates
def upcoming(ctx: TreeContext, days: int, scope: str) -> list[UpcomingOut]:
    """Upcoming birthdays/anniversaries/remembrance days (``scope=tree``) or your reminders (``mine``),
    as visible to you: a living relative's birthday appears only if you may see their full birth date."""
    user_id = _require_member(ctx)
    today = _now().date()
    horizon = today + dt.timedelta(days=days)
    mine = {
        r.event_id: r
        for r in ctx.db.scalars(
            select(EventReminder).where(
                EventReminder.tree_id == ctx.tree_id, EventReminder.user_id == user_id
            )
        )
    }
    from app.modules.lifeevents.service import serialize_events

    if scope == "mine":
        candidates = list(
            ctx.db.scalars(select(Event).where(Event.tree_id == ctx.tree_id, Event.id.in_(list(mine))))
        )
    else:
        candidates = list(
            ctx.db.scalars(
                select(Event)
                .where(
                    Event.tree_id == ctx.tree_id,
                    Event.type.in_(list(KIND_FOR_TYPE)),
                    Event.date_sort_from.is_not(None),
                    Event.date_sort_from == Event.date_sort_to,  # an exact day
                )
                .limit(5000)
            )
        )
    out: list[UpcomingOut] = []
    lang = _lang(ctx.user) if ctx.user else "en"
    for eo in serialize_events(ctx, candidates):
        r = mine.get(eo.id)
        kind = r.kind if r else KIND_FOR_TYPE.get(eo.type, ReminderKind.ONE_TIME)
        recurrence = r.recurrence if r else ReminderRecurrence.ANNUAL
        try:
            anchor = schedule.anchor_from_date(eo.date, recurrence)
        except schedule.NotSchedulable:
            continue
        occ = schedule.next_occurrence(anchor, recurrence, today)
        if occ is None or occ > horizon:
            continue
        pid, name = _principal_name(eo)
        nth = occ.year - anchor.year if anchor.year and recurrence == ReminderRecurrence.ANNUAL else None
        out.append(
            UpcomingOut(
                event_id=eo.id,
                kind=kind,
                occurrence_date=occ,
                days_until=(occ - today).days,
                label=label_for(eo, kind, lang),
                person_id=pid,
                display_name=name,
                anniversary=nth if nth and nth > 0 else None,
                reminder_id=r.id if r else None,
            )
        )
    out.sort(key=lambda u: (u.occurrence_date, u.label))
    return out


# ---------------------------------------------------------------- history
def history(ctx: TreeContext, limit: int, offset: int) -> tuple[list[DeliveryOut], bool]:
    user_id = _require_member(ctx)
    rows = list(
        ctx.db.scalars(
            select(NotificationDelivery)
            .where(NotificationDelivery.tree_id == ctx.tree_id, NotificationDelivery.user_id == user_id)
            .order_by(NotificationDelivery.scheduled_for.desc(), NotificationDelivery.id)
            .offset(offset)
            .limit(limit + 1)
        )
    )
    from app.modules.lifeevents.service import serialize_events

    ids = {d.event_id for d in rows if d.event_id}
    visible = (
        {
            eo.id: eo
            for eo in serialize_events(
                ctx,
                list(ctx.db.scalars(select(Event).where(Event.tree_id == ctx.tree_id, Event.id.in_(ids)))),
            )
        }
        if ids
        else {}
    )
    reminders = {
        r.id: r
        for r in ctx.db.scalars(
            select(EventReminder).where(
                EventReminder.tree_id == ctx.tree_id,
                EventReminder.id.in_({d.reminder_id for d in rows if d.reminder_id}),
            )
        )
    }
    lang = _lang(ctx.user) if ctx.user else "en"
    out = []
    for d in rows[:limit]:
        eo = visible.get(d.event_id) if d.event_id else None
        kind = reminders[d.reminder_id].kind if d.reminder_id in reminders else ReminderKind.ONE_TIME
        out.append(
            DeliveryOut.model_validate(d).model_copy(
                update={"label": label_for(eo, kind, lang) if eo else None}
            )
        )
    return out, len(rows) > limit


# ---------------------------------------------------------------- test send
def send_test(ctx: TreeContext, reminder_id: uuid.UUID) -> list[NotificationDelivery]:
    """Send this reminder now, once per channel, marked as a test (rate limited)."""
    user_id = _require_member(ctx)
    r = _get_reminder(ctx, reminder_id)
    _visible_event(ctx, r.event_id)
    since = _now() - dt.timedelta(hours=1)
    recent = ctx.db.scalar(
        select(func.count())
        .select_from(NotificationDelivery)
        .where(
            NotificationDelivery.tree_id == ctx.tree_id,
            NotificationDelivery.user_id == user_id,
            NotificationDelivery.is_test.is_(True),
            NotificationDelivery.created_at >= since,
        )
    )
    if (recent or 0) >= TEST_SENDS_PER_HOUR:
        raise Unprocessable("Too many test reminders; try again later", code="rate_limited")
    out = []
    now = _now()
    for c in r.channels:
        d = NotificationDelivery(
            tree_id=ctx.tree_id,
            reminder_id=None,  # tests never count against the reminder's own schedule
            event_id=r.event_id,
            user_id=user_id,
            channel=NotificationChannel(c),
            occurrence_date=now.date(),
            lead_days=0,
            scheduled_for=now,
            is_test=True,
            created_by=user_id,
        )
        ctx.db.add(d)
        out.append(d)
    ctx.db.flush()
    audit.log(
        ctx,
        "reminder.test_sent",
        target_type="event_reminder",
        target_id=r.id,
        details={"channels": r.channels},
    )
    ctx.db.commit()
    for d in out:
        enqueue(deliver, str(d.id), str(ctx.tree_id))
    for d in out:
        ctx.db.refresh(d)
    return out


# ---------------------------------------------------------------- scheduler
@dataclass
class TickResult:
    trees: int = 0
    reminders: int = 0
    created: int = 0
    enqueued: int = 0


def tick(now: dt.datetime | None = None) -> TickResult:
    """Materialise due deliveries and (re-)enqueue pending ones. Safe to run concurrently and often."""
    now = now or _now()
    res = TickResult()
    maker = get_sessionmaker()
    with maker() as db:
        trees = list(db.scalars(select(Tree.id).where(Tree.deleted_at.is_(None))))
    grace = dt.timedelta(hours=get_settings().reminder_grace_hours)
    for tree_id in trees:
        to_send: list[str] = []
        created: list[NotificationDelivery] = []
        with maker() as db:
            bind_tree(db, tree_id)
            due = list(
                db.scalars(
                    select(EventReminder)
                    .where(
                        EventReminder.tree_id == tree_id,
                        EventReminder.active.is_(True),
                        EventReminder.next_fire_at.is_not(None),
                        EventReminder.next_fire_at <= now,
                    )
                    .with_for_update(skip_locked=True)
                )
            )
            if due:
                res.trees += 1
            prefs = {
                p.user_id: p
                for p in db.scalars(
                    select(NotificationPreference).where(NotificationPreference.tree_id == tree_id)
                )
            }
            for r in due:
                res.reminders += 1
                event = db.scalar(select(Event).where(Event.tree_id == tree_id, Event.id == r.event_id))
                pref = prefs.get(r.user_id)
                if event is None or pref is None:
                    r.next_fire_at = None
                    continue
                try:
                    # the raw date is used only for timing; content is re-checked as the recipient
                    anchor = _anchor_raw(event.date, r.recurrence, r)
                except schedule.NotSchedulable:
                    r.next_fire_at = None
                    continue
                window_start = max(r.last_fired_at or (now - grace), now - grace)
                for f in schedule.due_fires(
                    anchor, r.recurrence, r.lead_days, pref.send_hour, pref.timezone, window_start, now
                ):
                    for c in r.channels:
                        exists = db.scalar(
                            select(NotificationDelivery.id).where(
                                NotificationDelivery.tree_id == tree_id,
                                NotificationDelivery.reminder_id == r.id,
                                NotificationDelivery.channel == c,
                                NotificationDelivery.occurrence_date == f.occurrence,
                                NotificationDelivery.lead_days == f.lead_days,
                            )
                        )
                        if exists is not None:
                            continue
                        d = NotificationDelivery(
                            tree_id=tree_id,
                            reminder_id=r.id,
                            event_id=r.event_id,
                            user_id=r.user_id,
                            channel=NotificationChannel(c),
                            occurrence_date=f.occurrence,
                            lead_days=f.lead_days,
                            scheduled_for=f.at,
                        )
                        if not pref.enabled:
                            d.status, d.cancelled_reason = DeliveryStatus.CANCELLED, "notifications_paused"
                        db.add(d)
                        created.append(d)
                        res.created += 1
                r.last_fired_at = now
                r.next_fire_at = schedule.next_fire(
                    anchor, r.recurrence, r.lead_days, pref.send_hour, pref.timezone, now
                )
                if r.next_fire_at is None:
                    r.active = r.recurrence == ReminderRecurrence.ANNUAL
            db.flush()
            to_send.extend(str(d.id) for d in created if d.status == DeliveryStatus.PENDING)
            # deliveries whose job was lost (still pending after 10 minutes) and retries that are due
            stale = now - dt.timedelta(minutes=10)
            for d in db.scalars(
                select(NotificationDelivery).where(
                    NotificationDelivery.tree_id == tree_id,
                    (
                        (NotificationDelivery.status == DeliveryStatus.PENDING)
                        & (NotificationDelivery.updated_at < stale)
                    )
                    | (
                        (NotificationDelivery.status == DeliveryStatus.RETRYING)
                        & (NotificationDelivery.next_attempt_at <= now)
                    ),
                )
            ):
                if str(d.id) not in to_send:
                    to_send.append(str(d.id))
            db.commit()
        for did in to_send:
            enqueue(deliver, did, str(tree_id))
            res.enqueued += 1
    return res


# ---------------------------------------------------------------- delivery job
def _cancel(d: NotificationDelivery, reason: str) -> None:
    d.status, d.cancelled_reason, d.next_attempt_at = DeliveryStatus.CANCELLED, reason, None
    events.record("notification_cancelled")


def deliver(delivery_id: str, tree_id: str) -> str:
    """Job: send one delivery and record the outcome. Idempotent (sent/failed/cancelled are final)."""
    maker = get_sessionmaker()
    with maker() as db:
        bind_tree(db, tree_id)
        d = db.scalar(
            select(NotificationDelivery)
            .where(
                NotificationDelivery.tree_id == uuid.UUID(tree_id),
                NotificationDelivery.id == uuid.UUID(delivery_id),
            )
            .with_for_update(skip_locked=True)
        )
        if d is None or d.status not in (DeliveryStatus.PENDING, DeliveryStatus.RETRYING):
            return "skipped"
        status = _attempt(db, d)
        db.commit()
        return status


def _attempt(db: Session, d: NotificationDelivery) -> str:
    user = db.get(User, d.user_id)
    if user is None or not user.is_active:
        _cancel(d, "recipient_inactive")
        return d.status.value
    try:
        ctx = load_tree_context(db, d.tree_id, user)
    except NotFound:
        _cancel(d, "not_a_member")
        return d.status.value
    pref = db.scalar(
        select(NotificationPreference).where(
            NotificationPreference.tree_id == d.tree_id, NotificationPreference.user_id == user.id
        )
    )
    if not d.is_test and (pref is None or not pref.enabled):
        _cancel(d, "notifications_paused")
        return d.status.value
    if d.event_id is None:
        _cancel(d, "event_deleted")
        return d.status.value
    try:
        eo = _visible_event(ctx, d.event_id)
    except NotFound:
        _cancel(d, "no_longer_visible")
        return d.status.value
    reminder = db.get(EventReminder, d.reminder_id) if d.reminder_id else None
    kind = reminder.kind if reminder else KIND_FOR_TYPE.get(eo.type, ReminderKind.ONE_TIME)
    recurrence = reminder.recurrence if reminder else ReminderRecurrence.ANNUAL
    if not d.is_test:
        try:
            _anchor_raw(eo.date, recurrence, reminder)
        except schedule.NotSchedulable as exc:
            # the date became hidden, or a lunar convention is no longer offered
            _cancel(d, "date_hidden" if exc.code in ("date_hidden", "date_incomplete") else exc.code)
            return d.status.value
    try:
        msg = _compose(db, ctx, user, d, eo, kind, reminder)
    except ch.ProviderError as exc:
        _cancel(d, exc.code)
        return d.status.value
    d.attempts += 1
    try:
        result = ch.provider_for(d.channel).send(msg)
    except ch.ProviderError as exc:
        d.last_error_code = exc.code[:80]
        if exc.retryable and d.attempts < MAX_ATTEMPTS:
            d.status = DeliveryStatus.RETRYING
            d.next_attempt_at = _now() + dt.timedelta(seconds=RETRY_BACKOFF_S[d.attempts - 1])
            events.record("notification_retrying")
        else:
            d.status, d.next_attempt_at = DeliveryStatus.FAILED, None
            events.record("notification_failed")
        log.warning(
            "notification %s via %s attempt %d failed: %s", d.id, d.channel.value, d.attempts, exc.code
        )
        return d.status.value
    d.status, d.sent_at, d.next_attempt_at = DeliveryStatus.SENT, _now(), None
    d.provider, d.provider_message_id, d.last_error_code = result.provider[:40], result.message_id, None
    events.record("notification_sent")
    return d.status.value


def _compose(
    db: Session,
    ctx: TreeContext,
    user: User,
    d: NotificationDelivery,
    eo: EventOut,
    kind: ReminderKind,
    reminder: EventReminder | None,
) -> ch.OutboundMessage:
    s = get_settings()
    lang = _lang(user)
    t = _LABELS[lang]
    label = label_for(eo, kind, lang)
    pid, _name = _principal_name(eo)
    when = _when(d.lead_days if not d.is_test else 0, lang)
    date_text = d.occurrence_date.strftime("%d %b %Y")
    url = f"{s.public_base_url}/t/{d.tree_id}/" + (f"people/{pid}?tab=events" if pid else "events")
    manage = f"{s.public_base_url}/t/{d.tree_id}/reminders"
    prefix = t["test"] if d.is_test else ""
    if d.channel == NotificationChannel.EMAIL:
        lines = [f"{label} — {date_text} ({when})"]
        nth = None
        if eo.date and eo.date.get("year") and kind in ANNUAL_KINDS:
            nth = d.occurrence_date.year - int(eo.date["year"])
        if nth and nth > 0:
            lines.append(t["nth"].format(n=nth))
        if eo.place_name or eo.place_as_recorded:
            lines.append(str(eo.place_name or eo.place_as_recorded))
        if reminder and reminder.date_rule == ReminderDateRule.LUNAR:
            lines.append(_lunar_basis(eo, reminder, lang))
        if reminder and reminder.note:
            lines.append(reminder.note)
        text = "\n\n".join([*lines, f"{t['open']}: {url}", t["why"].format(url=manage), "— Vanshavali"])
        from html import escape

        html = (
            '<!doctype html><html><body style="font-family:sans-serif;line-height:1.5;color:#1f1a17">'
            + "".join(f"<p>{escape(x)}</p>" for x in lines)
            + f'<p><a href="{escape(url)}">{escape(t["open"])}</a></p>'
            + f'<p style="font-size:13px;color:#555">{escape(t["why"].format(url=manage))}</p>'
            "<p>— Vanshavali</p></body></html>"
        )
        return ch.OutboundMessage(
            channel=d.channel,
            to=user.email,
            subject=prefix + t["subject"].format(label=label, when=when),
            text=text,
            html=html,
            kind="reminder",
        )
    contact = _verified_contact(db, user.id, d.channel)
    if contact is None:
        raise ch.ProviderError("no_verified_contact", retryable=False)
    # SMS/WhatsApp go through third parties: no names, places or notes, only the kind, date and a link
    kind_word = t[f"kind_{kind.value}"] if kind in ANNUAL_KINDS else t["kind_event"]
    text = prefix + t["short"].format(kind=kind_word, when=when, date=date_text, url=url)
    return ch.OutboundMessage(
        channel=d.channel,
        to=decrypt(base64.b64decode(contact.address_enc), _aad(contact)).decode(),
        subject="",
        text=text,
        kind="reminder",
        template_params=[f"{prefix}{kind_word}", f"{when}, {date_text}", url],
    )


def _lunar_basis(eo: EventOut, r: EventReminder, lang: str) -> str:
    """How a tithi date was found: the tithi, convention, rule and city (ADR-0022 §5)."""
    from app.core.lunar import LunarDate
    from app.modules.calendar import conventions

    hi = lang.startswith("hi")
    lunar = LunarDate.model_validate((eo.date or {})["lunar"])
    conv = conventions.all_conventions()[str(r.convention)]
    city = conventions.cities()[str(r.observance_city)]
    rule = conv.rule_for(r.kind.value)
    rule_text = {
        "aparahna": ("afternoon rule", "अपराह्न नियम"),
        "sunrise": ("sunrise rule", "सूर्योदय नियम"),
    }[rule][1 if hi else 0]
    return f"{lunar.label(lang)} · {conv.labels['hi' if hi else 'en']} · {rule_text} · {city.hi if hi else city.en}"


# ---------------------------------------------------------------- contacts (user level)
def _aad(c: NotificationContact) -> str:
    return f"notification_contact:{c.user_id}:{c.channel.value}"


def _verified_contact(
    db: Session, user_id: uuid.UUID | None, channel: NotificationChannel
) -> NotificationContact | None:
    if user_id is None:
        return None
    return db.scalar(
        select(NotificationContact).where(
            NotificationContact.user_id == user_id,
            NotificationContact.channel == channel,
            NotificationContact.verified_at.is_not(None),
        )
    )


def _code_hash(contact_id: uuid.UUID, code: str) -> str:
    key = get_settings().signing_key.encode()
    return hmac.new(key, f"{contact_id}:{code}".encode(), hashlib.sha256).hexdigest()


def contact_out(c: NotificationContact) -> ContactOut:
    return ContactOut(
        id=c.id,
        channel=c.channel,
        address_hint=c.address_hint,
        verified=c.verified_at is not None,
        created_at=c.created_at,
    )


def list_contacts(db: Session, user: User) -> list[ContactOut]:
    return [
        contact_out(c)
        for c in db.scalars(
            select(NotificationContact)
            .where(NotificationContact.user_id == user.id)
            .order_by(NotificationContact.channel)
        )
    ]


def add_contact(db: Session, user: User, body: ContactIn) -> NotificationContact:
    if body.channel == NotificationChannel.EMAIL:
        raise Unprocessable(
            "Email reminders go to your account's verified address", code="email_is_account_address"
        )
    if not ch.channel_available(body.channel):
        raise Unprocessable(
            f"{body.channel.value} is not available on this server", code="channel_unavailable"
        )
    enforce(f"contact-code:{user.id}", 5, 3600)
    c = db.scalar(
        select(NotificationContact).where(
            NotificationContact.user_id == user.id, NotificationContact.channel == body.channel
        )
    )
    if c is None:
        c = NotificationContact(user_id=user.id, channel=body.channel, address_enc="", address_hint="")
        db.add(c)
        db.flush()
    c.address_enc = base64.b64encode(encrypt(body.address.encode(), "SYSTEM", _aad(c))).decode()
    c.address_hint = ch.mask_phone(body.address)
    c.verified_at = None
    code = f"{secrets.randbelow(1_000_000):06d}"
    c.verify_code_hash = _code_hash(c.id, code)
    c.verify_expires_at = _now() + CODE_TTL
    c.verify_attempts = 0
    db.flush()
    lang = "hi" if (user.preferred_language or "").startswith("hi") else "en"
    text = (
        f"वंशावली सत्यापन कोड: {code}। यह 10 मिनट में समाप्त हो जाएगा।"
        if lang == "hi"
        else f"Your Vanshavali verification code is {code}. It expires in 10 minutes."
    )
    try:
        ch.provider_for(body.channel).send(
            ch.OutboundMessage(
                channel=body.channel,
                to=body.address,
                subject="",
                text=text,
                kind="verify_contact",
                template_params=[code],
            )
        )
    except ch.ProviderError as exc:
        raise Unprocessable(
            "The verification code could not be sent; try again later", code=f"send_failed_{exc.code}"[:80]
        )
    audit.record(
        db,
        action="notification_contact.added",
        actor_user_id=user.id,
        target_type="notification_contact",
        target_id=c.id,
        details={"channel": body.channel.value},
    )
    return c


def verify_contact(db: Session, user: User, contact_id: uuid.UUID, code: str) -> NotificationContact:
    c = db.scalar(
        select(NotificationContact).where(
            NotificationContact.id == contact_id, NotificationContact.user_id == user.id
        )
    )
    if c is None:
        raise NotFound("Contact not found")
    if c.verified_at is not None:
        return c
    if c.verify_code_hash is None or c.verify_expires_at is None or c.verify_expires_at < _now():
        raise Unprocessable("The code has expired; request a new one", code="code_expired")
    if c.verify_attempts >= MAX_CODE_ATTEMPTS:
        raise Unprocessable("Too many attempts; request a new code", code="too_many_attempts")
    c.verify_attempts += 1
    if not hmac.compare_digest(c.verify_code_hash, _code_hash(c.id, code)):
        db.flush()
        db.commit()
        raise Unprocessable("That code is not right", code="code_invalid")
    c.verified_at, c.verify_code_hash, c.verify_expires_at = _now(), None, None
    audit.record(
        db,
        action="notification_contact.verified",
        actor_user_id=user.id,
        target_type="notification_contact",
        target_id=c.id,
        details={"channel": c.channel.value},
    )
    return c


def delete_contact(db: Session, user: User, contact_id: uuid.UUID) -> None:
    c = db.scalar(
        select(NotificationContact).where(
            NotificationContact.id == contact_id, NotificationContact.user_id == user.id
        )
    )
    if c is None:
        raise NotFound("Contact not found")
    db.delete(c)
    audit.record(
        db,
        action="notification_contact.removed",
        actor_user_id=user.id,
        target_type="notification_contact",
        target_id=c.id,
        details={"channel": c.channel.value},
    )
