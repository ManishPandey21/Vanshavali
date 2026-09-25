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
export type AuditEventOut = S["AuditEventOut"];
export type Role = S["Role"];
export type PrivacyLevel = S["PrivacyLevel"];
export type PublicMode = S["PublicMode"];

export type PersonSummary = S["PersonSummary"];
export type PersonOut = S["PersonOut"];
export type PersonCreate = S["PersonCreate"];
export type PersonUpdate = S["PersonUpdate"];
export type PrivacyUpdate = S["PrivacyUpdate"];
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

export interface Page<T> {
  items: T[];
  next_cursor?: string | null;
}
