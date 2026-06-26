import {describe, expect, it, vi} from "vitest";

import {MissingAdminTokenError, RadioApiClient} from "./client";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: {"Content-Type": "application/json"}
  });
}

describe("RadioApiClient", () => {
  it("builds API URLs and query strings", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({items: [], stats: {}}));
    const client = new RadioApiClient({baseUrl: "/edge/api/", fetcher});

    await client.tracks({q: " track ", status: "downloaded", limit: 10});

    expect(fetcher).toHaveBeenCalledWith(
      "/edge/api/tracks?status=downloaded&limit=10&q=track",
      undefined
    );
  });

  it("calls fetchers without binding them to the client instance", async () => {
    let called = false;
    const fetcher = vi.fn(function (this: unknown) {
      called = true;
      if (this !== undefined) {
        throw new Error("fetcher was called with a bound this value");
      }
      return Promise.resolve(jsonResponse({now_playing: null, queue: null}));
    }) as unknown as typeof fetch;
    const client = new RadioApiClient({fetcher});

    await client.current();

    expect(called).toBe(true);
  });

  it("sends bearer headers for admin mutations", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({queue_id: 7}));
    const client = new RadioApiClient({
      fetcher,
      tokenProvider: () => "secret-token"
    });

    await client.enqueueNext({track_id: 42});

    expect(fetcher).toHaveBeenCalledWith("/api/queue/append/admin", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: "Bearer secret-token"
      },
      body: '{"track_id":42}'
    });
  });

  it("rejects admin mutations without token before fetch", async () => {
    const fetcher = vi.fn<typeof fetch>();
    const client = new RadioApiClient({fetcher, tokenProvider: () => ""});

    await expect(client.skip()).rejects.toBeInstanceOf(MissingAdminTokenError);
    expect(fetcher).not.toHaveBeenCalled();
  });

  it("raises API errors with status and body", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(
      new Response("not allowed", {
        status: 401,
        statusText: "Unauthorized"
      })
    );
    const client = new RadioApiClient({fetcher});

    await expect(client.current()).rejects.toMatchObject({
      status: 401,
      body: "not allowed"
    });
  });
});
