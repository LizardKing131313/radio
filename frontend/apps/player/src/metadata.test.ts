import {describe, expect, it} from "vitest";

import {metadataTitle} from "./metadata";

describe("metadataTitle", () => {
  it("does not join unknown artist or title values", () => {
    expect(
      metadataTitle({
        now_playing: {source: {artist: "NA", title: "Track"}}
      })
    ).toBe("Track");
    expect(
      metadataTitle({
        now_playing: {source: {artist: "Artist", title: "N/A"}}
      })
    ).toBe("Artist");
  });

  it("removes hashtags from the displayed title", () => {
    expect(
      metadataTitle({
        now_playing: {source: {line: "Artist - Track #ремикс #2026"}}
      })
    ).toBe("Artist - Track");
  });
});
