"""All ORM models. Importing this package registers every table on ``Base.metadata``."""

from app.models.astrology import AstrologyProfile
from app.models.audit import AuditEvent
from app.models.base import Base
from app.models.documents import (
    Document,
    DocumentDerivative,
    DocumentLink,
    DocumentMetadataVersion,
    ExtractionProposal,
)
from app.models.evidence import Citation, Source
from app.models.family import BranchMembership, FamilyBranch, Household, HouseholdMembership
from app.models.genealogy import Event, EventParticipant, MergeRecord, NameRecord, Person, Place, Relationship
from app.models.heritage import Assertion
from app.models.identity import User, UserSession
from app.models.importexport import ExportJob, GedcomExtension, ImportJob
from app.models.privacy import ConsentRecord, ProfileClaim
from app.models.property import LandParcel, Property, PropertyEvent, PropertyEventParcel, PropertyInterest
from app.models.tree import AccessGrant, Tree, TreeInvitation, TreeMembership

__all__ = [
    "AccessGrant",
    "Assertion",
    "AstrologyProfile",
    "AuditEvent",
    "Base",
    "BranchMembership",
    "Citation",
    "ConsentRecord",
    "Document",
    "DocumentDerivative",
    "DocumentLink",
    "DocumentMetadataVersion",
    "Event",
    "EventParticipant",
    "ExportJob",
    "ExtractionProposal",
    "FamilyBranch",
    "GedcomExtension",
    "Household",
    "HouseholdMembership",
    "ImportJob",
    "LandParcel",
    "MergeRecord",
    "NameRecord",
    "Person",
    "Place",
    "ProfileClaim",
    "Property",
    "PropertyEvent",
    "PropertyEventParcel",
    "PropertyInterest",
    "Relationship",
    "Source",
    "Tree",
    "TreeInvitation",
    "TreeMembership",
    "User",
    "UserSession",
]
