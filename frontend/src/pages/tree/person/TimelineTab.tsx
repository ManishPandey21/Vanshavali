import type { PersonOut } from "../../../api/types";
import { StoryTimeline } from "../../../components/viz/StoryTimeline";

/** Lifetime event timeline (storytelling view). Events are managed on the Events tab. */
export function TimelineTab({ person }: { person: PersonOut }) {
  return <StoryTimeline personId={person.id} />;
}
