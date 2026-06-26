import type {QueueEntry, Track} from "@radio/api";

export function trackTitle(track?: Track | null): string {
  return nonEmpty(track?.title) ?? nonEmpty(track?.youtube_id) ?? "Без названия";
}

export function queueLabel(entry?: QueueEntry | null): string {
  if (!entry) {
    return "Очередь пуста";
  }
  const status = entry.queue_item.status ?? "?";
  return `${status}: ${trackTitle(entry.track)}`;
}

export function formatDuration(seconds?: number | null): string {
  if (seconds === undefined || seconds === null || seconds <= 0) {
    return "?:??";
  }
  const minutes = Math.floor(seconds / 60);
  const rest = Math.floor(seconds % 60);
  return `${String(minutes)}:${String(rest).padStart(2, "0")}`;
}

export function youtubeStatus(input?: {
  status?: string | null;
  quota_exhausted?: boolean | null;
  consecutive_errors?: number | null;
  estimated_quota_units?: number | null;
}): string {
  if (!input) {
    return "нет данных";
  }
  const status = input.quota_exhausted ? "квота закончилась" : (input.status ?? "нет данных");
  const errors = input.consecutive_errors ?? 0;
  const units = input.estimated_quota_units ?? 0;
  return `${status}; ошибок: ${String(errors)}; units: ${String(units)}`;
}

function nonEmpty(value?: string | null): string | null {
  const trimmed = value?.trim();
  return trimmed === undefined || trimmed === "" ? null : trimmed;
}
