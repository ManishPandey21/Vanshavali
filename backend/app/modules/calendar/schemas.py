from __future__ import annotations

import datetime as dt
import uuid
from typing import Literal

from pydantic import Field

from app.api.schemas import ApiModel
from app.core.lunar import LunarDate
from app.models.enums import ReminderKind


class ConventionOut(ApiModel):
    key: str
    label: str
    golden_verified: bool
    offered: bool  # computed lunar dates are available for it now


class CityOut(ApiModel):
    key: str
    label: str
    timezone: str


class CalendarSettingsOut(ApiModel):
    convention: str | None
    observance_city: str | None
    conventions: list[ConventionOut]
    cities: list[CityOut]
    # VSH_LUNAR_CALENDAR_ENABLED: off until the engine licence review is signed off (ADR-0022 §8)
    lunar_enabled: bool


class CalendarSettingsIn(ApiModel):
    convention: str | None = Field(default=None, max_length=40)
    observance_city: str | None = Field(default=None, max_length=60)


class CalendarEntryOut(ApiModel):
    day: dt.date
    kind: ReminderKind
    event_id: uuid.UUID
    person_id: uuid.UUID | None = None
    label: str
    anniversary: int | None = None
    basis: Literal["solar", "lunar"]
    # lunar entries say how the day was found
    lunar_label: str | None = None
    convention: str | None = None
    rule: Literal["sunrise", "aparahna"] | None = None
    city: str | None = None


class CalendarOut(ApiModel):
    start: dt.date
    end: dt.date
    entries: list[CalendarEntryOut]
    # why tithi dates are not on the calendar, when they are not
    lunar_unavailable: Literal["disabled", "convention_not_offered", "no_city"] | None = None


class ConvertIn(ApiModel):
    lunar: LunarDate
    convention: str | None = Field(default=None, max_length=40)
    observance_city: str | None = Field(default=None, max_length=60)


class ConvertOut(ApiModel):
    """A suggestion only: nothing is stored unless the user accepts it (ADR-0022 §2)."""

    suggestion: dt.date | None
    convention: str
    rule: Literal["sunrise", "aparahna"]
    city: str
    engine_version: str


class FeedIn(ApiModel):
    include_names: bool = False  # names go to a third-party calendar app only by explicit choice


class FeedOut(ApiModel):
    active: bool
    include_names: bool = False
    created_at: dt.datetime | None = None
    last_used_at: dt.datetime | None = None
    # shown once, when the feed is created or replaced; only its hash is stored
    url: str | None = None
