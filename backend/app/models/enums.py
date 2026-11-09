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
    REVIEWER = "REVIEWER"  # reviews proposed changes (ADR-0021); writes nothing by itself


class PrivacyLevel(StrEnum):
    PRIVATE_SELF = "PRIVATE_SELF"
    PRIVATE_TREE_ADMINS = "PRIVATE_TREE_ADMINS"
    FAMILY_BRANCH = "FAMILY_BRANCH"
    TREE_MEMBERS = "TREE_MEMBERS"
    INVITED_RESEARCHER = "INVITED_RESEARCHER"
    PUBLIC_DECEASED_ONLY = "PUBLIC_DECEASED_ONLY"
    CUSTOM = "CUSTOM"


class RecordPrivacyLevel(StrEnum):
    """Audience of a shareable record (ADR-0027 §1): every person level plus two record-only ones.

    ``ONLY_ME`` and ``SELECTED_MEMBERS`` give no role-based visibility at all: only the record's
    owner and, for ``SELECTED_MEMBERS``, members holding a grant. People, events and properties
    never take them (their columns keep ``PrivacyLevel``'s CHECK constraint).
    """

    ONLY_ME = "ONLY_ME"
    SELECTED_MEMBERS = "SELECTED_MEMBERS"
    PRIVATE_SELF = "PRIVATE_SELF"  # legacy on records: owner + tree OWNER
    PRIVATE_TREE_ADMINS = "PRIVATE_TREE_ADMINS"
    FAMILY_BRANCH = "FAMILY_BRANCH"
    TREE_MEMBERS = "TREE_MEMBERS"
    INVITED_RESEARCHER = "INVITED_RESEARCHER"
    PUBLIC_DECEASED_ONLY = "PUBLIC_DECEASED_ONLY"
    CUSTOM = "CUSTOM"  # legacy on records: admins + grants


PRIVATE_RECORD_LEVELS = frozenset({RecordPrivacyLevel.ONLY_ME, RecordPrivacyLevel.SELECTED_MEMBERS})


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
    ANCESTRAL_HOUSE = "ancestral_house"
    SHRINE = "shrine"
    LAND_PARCEL = "land_parcel"
    NEIGHBOURHOOD = "neighbourhood"
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
    # ADR-0026 §2
    DEVAK = "devak"
    ANCESTRAL_OCCUPATION = "ancestral_occupation"
    FAMILY_LANGUAGE = "family_language"
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
    TRADITION = "tradition"  # ADR-0026 §7


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
    TRADITION = "tradition"  # ADR-0026 §7


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


class ClaimKind(StrEnum):
    CLAIM = "claim"  # "this is me": link the profile to my account
    REMOVAL = "removal"  # "this is me, remove me": erase the profile (ADR-0011 §removal)


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
    TRADITION = "tradition"  # ADR-0027: family traditions archive entries


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    READY = "ready"  # import: parsed & awaiting confirmation
    COMMITTED = "committed"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


# ---------------------------------------------------------------- heritage visualization milestone
class LocationPrecision(StrEnum):
    """What a pair of coordinates means (ADR-0015). Coordinates are never required."""

    EXACT = "exact"  # surveyed / GPS point
    APPROXIMATE = "approximate"  # within a few km
    LOCALITY = "locality"  # village / town centre
    DISTRICT = "district"
    STATE = "state"
    COUNTRY = "country"
    UNKNOWN = "unknown"


class LifeEventCategory(StrEnum):
    """Fine-grained life-event vocabulary layered on the structural ``EventType`` (ADR-0015)."""

    BIRTH = "birth"
    NAMING_CEREMONY = "naming_ceremony"  # namkaran
    ANNAPRASHAN = "annaprashan"
    MUNDAN = "mundan"
    UPANAYANA = "upanayana"  # thread ceremony / janeu
    INITIATION = "initiation"  # diksha, baptism, amrit sanchar, ...
    EDUCATION = "education"
    GRADUATION = "graduation"
    ENGAGEMENT = "engagement"
    MARRIAGE = "marriage"
    MIGRATION = "migration"
    EMPLOYMENT = "employment"
    RETIREMENT = "retirement"
    AWARD = "award"
    PROPERTY_ACQUISITION = "property_acquisition"
    ILLNESS = "illness"
    RECOVERY = "recovery"
    PILGRIMAGE = "pilgrimage"
    DEATH = "death"
    MEMORIAL = "memorial"  # shraddha, barsi, punyatithi
    CUSTOM = "custom"


# default structural type for each category (the category refines it, never replaces it)
CATEGORY_EVENT_TYPE: dict[LifeEventCategory, EventType] = {
    LifeEventCategory.BIRTH: EventType.BIRTH,
    LifeEventCategory.NAMING_CEREMONY: EventType.RELIGIOUS_CEREMONY,
    LifeEventCategory.ANNAPRASHAN: EventType.RELIGIOUS_CEREMONY,
    LifeEventCategory.MUNDAN: EventType.RELIGIOUS_CEREMONY,
    LifeEventCategory.UPANAYANA: EventType.RELIGIOUS_CEREMONY,
    LifeEventCategory.INITIATION: EventType.RELIGIOUS_CEREMONY,
    LifeEventCategory.EDUCATION: EventType.EDUCATION,
    LifeEventCategory.GRADUATION: EventType.EDUCATION,
    LifeEventCategory.ENGAGEMENT: EventType.OTHER,
    LifeEventCategory.MARRIAGE: EventType.MARRIAGE,
    LifeEventCategory.MIGRATION: EventType.MIGRATION,
    LifeEventCategory.EMPLOYMENT: EventType.OCCUPATION,
    LifeEventCategory.RETIREMENT: EventType.OCCUPATION,
    LifeEventCategory.AWARD: EventType.OTHER,
    LifeEventCategory.PROPERTY_ACQUISITION: EventType.OTHER,
    LifeEventCategory.ILLNESS: EventType.OTHER,
    LifeEventCategory.RECOVERY: EventType.OTHER,
    LifeEventCategory.PILGRIMAGE: EventType.OTHER,
    LifeEventCategory.DEATH: EventType.DEATH,
    LifeEventCategory.MEMORIAL: EventType.MEMORIAL,
    LifeEventCategory.CUSTOM: EventType.OTHER,
}


class EventSignificance(StrEnum):
    STANDARD = "standard"
    IMPORTANT = "important"
    MILESTONE = "milestone"


class NotificationChannel(StrEnum):
    EMAIL = "email"
    SMS = "sms"
    WHATSAPP = "whatsapp"


class ReminderKind(StrEnum):
    BIRTHDAY = "birthday"
    ANNIVERSARY = "anniversary"
    MEMORIAL = "memorial"  # death anniversary (punyatithi) or memorial day
    ONE_TIME = "one_time"
    CUSTOM = "custom"


class ReminderRecurrence(StrEnum):
    NONE = "none"
    ANNUAL = "annual"


class DeliveryStatus(StrEnum):
    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    RETRYING = "retrying"
    CANCELLED = "cancelled"


class ChartType(StrEnum):
    FAN = "fan"
    GRAPH = "graph"
    PEDIGREE = "pedigree"
    FAMILY_TREE = "family_tree"
    LIFESPAN = "lifespan"
    EVENT_TIMELINE = "event_timeline"
    MAP = "map"


# charts that have an animated (Remotion) composition
ANIMATED_CHARTS = frozenset(
    {ChartType.FAN, ChartType.PEDIGREE, ChartType.FAMILY_TREE, ChartType.LIFESPAN, ChartType.EVENT_TIMELINE}
)


class RenderStatus(StrEnum):
    QUEUED = "queued"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    CANCELLED = "cancelled"


class RenderOutput(StrEnum):
    POSTER = "poster"  # quick still preview (PNG)
    MP4 = "mp4"  # poster + full video


class RenderArtifactKind(StrEnum):
    POSTER_PNG = "poster_png"
    VIDEO_MP4 = "video_mp4"


class VocabularyTermStatus(StrEnum):
    """Master-data term lifecycle (ADR-0018). Retired terms stay resolvable for stored references."""

    DRAFT = "draft"
    REVIEWED = "reviewed"
    RETIRED = "retired"


class GeoLevel(StrEnum):
    """Local Government Directory unit levels loaded in R2 (ADR-0019 §1)."""

    STATE = "state"
    DISTRICT = "district"
    SUB_DISTRICT = "sub_district"
    VILLAGE = "village"
    URBAN_BODY = "urban_body"


class GeoSnapshotStatus(StrEnum):
    """staged: imported, under review; active: the one snapshot queries read; inactive: kept for rollback."""

    STAGED = "staged"
    ACTIVE = "active"
    INACTIVE = "inactive"


class GeoAliasKind(StrEnum):
    ALTERNATIVE = "alternative"  # published by LGD
    HISTORICAL = "historical"  # a former LGD name, recorded when a rename is imported
    CURATED = "curated"  # added by code review (app/modules/geo/aliases.json)


# ---- change proposals and family review (ADR-0021)
class ReviewPolicy(StrEnum):
    """Which direct writes need review by someone with change.review (ADR-0021 §1)."""

    OFF = "off"
    STRUCTURE = "structure"  # relationships and heritage claims
    ALL = "all"  # plus people's names, vitals and other facts


class ReviewState(StrEnum):
    """Family review of a fact. Separate from EvidenceStatus: approval is not evidence (§6)."""

    UNREVIEWED = "unreviewed"
    FAMILY_REVIEWED = "family_reviewed"
    CONTESTED = "contested"


class ProposalKind(StrEnum):
    CHANGE = "change"
    CHALLENGE = "challenge"


class ChangeProposalStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_REVIEW = "awaiting_review"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    WITHDRAWN = "withdrawn"
    STALE = "stale"


class NominationStatus(StrEnum):
    """A Family Admin nomination (ADR-0006 amendment of 9 Nov 2026, §3)."""

    OPEN = "open"
    APPROVED = "approved"
    DECLINED_BY_OWNER = "declined_by_owner"
    DECLINED_BY_NOMINEE = "declined_by_nominee"
    WITHDRAWN = "withdrawn"
    EXPIRED = "expired"
    LAPSED = "lapsed"


class ProposalOp(StrEnum):
    CREATE = "create"
    UPDATE = "update"
    DELETE = "delete"


class ReviewTarget(StrEnum):
    """Record types that carry revisions and review state (and can be proposed or challenged)."""

    PERSON = "person"
    NAME = "name"
    EVENT = "event"
    RELATIONSHIP = "relationship"
    ASSERTION = "assertion"
    # ADR-0026: a family tradition and a family's own kinship word (not person-bound)
    TRADITION = "tradition"
    KINSHIP_WORD = "kinship_word"


class NotificationKind(StrEnum):
    PROPOSAL_TO_REVIEW = "proposal_to_review"
    PROPOSAL_ACCEPTED = "proposal_accepted"
    PROPOSAL_REJECTED = "proposal_rejected"
    PROPOSAL_STALE = "proposal_stale"
    CHALLENGE_OPENED = "challenge_opened"
    CHALLENGE_UPHELD = "challenge_upheld"
    CHALLENGE_DISMISSED = "challenge_dismissed"
    PROPOSAL_COMMENT = "proposal_comment"
    # ADR-0026 §4: an operator's decision on an entry the family offered to the common lists
    OFFER_ACCEPTED = "offer_accepted"
    OFFER_DECLINED = "offer_declined"
    # ADR-0006 amendment of 9 Nov 2026: Family Admin nominations (subject_id = the nomination)
    NOMINATION_CREATED = "nomination_created"
    NOMINATION_ACCEPTED = "nomination_accepted"
    NOMINATION_DECLINED = "nomination_declined"
    NOMINATION_APPROVED = "nomination_approved"
    NOMINATION_REJECTED = "nomination_rejected"
    NOMINATION_EXPIRED = "nomination_expired"
    NOMINATION_LAPSED = "nomination_lapsed"


# ---- cultural depth (ADR-0026)
class OfferStatus(StrEnum):
    """A family's own vocabulary entry offered to the common suggestion lists (§4)."""

    NONE = "none"
    OFFERED = "offered"
    ACCEPTED = "accepted"
    DECLINED = "declined"


class TraditionKind(StrEnum):
    RITUAL_GUIDE = "ritual_guide"
    CUSTOM = "custom"
    SONG = "song"
    RECIPE = "recipe"
    STORY = "story"
    OTHER = "other"


class TraditionLinkTarget(StrEnum):
    PERSON = "person"
    EVENT = "event"
    PLACE = "place"
