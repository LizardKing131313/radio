import {describe, expect, it, vi} from "vitest";

import {RadioApiClient} from "./client";

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

    expect(fetcher).toHaveBeenCalledWith("/edge/api/tracks?status=downloaded&limit=10&q=track", {
      credentials: "same-origin"
    });
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

  it("uses the session cookie for admin mutations", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({queue_id: 7}));
    const client = new RadioApiClient({fetcher});

    await client.enqueueNext({track_id: 42});

    expect(fetcher).toHaveBeenCalledWith("/api/queue/append/admin", {
      method: "POST",
      headers: {
        "Content-Type": "application/json"
      },
      body: '{"track_id":42}',
      credentials: "same-origin"
    });
  });

  it("logs in through the session endpoint", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(jsonResponse({status: "ok"}));
    const client = new RadioApiClient({fetcher});

    await client.login("admin", "password");

    expect(fetcher).toHaveBeenCalledWith("/api/auth/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: '{"username":"admin","password":"password"}',
      credentials: "same-origin"
    });
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
