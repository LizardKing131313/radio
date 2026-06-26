import {describe, expect, it, vi} from "vitest";

import {performTrackAction, skipCurrent} from "./actions";

describe("admin actions", () => {
  it("maps track actions to existing API mutations", async () => {
    const api = {
      enqueueNext: vi.fn().mockResolvedValue({queue_id: 1}),
      playNow: vi.fn().mockResolvedValue({status: "playing"}),
      retryTrack: vi.fn().mockResolvedValue({status: "scheduled"}),
      banTrack: vi.fn().mockResolvedValue({status: "banned"}),
      restoreTrack: vi.fn().mockResolvedValue({status: "restored"})
    };

    await expect(performTrackAction(api as never, "enqueue", 11)).resolves.toBe(
      "Поставлено следующим"
    );
    await expect(performTrackAction(api as never, "play-now", 12)).resolves.toBe(
      "Отправлено в эфир сейчас"
    );
    await expect(performTrackAction(api as never, "retry", 13)).resolves.toBe(
      "Скачивание запланировано заново"
    );
    await expect(performTrackAction(api as never, "ban", 14)).resolves.toBe("Трек забанен");
    await expect(performTrackAction(api as never, "restore", 15)).resolves.toBe("Трек возвращен");

    expect(api.enqueueNext).toHaveBeenCalledWith({track_id: 11});
    expect(api.playNow).toHaveBeenCalledWith(12);
    expect(api.retryTrack).toHaveBeenCalledWith(13);
    expect(api.banTrack).toHaveBeenCalledWith(14);
    expect(api.restoreTrack).toHaveBeenCalledWith(15);
  });

  it("skips current playback through queue skip", async () => {
    const api = {skip: vi.fn().mockResolvedValue({status: "skipped"})};

    await expect(skipCurrent(api as never)).resolves.toBe("Текущий трек пропущен");
    expect(api.skip).toHaveBeenCalledWith();
  });
});
