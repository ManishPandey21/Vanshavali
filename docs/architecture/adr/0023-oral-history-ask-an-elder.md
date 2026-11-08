# ADR-0023: Oral history: "Ask an Elder", recorded stories, consent and transcripts

- Status: **Proposed** · Date: 2026-11-08 · Release: R5, phase I
- Relates to: ADR-0004 (document storage and the vault pipeline), ADR-0006 (privacy, field groups),
  ADR-0009 (OCR/AI output is a proposal), ADR-0011 (single-use invite links, "remove me"),
  ADR-0021 (proposals and family review), ADR-0026 (traditions archive, whose `story` entries are
  text), ADR-0016 (notifications); open questions Q7 (no external AI by default) and **Q17** (voice
  processing), which gates this phase
- Plan: [india-master-data-and-smart-forms-plan.md](../india-master-data-and-smart-forms-plan.md),
  release R5, phase I

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
   and revocable (the DPDP Act 2023 applies to the family's data). Withdrawal must really erase.
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
  - title and narrator (a person in the tree, or just a name, for example a neighbour);
  - interviewer (a member), recording date and place;
  - language and script;
  - privacy level, status and the consent record.
- Status runs `draft → consented → recorded → transcribed → reviewed`, with `withdrawn` possible at
  any point.
- **Media are vault documents** (ADR-0004), with source type `oral_history`, linked to the story.
  Uploads never bypass the vault pipeline: validate → malware scan → immutable storage.
- **`story_mention`** tags a person, optionally to a time range. It drives privacy (§5) and lets a
  tagged person ask to be untagged or for a passage to be hidden.
- A tradition entry (ADR-0026) can link to an oral story. Written stories are not duplicated.

### 2. Recording and upload
- **In-browser recording** uses MediaRecorder, preferring Opus (WebM or Ogg) and falling back to
  MP4/AAC on Safari. Existing voice notes can also be uploaded: a WhatsApp `.opus` file is an Ogg
  file.
- **Audio-only WebM is classified as `audio/webm`.** The sniffer checks that the file has no video
  track. A file whose container claims audio but which holds video is refused.
- **Resumable upload:**
  - fixed-size chunks, each with its SHA-256;
  - assembled on the server, then the whole file goes through the vault pipeline;
  - an incomplete upload expires after 24 hours (proposed).
- **Limits (proposed):** 60 minutes and 200 MB per recording, both configurable, plus a per-tree
  storage quota.
- **Elders and low-end phones.** Controls are large, the screen is in the elder's language, and the
  recording can be reviewed before sending. Upload continues after a dropped connection. (Phase L
  will build on this.)

### 3. Consent before anything is recorded
- **A `recording_consent` record** captures:
  - who consents (the narrator, or a guardian for a narrator who cannot);
  - how (a short spoken statement recorded as its own clip, plus a tick-box);
  - the versioned statement text in the narrator's language (`consent/statements`);
  - the time and the person who collected it.
- **Separate scopes**, each a yes or no:
  1. record;
  2. transcribe on our own servers;
  3. transcribe with an external service (§6), off unless explicitly given;
  4. share within the tree at the story's privacy level;
  5. keep the raw audio beyond the default retention ("archive").
- **No consent, no recording.** The recorder does not start until scopes 1 and 4 are given. The
  server refuses a story upload without a consent record.
- **Minors** (under 18): recorded only with a guardian's consent and never through an "Ask an Elder"
  link. A narrator unable to consent needs a guardian, and the record names the guardian.

### 4. "Ask an Elder" link
- **Built on the ADR-0011 link infrastructure.** It is a single-use bearer token in the URL fragment
  and expires (7 days, proposed). It is single-purpose: one question, written (and optionally
  spoken) by the asking member, in the elder's language.
- **The holder gets no account and no tree access.** The page shows only:
  - the question and the consent statement;
  - the recorder;
  - a review-before-send step.

  After sending, the link is spent. The elder gets a **withdrawal code** (§7) on screen, and by SMS
  or WhatsApp if a number was given.
- **Forwarded links.** A recording that arrives by link is held as "narrator not confirmed". It
  reaches the tree only after the asking member confirms who spoke. Until then only that member and
  tree admins can hear it.
- Creation is rate-limited per member, and so is use per token. Every event is audited with the
  token hash, never the token.

### 5. Privacy
- **A story is never public** in v1, whatever the tree's public mode. This matches the traditions
  archive (ADR-0026).
- **The default privacy is the most restrictive** of three: the narrator's, every tagged living
  person's, and the tree default. A member may make it more restrictive, never less.
- **Mentions of other living relatives:**
  - facts drawn from a story about another person become proposals governed by *that person's*
    privacy (ADR-0021);
  - a tagged relative can ask to be untagged, or for a passage (a time range) to be hidden.
- **Hiding a passage (v1).** It hides that span of the transcript and limits the **audio** to the
  narrator, the interviewer and tree admins. Editing the audio to silence a span is a later step.
- **Access and logging.** Media are served through short-lived signed URLs (ADR-0004), and every
  playback and download is audited. Logs never contain transcript text or audio.

### 6. Transcripts and speech-to-text (answers Q17)
- **Self-hosted by default.** A background job (RQ) runs an open-source engine on our own servers.
  Candidates, by their PyPI-declared code licences on 8 Nov 2026: faster-whisper (MIT), on
  CTranslate2 (MIT), using Whisper models; or Vosk (Apache-2.0).
- **The engine is chosen only after:**
  - a licence review of the **model weights**, which is separate from the code licence;
  - a benchmark on Hindi and the pilot's other languages, using recordings made with consent for
    that purpose;
  - a resource check on the pilot VM (ADR-0014).

  If no engine is good enough for a language, it gets no machine transcript; manual transcription
  remains available.
- **External services** (for example the Government of India's BHASHINI) are used only when both
  hold:
  1. a tree admin has opted in for the tree, with informed wording;
  2. the narrator's consent includes scope 3.

  Whatever the provider's terms promise about retention and training is recorded, and the call is
  audited. Without both, nothing leaves our servers.
- **A transcript is machine output.** It is stored as a versioned derivative with the engine, the
  model, the version and the language, and marked "machine transcript" until a person corrects it.
  Corrections create new versions.
- **Facts become `extraction_proposal`s** (ADR-0009), each citing the story and a time range. They
  are reviewed like any proposal and never applied directly.

### 7. Withdrawal, retention and erasure
- **Who can withdraw:** the narrator (or guardian), at any time. They can do it:
  - with the withdrawal code;
  - from their own account, if they have one;
  - by asking a tree admin, who must act within a set time (proposed: 7 days).
- **What withdrawal does:**
  - **hard-deletes** the recording, the consent clip, every derivative and transcript version, and
    every unreviewed proposal from the story;
  - accepted facts keep a citation reading "oral history (withdrawn)", with no media and no text.

  The consent and withdrawal records stay, without content, as evidence. The audit log records the
  event without content.
- **Backups:** erased media leave backups as they rotate out. The privacy model states the maximum
  time; it is the backup retention from ADR-0014's runbook.
- **Retention without archive consent:** raw audio is kept until the transcript is reviewed plus 90
  days (the Q17 default), then deleted. The reviewed transcript stays at the story's privacy level.
  With archive consent (scope 5), the audio is kept until withdrawal.
- **"Remove me"** (ADR-0011) covers a narrator's stories and a tagged person's mentions.
- **A narrator who has died.** Consent already given stays in force. Whether family members may
  later withdraw it, and who among them, is open point 4.

### 8. API (all under `/api/v1`, typed, authorised)
- `POST|GET /trees/{t}/stories`, `GET|PATCH|DELETE /trees/{t}/stories/{id}`
- `POST /trees/{t}/stories/{id}/consent` (scopes, statement version, consent clip upload)
- `POST /trees/{t}/stories/{id}/uploads` (start), `PUT …/uploads/{u}/parts/{n}`, `POST …/uploads/{u}/complete`
- `POST|GET /trees/{t}/stories/{id}/mentions`, `POST …/mentions/{m}/hide-request`
- `POST /trees/{t}/stories/{id}/transcribe` (engine per tree policy and consent),
  `GET|PUT …/transcript` (versions)
- `POST /trees/{t}/ask-elder` (create a link), `DELETE /trees/{t}/ask-elder/{id}` (revoke)
- `GET|POST /ask-elder/{token}…` (no session: the question, consent, upload, send)
- `POST /stories/withdraw` (withdrawal code, rate-limited)

### 9. Gates
Code starts only after **this ADR is accepted, Q17 is decided, and the privacy model (new §15) and
threat model (new entries) are written**, as for every security-sensitive change. External STT
stays off until its own opt-in rules and wording are reviewed. The STT engine choice is a later,
separate decision (§6).

## Consequences
- Families can record elders, in the app or through a link, with consent captured first and
  withdrawal that really erases.
- The vault, the proposals system and the invite links are reused. The new parts are the story
  model, the consent scopes, resumable upload and the STT job.
- Storage grows with audio, so quotas and the retention default matter.
- Machine transcripts in Indian languages will often be poor. They are labelled, correctable, and
  never data until reviewed.
- Self-hosted STT costs CPU on the pilot VM. If it is too slow, transcription queues or is turned
  off for a language; it never silently falls back to an external service.

## Alternatives considered
- **Upload only (no in-app recording).** Simpler, but elders without a smartphone helper are left
  out, and consent could not be captured in the same flow.
- **External STT by default.** Better quality for some languages, but voice data leaves our servers
  without the person's specific choice (against Q7 and Q17).
- **Keep all audio forever.** Families may want this, so it is the archive scope (scope 5), opted
  into by the narrator. It is not the default.
- **Stories as tradition entries.** The traditions archive (ADR-0026) is text-first and has no
  consent, media or withdrawal model. The two are linked, not merged.
- **Audio redaction in v1.** Silencing a passage means re-encoding and verifying the output. v1
  restricts the whole recording instead; redaction comes later.

## Stress test
1. *A forwarded "Ask an Elder" link is used by someone else.* The recording is held as "narrator not
   confirmed" and is visible only to the asking member and admins until confirmed. The link is
   single-use and expires.
2. *An elder speaks about a cousin's divorce.* The cousin, if tagged, raises the story's privacy and
   can ask for the passage to be hidden. Facts about the cousin are proposals under the cousin's
   privacy.
3. *The elder withdraws a year later.* Media, transcripts and unreviewed proposals are erased.
   Accepted facts keep a content-free citation. Backups age out within the stated time.
4. *A browser records WebM with a video track.* It is refused as "not an audio recording". An
   audio-only WebM is stored as `audio/webm`.
5. *The upload drops on 2G.* The upload resumes from the last confirmed chunk, and the session
   expires after 24 hours.
6. *STT mishears a name.* The transcript is marked machine output, so nothing changes in the tree
   until a reviewed proposal is accepted.
7. *A tree admin turns on external STT.* Recordings whose consent lacks scope 3 are still never
   sent.
8. *A child is recorded.* Only with a guardian's consent, and never through a link.
9. *The narrator has died.* Earlier consent stands. Who may withdraw on their behalf is open
   point 4.

## Open points for the reviewer
1. **Q17:** confirm self-hosted by default, external only by per-tree opt-in plus narrator consent,
   and the 90-day raw-audio default.
2. Limits: 60 minutes and 200 MB per recording, the 24-hour upload expiry, the 7-day link expiry,
   and the per-tree storage quota (a value is needed).
3. Hiding a passage in v1 restricts the whole recording; audio redaction comes later. Acceptable?
4. Withdrawal after the narrator's death: nobody, the tree admins, or named heirs?
5. A legal review of the consent wording and the withdrawal and erasure flow under the DPDP Act
   2023, including backups.
6. The STT engine and its model weights: a licence review and an accuracy benchmark before it is
   enabled.
