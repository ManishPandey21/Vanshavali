"""Domain vocabularies. Stored as strings with CHECK constraints (see models.base.enum_column)."""

from __future__ import annotations

from enum import StrEnum


class Role(StrEnum):
    OWNER = "OWNER"
    FAMILY_ADMIN = "FAMILY_ADMIN"
    BRANCH_ADMIN = "BRANCH_ADMIN"
    CONTRIBUTOR = "CONTRIBUTOR"
    RESEARCHER = "RESEARCHER"
    VIEWER = "VIEWER"
    DOCUMENT_CUSTODIAN = "DOCUMENT_CUSTODIAN"
    PROPERTY_CUSTODIAN = "PROPERTY_CUSTODIAN"


class PrivacyLevel(StrEnum):
    PRIVATE_SELF = "PRIVATE_SELF"
    PRIVATE_TREE_ADMINS = "PRIVATE_TREE_ADMINS"
    FAMILY_BRANCH = "FAMILY_BRANCH"
    TREE_MEMBERS = "TREE_MEMBERS"
    INVITED_RESEARCHER = "INVITED_RESEARCHER"
    PUBLIC_DECEASED_ONLY = "PUBLIC_DECEASED_ONLY"
    CUSTOM = "CUSTOM"


class PublicMode(StrEnum):
    OFF = "OFF"
    DECEASED_ONLY = "DECEASED_ONLY"


class ProfileStatus(StrEnum):
    LIVING = "living"
    DECEASED = "deceased"
    UNKNOWN = "unknown"


class SexAtBirth(StrEnum):
    MALE = "male"
    FEMALE = "female"
    INTERSEX = "intersex"
    UNKNOWN = "unknown"


class EvidenceStatus(StrEnum):
    USER_ASSERTION = "USER_ASSERTION"
    FAMILY_RECOLLECTION = "FAMILY_RECOLLECTION"
    SOURCED = "SOURCED"
    CORROBORATED = "CORROBORATED"
    DISPUTED = "DISPUTED"
    SUPERSEDED = "SUPERSEDED"
    DISPROVEN = "DISPROVEN"


class Confidence(StrEnum):
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"
    UNKNOWN = "unknown"


class ProvenanceOrigin(StrEnum):
    MANUAL = "manual"
    OCR = "ocr"
    GEDCOM = "gedcom"
    API = "api"
    CALCULATION = "calculation"
    IMPORTED_DOCUMENT = "imported_document"


class NameType(StrEnum):
    BIRTH = "birth"
    MARRIED = "married"
    ALIAS = "alias"
    RELIGIOUS = "religious"
    PROFESSIONAL = "professional"
    NICKNAME = "nickname"
    TRANSLITERATION = "transliteration"
    HISTORICAL = "historical"


class RelationshipType(StrEnum):
    BIOLOGICAL_PARENT = "biological_parent"
    ADOPTIVE_PARENT = "adoptive_parent"
    STEP_PARENT = "step_parent"
    FOSTER_PARENT = "foster_parent"
    GUARDIAN = "guardian"
    SPOUSE = "spouse"
    PARTNER = "partner"
    DIVORCED_SPOUSE = "divorced_spouse"
    SEPARATED_SPOUSE = "separated_spouse"
    SIBLING = "sibling"
    OTHER = "other"


PARENT_TYPES = frozenset(
    {
        RelationshipType.BIOLOGICAL_PARENT,
        RelationshipType.ADOPTIVE_PARENT,
        RelationshipType.STEP_PARENT,
        RelationshipType.FOSTER_PARENT,
        RelationshipType.GUARDIAN,
    }
)
UNION_TYPES = frozenset(
    {
        RelationshipType.SPOUSE,
        RelationshipType.PARTNER,
        RelationshipType.DIVORCED_SPOUSE,
        RelationshipType.SEPARATED_SPOUSE,
    }
)
SYMMETRIC_TYPES = UNION_TYPES | {RelationshipType.SIBLING, RelationshipType.OTHER}


class Lineage(StrEnum):
    BIOLOGICAL = "biological"
    LEGAL = "legal"
    RITUAL = "ritual"
    SOCIAL = "social"


DEFAULT_LINEAGE = {
    RelationshipType.BIOLOGICAL_PARENT: Lineage.BIOLOGICAL,
    RelationshipType.ADOPTIVE_PARENT: Lineage.LEGAL,
    RelationshipType.STEP_PARENT: Lineage.SOCIAL,
    RelationshipType.FOSTER_PARENT: Lineage.SOCIAL,
    RelationshipType.GUARDIAN: Lineage.LEGAL,
}


class EventType(StrEnum):
    BIRTH = "birth"
    DEATH = "death"
    MARRIAGE = "marriage"
    DIVORCE = "divorce"
    ADOPTION = "adoption"
    RESIDENCE = "residence"
    MIGRATION = "migration"
    EDUCATION = "education"
    OCCUPATION = "occupation"
    CREMATION = "cremation"
    BURIAL = "burial"
    MEMORIAL = "memorial"
    RELIGIOUS_CEREMONY = "religious_ceremony"
    OTHER = "other"


class ParticipantRole(StrEnum):
    PRINCIPAL = "principal"
    SPOUSE = "spouse"
    PARENT = "parent"
    WITNESS = "witness"
    OFFICIANT = "officiant"
    INFORMANT = "informant"
    OTHER = "other"


class PlaceType(StrEnum):
    VILLAGE = "village"
    TOWN = "town"
    CITY = "city"
    TEHSIL = "tehsil"
    DISTRICT = "district"
    STATE = "state"
    COUNTRY = "country"
    TEMPLE = "temple"
    PROPERTY = "property"
    OTHER = "other"


class AssertionSubject(StrEnum):
    PERSON = "person"
    BRANCH = "branch"


class HeritageAttribute(StrEnum):
    GOTRA = "gotra"
    PRAVARA = "pravara"
    KULA_OR_VAMSHA = "kula_or_vamsha"
    COMMUNITY = "community"
    JATI_OR_SUBGROUP = "jati_or_subgroup"
    RELIGION = "religion"
    ANCESTRAL_VILLAGE = "ancestral_village"
    ANCESTRAL_HOUSE_NAME = "ancestral_house_name"
    THARAVAD_OR_EQUIVALENT = "tharavad_or_equivalent"
    KULADEVATA = "kuladevata"
    KULADEVI = "kuladevi"
    TEMPLE = "temple"
    FAMILY_TRADITIONS = "family_traditions"
    LANGUAGE_TRADITIONS = "language_traditions"
    RECORDED_PARENT_NAME = "recorded_parent_name"
    OTHER = "other"


class ValueStatus(StrEnum):
    KNOWN = "known"
    UNKNOWN = "unknown"
    NOT_APPLICABLE = "not_applicable"
    WITHHELD = "withheld"


class DescentRule(StrEnum):
    PATRILINEAL = "patrilineal"
    MATRILINEAL = "matrilineal"
    BILATERAL = "bilateral"
    CUSTOM = "custom"


class HouseholdRole(StrEnum):
    HEAD = "head"
    KARTA = "karta"
    REFERENCE_PERSON = "reference_person"
    MEMBER = "member"
    DEPENDENT = "dependent"
    OTHER = "other"


class SourceType(StrEnum):
    CIVIL_RECORD = "civil_record"
    CERTIFICATE = "certificate"
    KUNDLI = "kundli"
    LAND_RECORD = "land_record"
    DEED = "deed"
    COURT_RECORD = "court_record"
    CENSUS = "census"
    TRADITIONAL_REGISTER = "traditional_register"  # Bahi / Panda / temple register (PRS §20)
    FAMILY_BOOK = "family_book"
    ORAL_HISTORY = "oral_history"
    LETTER = "letter"
    PHOTOGRAPH = "photograph"
    PUBLICATION = "publication"
    WEBSITE = "website"
    GEDCOM_IMPORT = "gedcom_import"
    OTHER = "other"


class CitationTarget(StrEnum):
    PERSON = "person"
    NAME_RECORD = "name_record"
    EVENT = "event"
    RELATIONSHIP = "relationship"
    ASSERTION = "assertion"
    ASTROLOGY_PROFILE = "astrology_profile"
    PROPERTY = "property"
    LAND_PARCEL = "land_parcel"
    PROPERTY_INTEREST = "property_interest"
    PROPERTY_EVENT = "property_event"
    HOUSEHOLD = "household"


class DocumentCategory(StrEnum):
    PHOTO = "photo"
    BIRTH_CERTIFICATE = "birth_certificate"
    DEATH_CERTIFICATE = "death_certificate"
    MARRIAGE_RECORD = "marriage_record"
    KUNDLI = "kundli"
    LETTER = "letter"
    DIARY = "diary"
    FAMILY_REGISTER = "family_register"
    TRADITIONAL_REGISTER = "traditional_register"
    SCHOOL_RECORD = "school_record"
    SERVICE_RECORD = "service_record"
    OBITUARY = "obituary"
    IDENTITY_DOCUMENT = "identity_document"
    AUDIO = "audio"
    VIDEO = "video"
    # property / land (PRS §17.5)
    RECORD_OF_RIGHTS = "record_of_rights"
    KHATAUNI = "khatauni"
    JAMABANDI = "jamabandi"
    KHASRA = "khasra"
    RTC = "rtc"
    PATTA = "patta"
    MUTATION_RECORD = "mutation_record"
    CADASTRAL_MAP = "cadastral_map"
    TITLE_DEED = "title_deed"
    SALE_DEED = "sale_deed"
    GIFT_DEED = "gift_deed"
    PARTITION_DEED = "partition_deed"
    FAMILY_SETTLEMENT = "family_settlement"
    RELINQUISHMENT_DEED = "relinquishment_deed"
    WILL = "will"
    PROBATE = "probate"
    SUCCESSION_CERTIFICATE = "succession_certificate"
    REVENUE_ORDER = "revenue_order"
    COURT_ORDER = "court_order"
    TAX_RECEIPT = "tax_receipt"
    MUNICIPAL_RECORD = "municipal_record"
    ENCUMBRANCE = "encumbrance"
    POSSESSION_RECORD = "possession_record"
    HISTORICAL_FAMILY_PAPER = "historical_family_paper"
    GEDCOM = "gedcom"
    OTHER = "other"


VAULT_CATEGORIES = frozenset(
    {
        DocumentCategory.BIRTH_CERTIFICATE,
        DocumentCategory.DEATH_CERTIFICATE,
        DocumentCategory.MARRIAGE_RECORD,
        DocumentCategory.KUNDLI,
        DocumentCategory.IDENTITY_DOCUMENT,
        DocumentCategory.RECORD_OF_RIGHTS,
        DocumentCategory.KHATAUNI,
        DocumentCategory.JAMABANDI,
        DocumentCategory.KHASRA,
        DocumentCategory.RTC,
        DocumentCategory.PATTA,
        DocumentCategory.MUTATION_RECORD,
        DocumentCategory.CADASTRAL_MAP,
        DocumentCategory.TITLE_DEED,
        DocumentCategory.SALE_DEED,
        DocumentCategory.GIFT_DEED,
        DocumentCategory.PARTITION_DEED,
        DocumentCategory.FAMILY_SETTLEMENT,
        DocumentCategory.RELINQUISHMENT_DEED,
        DocumentCategory.WILL,
        DocumentCategory.PROBATE,
        DocumentCategory.SUCCESSION_CERTIFICATE,
        DocumentCategory.REVENUE_ORDER,
        DocumentCategory.COURT_ORDER,
        DocumentCategory.ENCUMBRANCE,
        DocumentCategory.POSSESSION_RECORD,
        DocumentCategory.TAX_RECEIPT,
        DocumentCategory.MUNICIPAL_RECORD,
    }
)

PROPERTY_CATEGORIES = frozenset(
    {
        DocumentCategory.RECORD_OF_RIGHTS,
        DocumentCategory.KHATAUNI,
        DocumentCategory.JAMABANDI,
        DocumentCategory.KHASRA,
        DocumentCategory.RTC,
        DocumentCategory.PATTA,
        DocumentCategory.MUTATION_RECORD,
        DocumentCategory.CADASTRAL_MAP,
        DocumentCategory.TITLE_DEED,
        DocumentCategory.SALE_DEED,
        DocumentCategory.GIFT_DEED,
        DocumentCategory.PARTITION_DEED,
        DocumentCategory.FAMILY_SETTLEMENT,
        DocumentCategory.RELINQUISHMENT_DEED,
        DocumentCategory.WILL,
        DocumentCategory.PROBATE,
        DocumentCategory.SUCCESSION_CERTIFICATE,
        DocumentCategory.REVENUE_ORDER,
        DocumentCategory.COURT_ORDER,
        DocumentCategory.TAX_RECEIPT,
        DocumentCategory.MUNICIPAL_RECORD,
        DocumentCategory.ENCUMBRANCE,
        DocumentCategory.POSSESSION_RECORD,
    }
)


class StorageClass(StrEnum):
    STANDARD = "STANDARD"
    VAULT = "VAULT"


class ScanStatus(StrEnum):
    PENDING = "pending"
    CLEAN = "clean"
    INFECTED = "infected"
    ERROR = "error"


class ProcessingStatus(StrEnum):
    NOT_REQUESTED = "not_requested"
    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    SKIPPED = "skipped"


class DocumentLinkTarget(StrEnum):
    PERSON = "person"
    EVENT = "event"
    RELATIONSHIP = "relationship"
    PLACE = "place"
    PROPERTY = "property"
    LAND_PARCEL = "land_parcel"
    PROPERTY_EVENT = "property_event"
    SOURCE = "source"
    HOUSEHOLD = "household"


class DerivativeKind(StrEnum):
    PREVIEW = "preview"
    THUMBNAIL = "thumbnail"
    OCR_TEXT = "ocr_text"


class ProposalStatus(StrEnum):
    PENDING = "pending"
    ACCEPTED = "accepted"
    EDITED = "edited"
    REJECTED = "rejected"


class AstrologyProvenance(StrEnum):
    ENTERED = "entered"
    UPLOADED_CHART = "uploaded_chart"
    CALCULATED = "calculated"
    IMPORTED = "imported"


class PropertyType(StrEnum):
    AGRICULTURAL_LAND = "agricultural_land"
    RESIDENTIAL_LAND = "residential_land"
    HOUSE = "house"
    COMMERCIAL = "commercial"
    ANCESTRAL_HOME = "ancestral_home"
    ESTATE = "estate"
    OTHER = "other"


class PropertyClassification(StrEnum):
    ANCESTRAL = "ancestral"
    SELF_ACQUIRED = "self_acquired"
    JOINT_FAMILY = "joint_family"
    UNKNOWN = "unknown"


class HolderType(StrEnum):
    PERSON = "person"
    FAMILY_BRANCH = "family_branch"
    TRUST = "trust"
    ENTITY = "entity"
    UNKNOWN = "unknown"


class InterestType(StrEnum):
    OWNER = "owner"
    CO_OWNER = "co_owner"
    TENANT = "tenant"
    CULTIVATOR = "cultivator"
    LIFE_INTEREST = "life_interest"
    CLAIMANT = "claimant"
    BENEFICIARY = "beneficiary"
    MORTGAGEE = "mortgagee"
    OTHER = "other"


OWNERSHIP_INTERESTS = frozenset({InterestType.OWNER, InterestType.CO_OWNER})


class InterestStatus(StrEnum):
    ASSERTED = "asserted"
    DOCUMENTED = "documented"
    DISPUTED = "disputed"
    RELINQUISHED = "relinquished"
    TRANSFERRED = "transferred"
    UNKNOWN = "unknown"


class PropertyEventType(StrEnum):
    PURCHASE = "purchase"
    INHERITANCE = "inheritance"
    SUCCESSION = "succession"
    PARTITION = "partition"
    FAMILY_SETTLEMENT = "family_settlement"
    RELINQUISHMENT = "relinquishment"
    GIFT = "gift"
    SALE = "sale"
    MUTATION = "mutation"
    ACQUISITION = "acquisition"
    COURT_ORDER = "court_order"
    MORTGAGE = "mortgage"
    LEASE = "lease"
    CONSOLIDATION = "consolidation"
    SUBDIVISION = "subdivision"
    MERGER = "merger"
    BOUNDARY_CHANGE = "boundary_change"
    DISPUTE = "dispute"
    OTHER = "other"


class ConsentBasis(StrEnum):
    SELF = "self"
    PARENT_GUARDIAN = "parent_guardian"
    LEGAL_REPRESENTATIVE = "legal_representative"
    TREE_ADMIN_ATTESTATION = "tree_admin_attestation"


class ClaimStatus(StrEnum):
    REQUESTED = "requested"
    APPROVED = "approved"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"


class GrantPermission(StrEnum):
    VIEW = "view"
    DOWNLOAD = "download"


class GrantResource(StrEnum):
    PERSON = "person"
    DOCUMENT = "document"
    PROPERTY = "property"


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"  # import: parsed & awaiting confirmation
    COMMITTED = "committed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
