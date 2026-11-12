-- Tradition ownership inventory (ADR-0027 increment 2; PR #51 follow-up).
--
-- READ ONLY. Counts only: no ids, titles, bodies, names or e-mail addresses leave the database.
-- Run it only with the owner's approval, as the schema owner, inside a read-only transaction:
--     BEGIN READ ONLY; \i tradition-ownership-inventory.sql ROLLBACK;
-- It is a proposal for review; it has never been run against pilot or production data.
-- Categories (see docs/operations/tradition-ownership-recovery.md for what each one means):
--   orphaned                         no owner (the owner's membership was deleted)
--   orphaned_author_is_member_again  no owner, and the author's account has a newer membership
--   owner_membership_newer_than_entry owner is the author, through a membership created after the
--                                    entry: an author re-invited before 8d2e6b4f1a37 was backfilled
--   owner_is_not_author              ownership was transferred (or backfilled after a re-upgrade)
--   selected_members                 at Selected members
--   with_grants                      has at least one tradition grant
--   legacy_private_self              still PRIVATE_SELF (should be 0 after f2a9c4e7d815)
--   legacy_custom                    CUSTOM (tree admins and grantees read it)
--   offer_on_orphan                  a pending ownership offer on an orphan (lapsed since f2a9c4e7d815)
WITH e AS (
    SELECT t.tree_id, t.privacy_level, t.created_at, t.created_by, t.owner_membership_id,
           t.pending_owner_membership_id, t.id,
           o.user_id AS owner_user, o.created_at AS owner_since
    FROM tradition_entry t
    LEFT JOIN tree_membership o ON o.tree_id = t.tree_id AND o.id = t.owner_membership_id
    WHERE t.withdrawn_at IS NULL
)
SELECT category, privacy_level, count(*) AS entries
FROM (
    SELECT 'orphaned' AS category, privacy_level FROM e WHERE owner_membership_id IS NULL
    UNION ALL
    SELECT 'orphaned_author_is_member_again', privacy_level FROM e
     WHERE owner_membership_id IS NULL AND created_by IS NOT NULL
       AND EXISTS (SELECT 1 FROM tree_membership m WHERE m.tree_id = e.tree_id AND m.user_id = e.created_by)
    UNION ALL
    SELECT 'owner_membership_newer_than_entry', privacy_level FROM e
     WHERE owner_user = created_by AND owner_since > created_at
    UNION ALL
    SELECT 'owner_is_not_author', privacy_level FROM e
     WHERE owner_membership_id IS NOT NULL AND created_by IS DISTINCT FROM owner_user
    UNION ALL
    SELECT 'selected_members', privacy_level FROM e WHERE privacy_level = 'SELECTED_MEMBERS'
    UNION ALL
    SELECT 'with_grants', privacy_level FROM e
     WHERE EXISTS (SELECT 1 FROM access_grant g
                    WHERE g.tree_id = e.tree_id AND g.resource_type = 'tradition' AND g.resource_id = e.id)
    UNION ALL
    SELECT 'legacy_private_self', privacy_level FROM e WHERE privacy_level = 'PRIVATE_SELF'
    UNION ALL
    SELECT 'legacy_custom', privacy_level FROM e WHERE privacy_level = 'CUSTOM'
    UNION ALL
    SELECT 'offer_on_orphan', privacy_level FROM e
     WHERE owner_membership_id IS NULL AND pending_owner_membership_id IS NOT NULL
) AS c
GROUP BY category, privacy_level
ORDER BY category, privacy_level
