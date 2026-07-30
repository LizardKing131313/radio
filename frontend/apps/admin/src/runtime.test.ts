import {describe, expect, it} from "vitest";

import {runtimeSummary} from "./runtime";

describe("runtimeSummary", () => {
  it("summarizes current operational values", () => {
    expect(
      runtimeSummary({
        current: {hls: {age_sec: 12, is_probably_audible: true}},
        queue: {stats: {failed: 2}},
        tracks: {failed: 3},
        youtube_api: {consecutive_errors: 1}
      })
    ).toEqual({
      hls: "звук идёт",
      nowplaying: "12 сек",
      queueFailed: "2",
      tracksFailed: "3",
      youtube: "1 ошибок"
    });
  });

  it("shows safe values when runtime state is absent or quota is exhausted", () => {
    expect(runtimeSummary({youtube_api: {quota_exhausted: true}})).toEqual({
      hls: "нет подтверждения",
      nowplaying: "нет nowplaying",
      queueFailed: "0",
      tracksFailed: "0",
      youtube: "quota exhausted"
    });
  });
});
