import type {RadioApiClient} from "@radio/api";

export type TrackAction = "enqueue" | "play-now" | "retry" | "ban" | "restore";

export async function performTrackAction(
  api: RadioApiClient,
  action: TrackAction,
  trackId: number
): Promise<string> {
  switch (action) {
    case "enqueue":
      await api.enqueueNext({track_id: trackId});
      return "Поставлено следующим";
    case "play-now":
      await api.playNow(trackId);
      return "Отправлено в эфир сейчас";
    case "retry":
      await api.retryTrack(trackId);
      return "Скачивание запланировано заново";
    case "ban":
      await api.banTrack(trackId);
      return "Трек забанен";
    case "restore":
      await api.restoreTrack(trackId);
      return "Трек возвращен";
    default:
      return "Неизвестное действие";
  }
}

export async function skipCurrent(api: RadioApiClient): Promise<string> {
  await api.skip();
  return "Текущий трек пропущен";
}
