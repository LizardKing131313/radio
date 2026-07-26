import {describe, expect, it, vi} from "vitest";

import {HLS_OPTIONS, recoverFatalHlsError} from "./hls";

describe("HLS playback resilience", () => {
  it("keeps a buffered live profile instead of low-latency mode", () => {
    expect(HLS_OPTIONS).toMatchObject({
      lowLatencyMode: false,
      liveSyncDurationCount: 6,
      liveMaxLatencyDurationCount: 14,
      maxBufferLength: 30
    });
  });

  it("restarts loading after a fatal network error", () => {
    const hls = {startLoad: vi.fn(), recoverMediaError: vi.fn(), destroy: vi.fn()};
    const audio = {removeAttribute: vi.fn(), load: vi.fn()} as unknown as HTMLAudioElement;

    recoverFatalHlsError(
      hls,
      audio,
      {fatal: true, type: "networkError"},
      {
        NETWORK_ERROR: "networkError",
        MEDIA_ERROR: "mediaError"
      }
    );

    expect(hls.startLoad).toHaveBeenCalledOnce();
    expect(hls.recoverMediaError).not.toHaveBeenCalled();
    expect(hls.destroy).not.toHaveBeenCalled();
  });

  it("recovers the media pipeline after a fatal media error", () => {
    const hls = {startLoad: vi.fn(), recoverMediaError: vi.fn(), destroy: vi.fn()};
    const audio = {removeAttribute: vi.fn(), load: vi.fn()} as unknown as HTMLAudioElement;

    recoverFatalHlsError(
      hls,
      audio,
      {fatal: true, type: "mediaError"},
      {
        NETWORK_ERROR: "networkError",
        MEDIA_ERROR: "mediaError"
      }
    );

    expect(hls.recoverMediaError).toHaveBeenCalledOnce();
    expect(hls.startLoad).not.toHaveBeenCalled();
  });
});
