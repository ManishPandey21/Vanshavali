"""Per-request tree authorization context (ADR-0006)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.authz.permissions import ADMIN_ROLES, BRANCH_SCOPED_WRITES, Permission, permissions_for
from app.core.db import bind_tree
from app.core.errors import Forbidden, NotFound
from app.models import AccessGrant, BranchMembership, Tree, TreeMembership, User
from app.models.enums import GrantPermission, GrantResource, PublicMode, Role


@dataclass
class RequestInfo:
    ip: str | None = None
    user_agent: str | None = None


@dataclass
class TreeContext:
    db: Session
    tree: Tree
    user: User | None
    membership: TreeMembership | None
    roles: frozenset[Role]
    permissions: frozenset[Permission]
    public: bool = False
    request: RequestInfo = field(default_factory=RequestInfo)
    _branch_people: set[uuid.UUID] | None = None
    _viewer_branch_ids: set[uuid.UUID] | None = None
    _grants: dict[tuple[str, uuid.UUID], set[str]] | None = None

    # ---- identity ----
    @property
    def tree_id(self) -> uuid.UUID:
        return self.tree.id

    @property
    def user_id(self) -> uuid.UUID | None:
        return self.user.id if self.user else None

    @property
    def is_member(self) -> bool:
        return self.membership is not None

    @property
    def is_owner(self) -> bool:
        return Role.OWNER in self.roles

    @property
    def is_admin(self) -> bool:
        return bool(self.roles & ADMIN_ROLES)

    @property
    def is_researcher_only(self) -> bool:
        return self.roles == frozenset({Role.RESEARCHER})

    @property
    def branch_scope(self) -> uuid.UUID | None:
        if self.is_admin or self.membership is None:
            return None
        return self.membership.branch_id

    # ---- permission checks ----
    def has(self, perm: Permission) -> bool:
        return perm in self.permissions

    def require(self, perm: Permission, *, person_id: uuid.UUID | None = None) -> None:
        if not self.has(perm):
            raise Forbidden()
        if person_id is not None and perm in BRANCH_SCOPED_WRITES and self.branch_scope is not None:
            if person_id not in self.branch_people():
                raise Forbidden("This person is outside the family branch you manage")

    def branch_people(self) -> set[uuid.UUID]:
        if self._branch_people is None:
            scope = self.branch_scope
            if scope is None:
                self._branch_people = set()
            else:
                self._branch_people = set(
                    self.db.scalars(
                        select(BranchMembership.person_id).where(
                            BranchMembership.tree_id == self.tree_id, BranchMembership.branch_id == scope
                        )
                    )
                )
        return self._branch_people

    def viewer_branch_ids(self) -> set[uuid.UUID]:
        """Branches the viewer belongs to (via membership scope or their linked person)."""
        if self._viewer_branch_ids is None:
            ids: set[uuid.UUID] = set()
            if self.membership is not None:
                if self.membership.branch_id:
                    ids.add(self.membership.branch_id)
                if self.membership.linked_person_id:
                    ids |= set(
                        self.db.scalars(
                            select(BranchMembership.branch_id).where(
                                BranchMembership.tree_id == self.tree_id,
                                BranchMembership.person_id == self.membership.linked_person_id,
                            )
                        )
                    )
            self._viewer_branch_ids = ids
        return self._viewer_branch_ids

    def has_grant(
        self, resource_type: GrantResource, resource_id: uuid.UUID, permission: GrantPermission
    ) -> bool:
        if self.user is None:
            return False
        if self._grants is None:
            import datetime as dt

            now = dt.datetime.now(dt.UTC)
            rows = self.db.execute(
                select(
                    AccessGrant.resource_type,
                    AccessGrant.resource_id,
                    AccessGrant.permission,
                    AccessGrant.expires_at,
                ).where(AccessGrant.tree_id == self.tree_id, AccessGrant.user_id == self.user.id)
            ).all()
            grants: dict[tuple[str, uuid.UUID], set[str]] = {}
            for rt, rid, perm, exp in rows:
                if exp is not None and exp < now:
                    continue
                grants.setdefault((str(rt), rid), set()).add(str(perm))
            self._grants = grants
        perms = self._grants.get((str(resource_type), resource_id), set())
        if permission == GrantPermission.VIEW:
            return bool(perms)  # download implies view
        return str(permission) in perms


def load_tree_context(
    db: Session, tree_id: uuid.UUID, user: User | None, request: RequestInfo | None = None
) -> TreeContext:
    """Resolve membership. Non-members (and missing trees) get 404 — existence is not revealed."""
    tree = db.get(Tree, tree_id)
    if tree is None or tree.deleted_at is not None or user is None:
        raise NotFound("Tree not found")
    membership = db.scalar(
        select(TreeMembership).where(TreeMembership.tree_id == tree_id, TreeMembership.user_id == user.id)
    )
    if membership is None:
        raise NotFound("Tree not found")
    bind_tree(db, tree.id)  # row-level security: this session now only sees this tree's rows
    roles = frozenset(Role(r) for r in membership.roles)
    return TreeContext(
        db=db,
        tree=tree,
        user=user,
        membership=membership,
        roles=roles,
        permissions=permissions_for(roles),
        request=request or RequestInfo(),
    )


def load_public_context(db: Session, slug: str, request: RequestInfo | None = None) -> TreeContext:
    tree = db.scalar(select(Tree).where(Tree.slug == slug, Tree.deleted_at.is_(None)))
    if tree is None or tree.public_mode != PublicMode.DECEASED_ONLY:
        raise NotFound("Tree not found")
    bind_tree(db, tree.id)
    return TreeContext(
        db=db,
        tree=tree,
        user=None,
        membership=None,
        roles=frozenset(),
        permissions=frozenset(),
        public=True,
        request=request or RequestInfo(),
    )
