import { afterEach, describe, expect, it, vi } from "vitest";
import { act, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { renderWithProviders } from "../../test/utils";
import { GrowingTree } from "./GrowingTree";

/** An IntersectionObserver that reports the tree as on screen as soon as it is observed. */
function stubVisible() {
  vi.stubGlobal(
    "IntersectionObserver",
    class {
      constructor(private cb: IntersectionObserverCallback) {}
      observe() {
        this.cb([{ isIntersecting: true } as IntersectionObserverEntry], this as unknown as IntersectionObserver);
      }
      disconnect() {}
    },
  );
}

const lit = (container: HTMLElement) => container.querySelectorAll("g.gt-node.is-on").length;

describe("growing family tree", () => {
  afterEach(() => vi.useRealTimers());

  it("grows one generation at a time once it is on screen, then names the kinship", () => {
    vi.useFakeTimers();
    stubVisible();
    const { container } = renderWithProviders(<GrowingTree />, { tree: null });
    expect(lit(container)).toBe(0);

    act(() => vi.advanceTimersByTime(800)); // grandparents
    expect(lit(container)).toBe(2);
    act(() => vi.advanceTimersByTime(1500)); // their sons
    expect(lit(container)).toBe(4);
    act(() => vi.advanceTimersByTime(800)); // daughters-in-law
    expect(lit(container)).toBe(6);
    expect(container.querySelector(".gt-kin.is-on")).toBeNull();
    act(() => vi.advanceTimersByTime(3000)); // grandchildren and the kinship line
    expect(lit(container)).toBe(9);
    expect(container.querySelector(".gt-kin.is-on")).not.toBeNull();
  });

  it("can be replayed from the start", async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true });
    stubVisible();
    const { container } = renderWithProviders(<GrowingTree />, { tree: null });
    act(() => vi.advanceTimersByTime(7000));
    expect(lit(container)).toBe(9);

    await userEvent.setup({ advanceTimers: vi.advanceTimersByTime }).click(screen.getByRole("button", { name: "Watch it grow again" }));
    expect(lit(container)).toBe(0);
    act(() => vi.advanceTimersByTime(7000));
    expect(lit(container)).toBe(9);
  });

  it("shows the finished tree when motion is unavailable", () => {
    // jsdom has no IntersectionObserver: nothing waits on scrolling
    const { container } = renderWithProviders(<GrowingTree />, { tree: null });
    expect(lit(container)).toBe(9);
    expect(screen.getByRole("img", { name: /growing generation by generation/ })).toBeInTheDocument();
  });
});
