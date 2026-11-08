import { describe, expect, it, vi } from "vitest";
import { act, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { Route, Routes } from "react-router-dom";
import { jsonResponse, renderWithProviders } from "../../test/utils";
import { ApiError } from "../../api/client";
import { orPropose, reviewBus } from "../../lib/reviewBus";
import { ChallengeButton, DuplicatePanel, NotificationBell, ProposeChangeHost, ReviewBadge, formatValue } from "./ReviewParts";
import { ReviewPage } from "../../pages/tree/ReviewPage";

type Call = { url: string; init?: RequestInit };

function mockFetch(route: (url: string, init?: RequestInit) => Response | undefined) {
  const calls: Call[] = [];
  vi.stubGlobal(
    "fetch",
    vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      calls.push({ url, init });
      return Promise.resolve(route(url, init) ?? jsonResponse({ error: { code: "not_found", message: "Not found" } }, 404));
    }),
  );
  return calls;
}

const body = (c: Call) => JSON.parse(String(c.init?.body ?? "{}"));

describe("review_required routing", () => {
  it("offers a refused direct edit as a proposal, and rethrows", async () => {
    const seen: unknown[] = [];
    const off = reviewBus.subscribe((i) => seen.push(i));
    const item = { target_type: "name" as const, op: "update" as const, target_id: "n1", patch: { given_name: "Kamala" } };
    await expect(orPropose(item, () => Promise.reject(new ApiError(409, "review_required", "needs review")))).rejects.toThrow();
    await expect(orPropose(item, () => Promise.reject(new ApiError(409, "conflict", "other")))).rejects.toThrow();
    off();
    expect(seen).toEqual([item]); // only review_required is offered
  });

  it("sends the change for review with a rationale, never without one", async () => {
    const calls = mockFetch((url, init) => (url.endsWith("/proposals") && init?.method === "POST" ? jsonResponse({ id: "p1", status: "awaiting_review" }, 201) : undefined));
    renderWithProviders(<ProposeChangeHost treeId="tree-1" />);
    act(() => reviewBus.offer({ target_type: "name", op: "update", target_id: "n1", patch: { given_name: "Kamala" } }));
    const dialog = await screen.findByRole("dialog", { name: "Send this change for review" });
    expect(dialog).toHaveTextContent("Given name: Kamala");
    const send = screen.getByRole("button", { name: "Send for review" });
    expect(send).toBeDisabled();
    await userEvent.type(screen.getByLabelText(/Why this change is right/), "School certificate");
    await userEvent.click(send);
    await screen.findByText(/Sent for review/);
    const post = calls.find((c) => c.url.endsWith("/trees/tree-1/proposals"))!;
    expect(body(post)).toEqual({ rationale: "School certificate", items: [{ target_type: "name", op: "update", target_id: "n1", patch: { given_name: "Kamala" } }], submit: true });
  });
});

describe("challenges and review state", () => {
  it("shows family review as a label, separate from evidence", () => {
    const { rerender } = renderWithProviders(<ReviewBadge state="family_reviewed" />);
    expect(screen.getByText("Family-confirmed")).toBeInTheDocument();
    rerender(<ReviewBadge state="unreviewed" />);
    expect(screen.queryByText("Family-confirmed")).toBeNull();
  });

  it("sends a challenge with a reason", async () => {
    const calls = mockFetch((url) => (url.endsWith("/challenges") ? jsonResponse({ id: "c1" }, 201) : undefined));
    renderWithProviders(<ChallengeButton treeId="tree-1" targetType="relationship" targetId="r1" label="Ramesh → Suresh" />);
    await userEvent.click(screen.getByRole("button", { name: "Challenge: Ramesh → Suresh" }));
    await userEvent.type(screen.getByLabelText(/Why it may be wrong/), "He was adopted");
    await userEvent.click(screen.getByRole("button", { name: "Send challenge" }));
    await screen.findByText(/Your challenge was sent/);
    expect(body(calls.find((c) => c.url.endsWith("/challenges"))!)).toEqual({ target_type: "relationship", target_id: "r1", rationale: "He was adopted" });
  });
});

describe("notifications", () => {
  it("shows the unread count and the text built by the server, and marks read", async () => {
    const calls = mockFetch((url) => {
      if (url.endsWith("/inbox/read")) return jsonResponse({ items: [], unread: 0 });
      if (url.includes("/inbox"))
        return jsonResponse({ items: [{ id: "n1", kind: "proposal_to_review", proposal_id: "p1", text: "Ravi proposed 1 change(s) to Kamla for review.", created_at: "2026-11-07T00:00:00Z", read: false }], unread: 1 });
      return undefined;
    });
    renderWithProviders(<NotificationBell treeId="tree-1" />);
    const bell = await screen.findByRole("button", { name: "Notifications, 1 unread" });
    await userEvent.click(bell);
    const link = screen.getByRole("link", { name: /Ravi proposed 1 change/ });
    expect(link).toHaveAttribute("href", "/t/tree-1/review/p1");
    await userEvent.click(link);
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/inbox/read") && body(c).ids[0] === "n1")).toBe(true));
  });
});

describe("duplicates at entry", () => {
  it("suggests people already in the tree with reasons, and lets the user decide", async () => {
    mockFetch((url) =>
      url.endsWith("/duplicates/check")
        ? jsonResponse({ candidates: [{ person: { id: "k1", display_name: "Kamla Sharma", profile_status: "deceased" }, score: 0.9, likely: true, reasons: ["birth year 1932", "same parent"] }] })
        : undefined,
    );
    const onUse = vi.fn();
    renderWithProviders(<DuplicatePanel treeId="tree-1" check={{ names: [{ given_name: "Kamala", surname: "Sharma" }], birth_year: 1931 }} onUse={onUse} />);
    expect(await screen.findByText("Already in the tree?", {}, { timeout: 3000 })).toBeInTheDocument();
    expect(screen.getByText("birth year 1932 · same parent")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("button", { name: "Use this person" }));
    expect(onUse).toHaveBeenCalledWith({ id: "k1", display_name: "Kamla Sharma" });
    await userEvent.click(screen.getByRole("button", { name: "This is someone else" }));
    expect(screen.queryByText("Already in the tree?")).toBeNull();
  });
});

const proposal = (over: Record<string, unknown> = {}) => ({
  id: "p1",
  kind: "change",
  status: "awaiting_review",
  rationale: "The deed says so",
  proposer: { id: "u2", display_name: "Ravi" },
  person_id: "s1",
  person_label: "Suresh Sharma",
  created_at: "2026-11-07T00:00:00Z",
  submitted_at: "2026-11-07T00:00:00Z",
  items: [
    {
      id: "i1",
      target_type: "relationship",
      op: "update",
      target_id: "r1",
      person_id: "s1",
      label: "Change relationship",
      outdated: false,
      changes: [
        { field: "notes", current: null, proposed: "adopted", hidden: false },
        { field: "date", current: null, proposed: null, hidden: true },
      ],
    },
  ],
  comments: [],
  can_decide: true,
  cannot_decide_reason: null,
  can_withdraw: false,
  can_rebase: false,
  ...over,
});

describe("Review page", () => {
  const renderDetail = () =>
    renderWithProviders(
      <Routes>
        <Route path="/t/:treeId/review/:proposalId" element={<ReviewPage />} />
      </Routes>,
      { route: "/t/tree-1/review/p1" },
    );

  it("shows today's values against the proposal, hides what the reader may not see, and approves", async () => {
    const calls = mockFetch((url) => {
      if (url.endsWith("/approve")) return jsonResponse(proposal({ status: "accepted", can_decide: false }));
      if (url.endsWith("/proposals/p1")) return jsonResponse(proposal());
      return undefined;
    });
    renderDetail();
    expect(await screen.findByRole("heading", { level: 1, name: "1 change to Suresh Sharma" })).toBeInTheDocument();
    expect(screen.getByText("adopted")).toBeInTheDocument();
    expect(screen.getByText("Hidden from you")).toBeInTheDocument();
    // not accepting needs a note
    expect(screen.getByRole("button", { name: "Do not accept" })).toBeDisabled();
    await userEvent.click(screen.getByRole("button", { name: "Approve" }));
    await waitFor(() => expect(calls.some((c) => c.url.endsWith("/proposals/p1/approve"))).toBe(true));
  });

  it("explains a stale proposal and why a reader cannot decide", async () => {
    let stale = false;
    mockFetch((url) => {
      if (url.endsWith("/approve")) {
        stale = true;
        return jsonResponse({ error: { code: "proposal_stale", message: "changed" } }, 409);
      }
      if (url.endsWith("/proposals/p1")) return jsonResponse(stale ? proposal({ status: "stale", can_decide: false, stale_reason: "A relationship this change depends on was changed." }) : proposal());
      return undefined;
    });
    renderDetail();
    await userEvent.click(await screen.findByRole("button", { name: "Approve" }));
    expect(await screen.findByText(/Nothing was applied/)).toBeInTheDocument();
  });

  it("formats dates and values as families read them", () => {
    expect(formatValue({ year: 1932, month: 5, day: 6, precision: "exact" })).toBe("6/5/1932");
    expect(formatValue(null)).toBe("—");
    expect(formatValue(["a", "b"])).toBe("a, b");
  });
});
