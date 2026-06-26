export interface Track {
  id: number;
  youtube_id?: string | null;
  title?: string | null;
  duration_sec?: number | null;
  channel?: string | null;
  url?: string | null;
  audio_path?: string | null;
  cache_state?: string | null;
  fail_count?: number | null;
  deleted_at?: string | null;
  is_active?: boolean | number | null;
  play_count?: number | null;
}

export interface QueueItem {
  id: number;
  track_id?: number | null;
  status?: string | null;
  error_detail?: string | null;
}

export interface QueueEntry {
  queue_item: QueueItem;
  track: Track;
}

export interface NowPlayingSource {
  line?: string | null;
  title?: string | null;
  artist?: string | null;
}

export interface HlsState {
  live_offset_sec?: number | null;
  age_sec?: number | null;
  estimated_audible_at?: string | null;
  is_probably_audible?: boolean | null;
}

export interface CurrentResponse {
  now_playing?: {
    source?: NowPlayingSource | null;
    hls?: HlsState | null;
  } | null;
  queue?: QueueEntry | null;
}

export interface MetricsResponse {
  status?: string;
  tracks?: Record<string, number>;
  queue?: {
    visible?: QueueEntry[];
    history?: QueueEntry[];
  };
  current?: CurrentResponse["now_playing"];
  youtube_api?: {
    status?: string | null;
    quota_exhausted?: boolean | null;
    consecutive_errors?: number | null;
    estimated_quota_units?: number | null;
  };
}

export interface TracksResponse {
  items: Track[];
  stats: Record<string, number>;
}

export interface Offer {
  id: number;
  youtube_url: string;
  status?: string | null;
  submitted_by?: string | null;
  note?: string | null;
  accepted_track_id?: number | null;
}

export interface OffersResponse {
  items: Offer[];
}

export interface EnqueueRequest {
  track_id: number;
  requested_by?: string | null;
  note?: string | null;
}

export interface OfferRequest {
  youtube_url: string;
  submitted_by?: string | null;
  note?: string | null;
}
