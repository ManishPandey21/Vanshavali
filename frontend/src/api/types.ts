import type { components } from "./schema";

type S = components["schemas"];

export type UserOut = S["UserOut"];
export type TreeOut = S["TreeOut"];
export type TreeUpdate = S["TreeUpdate"];
export type MemberOut = S["MemberOut"];
export type MemberUpdate = S["MemberUpdate"];
export type InvitationOut = S["InvitationOut"];
export type InvitationCreate = S["InvitationCreate"];
export type InvitationPreview = S["InvitationPreview"];
export type NominationOut = S["NominationOut"];
export type NominationCreate = S["NominationCreate"];
export type AuditEventOut = S["AuditEventOut"];
export type Role = S["Role"];
export type PrivacyLevel = S["PrivacyLevel"];
export type PublicMode = S["PublicMode"];
export type SiteImpactOut = S["SiteImpactOut"];

export type PersonSummary = S["PersonSummary"];
export type PersonOut = S["PersonOut"];
export type PersonCreate = S["PersonCreate"];
export type PersonUpdate = S["PersonUpdate"];
export type PrivacyUpdate = S["PrivacyUpdate"];
export type AddressPurpose = S["AddressPurpose"];
export type AddressStatus = S["AddressStatus"];
export type AddressIn = S["AddressIn"];
export type AddressUpdate = S["AddressUpdate"];
export type AddressOut = S["AddressOut"];
export type MoveAddressIn = S["MoveAddressIn"];
export type MoveAddressOut = S["MoveAddressOut"];
export type AddressReuseMode = S["AddressReuseMode"];
export type AddressReuseIn = S["AddressReuseIn"];
export type FamilyAddressSourceOut = S["FamilyAddressSourceOut"];
export type AdoptFamilyAddressVersionIn = S["AdoptFamilyAddressVersionIn"];
export type RevisionSnapshot = S["RevisionSnapshot"];
export type ContactKind = S["ContactKind"];
export type PersonContactIn = S["app__modules__profile_details__schemas__ContactIn"];
export type ContactUpdate = S["ContactUpdate"];
export type PersonContactOut = S["app__modules__profile_details__schemas__ContactOut"];
export type ContactReveal = S["ContactReveal"];
export type NameIn = S["NameIn"];
export type NameOut = S["NameOut"];
export type NameUpdate = S["NameUpdate"];
export type NameType = S["NameType"];
export type VitalIn = S["VitalIn"];
export type VitalSummary = S["VitalSummary"];
export type ProfileStatus = S["ProfileStatus"];
export type SexAtBirth = S["SexAtBirth"];
export type EvidenceStatus = S["EvidenceStatus"];
export type Confidence = S["Confidence"];

export type GenealogicalDate = S["GenealogicalDate"];
export type GenealogicalTime = S["GenealogicalTime"];
export type DatePrecision = S["DatePrecision"];
export type DateCalendar = S["DateCalendar"];
export type TimePrecision = S["TimePrecision"];
export type TimeSource = S["TimeSource"];

export type EventOut = S["EventOut"];
export type EventIn = S["EventIn"];
export type EventUpdate = S["EventUpdate"];
export type EventType = S["EventType"];

export type PlaceOut = S["PlaceOut"];
export type PlaceIn = S["PlaceIn"];
export type PlaceUpdate = S["PlaceUpdate"];
export type PlaceName = S["PlaceName"];
export type PlaceType = S["PlaceType"];

export type RelationshipType = S["RelationshipType"];
export type RelationshipOut = S["RelationshipOut"];
export type RelativeIn = S["RelativeIn"];
export type RelativeOut = S["RelativeOut"];
export type Lineage = S["Lineage"];
export type FamilyOut = S["FamilyOut"];
export type RelatedPerson = S["RelatedPerson"];
export type UnionOut = S["UnionOut"];
export type SiblingOut = S["SiblingOut"];
export type GraphOut = S["GraphOut"];
export type GraphNode = S["GraphNode"];
export type GraphEdge = S["GraphEdge"];
export type RelationshipPathOut = S["RelationshipPathOut"];

export type AssertionIn = S["AssertionIn"];
export type AssertionOut = S["AssertionOut"];
export type AssertionUpdate = S["AssertionUpdate"];
export type HeritageProfileOut = S["HeritageProfileOut"];
export type HeritageAttributeView = S["HeritageAttributeView"];
export type HeritageAttribute = S["HeritageAttribute"];
export type ValueStatus = S["ValueStatus"];

export type SourceOut = S["SourceOut"];
export type SourceIn = S["SourceIn"];
export type SourceType = S["SourceType"];
export type TraditionIn = S["TraditionIn"];
export type CitationOut = S["CitationOut"];
export type CitationIn = S["CitationIn"];
export type CitationTarget = S["CitationTarget"];

export type BranchOut = S["BranchOut"];
export type BranchIn = S["BranchIn"];
export type BranchDetailOut = S["BranchDetailOut"];
export type DescentRule = S["DescentRule"];
export type HouseholdOut = S["HouseholdOut"];
export type HouseholdIn = S["HouseholdIn"];
export type HouseholdDetailOut = S["HouseholdDetailOut"];
export type HouseholdMemberIn = S["HouseholdMemberIn"];
export type HouseholdMemberOut = S["HouseholdMemberOut"];
export type HouseholdRole = S["HouseholdRole"];
export type PersonHouseholdOut = S["PersonHouseholdOut"];
export type DeriveOut = S["DeriveOut"];

export type SearchOut = S["SearchOut"];
export type SearchHit = S["SearchHit"];
export type DuplicateCandidate = S["DuplicateCandidate"];

export type ConsentOut = S["ConsentOut"];
export type ConsentIn = S["ConsentIn"];
export type ConsentBasis = S["ConsentBasis"];
export type ClaimOut = S["ClaimOut"];

export type PublicTreeOut = S["PublicTreeOut"];
export type Message = S["Message"];

export type DocumentOut = S["DocumentOut"];
export type RecordPrivacyLevel = S["RecordPrivacyLevel"];
export type SharingOut = S["SharingOut"];
export type SharingUpdate = S["SharingUpdate"];
export type SharingMemberOut = S["SharingMemberOut"];
export type SharingMemberIn = S["SharingMemberIn"];
export type CollectionIn = S["CollectionIn"];
export type CollectionOut = S["CollectionOut"];
export type CollectionSummaryOut = S["CollectionSummaryOut"];
export type CollectionItemOut = S["CollectionItemOut"];
export type CollectionItemUpdate = S["CollectionItemUpdate"];
export type DocumentUpdate = S["DocumentUpdate"];
export type DocumentLinkIn = S["DocumentLinkIn"];
export type DocumentLinkOut = S["DocumentLinkOut"];
export type DocumentLinkTarget = S["DocumentLinkTarget"];
export type DocumentCategory = S["DocumentCategory"];
export type DownloadUrlOut = S["DownloadUrlOut"];
export type MetadataVersionOut = S["MetadataVersionOut"];
export type StorageClass = S["StorageClass"];
export type ScanStatus = S["ScanStatus"];
export type ProcessingStatus = S["ProcessingStatus"];
export type ProposalOut = S["ProposalOut"];
export type ProposalStatus = S["ProposalStatus"];
export type ReviewIn = S["ReviewIn"];
export type OcrTextOut = S["OcrTextOut"];
export type ReprocessOut = S["ReprocessOut"];
export type AstrologyIn = S["AstrologyIn"];
export type AstrologyOut = S["AstrologyOut"];
export type AstrologyUpdate = S["AstrologyUpdate"];
export type AstrologyProvenance = S["AstrologyProvenance"];
export type BirthConflictsOut = S["BirthConflictsOut"];
export type BirthClaim = S["BirthClaim"];
export type BirthConflict = S["BirthConflict"];
export type PropertyIn = S["PropertyIn"];
export type PropertyOut = S["PropertyOut"];
export type PropertyUpdate = S["PropertyUpdate"];
export type PropertyDetailOut = S["PropertyDetailOut"];
export type PropertyType = S["PropertyType"];
export type PropertyClassification = S["PropertyClassification"];
export type ParcelIn = S["ParcelIn"];
export type ParcelOut = S["ParcelOut"];
export type ParcelUpdate = S["ParcelUpdate"];
export type ParcelRef = S["ParcelRef"];
export type ParcelLineageOut = S["ParcelLineageOut"];
export type SubdivideIn = S["SubdivideIn"];
export type SubdivideOut = S["SubdivideOut"];
export type SubdivisionChildIn = S["SubdivisionChildIn"];
export type AreaUnit = S["AreaUnit"];
export type InterestIn = S["InterestIn"];
export type InterestOut = S["InterestOut"];
export type InterestUpdate = S["InterestUpdate"];
export type InterestEndIn = S["InterestEndIn"];
export type InterestStatus = S["InterestStatus"];
export type InterestType = S["InterestType"];
export type HolderType = S["HolderType"];
export type HolderOut = S["HolderOut"];
export type PropertyEventIn = S["PropertyEventIn"];
export type PropertyEventOut = S["PropertyEventOut"];
export type PropertyEventType = S["PropertyEventType"];
export type PartitionIn = S["PartitionIn"];
export type AllocationIn = S["AllocationIn"];
export type TimelineOut = S["TimelineOut"];
export type LineageOut = S["LineageOut"];
export type LineageChain = S["LineageChain"];
export type DocumentRef = S["DocumentRef"];
export type PersonPropertyInterestsOut = S["PersonPropertyInterestsOut"];
export type ImportJobOut = S["ImportJobOut"];
export type ImportJobSummary = S["ImportJobSummary"];
export type StagedPersonPreview = S["StagedPersonPreview"];
export type CommitIn = S["CommitIn"];
export type JobStatus = S["JobStatus"];
export type DuplicateMatch = S["DuplicateMatch"];
export type MergeIn = S["MergeIn"];
export type MergeOut = S["MergeOut"];
export type GrantCreate = S["GrantCreate"];
export type GrantOut = S["GrantOut"];
export type GrantPermission = S["GrantPermission"];
export type GrantResource = S["GrantResource"];
export type SourceUpdate = S["SourceUpdate"];
export type HouseholdUpdate = S["HouseholdUpdate"];
export type BranchUpdate = S["BranchUpdate"];

export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
}

// Onboarding: family-data attestation and shareable claim invites (ADR-0011)
export type StatementOut = S["StatementOut"];
export type StatementKind = S["StatementKind"];
export type AttestationStatus = S["AttestationStatus"];
export type AttestationOut = S["AttestationOut"];
export type ClaimInviteOut = S["ClaimInviteOut"];
export type ClaimInviteCreated = S["ClaimInviteCreated"];
export type ClaimInvitePreview = S["ClaimInvitePreview"];
export type ClaimInviteAccept = S["ClaimInviteAccept"];
export type ClaimSubmitted = S["ClaimSubmitted"];
export type RemovalRequestIn = S["RemovalRequestIn"];
export type ClaimKind = S["ClaimKind"];

// ---- heritage visualization milestone (ADR-0015/0016/0017)
export type LifeEventCategory = S["LifeEventCategory"];
export type EventSignificance = S["EventSignificance"];
export type LocationPrecision = S["LocationPrecision"];
export type EventMediaOut = S["EventMediaOut"];
export type EventMediaUpdate = S["EventMediaUpdate"];
export type EventMediaLinkIn = S["EventMediaLinkIn"];
export type NotificationChannel = S["NotificationChannel"];
export type ReminderKind = S["ReminderKind"];
export type ReminderRecurrence = S["ReminderRecurrence"];
export type ReminderIn = S["ReminderIn"];
export type ReminderOut = S["ReminderOut"];
export type ReminderUpdate = S["ReminderUpdate"];
export type PreferenceIn = S["PreferenceIn"];
export type PreferenceOut = S["PreferenceOut"];
export type UpcomingOut = S["UpcomingOut"];
export type DeliveryOut = S["DeliveryOut"];
export type DeliveryStatus = S["DeliveryStatus"];
export type ContactIn = S["app__modules__notifications__schemas__ContactIn"];
export type ContactOut = S["app__modules__notifications__schemas__ContactOut"];
export type ChannelsOut = S["ChannelsOut"];
export type VizPerson = S["VizPerson"];
export type AncestryOut = S["AncestryOut"];
export type AncestryNode = S["AncestryNode"];
export type NeighbourhoodOut = S["NeighbourhoodOut"];
export type GraphNodeOut = S["GraphNodeOut"];
export type GraphEdgeOut = S["GraphEdgeOut"];
export type LifespansOut = S["LifespansOut"];
export type LifespanRow = S["LifespanRow"];
export type StoryOut = S["StoryOut"];
export type StoryEvent = S["StoryEvent"];
export type MapOut = S["MapOut"];
export type MapPoint = S["MapPoint"];
export type MapPath = S["MapPath"];
export type GeoPoint = S["GeoPoint"];
export type ChartType = S["ChartType"];
export type PresetIn = S["PresetIn"];
export type PresetOut = S["PresetOut"];
export type RenderJobIn = S["RenderJobIn"];
export type RenderJobOut = S["RenderJobOut"];
export type RenderSettings = S["RenderSettings"];
export type RenderDownloadOut = S["RenderDownloadOut"];
export type RenderStatus = S["RenderStatus"];

// Smart Add Relative (ADR-0020)
export type SmartAddTerm = S["SmartAddTermOut"];
export type SmartAddPlanIn = S["SmartAddPlanIn"];
export type SmartAddPlan = S["SmartAddPlanOut"];
export type SmartAddStep = S["SmartAddStepOut"];
export type SmartAddTarget = S["SmartAddTargetOut"];
export type SmartAddPreviewItem = S["SmartAddPreviewItem"];
export type SmartAddCommitIn = S["SmartAddCommitIn"];
export type SmartAddCommitOut = S["SmartAddCommitOut"];

// Master data vocabularies (ADR-0018)
export type VocabularyOut = S["VocabularyOut"];
export type VocabularyTerm = S["VocabularyTermOut"];
export type VocabularyTerms = S["VocabularyTermsOut"];
export type TreeTermIn = S["TreeTermIn"];
export type TreeTermOut = S["TreeTermOut"];

// name transliteration suggestions (ADR-0025)
export type TransliterateOut = S["TransliterateOut"];
export type TransliterationCandidate = S["TransliterationCandidate"];

// Indian geography reference data (ADR-0019)
export type GeoLevel = S["GeoLevel"];
export type GeoUnitOut = S["GeoUnitOut"];
export type GeoUnitBrief = S["GeoUnitBrief"];
export type GeoUnitsPage = S["GeoUnitsPage"];
export type GeoUnitResponse = S["GeoUnitResponse"];
export type PincodeOut = S["PincodeOut"];
export type PlaceLgdNote = S["PlaceLgdNote"];

// change proposals, family review and duplicates at entry (ADR-0021)
export type ReviewPolicy = S["ReviewPolicy"];
export type ReviewState = S["ReviewState"];
export type ReviewTarget = S["ReviewTarget"];
export type ProposalOp = S["ProposalOp"];
export type ProposalIn = S["ProposalIn"];
export type ProposalItemIn = S["ProposalItemIn"];
export type ChangeProposalOut = S["ChangeProposalOut"];
export type ProposalSummary = S["ProposalSummary"];
export type ChallengeIn = S["ChallengeIn"];
export type RevisionOut = S["RevisionOut"];
export type RevertOut = S["RevertOut"];
export type NotificationsOut = S["NotificationsOut"];
export type NotificationOut = S["NotificationOut"];
export type DuplicateCheckIn = S["DuplicateCheckIn"];
export type DuplicateCheckOut = S["DuplicateCheckOut"];

// ADR-0026: cultural depth
export type OfferIn = S["OfferIn"];
export type OfferOut = S["OfferOut"];
export type OfferStatus = S["OfferStatus"];
export type KinshipTermOut = S["KinshipTermOut"];
export type KinshipPackOut = S["KinshipPackOut"];
export type KinshipPreferenceIn = S["KinshipPreferenceIn"];
export type KinshipOverrideIn = S["KinshipOverrideIn"];
export type KinshipOverrideOut = S["KinshipOverrideOut"];
export type TraditionKind = S["TraditionKind"];
export type TraditionEntryIn = S["TraditionEntryIn"];
export type TraditionEntryUpdate = S["TraditionEntryUpdate"];
export type TraditionOut = S["TraditionOut"];
export type TraditionSummaryOut = S["TraditionSummaryOut"];
export type TraditionsOut = S["TraditionsOut"];
export type TraditionLinkIn = S["TraditionLinkIn"];
export type TraditionLinkOut = S["TraditionLinkOut"];
export type TraditionRevisionOut = S["TraditionRevisionOut"];

// ADR-0022: family calendar
export type LunarDate = S["LunarDate"];
export type Paksha = S["Paksha"];
export type MonthConvention = S["MonthConvention"];
export type Samvat = S["Samvat"];
export type DateDerivation = S["DateDerivation"];
export type CalendarSettingsOut = S["CalendarSettingsOut"];
export type CalendarSettingsIn = S["CalendarSettingsIn"];
export type CalendarOut = S["CalendarOut"];
export type CalendarEntryOut = S["CalendarEntryOut"];
export type ConvertIn = S["ConvertIn"];
export type ConvertOut = S["ConvertOut"];
export type FeedOut = S["FeedOut"];
export type ReminderDateRule = S["ReminderDateRule"];
