"""All ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models import rls as _rls
from app.models.astrology import AstrologyProfile
from app.models.audit import AuditEvent
from app.models.base import Base
from app.models.documents import (
    Document,
    DocumentDerivative,
    DocumentLink,
    DocumentMetadataVersion,
    EventMedia,
    ExtractionProposal,
)
from app.models.evidence import Citation, Source
from app.models.family import BranchMembership, FamilyBranch, Household, HouseholdMembership
from app.models.genealogy import Event, EventParticipant, MergeRecord, NameRecord, Person, Place, Relationship
from app.models.heritage import Assertion
from app.models.identity import AuthToken, AuthTokenPurpose, ExternalIdentity, User, UserSession
from app.models.importexport import ExportJob, GedcomExtension, ImportJob
from app.models.notifications import (
    EventReminder,
    NotificationContact,
    NotificationDelivery,
    NotificationPreference,
)
from app.models.privacy import ConsentRecord, FamilyDataAttestation, ProfileClaim, ProfileClaimInvite
from app.models.property import LandParcel, Property, PropertyEvent, PropertyEventParcel, PropertyInterest
from app.models.tree import AccessGrant, Tree, TreeInvitation, TreeMembership
from app.models.visualization import ChartPreset, RenderArtifact, RenderJob

_rls.attach_to_metadata(Base.metadata.tables)  # type: ignore[arg-type]

__all__ = [
    "AccessGrant",
    "Assertion",
    "AstrologyProfile",
    "AuditEvent",
    "AuthToken",
    "AuthTokenPurpose",
    "Base",
    "BranchMembership",
    "ChartPreset",
    "Citation",
    "ConsentRecord",
    "Document",
    "DocumentDerivative",
    "DocumentLink",
    "DocumentMetadataVersion",
    "Event",
    "EventMedia",
    "EventParticipant",
    "EventReminder",
    "ExportJob",
    "ExternalIdentity",
    "ExtractionProposal",
    "FamilyBranch",
    "FamilyDataAttestation",
    "GedcomExtension",
    "Household",
    "HouseholdMembership",
    "ImportJob",
    "LandParcel",
    "MergeRecord",
    "NameRecord",
    "NotificationContact",
    "NotificationDelivery",
    "NotificationPreference",
    "Person",
    "Place",
    "ProfileClaim",
    "ProfileClaimInvite",
    "Property",
    "PropertyEvent",
    "PropertyEventParcel",
    "PropertyInterest",
    "Relationship",
    "RenderArtifact",
    "RenderJob",
    "Source",
    "Tree",
    "TreeInvitation",
    "TreeMembership",
    "User",
    "UserSession",
]
