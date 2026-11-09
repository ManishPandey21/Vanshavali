# Data model (generated)

> Generated from the SQLAlchemy models by `uv run python -m app.cli.describe_schema`. **Do not edit by hand.**
> The Alembic migrations in `backend/alembic/versions/` are the deployable form of this schema; `tests/test_migrations.py` asserts that the two are identical.

Conventions: every tree-scoped table has `tree_id` and a `UNIQUE (tree_id, id)`; cross-entity foreign keys are composite `(tree_id, x_id) → target(tree_id, id)` so rows cannot reference another tree (ADR-0002). Genealogical dates are JSONB `GenealogicalDate` objects with derived `*_sort*` DATE columns (ADR-0003).

## Identity & access

### `app_user`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID | no | PK |
| `email` | VARCHAR(320) | no | unique |
| `password_hash` | VARCHAR(255) | no |  |
| `display_name` | VARCHAR(200) | no |  |
| `preferred_language` | VARCHAR(16) | no |  |
| `kinship_lang` | VARCHAR(16) | yes |  |
| `kinship_region` | VARCHAR(40) | yes |  |
| `is_active` | BOOLEAN | no |  |
| `is_system_admin` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `password_changed_at` | DATETIME | no |  |
| `mfa_secret_enc` | VARCHAR(400) | yes |  |
| `mfa_enabled_at` | DATETIME | yes |  |
| `email_verified_at` | DATETIME | yes |  |
| `must_change_password` | BOOLEAN | no |  |

### `user_session`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID | no | PK |
| `user_id` | UUID | no | → app_user |
| `token_hash` | VARCHAR(64) | no | unique |
| `created_at` | DATETIME | no |  |
| `last_seen_at` | DATETIME | no |  |
| `idle_expires_at` | DATETIME | no |  |
| `absolute_expires_at` | DATETIME | no |  |
| `revoked_at` | DATETIME | yes |  |
| `ip` | VARCHAR(64) | yes |  |
| `user_agent` | VARCHAR(400) | yes |  |

Constraints/indexes: `INDEX ix_user_session_user_active (user_id, revoked_at)`

### `tree`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID | no | PK |
| `name` | VARCHAR(200) | no |  |
| `description` | TEXT | yes |  |
| `slug` | VARCHAR(80) | no | unique |
| `public_mode` | enum(OFF, DECEASED_ONLY) | no |  |
| `default_person_privacy` | enum(PRIVATE_SELF, PRIVATE_TREE_ADMINS, FAMILY_BRANCH, TREE_MEMBERS, INVITED_RESEARCHER, PUBLIC_DECEASED_ONLY, CUSTOM) | no |  |
| `review_policy` | enum(off, structure, all) | no |  |
| `kinship_lang` | VARCHAR(16) | yes |  |
| `kinship_region` | VARCHAR(40) | yes |  |
| `created_by` | UUID | yes | → app_user |
| `deleted_at` | DATETIME | yes |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

### `tree_membership`

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no | → app_user |
| `roles` | ARRAY | no |  |
| `branch_id` | UUID | yes | → family_branch (composite, same tree) |
| `linked_person_id` | UUID | yes | → person (composite, same tree) |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `CHECK cardinality(roles) > 0`; `UNIQUE (tree_id, id)`; `UNIQUE (tree_id, user_id)`; `INDEX ix_tree_membership_tree_id (tree_id)`; `INDEX ix_tree_membership_user_id (user_id)`

### `tree_invitation`

| Column | Type | Null | Notes |
|---|---|---|---|
| `email` | VARCHAR(320) | no |  |
| `roles` | ARRAY | no |  |
| `branch_id` | UUID | yes | → family_branch (composite, same tree) |
| `token_hash` | VARCHAR(64) | no | unique |
| `expires_at` | DATETIME | no |  |
| `accepted_by` | UUID | yes | → app_user |
| `accepted_at` | DATETIME | yes |  |
| `revoked_at` | DATETIME | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_tree_invitation_tree_id (tree_id)`

### `access_grant`

| Column | Type | Null | Notes |
|---|---|---|---|
| `membership_id` | UUID | no | → tree_membership (composite, same tree) |
| `user_id` | UUID | no | → app_user |
| `resource_type` | enum(person, document, property, tradition) | no |  |
| `resource_id` | UUID | no |  |
| `permission` | enum(view, download) | no |  |
| `expires_at` | DATETIME | yes |  |
| `granted_at` | DATETIME | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, membership_id, resource_type, resource_id, permission)`; `UNIQUE (tree_id, id)`; `INDEX ix_access_grant_lookup (tree_id, resource_type, resource_id)`; `INDEX ix_access_grant_tree_id (tree_id)`

## Genealogy

### `person`

| Column | Type | Null | Notes |
|---|---|---|---|
| `profile_status` | enum(living, deceased, unknown) | no |  |
| `preferred_display_name` | VARCHAR(300) | no |  |
| `sex_at_birth` | enum(male, female, intersex, unknown) | yes |  |
| `gender_identity` | VARCHAR(100) | yes |  |
| `primary_language` | VARCHAR(16) | yes |  |
| `scripts_used` | ARRAY | no |  |
| `privacy_level` | enum(PRIVATE_SELF, PRIVATE_TREE_ADMINS, FAMILY_BRANCH, TREE_MEMBERS, INVITED_RESEARCHER, PUBLIC_DECEASED_ONLY, CUSTOM) | no |  |
| `field_privacy` | JSONB | no |  |
| `claimed_by_user_id` | UUID | yes | → app_user |
| `occupation` | VARCHAR(200) | yes |  |
| `notes` | TEXT | yes |  |
| `contact_info` | TEXT | yes |  |
| `residential_address` | TEXT | yes |  |
| `deleted_at` | DATETIME | yes |  |
| `merged_into_id` | UUID | yes | → person (composite, same tree) |
| `is_provisional` | BOOLEAN | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `revision` | INTEGER | no |  |
| `review_state` | enum(unreviewed, family_reviewed, contested) | no |  |
| `review_state_by` | UUID | yes |  |
| `review_state_at` | DATETIME | yes |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_person_tree_id (tree_id)`

### `name_record`

| Column | Type | Null | Notes |
|---|---|---|---|
| `person_id` | UUID | no | → person (composite, same tree) |
| `type` | enum(birth, married, alias, religious, professional, nickname, transliteration, historical) | no |  |
| `given_name` | VARCHAR(200) | yes |  |
| `middle_names` | VARCHAR(200) | yes |  |
| `patronymic` | VARCHAR(200) | yes |  |
| `matronymic` | VARCHAR(200) | yes |  |
| `surname` | VARCHAR(200) | yes |  |
| `family_house_name` | VARCHAR(200) | yes |  |
| `village_prefix` | VARCHAR(200) | yes |  |
| `honorific_prefix` | VARCHAR(80) | yes |  |
| `honorific_suffix` | VARCHAR(80) | yes |  |
| `full_name_as_recorded` | VARCHAR(500) | yes |  |
| `language` | VARCHAR(16) | yes |  |
| `script` | VARCHAR(20) | yes |  |
| `romanized_value` | VARCHAR(500) | yes |  |
| `date_range` | JSONB | yes |  |
| `is_preferred` | BOOLEAN | no |  |
| `search_text` | TEXT | no |  |
| `search_phonetic` | TEXT | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `evidence_status` | enum(USER_ASSERTION, FAMILY_RECOLLECTION, SOURCED, CORROBORATED, DISPUTED, SUPERSEDED, DISPROVEN) | no |  |
| `confidence` | enum(high, medium, low, unknown) | no |  |
| `prov_origin` | enum(manual, ocr, gedcom, api, calculation, imported_document) | no |  |
| `prov_algorithm` | VARCHAR(120) | yes |  |
| `prov_model_version` | VARCHAR(80) | yes |  |
| `prov_source_document_id` | UUID | yes |  |
| `prov_source_location` | TEXT | yes |  |
| `prov_extracted_at` | DATETIME | yes |  |
| `prov_confirmed_by` | UUID | yes |  |
| `prov_confirmed_at` | DATETIME | yes |  |
| `revision` | INTEGER | no |  |
| `review_state` | enum(unreviewed, family_reviewed, contested) | no |  |
| `review_state_by` | UUID | yes |  |
| `review_state_at` | DATETIME | yes |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_name_record_person (tree_id, person_id)`; `INDEX ix_name_record_search_trgm (search_text)`; `INDEX ix_name_record_tree_id (tree_id)`

### `relationship`

| Column | Type | Null | Notes |
|---|---|---|---|
| `person_a_id` | UUID | no | → person (composite, same tree) |
| `person_b_id` | UUID | no | → person (composite, same tree) |
| `type` | enum(biological_parent, adoptive_parent, step_parent, foster_parent, guardian, spouse, partner, divorced_spouse, …) | no |  |
| `subtype` | VARCHAR(80) | yes |  |
| `lineage` | enum(biological, legal, ritual, social) | yes |  |
| `union_id` | UUID | yes | → relationship (composite, same tree) |
| `start_date` | JSONB | yes |  |
| `end_date` | JSONB | yes |  |
| `union_order` | INTEGER | yes |  |
| `legal_status` | VARCHAR(80) | yes |  |
| `notes` | TEXT | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `evidence_status` | enum(USER_ASSERTION, FAMILY_RECOLLECTION, SOURCED, CORROBORATED, DISPUTED, SUPERSEDED, DISPROVEN) | no |  |
| `confidence` | enum(high, medium, low, unknown) | no |  |
| `prov_origin` | enum(manual, ocr, gedcom, api, calculation, imported_document) | no |  |
| `prov_algorithm` | VARCHAR(120) | yes |  |
| `prov_model_version` | VARCHAR(80) | yes |  |
| `prov_source_document_id` | UUID | yes |  |
| `prov_source_location` | TEXT | yes |  |
| `prov_extracted_at` | DATETIME | yes |  |
| `prov_confirmed_by` | UUID | yes |  |
| `prov_confirmed_at` | DATETIME | yes |  |
| `revision` | INTEGER | no |  |
| `review_state` | enum(unreviewed, family_reviewed, contested) | no |  |
| `review_state_by` | UUID | yes |  |
| `review_state_at` | DATETIME | yes |  |

Constraints/indexes: `CHECK person_a_id <> person_b_id`; `UNIQUE (tree_id, type, person_a_id, person_b_id)`; `UNIQUE (tree_id, id)`; `INDEX ix_relationship_a (tree_id, person_a_id, type)`; `INDEX ix_relationship_b (tree_id, person_b_id, type)`; `INDEX ix_relationship_tree_id (tree_id)`

### `event`

| Column | Type | Null | Notes |
|---|---|---|---|
| `type` | enum(birth, death, marriage, divorce, adoption, residence, migration, education, …) | no |  |
| `subtype` | VARCHAR(80) | yes |  |
| `date` | JSONB | yes |  |
| `date_sort_from` | DATE | yes |  |
| `date_sort_to` | DATE | yes |  |
| `time` | JSONB | yes |  |
| `timezone_id` | VARCHAR(64) | yes |  |
| `utc_offset_minutes` | INTEGER | yes |  |
| `place_id` | UUID | yes | → place (composite, same tree) |
| `place_as_recorded` | VARCHAR(500) | yes |  |
| `origin_place_id` | UUID | yes | → place (composite, same tree) |
| `origin_place_as_recorded` | VARCHAR(500) | yes |  |
| `latitude` | NUMERIC(9, 6) | yes |  |
| `longitude` | NUMERIC(9, 6) | yes |  |
| `reason` | TEXT | yes |  |
| `description` | TEXT | yes |  |
| `is_preferred` | BOOLEAN | no |  |
| `privacy_level` | enum(PRIVATE_SELF, PRIVATE_TREE_ADMINS, FAMILY_BRANCH, TREE_MEMBERS, INVITED_RESEARCHER, PUBLIC_DECEASED_ONLY, CUSTOM) | yes |  |
| `title` | VARCHAR(300) | yes |  |
| `category` | enum(birth, naming_ceremony, annaprashan, mundan, upanayana, initiation, education, graduation, …) | yes |  |
| `significance` | enum(standard, important, milestone) | no |  |
| `location_precision` | enum(exact, approximate, locality, district, state, country, unknown) | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `evidence_status` | enum(USER_ASSERTION, FAMILY_RECOLLECTION, SOURCED, CORROBORATED, DISPUTED, SUPERSEDED, DISPROVEN) | no |  |
| `confidence` | enum(high, medium, low, unknown) | no |  |
| `prov_origin` | enum(manual, ocr, gedcom, api, calculation, imported_document) | no |  |
| `prov_algorithm` | VARCHAR(120) | yes |  |
| `prov_model_version` | VARCHAR(80) | yes |  |
| `prov_source_document_id` | UUID | yes |  |
| `prov_source_location` | TEXT | yes |  |
| `prov_extracted_at` | DATETIME | yes |  |
| `prov_confirmed_by` | UUID | yes |  |
| `prov_confirmed_at` | DATETIME | yes |  |
| `revision` | INTEGER | no |  |
| `review_state` | enum(unreviewed, family_reviewed, contested) | no |  |
| `review_state_by` | UUID | yes |  |
| `review_state_at` | DATETIME | yes |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_event_tree_id (tree_id)`; `INDEX ix_event_type_sort (tree_id, type, date_sort_from)`

### `event_participant`

| Column | Type | Null | Notes |
|---|---|---|---|
| `event_id` | UUID | no | → event (composite, same tree) |
| `person_id` | UUID | no | → person (composite, same tree) |
| `role` | enum(principal, spouse, parent, witness, officiant, informant, other) | no |  |
| `role_detail` | VARCHAR(80) | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (event_id, person_id, role)`; `UNIQUE (tree_id, id)`; `INDEX ix_event_participant_person (tree_id, person_id)`; `INDEX ix_event_participant_tree_id (tree_id)`

### `place`

| Column | Type | Null | Notes |
|---|---|---|---|
| `canonical_name` | VARCHAR(300) | no |  |
| `local_names` | JSONB | no |  |
| `historical_names` | JSONB | no |  |
| `place_type` | enum(village, town, city, tehsil, district, state, country, temple, …) | no |  |
| `parent_place_id` | UUID | yes | → place (composite, same tree) |
| `latitude` | NUMERIC(9, 6) | yes |  |
| `longitude` | NUMERIC(9, 6) | yes |  |
| `geocoding_source` | VARCHAR(120) | yes |  |
| `date_validity` | JSONB | yes |  |
| `lgd_code` | VARCHAR(40) | yes |  |
| `lgd_level` | enum(state, district, sub_district, village, urban_body) | yes |  |
| `lgd_snapshot_id` | VARCHAR(7) | yes | → geo_snapshot |
| `search_text` | TEXT | no |  |
| `locality` | VARCHAR(200) | yes |  |
| `district` | VARCHAR(120) | yes |  |
| `state` | VARCHAR(120) | yes |  |
| `country` | VARCHAR(120) | yes |  |
| `map_label` | VARCHAR(200) | yes |  |
| `location_precision` | enum(exact, approximate, locality, district, state, country, unknown) | no |  |
| `geo_confidence` | enum(high, medium, low, unknown) | no |  |
| `geo_note` | TEXT | yes |  |
| `coordinate_privacy` | enum(PRIVATE_SELF, PRIVATE_TREE_ADMINS, FAMILY_BRANCH, TREE_MEMBERS, INVITED_RESEARCHER, PUBLIC_DECEASED_ONLY, CUSTOM) | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_place_search_trgm (search_text)`; `INDEX ix_place_tree_id (tree_id)`

### `merge_record`

| Column | Type | Null | Notes |
|---|---|---|---|
| `survivor_id` | UUID | no | → person (composite, same tree) |
| `merged_id` | UUID | no | → person (composite, same tree) |
| `reason` | TEXT | yes |  |
| `changes` | JSONB | no |  |
| `reverted_at` | DATETIME | yes |  |
| `reverted_by` | UUID | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_merge_record_tree_id (tree_id)`

### `relative_age_order`

| Column | Type | Null | Notes |
|---|---|---|---|
| `elder_person_id` | UUID | no | → person (composite, same tree) |
| `younger_person_id` | UUID | no | → person (composite, same tree) |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `CHECK elder_person_id <> younger_person_id`; `UNIQUE (tree_id, elder_person_id, younger_person_id)`; `UNIQUE (tree_id, id)`; `INDEX ix_relative_age_order_tree_id (tree_id)`

## Heritage & family structure

### `assertion`

| Column | Type | Null | Notes |
|---|---|---|---|
| `subject_type` | enum(person, branch) | no |  |
| `person_id` | UUID | yes | → person (composite, same tree) |
| `branch_id` | UUID | yes | → family_branch (composite, same tree) |
| `attribute` | VARCHAR(60) | no |  |
| `value_text` | TEXT | yes |  |
| `value_json` | JSONB | yes |  |
| `place_id` | UUID | yes | → place (composite, same tree) |
| `value_status` | enum(known, unknown, not_applicable, withheld) | no |  |
| `is_preferred` | BOOLEAN | no |  |
| `privacy_level` | enum(PRIVATE_SELF, PRIVATE_TREE_ADMINS, FAMILY_BRANCH, TREE_MEMBERS, INVITED_RESEARCHER, PUBLIC_DECEASED_ONLY, CUSTOM) | yes |  |
| `notes` | TEXT | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `evidence_status` | enum(USER_ASSERTION, FAMILY_RECOLLECTION, SOURCED, CORROBORATED, DISPUTED, SUPERSEDED, DISPROVEN) | no |  |
| `confidence` | enum(high, medium, low, unknown) | no |  |
| `prov_origin` | enum(manual, ocr, gedcom, api, calculation, imported_document) | no |  |
| `prov_algorithm` | VARCHAR(120) | yes |  |
| `prov_model_version` | VARCHAR(80) | yes |  |
| `prov_source_document_id` | UUID | yes |  |
| `prov_source_location` | TEXT | yes |  |
| `prov_extracted_at` | DATETIME | yes |  |
| `prov_confirmed_by` | UUID | yes |  |
| `prov_confirmed_at` | DATETIME | yes |  |
| `revision` | INTEGER | no |  |
| `review_state` | enum(unreviewed, family_reviewed, contested) | no |  |
| `review_state_by` | UUID | yes |  |
| `review_state_at` | DATETIME | yes |  |

Constraints/indexes: `CHECK (subject_type = 'person' AND person_id IS NOT NULL AND branch_id IS NULL) OR (subject_type = 'branch' AND branch_id IS NOT NULL AND person_id IS NULL)`; `UNIQUE (tree_id, id)`; `INDEX ix_assertion_subject (tree_id, person_id, branch_id, attribute)`; `INDEX ix_assertion_tree_id (tree_id)`

### `family_branch`

| Column | Type | Null | Notes |
|---|---|---|---|
| `name` | VARCHAR(200) | no |  |
| `description` | TEXT | yes |  |
| `founder_person_id` | UUID | yes | → person (composite, same tree) |
| `parent_branch_id` | UUID | yes | → family_branch (composite, same tree) |
| `descent_rule` | enum(patrilineal, matrilineal, bilateral, custom) | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_family_branch_tree_id (tree_id)`

### `branch_membership`

| Column | Type | Null | Notes |
|---|---|---|---|
| `branch_id` | UUID | no | → family_branch (composite, same tree) |
| `person_id` | UUID | no | → person (composite, same tree) |
| `basis` | VARCHAR(40) | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (branch_id, person_id)`; `UNIQUE (tree_id, id)`; `INDEX ix_branch_membership_person (tree_id, person_id)`; `INDEX ix_branch_membership_tree_id (tree_id)`

### `household`

| Column | Type | Null | Notes |
|---|---|---|---|
| `name` | VARCHAR(200) | no |  |
| `house_name` | VARCHAR(200) | yes |  |
| `place_id` | UUID | yes | → place (composite, same tree) |
| `branch_id` | UUID | yes | → family_branch (composite, same tree) |
| `start_date` | JSONB | yes |  |
| `end_date` | JSONB | yes |  |
| `notes` | TEXT | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_household_tree_id (tree_id)`

### `household_membership`

| Column | Type | Null | Notes |
|---|---|---|---|
| `household_id` | UUID | no | → household (composite, same tree) |
| `person_id` | UUID | no | → person (composite, same tree) |
| `role` | enum(head, karta, reference_person, member, dependent, other) | no |  |
| `start_date` | JSONB | yes |  |
| `end_date` | JSONB | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_household_membership_person (tree_id, person_id)`; `INDEX ix_household_membership_tree_id (tree_id)`

## Master data

### `vocabulary`

| Column | Type | Null | Notes |
|---|---|---|---|
| `key` | VARCHAR(40) | no | PK |
| `description` | TEXT | no |  |
| `version` | INTEGER | no |  |
| `source` | TEXT | yes |  |
| `licence` | VARCHAR(120) | yes |  |
| `allows_custom` | BOOLEAN | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

### `vocabulary_term`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID | no | PK |
| `vocabulary_key` | VARCHAR(40) | no | → vocabulary |
| `code` | VARCHAR(80) | no |  |
| `labels` | JSONB | no |  |
| `aliases` | ARRAY | no |  |
| `scope` | ARRAY | no |  |
| `parent_code` | VARCHAR(80) | yes |  |
| `attributes` | JSONB | no |  |
| `source_url` | TEXT | yes |  |
| `status` | enum(draft, reviewed, retired) | no |  |
| `sort_order` | INTEGER | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (vocabulary_key, code)`; `INDEX ix_vocabulary_term_vocabulary_key (vocabulary_key)`

### `tree_vocabulary_term`

| Column | Type | Null | Notes |
|---|---|---|---|
| `vocabulary_key` | VARCHAR(40) | no | → vocabulary |
| `code` | VARCHAR(90) | no |  |
| `label` | VARCHAR(200) | no |  |
| `aliases` | ARRAY | no |  |
| `offer_status` | enum(none, offered, accepted, declined) | no |  |
| `offered_by` | UUID | yes | → app_user |
| `offered_at` | DATETIME | yes |  |
| `offer_note` | VARCHAR(500) | yes |  |
| `offer_temple` | VARCHAR(200) | yes |  |
| `promoted_code` | VARCHAR(80) | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, vocabulary_key, code)`; `UNIQUE (tree_id, id)`; `INDEX ix_tree_vocabulary_term_tree_id (tree_id)`

## Cultural depth (ADR-0026)

### `kinship_override`

| Column | Type | Null | Notes |
|---|---|---|---|
| `pattern` | VARCHAR(200) | no |  |
| `lang` | VARCHAR(16) | no |  |
| `region` | VARCHAR(40) | yes |  |
| `word` | VARCHAR(120) | no |  |
| `branch_id` | UUID | yes | → family_branch (composite, same tree) |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `revision` | INTEGER | no |  |
| `review_state` | enum(unreviewed, family_reviewed, contested) | no |  |
| `review_state_by` | UUID | yes |  |
| `review_state_at` | DATETIME | yes |  |

Constraints/indexes: `UNIQUE (tree_id, pattern, lang, branch_id)`; `UNIQUE (tree_id, id)`; `INDEX ix_kinship_override_tree_id (tree_id)`

### `tradition_entry`

| Column | Type | Null | Notes |
|---|---|---|---|
| `kind` | enum(ritual_guide, custom, song, recipe, story, other) | no |  |
| `title` | VARCHAR(300) | no |  |
| `body` | TEXT | no |  |
| `language` | VARCHAR(16) | yes |  |
| `script` | VARCHAR(16) | yes |  |
| `branch_id` | UUID | yes | → family_branch (composite, same tree) |
| `privacy_level` | enum(ONLY_ME, SELECTED_MEMBERS, PRIVATE_SELF, PRIVATE_TREE_ADMINS, FAMILY_BRANCH, TREE_MEMBERS, INVITED_RESEARCHER, PUBLIC_DECEASED_ONLY, …) | no |  |
| `owner_membership_id` | UUID | yes | → tree_membership (composite, same tree) |
| `pending_owner_membership_id` | UUID | yes | → tree_membership (composite, same tree) |
| `search_text` | TEXT | no |  |
| `withdrawn_at` | DATETIME | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `revision` | INTEGER | no |  |
| `review_state` | enum(unreviewed, family_reviewed, contested) | no |  |
| `review_state_by` | UUID | yes |  |
| `review_state_at` | DATETIME | yes |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_tradition_entry_owner_membership_id (owner_membership_id)`; `INDEX ix_tradition_entry_search_trgm (search_text)`; `INDEX ix_tradition_entry_tree_id (tree_id)`; `INDEX ix_tradition_entry_tree_kind (tree_id, kind)`

### `tradition_link`

| Column | Type | Null | Notes |
|---|---|---|---|
| `tradition_id` | UUID | no | → tradition_entry (composite, same tree) |
| `target_type` | enum(person, event, place) | no |  |
| `target_id` | UUID | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tradition_id, target_type, target_id)`; `UNIQUE (tree_id, id)`; `INDEX ix_tradition_link_target (tree_id, target_type, target_id)`; `INDEX ix_tradition_link_tree_id (tree_id)`

## Geography reference (LGD, India Post)

### `geo_snapshot`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | VARCHAR(7) | no | PK |
| `status` | enum(staged, active, inactive) | no |  |
| `imports` | JSONB | no |  |
| `activated_at` | DATETIME | yes |  |
| `activated_by` | VARCHAR(120) | yes |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `INDEX uq_geo_snapshot_active (status) UNIQUE`

### `geo_unit`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID | no | PK |
| `level` | enum(state, district, sub_district, village, urban_body) | no |  |
| `lgd_code` | VARCHAR(20) | no |  |
| `parent_level` | enum(state, district, sub_district, village, urban_body) | yes |  |
| `parent_lgd_code` | VARCHAR(20) | yes |  |
| `state_code` | VARCHAR(20) | yes |  |
| `district_code` | VARCHAR(20) | yes |  |
| `sub_district_code` | VARCHAR(20) | yes |  |
| `name_en` | VARCHAR(200) | no |  |
| `name_local` | VARCHAR(200) | yes |  |
| `local_script` | VARCHAR(10) | yes |  |
| `category` | VARCHAR(80) | yes |  |
| `name_key` | TEXT | no |  |
| `local_key` | TEXT | no |  |
| `first_snapshot` | VARCHAR(7) | no | → geo_snapshot |
| `last_snapshot` | VARCHAR(7) | yes | → geo_snapshot |
| `successor_codes` | ARRAY | no |  |

Constraints/indexes: `UNIQUE (level, lgd_code, first_snapshot)`; `INDEX ix_geo_unit_code (level, lgd_code)`; `INDEX ix_geo_unit_current_district_code (district_code, level, name_en)`; `INDEX ix_geo_unit_current_local_key_prefix (local_key)`; `INDEX ix_geo_unit_current_name_key_prefix (name_key)`; `INDEX ix_geo_unit_current_state_code (state_code, level, name_en)`; `INDEX ix_geo_unit_current_sub_district_code (sub_district_code, level, name_en)`; `INDEX ix_geo_unit_local_trgm (local_key)`; `INDEX ix_geo_unit_name_trgm (name_key)`; `INDEX ix_geo_unit_state (state_code, level)`; `INDEX uq_geo_unit_current (level, lgd_code) UNIQUE`

### `geo_unit_alias`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID | no | PK |
| `level` | enum(state, district, sub_district, village, urban_body) | no |  |
| `lgd_code` | VARCHAR(20) | no |  |
| `name` | VARCHAR(200) | no |  |
| `script` | VARCHAR(10) | yes |  |
| `kind` | enum(alternative, historical, curated) | no |  |
| `source` | VARCHAR(200) | yes |  |
| `name_key` | TEXT | no |  |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (level, lgd_code, name_key)`; `INDEX ix_geo_unit_alias_prefix (name_key)`; `INDEX ix_geo_unit_alias_trgm (name_key)`; `INDEX ix_geo_unit_alias_unit (level, lgd_code)`

### `pincode_office`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID | no | PK |
| `pincode` | VARCHAR(6) | no |  |
| `office_name` | VARCHAR(200) | no |  |
| `office_key` | VARCHAR(200) | no |  |
| `office_type` | VARCHAR(20) | yes |  |
| `delivery` | BOOLEAN | yes |  |
| `division` | VARCHAR(120) | yes |  |
| `region` | VARCHAR(120) | yes |  |
| `circle` | VARCHAR(120) | yes |  |
| `district_name` | VARCHAR(120) | yes |  |
| `state_name` | VARCHAR(120) | yes |  |
| `taluk_name` | VARCHAR(120) | yes |  |
| `state_code` | VARCHAR(20) | yes |  |
| `district_code` | VARCHAR(20) | yes |  |
| `sub_district_code` | VARCHAR(20) | yes |  |
| `first_snapshot` | VARCHAR(7) | no | → geo_snapshot |
| `last_snapshot` | VARCHAR(7) | yes | → geo_snapshot |

Constraints/indexes: `UNIQUE (pincode, office_key, first_snapshot)`; `INDEX ix_pincode_office_current (pincode)`; `INDEX ix_pincode_office_pincode (pincode)`

## Review and history (ADR-0021)

### `change_proposal`

| Column | Type | Null | Notes |
|---|---|---|---|
| `proposer_id` | UUID | yes |  |
| `kind` | enum(change, challenge) | no |  |
| `status` | enum(draft, awaiting_review, accepted, rejected, withdrawn, stale) | no |  |
| `rationale` | TEXT | no |  |
| `person_id` | UUID | yes |  |
| `target_type` | enum(person, name, event, relationship, assertion, tradition, kinship_word) | yes |  |
| `target_id` | UUID | yes |  |
| `submitted_at` | DATETIME | yes |  |
| `decided_by` | UUID | yes |  |
| `decided_at` | DATETIME | yes |  |
| `decision_note` | TEXT | yes |  |
| `stale_reason` | TEXT | yes |  |
| `supersedes_id` | UUID | yes | → change_proposal (composite, same tree) |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_change_proposal_person (tree_id, person_id)`; `INDEX ix_change_proposal_status (tree_id, status, created_at)`; `INDEX ix_change_proposal_tree_id (tree_id)`

### `change_proposal_item`

| Column | Type | Null | Notes |
|---|---|---|---|
| `proposal_id` | UUID | no | → change_proposal (composite, same tree) |
| `position` | INTEGER | no |  |
| `target_type` | enum(person, name, event, relationship, assertion, tradition, kinship_word) | no |  |
| `op` | enum(create, update, delete) | no |  |
| `target_id` | UUID | yes |  |
| `person_id` | UUID | yes |  |
| `patch` | JSONB | no |  |
| `base_revisions` | JSONB | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_change_proposal_item_proposal (tree_id, proposal_id)`; `INDEX ix_change_proposal_item_target (tree_id, target_type, target_id)`; `INDEX ix_change_proposal_item_tree_id (tree_id)`

### `proposal_citation`

| Column | Type | Null | Notes |
|---|---|---|---|
| `proposal_id` | UUID | no | → change_proposal (composite, same tree) |
| `source_id` | UUID | no | → source (composite, same tree) |
| `note` | VARCHAR(500) | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_proposal_citation_proposal (tree_id, proposal_id)`; `INDEX ix_proposal_citation_tree_id (tree_id)`

### `proposal_comment`

| Column | Type | Null | Notes |
|---|---|---|---|
| `proposal_id` | UUID | no | → change_proposal (composite, same tree) |
| `author_id` | UUID | yes |  |
| `body` | TEXT | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_proposal_comment_proposal (tree_id, proposal_id, created_at)`; `INDEX ix_proposal_comment_tree_id (tree_id)`

### `record_revision`

| Column | Type | Null | Notes |
|---|---|---|---|
| `record_type` | enum(person, name, event, relationship, assertion, tradition, kinship_word) | no |  |
| `record_id` | UUID | no |  |
| `revision` | INTEGER | no |  |
| `op` | enum(create, update, delete) | no |  |
| `person_id` | UUID | yes |  |
| `person_b_id` | UUID | yes |  |
| `before` | JSONB | no |  |
| `after` | JSONB | no |  |
| `actor_id` | UUID | yes |  |
| `proposal_id` | UUID | yes |  |
| `reviewer_id` | UUID | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_record_revision_person (tree_id, person_id, created_at)`; `INDEX ix_record_revision_person_b (tree_id, person_b_id)`; `INDEX ix_record_revision_record (tree_id, record_type, record_id, revision)`; `INDEX ix_record_revision_tree_id (tree_id)`

### `user_notification`

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no |  |
| `kind` | enum(proposal_to_review, proposal_accepted, proposal_rejected, proposal_stale, challenge_opened, challenge_upheld, challenge_dismissed, proposal_comment, …) | no |  |
| `proposal_id` | UUID | yes |  |
| `subject_id` | UUID | yes |  |
| `actor_id` | UUID | yes |  |
| `read_at` | DATETIME | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_user_notification_tree_id (tree_id)`; `INDEX ix_user_notification_user (tree_id, user_id, read_at, created_at)`

## Evidence

### `source`

| Column | Type | Null | Notes |
|---|---|---|---|
| `source_type` | enum(civil_record, certificate, kundli, land_record, deed, court_record, census, traditional_register, …) | no |  |
| `title` | VARCHAR(400) | no |  |
| `issuing_authority` | VARCHAR(300) | yes |  |
| `repository` | VARCHAR(300) | yes |  |
| `record_number` | VARCHAR(200) | yes |  |
| `date` | JSONB | yes |  |
| `place_id` | UUID | yes | → place (composite, same tree) |
| `place_text` | VARCHAR(300) | yes |  |
| `url` | VARCHAR(1000) | yes |  |
| `document_id` | UUID | yes | → document (composite, same tree) |
| `transcription` | TEXT | yes |  |
| `translation` | TEXT | yes |  |
| `notes` | TEXT | yes |  |
| `tradition` | JSONB | yes |  |
| `privacy_level` | enum(PRIVATE_SELF, PRIVATE_TREE_ADMINS, FAMILY_BRANCH, TREE_MEMBERS, INVITED_RESEARCHER, PUBLIC_DECEASED_ONLY, CUSTOM) | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_source_tree_id (tree_id)`

### `citation`

| Column | Type | Null | Notes |
|---|---|---|---|
| `source_id` | UUID | no | → source (composite, same tree) |
| `target_type` | enum(person, name_record, event, relationship, assertion, astrology_profile, property, land_parcel, …) | no |  |
| `target_id` | UUID | no |  |
| `page_or_image` | VARCHAR(200) | yes |  |
| `text_excerpt` | TEXT | yes |  |
| `accessed_date` | DATE | yes |  |
| `confidence` | enum(high, medium, low, unknown) | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_citation_target (tree_id, target_type, target_id)`; `INDEX ix_citation_tree_id (tree_id)`

## Documents & extraction

### `document`

| Column | Type | Null | Notes |
|---|---|---|---|
| `category` | enum(photo, birth_certificate, death_certificate, marriage_record, kundli, letter, diary, family_register, …) | no |  |
| `storage_class` | enum(STANDARD, VAULT) | no |  |
| `title` | VARCHAR(400) | no |  |
| `description` | TEXT | yes |  |
| `original_filename` | VARCHAR(400) | no |  |
| `mime_type` | VARCHAR(120) | no |  |
| `size_bytes` | BIGINT | no |  |
| `checksum_sha256` | VARCHAR(64) | no |  |
| `storage_key` | VARCHAR(500) | no |  |
| `encryption_key_id` | VARCHAR(40) | no |  |
| `document_date` | JSONB | yes |  |
| `language` | VARCHAR(16) | yes |  |
| `script` | VARCHAR(20) | yes |  |
| `issuing_authority` | VARCHAR(300) | yes |  |
| `privacy_level` | enum(ONLY_ME, SELECTED_MEMBERS, PRIVATE_SELF, PRIVATE_TREE_ADMINS, FAMILY_BRANCH, TREE_MEMBERS, INVITED_RESEARCHER, PUBLIC_DECEASED_ONLY, …) | no |  |
| `owner_membership_id` | UUID | yes | → tree_membership (composite, same tree) |
| `pending_owner_membership_id` | UUID | yes | → tree_membership (composite, same tree) |
| `audience_branch_id` | UUID | yes | → family_branch (composite, same tree) |
| `allow_download` | BOOLEAN | no |  |
| `retention_policy` | VARCHAR(40) | no |  |
| `scan_status` | enum(pending, clean, infected, error) | no |  |
| `scan_engine` | VARCHAR(80) | yes |  |
| `page_count` | INTEGER | yes |  |
| `ocr_status` | enum(not_requested, pending, running, completed, failed, skipped) | no |  |
| `ocr_engine` | VARCHAR(120) | yes |  |
| `ocr_error` | TEXT | yes |  |
| `extraction_status` | enum(not_requested, pending, running, completed, failed, skipped) | no |  |
| `preview_status` | enum(not_requested, pending, running, completed, failed, skipped) | no |  |
| `metadata_version` | INTEGER | no |  |
| `deleted_at` | DATETIME | yes |  |
| `deleted_by` | UUID | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_document_owner_membership_id (owner_membership_id)`; `INDEX ix_document_tree_checksum (tree_id, checksum_sha256)`; `INDEX ix_document_tree_id (tree_id)`

### `document_metadata_version`

| Column | Type | Null | Notes |
|---|---|---|---|
| `document_id` | UUID | no | → document (composite, same tree) |
| `version` | INTEGER | no |  |
| `snapshot` | JSONB | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (document_id, version)`; `UNIQUE (tree_id, id)`; `INDEX ix_document_metadata_version_tree_id (tree_id)`

### `document_derivative`

| Column | Type | Null | Notes |
|---|---|---|---|
| `document_id` | UUID | no | → document (composite, same tree) |
| `kind` | enum(preview, thumbnail, ocr_text) | no |  |
| `page` | INTEGER | no |  |
| `storage_key` | VARCHAR(500) | no |  |
| `mime_type` | VARCHAR(120) | no |  |
| `size_bytes` | BIGINT | no |  |
| `engine` | VARCHAR(120) | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (document_id, kind, page)`; `UNIQUE (tree_id, id)`; `INDEX ix_document_derivative_tree_id (tree_id)`

### `document_link`

| Column | Type | Null | Notes |
|---|---|---|---|
| `document_id` | UUID | no | → document (composite, same tree) |
| `target_type` | enum(person, event, relationship, place, property, land_parcel, property_event, source, …) | no |  |
| `target_id` | UUID | no |  |
| `note` | VARCHAR(300) | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (document_id, target_type, target_id)`; `UNIQUE (tree_id, id)`; `INDEX ix_document_link_target (tree_id, target_type, target_id)`; `INDEX ix_document_link_tree_id (tree_id)`

### `extraction_proposal`

| Column | Type | Null | Notes |
|---|---|---|---|
| `document_id` | UUID | no | → document (composite, same tree) |
| `subject_person_id` | UUID | yes | → person (composite, same tree) |
| `subject_property_id` | UUID | yes | → property (composite, same tree) |
| `extractor` | VARCHAR(80) | no |  |
| `extractor_version` | VARCHAR(40) | no |  |
| `engine` | VARCHAR(120) | yes |  |
| `field` | VARCHAR(80) | no |  |
| `label` | VARCHAR(200) | no |  |
| `proposed_value` | JSONB | no |  |
| `display_value` | TEXT | no |  |
| `confidence` | DOUBLE | no |  |
| `source_location` | JSONB | yes |  |
| `status` | enum(pending, accepted, edited, rejected) | no |  |
| `final_value` | JSONB | yes |  |
| `reviewed_by` | UUID | yes |  |
| `reviewed_at` | DATETIME | yes |  |
| `review_note` | TEXT | yes |  |
| `applied_target_type` | VARCHAR(40) | yes |  |
| `applied_target_id` | UUID | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_extraction_proposal_doc (tree_id, document_id, status)`; `INDEX ix_extraction_proposal_tree_id (tree_id)`

### `event_media`

| Column | Type | Null | Notes |
|---|---|---|---|
| `event_id` | UUID | no | → event (composite, same tree) |
| `document_id` | UUID | no | → document (composite, same tree) |
| `caption` | VARCHAR(500) | yes |  |
| `taken_date` | JSONB | yes |  |
| `is_cover` | BOOLEAN | no |  |
| `sort_order` | INTEGER | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (event_id, document_id)`; `UNIQUE (tree_id, id)`; `INDEX ix_event_media_event (tree_id, event_id, sort_order)`; `INDEX ix_event_media_tree_id (tree_id)`; `INDEX uq_event_media_cover (event_id) UNIQUE`

## Reminders & notifications

### `notification_preference`

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no | → app_user |
| `enabled` | BOOLEAN | no |  |
| `channels` | ARRAY | no |  |
| `timezone` | VARCHAR(64) | no |  |
| `send_hour` | SMALLINT | no |  |
| `default_lead_days` | ARRAY | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, user_id)`; `UNIQUE (tree_id, id)`; `INDEX ix_notification_preference_tree_id (tree_id)`; `INDEX ix_notification_preference_user_id (user_id)`

### `event_reminder`

| Column | Type | Null | Notes |
|---|---|---|---|
| `event_id` | UUID | no | → event (composite, same tree) |
| `user_id` | UUID | no | → app_user |
| `kind` | enum(birthday, anniversary, memorial, one_time, custom) | no |  |
| `recurrence` | enum(none, annual) | no |  |
| `lead_days` | ARRAY | no |  |
| `channels` | ARRAY | no |  |
| `note` | VARCHAR(300) | yes |  |
| `active` | BOOLEAN | no |  |
| `next_fire_at` | DATETIME | yes |  |
| `last_fired_at` | DATETIME | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (event_id, user_id)`; `UNIQUE (tree_id, id)`; `INDEX ix_event_reminder_due (tree_id, active, next_fire_at)`; `INDEX ix_event_reminder_tree_id (tree_id)`; `INDEX ix_event_reminder_user_id (user_id)`

### `notification_delivery`

| Column | Type | Null | Notes |
|---|---|---|---|
| `reminder_id` | UUID | yes | → event_reminder (composite, same tree) |
| `event_id` | UUID | yes | → event (composite, same tree) |
| `user_id` | UUID | no | → app_user |
| `channel` | enum(email, sms, whatsapp) | no |  |
| `occurrence_date` | DATE | no |  |
| `lead_days` | INTEGER | no |  |
| `scheduled_for` | DATETIME | no |  |
| `status` | enum(pending, sent, failed, retrying, cancelled) | no |  |
| `attempts` | INTEGER | no |  |
| `next_attempt_at` | DATETIME | yes |  |
| `last_error_code` | VARCHAR(80) | yes |  |
| `provider` | VARCHAR(40) | yes |  |
| `provider_message_id` | VARCHAR(120) | yes |  |
| `sent_at` | DATETIME | yes |  |
| `cancelled_reason` | VARCHAR(80) | yes |  |
| `is_test` | BOOLEAN | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (reminder_id, channel, occurrence_date, lead_days)`; `UNIQUE (tree_id, id)`; `INDEX ix_notification_delivery_retry (tree_id, status, next_attempt_at)`; `INDEX ix_notification_delivery_tree_id (tree_id)`; `INDEX ix_notification_delivery_user (tree_id, user_id, scheduled_for)`; `INDEX ix_notification_delivery_user_id (user_id)`

### `notification_contact`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID | no | PK |
| `user_id` | UUID | no | → app_user |
| `channel` | enum(email, sms, whatsapp) | no |  |
| `address_enc` | VARCHAR(400) | no |  |
| `address_hint` | VARCHAR(40) | no |  |
| `verified_at` | DATETIME | yes |  |
| `verify_code_hash` | VARCHAR(64) | yes |  |
| `verify_expires_at` | DATETIME | yes |  |
| `verify_attempts` | INTEGER | no |  |
| `created_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (user_id, channel)`; `INDEX ix_notification_contact_user_id (user_id)`

## Visualization & exports

### `chart_preset`

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no | → app_user |
| `name` | VARCHAR(120) | no |  |
| `chart_type` | enum(fan, graph, pedigree, family_tree, lifespan, event_timeline, map) | no |  |
| `settings` | JSONB | no |  |
| `shared` | BOOLEAN | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_chart_preset_owner (tree_id, user_id, chart_type)`; `INDEX ix_chart_preset_tree_id (tree_id)`; `INDEX ix_chart_preset_user_id (user_id)`

### `render_job`

| Column | Type | Null | Notes |
|---|---|---|---|
| `requested_by` | UUID | yes | → app_user |
| `chart_type` | enum(fan, graph, pedigree, family_tree, lifespan, event_timeline, map) | no |  |
| `output` | enum(poster, mp4) | no |  |
| `status` | enum(queued, running, succeeded, failed, cancelled) | no |  |
| `progress` | SMALLINT | no |  |
| `settings` | JSONB | no |  |
| `payload_storage_key` | VARCHAR(500) | yes |  |
| `payload_sha256` | VARCHAR(64) | yes |  |
| `renderer` | VARCHAR(80) | yes |  |
| `attempts` | INTEGER | no |  |
| `error_code` | VARCHAR(80) | yes |  |
| `error_message` | VARCHAR(300) | yes |  |
| `started_at` | DATETIME | yes |  |
| `finished_at` | DATETIME | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_render_job_requested_by (requested_by)`; `INDEX ix_render_job_requester (tree_id, requested_by, created_at)`; `INDEX ix_render_job_tree_id (tree_id)`

### `render_artifact`

| Column | Type | Null | Notes |
|---|---|---|---|
| `job_id` | UUID | no | → render_job (composite, same tree) |
| `kind` | enum(poster_png, video_mp4) | no |  |
| `storage_key` | VARCHAR(500) | no |  |
| `mime_type` | VARCHAR(120) | no |  |
| `size_bytes` | BIGINT | no |  |
| `checksum_sha256` | VARCHAR(64) | no |  |
| `width` | INTEGER | yes |  |
| `height` | INTEGER | yes |  |
| `duration_s` | FLOAT | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_render_artifact_job_id (job_id)`; `INDEX ix_render_artifact_tree_id (tree_id)`

## Astrology

### `astrology_profile`

| Column | Type | Null | Notes |
|---|---|---|---|
| `person_id` | UUID | no | → person (composite, same tree) |
| `birth_event_id` | UUID | yes | → event (composite, same tree) |
| `document_id` | UUID | yes | → document (composite, same tree) |
| `provenance_kind` | enum(entered, uploaded_chart, calculated, imported) | no |  |
| `nakshatra` | VARCHAR(60) | yes |  |
| `nakshatra_pada` | INTEGER | yes |  |
| `rashi` | VARCHAR(60) | yes |  |
| `lagna` | VARCHAR(60) | yes |  |
| `tithi` | VARCHAR(60) | yes |  |
| `paksha` | VARCHAR(20) | yes |  |
| `yoga` | VARCHAR(60) | yes |  |
| `karana` | VARCHAR(60) | yes |  |
| `lunar_month` | VARCHAR(60) | yes |  |
| `ayanamsha` | VARCHAR(60) | yes |  |
| `calculation_system` | VARCHAR(120) | yes |  |
| `ephemeris_version` | VARCHAR(80) | yes |  |
| `chart_birth_date` | JSONB | yes |  |
| `chart_birth_time` | JSONB | yes |  |
| `chart_birth_place` | VARCHAR(300) | yes |  |
| `place_latitude` | NUMERIC(9, 6) | yes |  |
| `place_longitude` | NUMERIC(9, 6) | yes |  |
| `timezone_id` | VARCHAR(64) | yes |  |
| `utc_offset_minutes` | INTEGER | yes |  |
| `calculation_timestamp` | DATETIME | yes |  |
| `is_preferred` | BOOLEAN | no |  |
| `privacy_level` | enum(PRIVATE_SELF, PRIVATE_TREE_ADMINS, FAMILY_BRANCH, TREE_MEMBERS, INVITED_RESEARCHER, PUBLIC_DECEASED_ONLY, CUSTOM) | no |  |
| `notes` | TEXT | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `evidence_status` | enum(USER_ASSERTION, FAMILY_RECOLLECTION, SOURCED, CORROBORATED, DISPUTED, SUPERSEDED, DISPROVEN) | no |  |
| `confidence` | enum(high, medium, low, unknown) | no |  |
| `prov_origin` | enum(manual, ocr, gedcom, api, calculation, imported_document) | no |  |
| `prov_algorithm` | VARCHAR(120) | yes |  |
| `prov_model_version` | VARCHAR(80) | yes |  |
| `prov_source_document_id` | UUID | yes |  |
| `prov_source_location` | TEXT | yes |  |
| `prov_extracted_at` | DATETIME | yes |  |
| `prov_confirmed_by` | UUID | yes |  |
| `prov_confirmed_at` | DATETIME | yes |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_astrology_profile_person (tree_id, person_id)`; `INDEX ix_astrology_profile_tree_id (tree_id)`

## Property

### `property`

| Column | Type | Null | Notes |
|---|---|---|---|
| `property_type` | enum(agricultural_land, residential_land, house, commercial, ancestral_home, estate, other) | no |  |
| `classification` | enum(ancestral, self_acquired, joint_family, unknown) | no |  |
| `display_name` | VARCHAR(300) | no |  |
| `description` | TEXT | yes |  |
| `place_id` | UUID | yes | → place (composite, same tree) |
| `address_text` | TEXT | yes |  |
| `current_status` | VARCHAR(120) | yes |  |
| `privacy_level` | enum(PRIVATE_SELF, PRIVATE_TREE_ADMINS, FAMILY_BRANCH, TREE_MEMBERS, INVITED_RESEARCHER, PUBLIC_DECEASED_ONLY, CUSTOM) | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_property_tree_id (tree_id)`

### `land_parcel`

| Column | Type | Null | Notes |
|---|---|---|---|
| `property_id` | UUID | no | → property (composite, same tree) |
| `parent_parcel_id` | UUID | yes | → land_parcel (composite, same tree) |
| `place_id` | UUID | yes | → place (composite, same tree) |
| `state_or_ut` | VARCHAR(100) | yes |  |
| `district` | VARCHAR(100) | yes |  |
| `tehsil_taluk` | VARCHAR(100) | yes |  |
| `village` | VARCHAR(150) | yes |  |
| `revenue_village_code` | VARCHAR(60) | yes |  |
| `survey_number` | VARCHAR(60) | yes |  |
| `khasra_or_gata_number` | VARCHAR(60) | yes |  |
| `khata_number` | VARCHAR(60) | yes |  |
| `khatauni_number` | VARCHAR(60) | yes |  |
| `patta_number` | VARCHAR(60) | yes |  |
| `plot_number` | VARCHAR(60) | yes |  |
| `subdivision_number` | VARCHAR(60) | yes |  |
| `ulpin` | VARCHAR(20) | yes |  |
| `area` | NUMERIC(18, 4) | yes |  |
| `area_unit` | VARCHAR(40) | yes |  |
| `land_use` | VARCHAR(100) | yes |  |
| `latitude` | NUMERIC(9, 6) | yes |  |
| `longitude` | NUMERIC(9, 6) | yes |  |
| `cadastral_map_reference` | VARCHAR(200) | yes |  |
| `state_portal_reference` | VARCHAR(300) | yes |  |
| `extra_identifiers` | JSONB | no |  |
| `notes` | TEXT | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `prov_origin` | enum(manual, ocr, gedcom, api, calculation, imported_document) | no |  |
| `prov_algorithm` | VARCHAR(120) | yes |  |
| `prov_model_version` | VARCHAR(80) | yes |  |
| `prov_source_document_id` | UUID | yes |  |
| `prov_source_location` | TEXT | yes |  |
| `prov_extracted_at` | DATETIME | yes |  |
| `prov_confirmed_by` | UUID | yes |  |
| `prov_confirmed_at` | DATETIME | yes |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_land_parcel_property (tree_id, property_id)`; `INDEX ix_land_parcel_tree_id (tree_id)`

### `property_interest`

| Column | Type | Null | Notes |
|---|---|---|---|
| `property_id` | UUID | no | → property (composite, same tree) |
| `parcel_id` | UUID | yes | → land_parcel (composite, same tree) |
| `holder_type` | enum(person, family_branch, trust, entity, unknown) | no |  |
| `holder_person_id` | UUID | yes | → person (composite, same tree) |
| `holder_branch_id` | UUID | yes | → family_branch (composite, same tree) |
| `holder_name` | VARCHAR(300) | yes |  |
| `interest_type` | enum(owner, co_owner, tenant, cultivator, life_interest, claimant, beneficiary, mortgagee, …) | no |  |
| `share_numerator` | BIGINT | no |  |
| `share_denominator` | BIGINT | no |  |
| `valid_from` | JSONB | yes |  |
| `valid_from_sort` | DATE | yes |  |
| `valid_to` | JSONB | yes |  |
| `valid_to_sort` | DATE | yes |  |
| `status` | enum(asserted, documented, disputed, relinquished, transferred, unknown) | no |  |
| `created_by_event_id` | UUID | yes | → property_event (composite, same tree) |
| `ended_by_event_id` | UUID | yes | → property_event (composite, same tree) |
| `notes` | TEXT | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `evidence_status` | enum(USER_ASSERTION, FAMILY_RECOLLECTION, SOURCED, CORROBORATED, DISPUTED, SUPERSEDED, DISPROVEN) | no |  |
| `confidence` | enum(high, medium, low, unknown) | no |  |
| `prov_origin` | enum(manual, ocr, gedcom, api, calculation, imported_document) | no |  |
| `prov_algorithm` | VARCHAR(120) | yes |  |
| `prov_model_version` | VARCHAR(80) | yes |  |
| `prov_source_document_id` | UUID | yes |  |
| `prov_source_location` | TEXT | yes |  |
| `prov_extracted_at` | DATETIME | yes |  |
| `prov_confirmed_by` | UUID | yes |  |
| `prov_confirmed_at` | DATETIME | yes |  |

Constraints/indexes: `CHECK share_numerator <= share_denominator`; `CHECK share_denominator > 0 AND share_numerator >= 0`; `UNIQUE (tree_id, id)`; `INDEX ix_property_interest_holder (tree_id, holder_person_id)`; `INDEX ix_property_interest_property (tree_id, property_id)`; `INDEX ix_property_interest_tree_id (tree_id)`

### `property_event`

| Column | Type | Null | Notes |
|---|---|---|---|
| `property_id` | UUID | no | → property (composite, same tree) |
| `type` | enum(purchase, inheritance, succession, partition, family_settlement, relinquishment, gift, sale, …) | no |  |
| `date` | JSONB | yes |  |
| `date_sort_from` | DATE | yes |  |
| `description` | TEXT | yes |  |
| `registration_number` | VARCHAR(120) | yes |  |
| `registration_date` | JSONB | yes |  |
| `mutation_number` | VARCHAR(120) | yes |  |
| `consideration` | VARCHAR(200) | yes |  |
| `related_event_id` | UUID | yes | → event (composite, same tree) |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |
| `evidence_status` | enum(USER_ASSERTION, FAMILY_RECOLLECTION, SOURCED, CORROBORATED, DISPUTED, SUPERSEDED, DISPROVEN) | no |  |
| `confidence` | enum(high, medium, low, unknown) | no |  |
| `prov_origin` | enum(manual, ocr, gedcom, api, calculation, imported_document) | no |  |
| `prov_algorithm` | VARCHAR(120) | yes |  |
| `prov_model_version` | VARCHAR(80) | yes |  |
| `prov_source_document_id` | UUID | yes |  |
| `prov_source_location` | TEXT | yes |  |
| `prov_extracted_at` | DATETIME | yes |  |
| `prov_confirmed_by` | UUID | yes |  |
| `prov_confirmed_at` | DATETIME | yes |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_property_event_property (tree_id, property_id, date_sort_from)`; `INDEX ix_property_event_tree_id (tree_id)`

### `property_event_parcel`

| Column | Type | Null | Notes |
|---|---|---|---|
| `property_event_id` | UUID | no | → property_event (composite, same tree) |
| `parcel_id` | UUID | no | → land_parcel (composite, same tree) |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (property_event_id, parcel_id)`; `UNIQUE (tree_id, id)`; `INDEX ix_property_event_parcel_tree_id (tree_id)`

## Privacy & consent

### `consent_record`

| Column | Type | Null | Notes |
|---|---|---|---|
| `subject_person_id` | UUID | no | → person (composite, same tree) |
| `granted_by_user_id` | UUID | yes | → app_user |
| `granted_by_name` | VARCHAR(200) | no |  |
| `authority_basis` | enum(self, parent_guardian, legal_representative, tree_admin_attestation) | no |  |
| `purpose` | VARCHAR(300) | no |  |
| `data_categories` | ARRAY | no |  |
| `granted_at` | DATETIME | no |  |
| `expires_at` | DATETIME | yes |  |
| `withdrawn_at` | DATETIME | yes |  |
| `evidence_document_id` | UUID | yes | → document (composite, same tree) |
| `notes` | TEXT | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_consent_record_tree_id (tree_id)`; `INDEX ix_consent_subject (tree_id, subject_person_id)`

### `profile_claim`

| Column | Type | Null | Notes |
|---|---|---|---|
| `person_id` | UUID | no | → person (composite, same tree) |
| `user_id` | UUID | no | → app_user |
| `kind` | enum(claim, removal) | no |  |
| `status` | enum(requested, approved, rejected, withdrawn) | no |  |
| `message` | TEXT | yes |  |
| `reviewed_by` | UUID | yes |  |
| `reviewed_at` | DATETIME | yes |  |
| `review_note` | TEXT | yes |  |
| `invite_id` | UUID | yes | → profile_claim_invite (composite, same tree) |
| `consent_version` | VARCHAR(40) | yes |  |
| `consent_language` | VARCHAR(10) | yes |  |
| `consent_sha256` | VARCHAR(64) | yes |  |
| `consent_at` | DATETIME | yes |  |
| `restore_privacy_level` | enum(PRIVATE_SELF, PRIVATE_TREE_ADMINS, FAMILY_BRANCH, TREE_MEMBERS, INVITED_RESEARCHER, PUBLIC_DECEASED_ONLY, CUSTOM) | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_profile_claim_tree_id (tree_id)`

### `profile_claim_invite`

| Column | Type | Null | Notes |
|---|---|---|---|
| `person_id` | UUID | no | → person (composite, same tree) |
| `token_hash` | VARCHAR(64) | no |  |
| `offered_role` | enum(OWNER, FAMILY_ADMIN, BRANCH_ADMIN, CONTRIBUTOR, RESEARCHER, VIEWER, DOCUMENT_CUSTODIAN, PROPERTY_CUSTODIAN, …) | no |  |
| `branch_id` | UUID | yes | → family_branch (composite, same tree) |
| `expires_at` | DATETIME | no |  |
| `used_by` | UUID | yes | → app_user |
| `used_at` | DATETIME | yes |  |
| `revoked_at` | DATETIME | yes |  |
| `declined_at` | DATETIME | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_profile_claim_invite_person (tree_id, person_id)`; `INDEX ix_profile_claim_invite_tree_id (tree_id)`

### `family_data_attestation`

| Column | Type | Null | Notes |
|---|---|---|---|
| `user_id` | UUID | no | → app_user |
| `statement_version` | VARCHAR(40) | no |  |
| `language` | VARCHAR(10) | no |  |
| `statement_sha256` | VARCHAR(64) | no |  |
| `accepted_at` | DATETIME | no |  |
| `ip` | VARCHAR(64) | yes |  |
| `user_agent` | VARCHAR(400) | yes |  |
| `withdrawn_at` | DATETIME | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_family_data_attestation_tree_id (tree_id)`; `INDEX ix_family_data_attestation_user (tree_id, user_id)`

## Interchange

### `import_job`

| Column | Type | Null | Notes |
|---|---|---|---|
| `format` | VARCHAR(20) | no |  |
| `status` | enum(pending, running, ready, committed, completed, failed, cancelled) | no |  |
| `document_id` | UUID | yes | → document (composite, same tree) |
| `original_filename` | VARCHAR(400) | yes |  |
| `original_storage_key` | VARCHAR(500) | yes |  |
| `detected_version` | VARCHAR(20) | yes |  |
| `detected_encoding` | VARCHAR(40) | yes |  |
| `report` | JSONB | no |  |
| `staged` | JSONB | no |  |
| `decisions` | JSONB | no |  |
| `error` | TEXT | yes |  |
| `committed_at` | DATETIME | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_import_job_tree_id (tree_id)`

### `export_job`

| Column | Type | Null | Notes |
|---|---|---|---|
| `kind` | VARCHAR(20) | no |  |
| `options` | JSONB | no |  |
| `status` | enum(pending, running, ready, committed, completed, failed, cancelled) | no |  |
| `storage_key` | VARCHAR(500) | yes |  |
| `filename` | VARCHAR(300) | yes |  |
| `size_bytes` | BIGINT | yes |  |
| `checksum_sha256` | VARCHAR(64) | yes |  |
| `error` | TEXT | yes |  |
| `completed_at` | DATETIME | yes |  |
| `expires_at` | DATETIME | yes |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_export_job_tree_id (tree_id)`

### `gedcom_extension`

| Column | Type | Null | Notes |
|---|---|---|---|
| `person_id` | UUID | yes | → person (composite, same tree) |
| `import_job_id` | UUID | yes | → import_job (composite, same tree) |
| `record_type` | VARCHAR(20) | no |  |
| `tag` | VARCHAR(80) | no |  |
| `uri` | VARCHAR(500) | yes |  |
| `payload` | TEXT | no |  |
| `id` | UUID | no | PK |
| `tree_id` | UUID | no | → tree |
| `created_by` | UUID | yes | → app_user |
| `updated_by` | UUID | yes | → app_user |
| `created_at` | DATETIME | no |  |
| `updated_at` | DATETIME | no |  |

Constraints/indexes: `UNIQUE (tree_id, id)`; `INDEX ix_gedcom_extension_person (tree_id, person_id)`; `INDEX ix_gedcom_extension_tree_id (tree_id)`

## Audit

### `audit_event`

| Column | Type | Null | Notes |
|---|---|---|---|
| `id` | UUID | no | PK |
| `tree_id` | UUID | yes |  |
| `actor_user_id` | UUID | yes |  |
| `action` | VARCHAR(80) | no |  |
| `target_type` | VARCHAR(40) | yes |  |
| `target_id` | UUID | yes |  |
| `summary` | TEXT | yes |  |
| `details` | JSONB | no |  |
| `ip` | VARCHAR(64) | yes |  |
| `user_agent` | VARCHAR(400) | yes |  |
| `created_at` | DATETIME | no |  |

Constraints/indexes: `INDEX ix_audit_event_target (target_type, target_id)`; `INDEX ix_audit_event_tree_time (tree_id, created_at)`

## Other

- `admin_nomination`
- `auth_token`
- `external_identity`
