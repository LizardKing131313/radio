import {describe, expect, it} from "vitest";

import {initialPlayerState, playerReducer} from "./state";

describe("playerReducer", () => {
  it("moves through loading, playing, and paused states", () => {
    const loading = playerReducer(initialPlayerState, {type: "load"});
    const playing = playerReducer(loading, {type: "play"});
    const paused = playerReducer(playing, {type: "pause"});

    expect(loading.status).toBe("loading");
    expect(playing.status).toBe("playing");
    expect(paused.status).toBe("paused");
  });

  it("keeps actionable offline and error messages", () => {
    expect(playerReducer(initialPlayerState, {type: "offline"})).toMatchObject({
      status: "offline",
      message: "Нет сети: эфир и метаданные недоступны"
    });
    expect(
      playerReducer(initialPlayerState, {type: "error", message: "HLS failed"})
    ).toMatchObject({
      status: "error",
      message: "HLS failed"
    });
  });
});
