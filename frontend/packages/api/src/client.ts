import type {
  CurrentResponse,
  EnqueueRequest,
  MetricsResponse,
  OfferRequest,
  OffersResponse,
  TracksResponse
} from "./types";

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly body: string
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface RadioApiClientOptions {
  baseUrl?: string;
  fetcher?: typeof fetch;
}

export interface TrackListOptions {
  q?: string;
  status?: string;
  limit?: number;
}

export class RadioApiClient {
  private readonly baseUrl: string;
  private readonly fetcher: typeof fetch;

  constructor(options: RadioApiClientOptions = {}) {
    const fetcher = options.fetcher ?? globalThis.fetch.bind(globalThis);
    this.baseUrl = options.baseUrl ?? "/api";
    this.fetcher = (input, init) => fetcher(input, {...init, credentials: "same-origin"});
  }

  login(username: string, password: string): Promise<{ status: string }> {
    return this.request("/auth/login", {
      method: "POST",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify({username, password})
    });
  }

  session(): Promise<{ status: string }> {
    return this.get("/auth/me");
  }

  logout(): Promise<{ status: string }> {
    return this.request("/auth/logout", {method: "POST"});
  }

  current(): Promise<CurrentResponse> {
    return this.get("/current");
  }

  metrics(): Promise<MetricsResponse> {
    return this.get("/metrics");
  }

  tracks(options: TrackListOptions = {}): Promise<TracksResponse> {
    const params = new URLSearchParams({
      status: options.status ?? "downloaded",
      limit: String(options.limit ?? 80)
    });
    if (options.q?.trim()) {
      params.set("q", options.q.trim());
    }
    return this.get(`/tracks?${params.toString()}`);
  }

  offers(status?: string): Promise<OffersResponse> {
    const params = new URLSearchParams({limit: "200"});
    if (status) {
      params.set("status", status);
    }
    return this.get(`/offers?${params.toString()}`);
  }

  addOffer(payload: OfferRequest): Promise<{ offer_id: number }> {
    return this.post("/offers/add", payload);
  }

  enqueueNext(payload: EnqueueRequest): Promise<{ queue_id: number }> {
    return this.post("/queue/append/admin", payload, true);
  }

  playNow(trackId: number): Promise<{ status: string }> {
    return this.post(`/tracks/${String(trackId)}/play-now`, undefined, true);
  }

  skip(): Promise<{ status: string }> {
    return this.post("/queue/skip", undefined, true);
  }

  banTrack(trackId: number): Promise<{ status: string }> {
    return this.post(`/tracks/${String(trackId)}/ban`, undefined, true);
  }

  restoreTrack(trackId: number): Promise<{ status: string }> {
    return this.post(`/tracks/${String(trackId)}/restore`, undefined, true);
  }

  retryTrack(trackId: number): Promise<{ status: string }> {
    return this.post(`/tracks/${String(trackId)}/retry`, undefined, true);
  }

  acceptOffer(offerId: number, trackId: number): Promise<{ status: string }> {
    return this.post(`/offers/${String(offerId)}/accept`, {track_id: trackId}, true);
  }

  cancelOffer(offerId: number): Promise<{ status: string }> {
    return this.post(`/offers/${String(offerId)}/cancel`, undefined, true);
  }

  private get<T>(path: string): Promise<T> {
    return this.request(path);
  }

  private async post<T>(path: string, body?: unknown, _authorized = false): Promise<T> {
    const headers: Record<string, string> = {};
    if (body !== undefined) {
      headers["Content-Type"] = "application/json";
    }
    const init: RequestInit = {
      method: "POST",
      headers
    };
    if (body !== undefined) {
      init.body = JSON.stringify(body);
    }
    return this.request(path, init);
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await this.fetcher(this.url(path), init);
    if (!response.ok) {
      const body = await response.text();
      throw new ApiError(body !== "" ? body : response.statusText, response.status, body);
    }
    return (await response.json()) as T;
  }

  private url(path: string): string {
    const base = this.baseUrl.replace(/\/$/, "");
    const endpoint = path.startsWith("/") ? path : `/${path}`;
    return `${base}${endpoint}`;
  }
}

export function defaultApiBase(): string {
  const configured = window.__RADIO_API_BASE__;
  return configured?.length ? configured : "/api";
}

declare global {
  interface Window {
    __RADIO_API_BASE__?: string;
  }
}
