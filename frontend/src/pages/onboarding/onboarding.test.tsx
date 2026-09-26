import { afterEach, describe, expect, it, vi } from "vitest";
import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "../../i18n";
import { jsonResponse, makeTree, renderWithProviders } from "../../test/utils";
import { inviteMessage, whatsappShareUrl } from "../../components/consent/ClaimInviteShare";
import { WelcomePage } from "./WelcomePage";
import { ClaimInvitePage, tokenFromHash } from "./ClaimInvitePage";

const FAMILY_TEXT = "I agree to add my family members' names to this private tree, and I confirm I have their permission to do so.";
const CLAIM_TEXT = "This profile is about me. I agree that this private family tree may keep my name.";
const TOKEN = "AbCdEfGhIjKlMnOpQrStUvWxYz0123456789_-abcde";
const me = { id: "u1", email: "asha@example.com", display_name: "Asha Iyer", preferred_language: "en" };

type Handler = (url: string, init: RequestInit | undefined) => Response | undefined;

/** Fetch mock that routes by method + path and records every call. */
function routed(handler: Handler) {
  return vi.fn((input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    const res = handler(url, init);
    if (!res) throw new Error(`unexpected request ${init?.method ?? "GET"} ${url}`);
    return Promise.resolve(res);
  });
}

const posts = (f: ReturnType<typeof routed>) => f.mock.calls.filter(([, init]) => init?.method === "POST").map(([u, init]) => ({ url: String(u), body: JSON.parse(String(init?.body ?? "{}")) }));

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("WhatsApp invite message", () => {
  it("contains only the link, with no phone number in the share URL", () => {
    const url = `https://vanshavali.example/claim#${TOKEN}`;
    const msg = inviteMessage(i18n.t.bind(i18n), url);
    expect(msg).toContain(url);
    const share = whatsappShareUrl(msg);
    expect(share.startsWith("https://wa.me/?text=")).toBe(true);
    expect(decodeURIComponent(share.slice("https://wa.me/?text=".length))).toBe(msg);
    // the fragment survives encoding (so the token still never reaches a server)
    expect(share).toContain(encodeURIComponent(`#${TOKEN}`));
  });
});

describe("tokenFromHash", () => {
  it("accepts a url-safe token and rejects anything else", () => {
    expect(tokenFromHash(`#${TOKEN}`)).toBe(TOKEN);
    expect(tokenFromHash("#short")).toBe("");
    expect(tokenFromHash("#<script>alert(1)</script>xxxxxxxxxxxx")).toBe("");
    expect(tokenFromHash("")).toBe("");
  });
});

describe("WelcomePage", () => {
  const tree = makeTree({ id: "t1", name: "Iyer parivar" });

  async function reachFamilyStep(fetchMock: ReturnType<typeof routed>) {
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<WelcomePage />, { tree: null });
    await userEvent.click(await screen.findByRole("button", { name: "I understand, continue" }));
    await userEvent.type(screen.getByLabelText(/Tree name/), "Iyer parivar");
    await userEvent.click(screen.getByRole("button", { name: "Create my private tree" }));
    return screen.findByRole("checkbox", { name: FAMILY_TEXT });
  }

  const handler: Handler = (url, init) => {
    const method = init?.method ?? "GET";
    if (url.includes("/auth/me")) return jsonResponse(me);
    if (url.includes("/consent-statements/family_data")) return jsonResponse({ kind: "family_data", version: "2026-09-v1", language: "en", text: FAMILY_TEXT });
    if (method === "POST" && url.endsWith("/api/v1/trees")) return jsonResponse(tree, 201);
    if (method === "POST" && url.endsWith("/trees/t1/attestation")) return jsonResponse({ id: "a1", statement_version: "2026-09-v1", language: "en", accepted_at: "2026-09-25T00:00:00Z", withdrawn_at: null }, 201);
    if (method === "POST" && url.endsWith("/trees/t1/people")) return jsonResponse({ id: "p-self", display_name: "Asha Iyer" }, 201);
    if (method === "POST" && url.endsWith("/people/p-self/relatives")) {
      const body = JSON.parse(String(init?.body));
      const name = body.new_person.names[0].given_name;
      return jsonResponse({ person: { id: `p-${name}`, display_name: `${name} Iyer`, profile_status: body.new_person.profile_status }, relationships: [] }, 201);
    }
    return undefined;
  };

  it("never pre-ticks the consent box and adds nobody until it is ticked", async () => {
    const fetchMock = routed(handler);
    const box = await reachFamilyStep(fetchMock);
    expect(box).not.toBeChecked();
    expect(within(screen.getByRole("group", { name: "You" })).getByLabelText(/Given name/)).toHaveValue("Asha");

    await userEvent.click(screen.getByRole("button", { name: "Save and continue" }));
    expect(await screen.findByText("Please tick the box to continue.")).toBeInTheDocument();
    expect(posts(fetchMock).map((p) => p.url)).toEqual(["/api/v1/trees"]);
  });

  it("records the confirmation first, then adds you and your parents, then offers WhatsApp invites", async () => {
    const fetchMock = routed(handler);
    await reachFamilyStep(fetchMock);
    const father = screen.getByRole("group", { name: "Father" });
    await userEvent.type(within(father).getByLabelText("Given name"), "Ravi");
    const mother = screen.getByRole("group", { name: "Mother" });
    await userEvent.type(within(mother).getByLabelText("Given name"), "Lalitha");
    await userEvent.selectOptions(within(mother).getByLabelText("Living or passed away?"), "deceased");
    await userEvent.click(screen.getByRole("checkbox", { name: FAMILY_TEXT }));
    await userEvent.click(screen.getByRole("button", { name: "Save and continue" }));

    await waitFor(() => expect(screen.queryByRole("alert")?.textContent ?? "").toBe(""));
    expect(await screen.findByRole("heading", { name: "Invite relatives" })).toBeInTheDocument();
    const calls = posts(fetchMock);
    expect(calls.map((c) => c.url)).toEqual([
      "/api/v1/trees",
      "/api/v1/trees/t1/attestation",
      "/api/v1/trees/t1/people",
      "/api/v1/trees/t1/people/p-self/relatives",
      "/api/v1/trees/t1/people/p-self/relatives",
    ]);
    expect(calls[1]!.body).toEqual({ statement_version: "2026-09-v1", language: "en" });
    expect(calls[3]!.body.new_person).toMatchObject({ profile_status: "living", sex_at_birth: "male" });
    // only living relatives are offered an invite
    expect(screen.getByRole("button", { name: "Create a private link for Ravi Iyer" })).toBeInTheDocument();
    expect(screen.queryByRole("button", { name: /Lalitha/ })).not.toBeInTheDocument();
  });
});

describe("ClaimInvitePage", () => {
  const preview = { tree_name: "Iyer parivar", person_name: "Meera Iyer", invited_by: "Asha Iyer", offered_role: "VIEWER", expires_at: "2026-10-01T00:00:00Z", state: "active", claim_id: null };

  it("asks a signed-out visitor to sign in and keeps the token in the fragment", async () => {
    vi.stubGlobal("fetch", routed((url) => (url.includes("/auth/me") ? jsonResponse({ error: { code: "unauthenticated", message: "x" } }, 401) : undefined)));
    renderWithProviders(<ClaimInvitePage />, { tree: null, route: `/claim#${TOKEN}` });
    const signUp = await screen.findByRole("link", { name: "Create account" });
    expect(signUp.getAttribute("href")).toBe(`/register?next=${encodeURIComponent(`/claim#${TOKEN}`)}`);
  });

  it("requires the relative's own consent and age confirmation before sending the claim", async () => {
    const fetchMock = routed((url, init) => {
      if (url.includes("/auth/me")) return jsonResponse(me);
      if (url.includes("/consent-statements/profile_claim")) return jsonResponse({ kind: "profile_claim", version: "2026-09-v1", language: "en", text: CLAIM_TEXT });
      if (init?.method === "POST" && url.endsWith(`/claim-invites/${TOKEN}/accept`)) return jsonResponse({ claim_id: "c1", status: "requested", tree_name: "Iyer parivar", person_name: "Meera Iyer" }, 201);
      if (url.endsWith(`/claim-invites/${TOKEN}`)) return jsonResponse(preview);
      return undefined;
    });
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ClaimInvitePage />, { tree: null, route: `/claim#${TOKEN}` });
    expect(await screen.findByText(/Asha Iyer added you as “Meera Iyer”/)).toBeInTheDocument();
    const consent = await screen.findByRole("checkbox", { name: CLAIM_TEXT });
    expect(consent).not.toBeChecked();

    await userEvent.click(screen.getByRole("button", { name: "Claim my profile" }));
    expect(await screen.findByText("You need to be 18 or older to claim a profile yourself.")).toBeInTheDocument();
    expect(posts(fetchMock)).toEqual([]);

    await userEvent.click(consent);
    await userEvent.click(screen.getByRole("checkbox", { name: /I am 18 or older/ }));
    await userEvent.click(screen.getByRole("button", { name: "Claim my profile" }));
    await waitFor(() => expect(posts(fetchMock)).toHaveLength(1));
    expect(posts(fetchMock)[0]!.body).toEqual({ consent_version: "2026-09-v1", language: "en", confirm_adult: true, message: null });
    expect((await screen.findAllByText(/Your request was sent to the tree admins/)).length).toBeGreaterThan(0);
  });

  it("explains a used link without showing any names", async () => {
    vi.stubGlobal(
      "fetch",
      routed((url) => {
        if (url.includes("/auth/me")) return jsonResponse(me);
        if (url.includes("/claim-invites/")) return jsonResponse({ error: { code: "invite_used", message: "used" } }, 410);
        return undefined;
      }),
    );
    renderWithProviders(<ClaimInvitePage />, { tree: null, route: `/claim#${TOKEN}` });
    expect(await screen.findByText(/already been used/)).toBeInTheDocument();
    expect(screen.queryByText(/Meera/)).not.toBeInTheDocument();
  });
});

describe("ClaimInvitePage: this isn't me / remove me", () => {
  const active = { tree_name: "Iyer parivar", person_name: "Meera Iyer", invited_by: "Asha Iyer", offered_role: "VIEWER", expires_at: "2026-10-01T00:00:00Z", state: "active", claim_id: null, claim_kind: null };

  function mockWith(onPost: (url: string) => Response | undefined, afterPost: () => unknown = () => active) {
    let posted = false;
    return routed((url, init) => {
      if (url.includes("/auth/me")) return jsonResponse(me);
      if (url.includes("/consent-statements/profile_claim")) return jsonResponse({ kind: "profile_claim", version: "2026-09-v1", language: "en", text: CLAIM_TEXT });
      if (init?.method === "POST") {
        posted = true;
        return onPost(url);
      }
      if (url.endsWith(`/claim-invites/${TOKEN}`)) return jsonResponse(posted ? afterPost() : active);
      return undefined;
    });
  }

  it("cancels the link after confirmation and saves nothing else", async () => {
    const fetchMock = mockWith((url) => (url.endsWith(`/claim-invites/${TOKEN}/decline`) ? jsonResponse({ message: "ok" }) : undefined));
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ClaimInvitePage />, { tree: null, route: `/claim#${TOKEN}` });
    await userEvent.click(await screen.findByRole("button", { name: "This isn't me" }));
    const dialog = await screen.findByRole("dialog", { name: "You are not “Meera Iyer”?" });
    expect(posts(fetchMock)).toEqual([]);
    await userEvent.click(within(dialog).getByRole("button", { name: "Yes, cancel this link" }));
    expect((await screen.findAllByText(/This link no longer works, and nothing about you was added/)).length).toBeGreaterThan(0);
    expect(posts(fetchMock).map((p) => p.url)).toEqual([`/api/v1/claim-invites/${TOKEN}/decline`]);
    expect(screen.queryByText(/Meera/)).not.toBeInTheDocument();
  });

  it("asks the person to confirm it's them before hiding the profile and requesting removal", async () => {
    const fetchMock = mockWith(
      (url) => (url.endsWith(`/claim-invites/${TOKEN}/request-removal`) ? jsonResponse({ claim_id: "c1", kind: "removal", status: "requested", tree_name: "Iyer parivar", person_name: "Meera Iyer" }, 201) : undefined),
      () => ({ ...active, state: "used", claim_id: "c1", claim_kind: "removal" }),
    );
    vi.stubGlobal("fetch", fetchMock);
    renderWithProviders(<ClaimInvitePage />, { tree: null, route: `/claim#${TOKEN}` });
    await userEvent.click(await screen.findByRole("button", { name: "This is me, but remove me" }));
    const dialog = await screen.findByRole("dialog", { name: "Remove me from this tree" });
    const confirm = within(dialog).getByRole("button", { name: "Hide my profile and ask for removal" });
    await userEvent.click(confirm);
    expect(await within(dialog).findByText("Please confirm that this profile is about you.")).toBeInTheDocument();
    expect(posts(fetchMock)).toEqual([]);

    await userEvent.click(within(dialog).getByRole("checkbox", { name: /I am “Meera Iyer”/ }));
    await userEvent.type(within(dialog).getByLabelText(/Message to the tree admins/), "Please take me out");
    await userEvent.click(confirm);
    await waitFor(() => expect(posts(fetchMock)).toHaveLength(1));
    expect(posts(fetchMock)[0]!.body).toEqual({ confirm_is_me: true, message: "Please take me out" });
    expect((await screen.findAllByText(/Your profile is now hidden from everyone except the tree admins/)).length).toBeGreaterThan(0);
  });
});
