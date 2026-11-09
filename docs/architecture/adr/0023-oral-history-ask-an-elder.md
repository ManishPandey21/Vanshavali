# ADR-0023: Oral history: "Ask an Elder", recorded stories, consent and transcripts

- Status: **Proposed** (revised twice after the owner's reviews of 8 Nov 2026; revision 3 of 9 Nov
  2026 prepares it for design review: alignment with ADR-0027, the admin-access contradiction
  resolved, interviewer-access options, and the §12 privacy/threat drafts; **not accepted**, no
  implementation) · Release: R5, phase I
- Relates to: ADR-0004 (document storage and the vault pipeline), ADR-0006 (privacy, field groups),
  ADR-0009 (OCR/AI output is a proposal), ADR-0011 (single-use invite links, "remove me"),
  ADR-0014 (pilot hosting and backups), ADR-0016 (notifications), ADR-0021 (proposals and family
  review), ADR-0026 (traditions archive, whose `story` entries are text), **ADR-0027** (record
  visibility and selective sharing, accepted 9 Nov 2026); open questions Q7 (no
  external AI by default) and **Q17** (voice processing, now answered by §8)
- Plan: [india-master-data-and-smart-forms-plan.md](../india-master-data-and-smart-forms-plan.md),
  release R5, phase I. Kept in its own PR, separate from the family calendar (owner decision 1).

## Context
Families want to keep their elders' voices: how the family came to the village, who the ancestors
were, the songs and the rituals. Often the elder is the only source, and there is little time.

What exists today:
- **Audio files.** The document vault accepts them (ADR-0004). Content is sniffed and structurally
  checked (`app/core/filetypes.py`), malware-scanned, stored immutably and cited, and
  `SourceType.ORAL_HISTORY` exists.
- **No recording.** There is no in-app recording, no way to ask an elder who has no account, and
  no speech-to-text. The traditions archive (ADR-0026) holds written stories only.

Voice is unlike a scanned document:
1. **It identifies a living person and records them speaking.** Consent must be informed, specific
   and revocable, and withdrawal must take effect at once and really erase. The Digital Personal
   Data Protection Act 2023 (DPDP Act) applies. Which of its provisions are in force, and when, is
   part of the legal review (§13).
2. **The narrator talks about other living people.** Health, disputes, adoptions and marriages
   come up, so their privacy has to hold as well.
3. **Recorders differ by browser.** Chrome and Firefox record WebM/Opus; Safari records MP4/AAC.
   The sniffer today labels every WebM file `video/webm`, so an audio-only recording would be
   stored as a video.
4. **Speech-to-text (STT) for Indian languages is imperfect.** Sending voice to an external service
   is a privacy decision (Q7, Q17). A transcript is machine output, so ADR-0009 and the project
   rule apply: it is a proposal, never canonical data.

## Decision

### 1. Stories and their media
- **`oral_story`** is tree-scoped and under row-level security. It holds:
  - title, narrator, interviewer (the member who recorded or asked), recording date and place;
  - language and script;
  - **visibility** (§6), status and the consent record (§4).
- The narrator is a person in the tree, or a name only, for example a neighbour. How the narrator
  was confirmed is part of the story (§5).
- Status runs `draft → consented → recorded → transcribed → reviewed`, with `withdrawn` possible at
  any point and taking effect at once (§9).
- **Media are vault documents** (ADR-0004), with source type `oral_history`, linked to the story.
  Uploads never bypass the vault pipeline: validate → malware scan → immutable storage.
- **`story_mention`** tags a person, optionally to a time range (§6).
- A tradition entry (ADR-0026) can link to an oral story. Written stories are not duplicated.

### 2. Recording and upload
- **In-browser recording** uses MediaRecorder, preferring Opus (WebM or Ogg) and falling back to
  MP4/AAC on Safari. Existing voice notes can also be uploaded: a WhatsApp `.opus` file is an Ogg
  file.
- **Audio-only WebM is classified as `audio/webm`.** The sniffer checks that the file has no video
  track. A file that holds video is refused as "not an audio recording".
- **Resumable upload:**
  - fixed-size chunks, each with its SHA-256;
  - assembled on the server, then the whole file goes through the vault pipeline;
  - **an incomplete upload expires 24 hours after its last chunk** (owner decision 4) and its parts
    are deleted.
- **Pilot limits** (owner decision 3), all configurable:
  - **60 minutes and 200 MB per recording**;
  - **5 GB in total of oral-history media per tree** (owner decisions 3 and, in the second round,
    5). It is one quota covering everything stored for the tree's stories:
    - originals and consent clips;
    - **archived recordings**, with no separate archive quota in the pilot;
    - **temporary upload parts**;
    - **derivatives** (transcripts, previews).

    An upload that would exceed the quota is refused before it starts, and the remaining space is
    shown.
- **Elders and low-end phones.** Controls are large, the screen is in the elder's language, and the
  recording can be reviewed before sending. Upload continues after a dropped connection. (Phase L
  will build on this.)

### 3. Visibility, ownership and admin access: private by default, sharing is a choice
Owner decision 10: a recording can stay private, and sharing it is never a condition of recording.

**A story is an ADR-0027 shareable record, owned by its narrator** (revision 3; ADR-0027 §1–§2,
§10). The interviewer is **not** an owner (see §3a).

| Who | Their relation to a story |
|---|---|
| **Narrator** (or their guardian) | **Owner.** Decides the audience, within their consent (§4). When the narrator is a tree member, the story's owner is the narrator's membership (ADR-0027 §2). When they are not, see "Narrators who are not members" below. |
| **Interviewer** (the member who recorded or asked) | **Not an owner.** Any access they have is a separate permission the narrator gives, with its own duration and revocation. The form of that permission is **not yet decided** (§3a). |
| **Members in the chosen audience** | Can see the story and play the audio, as ADR-0027 defines each audience. |
| **Tree admins and owners** | No ordinary access to private stories (below). |
| **System jobs** | Withdrawal, erasure, retention and quota run as the system, return no content to any person, and are audited as `system` (ADR-0027 §8.1). |

**Audiences** (ADR-0027 §1), each within the narrator's consent:

| Narrator's choice | ADR-0027 audience | Needs |
|---|---|---|
| **Private** (default) | `ONLY_ME`: the narrator alone (plus the interviewer only as §3a allows) | scope 1 |
| **Shared with chosen members** | `SELECTED_MEMBERS` | scope 4 (§4); whether a narrower scope for "chosen members only" is needed is an open product decision (§14) |
| **Shared with a branch** | `FAMILY_BRANCH` + branch | scope 4 |
| **Shared with the family** | `TREE_MEMBERS` | scope 4 |

The narrator's consent is the story's **ceiling** (ADR-0027 §5.1): without scope 4 the ceiling is
private, and removing scope 4 narrows the story to private at once. A story is **never public** in
v1, whatever the tree's public mode, as for the traditions archive. Tagged living people cap a
shared story as in ADR-0027 §5.2 (and §6 below).

**Administrators and private stories** (second-round owner decision 7; revision 3 resolves the
contradiction with the old §6 in favour of this decision):
- "Private" means the two ADR-0027 private audiences, `ONLY_ME` and `SELECTED_MEMBERS`, and also
  every state in which a recording is restricted: **unconfirmed link recordings** (§5) and recordings
  under a **hide-passage request** (§6).
- Tree admins and owners receive **no ordinary access** to a private story: no audio, no transcript
  and **no metadata** (title, narrator, dates, mentions, or even its existence as a row). By default
  they see only the tree's aggregate oral-history storage usage.
- Being promoted to admin, owner or custodian grants nothing (ADR-0027 §1, T54). Being in a shared
  audience is the only way a person with an admin role sees a story, exactly like any member.
- This is enforced on the server. Story queries filter private stories to the people §3 and §3a
  allow **whatever the caller's role**. Usage is computed by an aggregate query that returns totals
  only. Admin, audit (ADR-0027 §11), grant-list and export screens use the same rules.
- The only exceptions are ADR-0027 §8's narrow, audited custodial ones: system jobs, takedown by
  **suspension without reading** (§3b, abuse reports), and the Legacy Nominee (§10). None of them
  gives a person the content.

**Narrators who are not members** (an elder recorded through a link, or a neighbour). No tree member
holds the narrator's ownership, so "Only me" cannot mean "a member". **Proposed for review** (not
decided):
- The story has no owner membership. Its owner is recorded as the **narrator reference** (a person
  in the tree, or a name only) together with the narrator's withdrawal-code holder.
- **"Only me" then means: nobody in the tree**, except the interviewer as §3a allows. The narrator
  reaches their own story through a **narrator page** opened with their withdrawal code (§5): they
  can listen, change scopes, choose an audience, name a nominee or withdraw. Nobody else can act as
  owner on their behalf.
- If the narrator later joins the tree (ADR-0011 claim or invitation) and their identity is
  confirmed as the narrator, ownership moves to their new membership. Nothing is widened by the
  move.
- Whether a narrator page is acceptable without an account, and how the code holder is verified for
  ownership changes, are open legal and product decisions (§14).

### 3a. Interviewer access: options for review (none approved)
The current text gave the interviewer standing access to every private story they recorded. That
makes them a second owner without the narrator saying so, which ADR-0027's ownership model and
owner decision 10 do not support. Revision 3 proposes the options below **for the owner to choose
from**. None is recorded as decided; until one is chosen, nothing about interviewer access is
implemented.

Every option shares these rules:
- The interviewer's access is a **separate permission the narrator grants**, shown in the consent
  statement in the narrator's language, with its own yes or no.
- It never exceeds the narrator's consent, is never wider than "listen and transcribe", and never
  lets the interviewer change the audience, scopes or nominee.
- The narrator (or guardian, or verified nominee) can **revoke it at any time**; revocation takes
  effect at once like any ADR-0027 revocation (signed URLs re-checked, 5-minute lifetime).
- Withdrawal (§9) ends it at once.
- It is audited (granted, used, expired, revoked) without content.

| Option | What the interviewer may do | Duration | Revocation and notes |
|---|---|---|---|
| **A. No standing access** | Nothing after sending the recording, except see that it was sent. Any later access is an explicit ADR-0027 grant from the narrator ("Selected members"), with view and transcribe as separate choices. | n/a | Strongest for the narrator. Needs a solution for **attributing link recordings** (§5), where today the asking member listens to identify the voice: either a short attribution-only window (as in C) or confirmation by the narrator only. |
| **B. Consent scope "interviewer may listen and transcribe"** | Listen, transcribe, propose facts. | Until the transcript is reviewed, and **at most N days** (proposal: 90, matching raw-audio retention) | A new consent **scope 6**, off by default. Revocable at any time from the narrator page or account. Expiry is automatic. |
| **C. Task-limited, time-boxed access** | Only named tasks: identify the voice (link recordings), transcribe, review the transcript. | Each task has its own window (proposal: attribution 30 days, as the existing unconfirmed-recording deletion; transcription until review or 90 days) | Granted per task in the consent step; revocable per task; ends when the task completes. More moving parts, but the narrowest standing access. |
| **D. Standing access, as currently drafted** | Listen and transcribe for as long as the story exists. | Unlimited | Kept only for comparison. It makes the interviewer a de facto co-owner; adopting it would need the owner to confirm explicitly that this is intended and a stated way for the narrator to remove it. |

Points the choice must settle (listed in §14): the default for each option, whether the interviewer
of a **minor's** or a **guardian-consented** recording is treated differently, and what the
interviewer sees after access ends (proposal: the story's existence and status only, as for any
private record they no longer hold).

### 3b. Abuse and legal reports about a story (proposed for review)
Resolves the old open point 3 as a **proposal**, to be confirmed with the legal review:
- **Who may report.** Anyone who can see the story; a person mentioned or tagged in it, through
  their own profile; and, for a private story, only its narrator, the interviewer (if §3a gives
  access) or a tagged person.
- **What a report does.** It creates a case with a reference. A family admin, or the platform's
  designated reviewer, may **suspend** the story by its case reference (ADR-0027 §8.2): it is then
  hidden from everyone except its narrator, and processing stops. **The person who suspends sees no
  content and no metadata beyond the case reference and the report's reason category.**
- **Who decides.** The narrator may respond. A decision that needs someone to hear the recording
  (for example a court order or a dispute between narrator and tagged person) goes to a process the
  legal review defines. Until then the story stays suspended, never opened to an admin.
- **Audit.** Report, suspension, response and outcome are audited without content.

### 4. Consent before anything is recorded
**Scopes** are each a separate yes or no, and none is required beyond scope 1:
1. record, including the consent clip;
2. transcribe on our own servers;
3. transcribe with an external service (§8), off unless explicitly given;
4. share in the tree (§3);
5. keep the raw audio long-term ("archive", §9).

**Sequence** (owner decision 10). No sound is recorded before step 2:
1. **The statement.** The app shows, and reads aloud in the narrator's language, the versioned
   statement (`consent/statements`): what is recorded, who can hear it, the scopes, how to
   withdraw, and the retention rules.
2. **Written consent.** The narrator (or guardian) chooses the scopes and confirms with a tick-box,
   or the interviewer records that consent was given orally, naming themselves. This creates the
   `recording_consent` record, holding the statement version, the scopes, who consented and who
   collected it, and the time. **This is the consent of record.**
3. **The consent clip (optional, recommended).** With scope 1 already given, a short clip records
   the narrator confirming in their own words ("Haan, main sahmat hoon"). It is stored inside the
   consent record as supporting evidence. If the narrator declines it, recording can still go
   ahead on the written consent.
4. **Recording.** The recorder unlocks only after step 2. The server refuses a story upload whose
   story has no consent record with scope 1.

A scope can be changed later, but only by the narrator or guardian. Removing scope 4 makes the story
private again at once.

**Who can consent:**
- **A minor** (under 18) is recorded only with a guardian's consent, and never through an "Ask an
  Elder" link.
- **A narrator unable to consent** needs a guardian, and the record names the guardian and their
  relationship.
- The legal review (§13) confirms both rules.

### 5. "Ask an Elder" links and narrator attribution
- **Built on the ADR-0011 link infrastructure:**
  - a single-use bearer token, carried in the URL fragment;
  - **unused links expire after 7 days** (owner decision 4), and the asking member can revoke one;
  - single-purpose: one question, written (and optionally spoken) by the asking member, in the
    elder's language.
- **Token exchange** (owner decision 10). The fragment is never sent to the server by the browser,
  so the page exchanges it:
  1. The page's script sends the token **once**, in a `POST` body, to `/ask-elder/session`.
  2. The server checks it and returns a **short-lived session cookie scoped to that one link**
     (HttpOnly, Secure, SameSite=Strict, path `/api/v1/ask-elder`, 30 minutes, renewed while
     recording or uploading).
  3. The page removes the fragment from the address bar (`history.replaceState`).
  4. The page sends `Referrer-Policy: no-referrer` and loads no third-party resources.

  The token is stored only as a SHA-256 hash and never logged. Exchange attempts are rate-limited
  per IP address and per token.
- **What the link holder sees.** No account and no tree access: only the question, the consent
  steps (§4), the recorder and a review-before-send step. After sending, the link is spent.
- **The withdrawal code** (owner decision 10):
  - a random code of at least 128 bits, shown as groups of words or characters a person can copy;
  - shown once, and sent by SMS or WhatsApp only if the elder gave a number;
  - **stored only as a hash (SHA-256)**;
  - redeemable only at the withdrawal endpoint, which is rate-limited and audited.

  A member-recorded story gets a code too, given to the narrator.
- **Narrator attribution** (owner decision 10):
  - A recording that arrives by link is held as **"narrator not confirmed"**. Until confirmed it is
    private: nobody sees it except, **if the chosen §3a option allows it**, the asking member, to
    identify the voice. Admins see it only in the aggregate usage (§3). Whether the asking member
    may listen for attribution is part of the §3a decision.
  - Confirmation names the narrator (a person in the tree, or a name only), and records who
    confirmed it, how ("I know this voice" or "the narrator confirmed with their account") and
    when.
  - **The consent stays the speaker's, whoever they turn out to be.** Changing the attribution
    doesn't transfer or widen it.
  - A recording that isn't confirmed within **30 days** is deleted (second-round owner decision 4).
    The asking member, and the narrator **where a verified contact exists** (a verified phone or
    email), are warned 5 days before.

### 6. Privacy of shared stories and of the people mentioned
- **The default privacy is the most restrictive** of three: the narrator's, every tagged living
  person's, and the tree default. A member may make it more restrictive, never less.
- **Facts drawn from a story** about another person become proposals governed by *that person's*
  privacy (ADR-0021).
- **A tagged living person** can ask to be untagged, or for a passage (a time range) to be hidden.
- **Hiding a passage** (owner decision 6):
  - While the request is open, the **whole original recording** is restricted to the narrator
    (and to the interviewer only as §3a allows), and the requested transcript span is hidden from
    everyone else. **Tree admins gain no access** (revision 3: the earlier text named "tree admins"
    here, contradicting §3 and second-round owner decision 7; the decision prevails).
  - **Who decides** the request: the narrator. When the narrator cannot (a non-member who does not
    respond, incapacity, death without a nominee) or disputes it, the request goes to the process in
    §3b; nobody hears the recording to decide it without that process. This is an open decision
    (§14).
  - The decision is either hiding the span for good, with the audio staying restricted, or
    declining the request with a reason.
  - **Silencing a passage in the audio is deferred.**
- **Access and logging.** Media are served through short-lived signed URLs (ADR-0004), and every
  playback and download is audited. Logs never contain transcript text, audio or tokens.

### 7. Transcripts
- **Manual transcription is always available** (owner decision 9), and is the only kind until an
  STT engine is approved (§8).
- A transcript is a versioned derivative recording its origin: manual, or machine with the engine,
  model, version and language. A machine transcript is marked as such until a person corrects it.
- **Facts become `extraction_proposal`s** (ADR-0009), each citing the story and a time range. They
  are reviewed like any proposal and never applied directly.

### 8. Speech-to-text (answers Q17; owner decision 2)
- **Self-hosted by default.** Transcription runs as a background job on our own servers.
- **External services** (for example the Government of India's BHASHINI) are used only when both
  hold:
  1. a tree admin has opted in for the tree, with informed wording;
  2. the narrator's consent includes **scope 3**.

  Whatever the provider's terms promise about retention and training is recorded, and every call
  is audited. Without both, nothing leaves our servers. A missing self-hosted engine never falls
  back to an external one.
- **The engine choice is deferred** (owner decision 9). It is made in a later decision record,
  after:
  - a licence review of the **code and the model weights**, which are licensed separately;
  - an accuracy benchmark in Hindi and the pilot's regional languages, using recordings made with
    consent for that purpose;
  - an assessment of the pilot hardware (ADR-0014).

  Candidates noted so far, by PyPI-declared code licence on 8 Nov 2026: faster-whisper (MIT) on
  CTranslate2 (MIT) with Whisper models, and Vosk (Apache-2.0). This is not a selection.

### 9. Withdrawal, retention and erasure

**Who can withdraw:**
- the narrator (or their guardian), at any time, with the withdrawal code;
- or from their own account, if they have one;
- after the narrator's death, only a **verified Legacy Nominee** (§10).

These are **verified withdrawals**. Each takes effect the moment it is made, with no person in the
loop.

**Requests without verification** (second-round owner decision 3):
- If the narrator has lost the code and has no account, and asks a tree admin, the admin must
  verify the requester and act within **7 days**. The admin acts **without content access**: they
  start a withdrawal case naming the narrator, the system suspends that narrator's stories at once,
  and the admin sees only how many stories the case covers. How the admin verifies the requester is
  an open legal decision (§14).
- Meanwhile the story is suspended: no processing, and no access except the narrator's.
- This manual path never delays a verified withdrawal.

**Immediately on a valid withdrawal** (owner decision 11; second-round decision 2):
1. **Future processing stops.** Queued and running transcription jobs are cancelled, no external
   call is started, and no new proposal is created from the story.
2. **Media access is revoked.**
   - No new signed URL is issued.
   - Playback and download stop.
   - Existing signed URLs can't outlive their lifetime. Oral-history playback and download URLs
     last **at most 5 minutes** (second-round decision 3), shorter than the vault default.
3. **The story disappears** from every member's view, except as "withdrawn".

**Work already running** (second-round decision 2):
- **Queued jobs** are removed.
- **A running job** checks the story's withdrawal flag before each step and before writing any
  output. Output from a job that finishes after the withdrawal is discarded, never stored.
- **An external transcription call in flight** has its response discarded. Where the provider
  supports it, a deletion request is sent, and the request and its reply are recorded.
- **An upload in progress** has further parts refused, and its parts are deleted with the rest.

**Within 24 hours (erasure job):**
- **Hard-delete from primary storage:** the recording, the consent clip, the temporary upload
  parts, every derivative and every transcript version, and every unreviewed proposal from the
  story.
- **Every version is deleted.** The document bucket keeps noncurrent versions for 30 days
  (backup-restore runbook), so erasure removes all versions of each object, not just the current
  one.
- **Kept, without content, as evidence:** the consent record (scopes, dates, statement version) and
  the withdrawal record. The audit log records the event without content.
- **Backups** (documented handling):
  - Backups are not edited. The nightly object mirror and database dumps are kept for 35 days under
    Object Lock (backup-restore runbook), so withdrawn media leave backups **within 35 days**.
  - **Restores re-apply withdrawals.** The withdrawal records are kept (without content) in the
    database and in an append-only withdrawal log. After any restore, the erasure job replays every
    withdrawal made since the backup was taken, before the system is reopened to users.
  - The privacy model states these limits, and the legal review confirms they are acceptable.

**Facts accepted before the withdrawal** (owner decision 11, defined separately):
- **A fact is genealogy data a reviewer accepted.** It is not part of the recording, so it isn't
  deleted automatically, and it isn't kept silently either.
- **Its citation to the story becomes a tombstone,** "oral history (withdrawn)", with no quote, no
  time range, no media and no transcript.
- **A fact whose only evidence was the withdrawn story** is flagged **"evidence withdrawn"** for
  review. Its reviewers decide to keep it as family knowledge (re-cited if they can) or to delete
  it. The narrator is told which facts were flagged.
- **Facts about the narrator themselves** are not affected by withdrawal; "remove me" (ADR-0011)
  is the narrator's route for those.

**Retention without archive consent** (owner decision 5):
- Raw audio is deleted **30 days after the transcript is reviewed**, and in any case **no later
  than 90 days after upload**, even if no transcript was reviewed.
- **Where possible** (second-round decision 4), the interviewer, and the narrator if a verified
  contact exists, are warned **14 days before** temporary raw audio reaches its 90-day maximum.
- Reviewed transcripts stay at the story's visibility and privacy.

**Long-term archive** keeps the raw audio until withdrawal. It is allowed only with the narrator's
**separate archive consent** (scope 5), never by a member's or admin's choice.

**"Remove me"** (ADR-0011) covers a narrator's stories and a tagged person's mentions.

### 10. Legacy Nominee (owner decision 7)
- **Who names one.** A narrator may name a **Legacy Nominee**: one person who may withdraw the
  narrator's stories, or change their scopes, after the narrator's death or incapacity. This
  follows the nomination right in DPDP Act Section 14, subject to the legal review (§13).
- **How the nominee is recorded.** The narrator makes the nomination themselves (with the
  withdrawal code or from their account). It names the person and how they will be contacted.
- **Before a nominee can act** (second-round owner decision 6), both are required:
  1. **verified identity:** an account with a verified phone or email matching the nomination,
     plus whatever identity check the legal review sets;
  2. **documented authority:** the narrator's own nomination record, plus documentary evidence of
     the narrator's death or incapacity.
- **Who checks the evidence** is set by the legal review. Checking it grants **no access** to the
  story's content. Every step is audited.
- **Nobody else.** Tree admins and heirs **do not automatically** gain this authority. Without a
  verified nominee, consent given while the narrator was alive stays in force, the story keeps its
  visibility, and retention still applies.
- **What a nominee can do:** withdraw, or narrow the scopes. They cannot widen them.

### 11. API (all under `/api/v1`, typed, authorised)
- `POST|GET /trees/{t}/stories`, `GET|PATCH|DELETE /trees/{t}/stories/{id}`
- `POST /trees/{t}/stories/{id}/consent` (statement version, scopes, who), then
  `POST …/consent/clip` (the optional clip, after the consent record exists)
- `POST /trees/{t}/stories/{id}/uploads` (start; quota checked), `PUT …/uploads/{u}/parts/{n}`,
  `POST …/uploads/{u}/complete`
- `POST|GET /trees/{t}/stories/{id}/mentions`, `POST …/mentions/{m}/hide-request`
- `POST /trees/{t}/stories/{id}/attribution` (confirm the narrator of a link recording)
- `GET|PUT /trees/{t}/stories/{id}/transcript` (versions), `POST …/transcribe` (only once an
  engine is approved, and per consent and tree policy)
- `POST /trees/{t}/ask-elder` (create), `DELETE /trees/{t}/ask-elder/{id}` (revoke)
- `POST /ask-elder/session` (exchange the fragment token for the link-scoped cookie), then
  `GET /ask-elder/question`, `POST /ask-elder/consent`, the upload endpoints, and
  `POST /ask-elder/send`
- `POST /stories/withdraw` (withdrawal code; rate-limited), `POST /trees/{t}/stories/{id}/nominee`

### 12. Gates before implementation
1. This ADR completes design review and is accepted.
2. The **privacy model (new §15) and threat model (new entries)** are written and reviewed. They
   are prepared after the design review (owner decision 12). **Drafts for review** are in
   `docs/security/privacy-model.md` §15 and `docs/security/threat-model.md` §6 (entries OH-1 to
   OH-14, not yet numbered as T-entries because nothing is implemented).
3. **Before any external user records** (anyone recording through a link, or any narrator who is not
   a member), the legal review in §13 is done.
4. STT stays off until the engine decision record (§8). External STT also needs its own reviewed
   opt-in wording.

### 13. Legal and licensing reviews required (owner decisions 7, 8 and 9)
- **Qualified legal review**, completed before any external user records:
  - the consent statements, in every language used;
  - the withdrawal process and its timings;
  - third-party privacy (people mentioned and tagged);
  - minors and narrators unable to consent;
  - backup erasure;
  - the Legacy Nominee under DPDP Act Section 14;
  - the applicable DPDP **commencement provisions**: which parts of the DPDP Act and Rules are in
    force, and from when.
- **Licensing review of the STT engine** (code and model weights), as part of its decision record.

## Consequences
- Families can record elders, privately or shared, in the app or through a link. Consent comes
  first, and withdrawal is immediate.
- The vault, the proposals system and the invite links are reused. The new parts are the story
  model, the consent sequence and scopes, resumable upload with quotas, attribution, the nominee
  and the erasure jobs.
- Storage is bounded by per-tree quotas that count temporary parts and derivatives. Raw audio
  leaves by default within 90 days.
- Until an STT engine is approved, transcripts are manual. That is slower, but no voice leaves our
  servers and no machine output is mistaken for data.

## Alternatives considered
- **Upload only (no in-app recording).** Simpler, but elders without a smartphone helper are left
  out, and consent could not be captured in the same flow.
- **Sharing as a condition of recording.** Rejected: it would push narrators either to share what
  they would rather keep private, or not to record at all.
- **Fragment token sent on every request.** Rejected in favour of a one-time exchange for a scoped
  cookie: the token then appears in no further request, and no log or referrer.
- **External STT by default.** Rejected (Q7, Q17).
- **Heirs or admins withdrawing after death.** Rejected as a default: it would give an authority the
  narrator never gave. A verified nominee the narrator chose is used instead.
- **Audio redaction in v1.** Deferred: v1 restricts the whole recording.
- **Stories as tradition entries.** The traditions archive (ADR-0026) has no consent, media or
  withdrawal model. The two are linked, not merged.

## Stress test
1. *A forwarded link is used by someone else.* The recording is "narrator not confirmed", private,
   heard by nobody except (if the §3a option allows) the asking member, and deleted if not confirmed
   in 30 days. The consent is the actual speaker's.
2. *The fragment token leaks through history or a screenshot.* It is single-use, exchanged once,
   expires in 7 days if unused, and can be revoked. The cookie it yields covers only that link.
3. *An elder speaks about a cousin's divorce.* The cousin, if tagged, raises the story's privacy and
   can ask for the passage to be hidden; the whole recording is restricted while the request is
   open.
4. *An elder wants a recording only for their grandchild.* With scope 4 they choose Selected
   members and name the grandchild; without it, it stays Only me. Admins see only the tree's
   aggregate usage, not the story, and promotion to admin changes nothing.
11. *An admin is asked to look into a complaint about a private story.* They can suspend it by the
   case reference without seeing it (§3b); it is then hidden from everyone but the narrator.
12. *The interviewer falls out with the narrator.* The narrator revokes the interviewer's access
   from the narrator page or their account; it ends at once (§3a, whichever option is chosen).
5. *Withdrawal arrives while a transcription is running.* The job is stopped at its next step,
   its output is discarded and access is revoked at once; erasure finishes within 24 hours. Accepted facts get tombstone citations, and facts that
   relied only on this story are flagged.
6. *The narrator has died; a son asks to delete.* Without a verified Legacy Nominee, he cannot. With
   one, the nominee can, after verification.
7. *A tree fills its 5 GB.* New uploads are refused before they start. Temporary parts and
   derivatives count, so the quota can't be bypassed through abandoned uploads.
8. *Nobody reviews a transcript.* The raw audio is still deleted 90 days after upload, unless the
   narrator gave archive consent; members are warned 14 days before.
9. *A browser records WebM with a video track.* It is refused. An audio-only WebM is stored as
   `audio/webm`.
10. *A child is recorded.* Only with a guardian's consent, and never through a link.

## 14. Decisions made and decisions still open (revision 3)

**Decided by the owner** (8 Nov 2026, first and second review rounds):
- Kept in its own PR, separate from the family calendar (1); self-hosted STT by default and
  external STT only with tree opt-in and scope 3 (2); pilot limits and a single 5 GB per-tree quota
  counting archives, temporary parts and derivatives (3, second-round 5); incomplete uploads expire
  after 24 hours and unused links after 7 days (4); raw-audio retention of 30 days after review and
  at most 90 days without archive consent (5); hide-passage restricts the whole recording, audio
  silencing deferred (6); Legacy Nominee only, never heirs or admins by default (7); legal and
  licensing reviews as §13 (8); engine choice deferred and manual transcription always available
  (9); consent sequence, written consent of record, optional consent clip, fragment-token exchange,
  withdrawal code, narrator attribution (10); immediate effect of withdrawal and the definition of
  accepted facts (11); privacy and threat model drafted after design review (12).
- Second round: verified withdrawals immediate, unverified ones within 7 days with suspension
  meanwhile (3); in-flight work handling (2); 5-minute playback URLs, 30-day deletion of
  unconfirmed recordings with a 5-day warning, 14-day warning before the 90-day maximum (3, 4);
  nominee verification needs identity and documented authority (6); **admins see only aggregate
  usage of private stories** (7), which revision 3 applies everywhere (§3, §6).
- Through ADR-0027 (accepted): a story uses the record audiences, the narrator's consent and tagged
  people are its ceiling, private audiences admit no role, grants belong to memberships, nothing is
  public in v1.

**Open product decisions** (for the owner):
1. **Interviewer access** (§3a): option A, B, C or D, its default, duration and what the
   interviewer sees afterwards; special handling for minors' and guardian-consented recordings.
2. **Non-member narrators** (§3): whether the narrator page opened by the withdrawal code is the
   narrator's way to own and manage a story, and how ownership moves when they join.
3. Whether **"Selected members"** needs its own consent scope, narrower than scope 4.
4. **Hide-passage decisions** when the narrator cannot or will not decide (§6).
5. **Abuse and legal reports** (§3b): who may suspend (family admin, platform reviewer or both) and
   the reason categories shown to them.
6. Whether a story's audience may be widened by the narrator's **nominee** (today: never; they may
   only narrow and withdraw).
7. Whether members who can play a shared story may also **download** the original (ADR-0027 §4);
   proposed default: off, the narrator may allow it.

**Open legal decisions** (§13 review; none blocks a design decision, all block external recording):
1. Consent statements and their translations; whether the consent clip is useful evidence.
2. Withdrawal: process, timings, and how an admin verifies a requester without the code (§9).
3. Whether 35 days of withdrawn media in Object-Locked backups is acceptable, and the restore
   re-apply procedure (§9; privacy model §15).
4. Third-party privacy of people mentioned and tagged, including the hide-passage process.
5. Minors and narrators unable to consent; guardian authority.
6. Legacy Nominee under DPDP Act Section 14: identity checks and who reviews evidence of death or
   incapacity.
7. The process for reports that require someone to hear a recording (§3b).
8. Which DPDP Act and Rules provisions are in force, and from when.

**Not decided here** (separate records): the STT engine and its licence (§8); audio silencing of
passages (deferred).
