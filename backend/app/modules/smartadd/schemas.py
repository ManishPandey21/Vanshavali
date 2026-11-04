from __future__ import annotations

import uuid
from typing import Literal

from pydantic import Field

from app.api.schemas import ApiModel
from app.models.enums import SexAtBirth
from app.modules.genealogy.schemas import PersonCreate, PersonSummary, RelationshipOut

Choice = Literal["new"] | uuid.UUID
LinkMode = Literal["parent", "child", "spouse", "shared_parents", "explicit_sibling"]


class SmartAddHopOut(ApiModel):
    relation: Literal["parent", "child", "sibling", "spouse"]
    sex: SexAtBirth | None = None
    age: Literal["elder", "younger"] | None = None


class SmartAddTermOut(ApiModel):
    code: str
    group: str
    hops: list[SmartAddHopOut]
    # whether the user may say "older / younger than …" for the new person (term does not fix it)
    asks_relative_age: bool = False


class SmartAddPlanIn(ApiModel):
    term: str = Field(max_length=40)
    # one per intermediate step resolved so far: an existing person, or "new" (provisional)
    choices: list[Choice] = Field(default=[], max_length=4)


class SmartAddStepOut(ApiModel):
    index: int
    relation: Literal["parent", "child", "sibling", "spouse"]
    sex: SexAtBirth | None = None
    age: Literal["elder", "younger"] | None = None
    # the person this step starts from; None when it is a new provisional person
    from_person: PersonSummary | None = None
    candidates: list[PersonSummary] = []
    # recorded relatives at this step the viewer cannot see (never identified)
    hidden_candidates: int = 0
    allow_new: bool = True
    chosen: PersonSummary | Literal["new"] | None = None


class SmartAddTargetOut(ApiModel):
    relation: Literal["parent", "child", "sibling", "spouse"]
    sex: SexAtBirth | None = None
    age: Literal["elder", "younger"] | None = None
    from_person: PersonSummary | None = None
    link: LinkMode
    # shared_parents: the parents the new sibling will be linked to
    shared_parents: list[PersonSummary] = []
    # child: who else may be recorded as the new child's parent
    other_parent_options: list[PersonSummary] = []
    blocked: str | None = None  # why the new person cannot be added here, if so


class SmartAddPreviewItem(ApiModel):
    kind: Literal["existing", "provisional", "new"]
    person: PersonSummary | None = None
    relation: Literal["parent", "child", "sibling", "spouse"] | None = None  # to the previous item
    link: LinkMode | None = None
    age: Literal["elder", "younger"] | None = None


class SmartAddPlanOut(ApiModel):
    term: str
    anchor: PersonSummary
    steps: list[SmartAddStepOut]
    complete: bool  # every intermediate step has a choice
    target: SmartAddTargetOut | None = None  # once complete
    preview: list[SmartAddPreviewItem] = []  # anchor → … → new person, once complete


class SmartAddCommitIn(ApiModel):
    term: str = Field(max_length=40)
    choices: list[Choice] = Field(default=[], max_length=4)
    new_person: PersonCreate
    other_parent_id: uuid.UUID | None = None
    # one per intermediate step, used only where that step is "new": sex at birth for the provisional
    # person, as confirmed (or cleared) by the user; the server never derives it from the term
    provisional_sex_at_birth: list[SexAtBirth | None] = Field(default=[], max_length=4)
    # only for terms that do not fix it (brother, sister): the new person vs the previous person
    relative_age: Literal["elder", "younger"] | None = None


class SmartAddCommitOut(ApiModel):
    operation_id: uuid.UUID
    person: PersonSummary
    created_people: list[PersonSummary]
    relationships: list[RelationshipOut]
    relative_age_order_ids: list[uuid.UUID] = []
    undo_expires_in_seconds: int
