"""All ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models import rls as _rls
from app.models.astrology import AstrologyProfile
from app.models.audit import AuditEvent
from app.models.base import Base
from app.models.calendar import CalendarFeed, PanchangDay
from app.models.collections import PhotoCollection, PhotoCollectionItem
from app.models.culture import KinshipOverride, TraditionEntry, TraditionLink
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
from app.models.family_addresses import (
    FamilyAddress,
    FamilyAddressReleaseConsent,
    FamilyAddressVersion,
    FamilyAddressVersionAncestor,
    FamilyAddressVersionSource,
)
from app.models.genealogy import (
    Event,
    EventParticipant,
    MergeRecord,
    NameRecord,
    Person,
    Place,
    Relationship,
    RelativeAgeOrder,
)
from app.models.geo import GeoSnapshot, GeoUnit, GeoUnitAlias, PincodeOffice
from app.models.heritage import Assertion
from app.models.identity import (
    AuthToken,
    AuthTokenPurpose,
    ExternalIdentity,
    PlatformCapability,
    PlatformCapabilityGrant,
    User,
    UserSession,
)
from app.models.importexport import ExportJob, GedcomExtension, ImportJob
from app.models.masterdata import TreeVocabularyTerm, Vocabulary, VocabularyTerm
from app.models.notifications import (
    EventReminder,
    NotificationContact,
    NotificationDelivery,
    NotificationPreference,
)
from app.models.privacy import ConsentRecord, FamilyDataAttestation, ProfileClaim, ProfileClaimInvite
from app.models.profile_details import PersonAddress, PersonContactMethod, PersonDetailRevision
from app.models.property import LandParcel, Property, PropertyEvent, PropertyEventParcel, PropertyInterest
from app.models.review import (
    ChangeProposal,
    ChangeProposalItem,
    ProposalCitation,
    ProposalComment,
    RecordRevision,
    UserNotification,
)
from app.models.takedown import RecordReport, RecordSuspension
from app.models.tree import AccessGrant, AdminNomination, Tree, TreeInvitation, TreeMembership
from app.models.visualization import ChartPreset, RenderArtifact, RenderJob

_rls.attach_to_metadata(Base.metadata.tables)  # type: ignore[arg-type]

__all__ = [
    "AccessGrant",
    "AdminNomination",
    "Assertion",
    "AstrologyProfile",
    "AuditEvent",
    "AuthToken",
    "AuthTokenPurpose",
    "Base",
    "BranchMembership",
    "CalendarFeed",
    "ChangeProposal",
    "ChangeProposalItem",
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
    "FamilyAddress",
    "FamilyAddressReleaseConsent",
    "FamilyAddressVersion",
    "FamilyAddressVersionAncestor",
    "FamilyAddressVersionSource",
    "FamilyBranch",
    "FamilyDataAttestation",
    "GedcomExtension",
    "GeoSnapshot",
    "GeoUnit",
    "GeoUnitAlias",
    "Household",
    "HouseholdMembership",
    "ImportJob",
    "KinshipOverride",
    "LandParcel",
    "MergeRecord",
    "NameRecord",
    "NotificationContact",
    "NotificationDelivery",
    "NotificationPreference",
    "PanchangDay",
    "Person",
    "PersonAddress",
    "PersonContactMethod",
    "PersonDetailRevision",
    "PhotoCollection",
    "PhotoCollectionItem",
    "PincodeOffice",
    "Place",
    "PlatformCapability",
    "PlatformCapabilityGrant",
    "ProfileClaim",
    "ProfileClaimInvite",
    "Property",
    "PropertyEvent",
    "PropertyEventParcel",
    "PropertyInterest",
    "ProposalCitation",
    "ProposalComment",
    "RecordReport",
    "RecordRevision",
    "RecordSuspension",
    "Relationship",
    "RelativeAgeOrder",
    "RenderArtifact",
    "RenderJob",
    "Source",
    "TraditionEntry",
    "TraditionLink",
    "Tree",
    "TreeInvitation",
    "TreeMembership",
    "TreeVocabularyTerm",
    "User",
    "UserNotification",
    "UserSession",
    "Vocabulary",
    "VocabularyTerm",
]

# revisions and history for every write path (ADR-0021 §3): one flush hook on every session
from app.modules.review import revisions as _revisions  # noqa: E402

_revisions.install()
