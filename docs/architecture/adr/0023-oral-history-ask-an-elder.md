# ADR-0023: Oral history: "Ask an Elder", recorded stories, consent and transcripts

- Status: **Proposed** (revised after the owner's review of 8 Nov 2026; still awaiting design review) · Release: R5, phase I
- Relates to: ADR-0004 (document storage and the vault pipeline), ADR-0006 (privacy, field groups),
  ADR-0009 (OCR/AI output is a proposal), ADR-0011 (single-use invite links, "remove me"),
  ADR-0014 (pilot hosting and backups), ADR-0016 (notifications), ADR-0021 (proposals and family
  review), ADR-0026 (traditions archive, whose `story` entries are text); open questions Q7 (no
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
  - **5 GB of active oral-history media per tree.** This counts everything stored for the tree's
    stories: originals, consent clips, **temporary upload parts**, **derivatives** (transcripts,
    previews) and archived audio. An upload that would exceed the quota is refused before it
    starts, and the remaining space is shown.
- **Elders and low-end phones.** Controls are large, the screen is in the elder's language, and the
  recording can be reviewed before sending. Upload continues after a dropped connection. (Phase L
  will build on this.)

### 3. Visibility: private by default, sharing is a choice
Owner decision 10: a recording can stay private, and sharing it is never a condition of recording.

| Visibility | Who can see the story and play the audio |
|---|---|
| **Private** (default) | The narrator (if they have an account) and the interviewer. Tree admins see only that a private story exists and how much space it uses, for quota and moderation. They don't see its title, audio or transcript. |
| **Shared in the tree** | Members allowed by the story's privacy level (§6). Needs consent scope 4 (§4). |

A story is **never public** in v1, whatever the tree's public mode, as for the traditions archive.

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
  - A recording that arrives by link is held as **"narrator not confirmed"**. Until confirmed, only
    the asking member and tree admins can see that it exists, and only the asking member can play
    it, to identify the voice.
  - Confirmation names the narrator (a person in the tree, or a name only), and records who
    confirmed it, how ("I know this voice" or "the narrator confirmed with their account") and
    when.
  - **The consent stays the speaker's, whoever they turn out to be.** Changing the attribution
    doesn't transfer or widen it.
  - A recording that isn't confirmed within 30 days is deleted, and the asking member is warned
    5 days before.

### 6. Privacy of shared stories and of the people mentioned
- **The default privacy is the most restrictive** of three: the narrator's, every tagged living
  person's, and the tree default. A member may make it more restrictive, never less.
- **Facts drawn from a story** about another person become proposals governed by *that person's*
  privacy (ADR-0021).
- **A tagged living person** can ask to be untagged, or for a passage (a time range) to be hidden.
- **Hiding a passage** (owner decision 6):
  - While the request is open, the **whole original recording** is restricted to the narrator,
    the interviewer and tree admins, and the requested transcript span is hidden from everyone
    else.
  - Review decides between hiding the span for good, with the audio staying restricted, and
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
- or by asking a tree admin, who must act within 7 days (proposed);
- after the narrator's death, only a **verified Legacy Nominee** (§10).

**Immediately on withdrawal** (owner decision 11):
1. **Future processing stops.** Queued and running transcription jobs are cancelled, no external
   call is started, and no new proposal is created from the story.
2. **Media access is revoked.**
   - No new signed URL is issued.
   - Playback and download stop.
   - Existing signed URLs can't outlive their lifetime. This is at most 5 minutes for oral-history
     media, shorter than the vault default.
3. **The story disappears** from every member's view, except as "withdrawn".

**Within 24 hours (erasure job):**
- **Hard-delete:** the recording, the consent clip, the temporary upload parts, every derivative and
  every transcript version, and every unreviewed proposal from the story.
- **Kept, without content, as evidence:** the consent record (scopes, dates, statement version) and
  the withdrawal record. The audit log records the event without content.
- **Backups:** erased media leave backups as they rotate out, within the backup retention stated in
  the ADR-0014 runbook. The privacy model states that limit, and the legal review confirms it is
  acceptable.

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
- Members are warned 14 days before an unreviewed recording reaches 90 days.
- Reviewed transcripts stay at the story's visibility and privacy.

**Long-term archive** keeps the raw audio until withdrawal. It is allowed only with the narrator's
**separate archive consent** (scope 5), never by a member's or admin's choice.

**"Remove me"** (ADR-0011) covers a narrator's stories and a tagged person's mentions.

### 10. Legacy Nominee (owner decision 7)
- **Who names one.** A narrator may name a **Legacy Nominee**: one person who may withdraw the
  narrator's stories, or change their scopes, after the narrator's death or incapacity. This
  follows the nomination right in DPDP Act Section 14, subject to the legal review (§13).
- **How the nominee is recorded.** The nomination names the person and how they will be contacted.
  The nominee is **verified when they act**: an account with a verified email or phone, matched to
  the nomination, plus evidence of death or incapacity reviewed by a tree admin. Every step is
  audited.
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
   are prepared after the design review (owner decision 12).
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
1. *A forwarded link is used by someone else.* The recording is "narrator not confirmed", heard only
   by the asking member, and deleted if not confirmed in 30 days. The consent is the actual
   speaker's.
2. *The fragment token leaks through history or a screenshot.* It is single-use, exchanged once,
   expires in 7 days if unused, and can be revoked. The cookie it yields covers only that link.
3. *An elder speaks about a cousin's divorce.* The cousin, if tagged, raises the story's privacy and
   can ask for the passage to be hidden; the whole recording is restricted while the request is
   open.
4. *An elder wants a recording only for their grandchild.* It stays private (scope 4 not given);
   admins see only that it exists and its size.
5. *Withdrawal arrives while a transcription is running.* The job is cancelled and access revoked at
   once; erasure finishes within 24 hours. Accepted facts get tombstone citations, and facts that
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

## Open points for design review
1. The admin action time for withdrawal requests (proposed: 7 days); the erasure job time (24 hours);
   the signed-URL lifetime for oral-history media (5 minutes).
2. The deletion time for unconfirmed link recordings (30 days, with a warning 5 days before), and
   the warning time before the 90-day raw-audio limit (14 days).
3. Whether archived audio needs a quota of its own, separate from the 5 GB of active media.
4. How a Legacy Nominee's verification and the evidence of death or incapacity are checked in
   practice (subject to the legal review).
5. Whether admins should see that a private story exists at all, or only the tree's total usage.
