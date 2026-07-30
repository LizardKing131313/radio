import type {MetricsResponse} from "@radio/api";

export interface RuntimeSummary {
  hls: string;
  nowplaying: string;
  queueFailed: string;
  tracksFailed: string;
  youtube: string;
}

export function runtimeSummary(metrics: MetricsResponse | null): RuntimeSummary {
  const hls = metrics?.current?.hls;
  const age = hls?.age_sec;
  return {
    hls: hls?.is_probably_audible ? "звук идёт" : "нет подтверждения",
    nowplaying: age === null || age === undefined ? "нет nowplaying" : `${String(age)} сек`,
    queueFailed: String(metrics?.queue?.stats?.["failed"] ?? 0),
    tracksFailed: String(metrics?.tracks?.["failed"] ?? 0),
    youtube: metrics?.youtube_api?.quota_exhausted
      ? "quota exhausted"
      : `${String(metrics?.youtube_api?.consecutive_errors ?? 0)} ошибок`
  };
}
