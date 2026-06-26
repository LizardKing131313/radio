import {
  defaultApiBase,
  type MetricsResponse,
  MissingAdminTokenError,
  type Offer,
  type QueueEntry,
  RadioApiClient,
  type Track,
  type TracksResponse
} from "@radio/api";
import {formatDuration, trackTitle, youtubeStatus} from "@radio/ui";
import {type ComponentChildren, render} from "preact";
import {useCallback, useEffect, useState} from "preact/hooks";

import "../../shared/styles.css";
import {performTrackAction, skipCurrent, type TrackAction} from "./actions";

const TOKEN_KEY = "radioAdminToken";

function readStoredToken(): string {
  return localStorage.getItem(TOKEN_KEY) ?? sessionStorage.getItem(TOKEN_KEY) ?? "";
}

const api = new RadioApiClient({
  baseUrl: defaultApiBase(),
  tokenProvider: readStoredToken
});

function App() {
  const [token, setToken] = useState(readStoredToken());
  const [remember, setRemember] = useState(Boolean(localStorage.getItem(TOKEN_KEY)));
  const [query, setQuery] = useState("");
  const [status, setStatus] = useState("downloaded");
  const [metrics, setMetrics] = useState<MetricsResponse | null>(null);
  const [tracks, setTracks] = useState<TracksResponse>({items: [], stats: {}});
  const [offers, setOffers] = useState<Offer[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const playingEntry = metrics?.queue?.visible?.find(
    (entry) => entry.queue_item.status === "playing"
  );
  const currentTitle = playingEntry
    ? trackTitle(playingEntry.track)
    : (metrics?.current?.source?.line ?? "нет данных");
  const statsSummary = Object.entries(tracks.stats)
    .map(([key, value]) => `${key}: ${String(value)}`)
    .join(", ");

  function saveToken() {
    localStorage.removeItem(TOKEN_KEY);
    sessionStorage.removeItem(TOKEN_KEY);
    if (token.trim()) {
      if (remember) {
        localStorage.setItem(TOKEN_KEY, token.trim());
      } else {
        sessionStorage.setItem(TOKEN_KEY, token.trim());
      }
    }
    setNotice("Token сохранен");
  }

  const loadAll = useCallback(async () => {
    setError(null);
    try {
      const [nextMetrics, nextTracks, nextOffers] = await Promise.all([
        api.metrics(),
        api.tracks({q: query, status, limit: 80}),
        api.offers("new")
      ]);
      setMetrics(nextMetrics);
      setTracks(nextTracks);
      setOffers(nextOffers.items);
    } catch (caught) {
      setError(errorMessage(caught));
    }
  }, [query, status]);

  const run = useCallback(
    async (messageTask: () => Promise<string>) => {
      setBusy(true);
      setError(null);
      setNotice(null);
      try {
        const message = await messageTask();
        setNotice(message);
        await loadAll();
      } catch (caught) {
        setError(errorMessage(caught));
      } finally {
        setBusy(false);
      }
    },
    [loadAll]
  );

  useEffect(() => {
    void loadAll();
  }, [loadAll]);

  return (
    <main className="min-h-screen bg-[#102225] text-[#f5efe0]">
      <section className="mx-auto max-w-7xl px-4 py-5 sm:px-6 lg:px-8">
        <header
          className="grid gap-4 rounded-[1.75rem] bg-[#e9c46a] p-5 text-[#102225] shadow-xl lg:grid-cols-[1fr_auto]">
          <div>
            <p className="text-xs font-black tracking-[0.35em] uppercase">radio control</p>
            <h1 className="mt-1 text-4xl font-black tracking-[-0.07em] sm:text-5xl">Пульт эфира</h1>
            <p className="mt-3 text-sm font-bold">Сейчас: {currentTitle}</p>
          </div>
          <div className="grid gap-2 sm:grid-cols-[minmax(220px,1fr)_auto] lg:min-w-[460px]">
            <input
              type="password"
              value={token}
              onInput={(event) => setToken(event.currentTarget.value)}
              placeholder="Admin token"
              autoComplete="current-password"
              className="rounded-2xl border-2 border-[#102225] bg-white px-4 py-3 text-[#102225]"
            />
            <button
              type="button"
              onClick={saveToken}
              className="rounded-2xl bg-[#102225] px-5 py-3 font-black text-[#f5efe0]"
            >
              Сохранить
            </button>
            <label className="flex items-center gap-2 text-sm font-bold">
              <input
                type="checkbox"
                checked={remember}
                onChange={(event) => setRemember(event.currentTarget.checked)}
              />
              Запомнить на устройстве
            </label>
          </div>
        </header>

        <section className="mt-5 grid gap-4 lg:grid-cols-4">
          <Stat title="Очередь" value={String(metrics?.queue?.visible?.length ?? 0)}/>
          <Stat title="История" value={String(metrics?.queue?.history?.length ?? 0)}/>
          <Stat title="YouTube" value={youtubeStatus(metrics?.youtube_api)}/>
          <Stat title="Треки" value={statsSummary === "" ? "нет данных" : statsSummary}/>
        </section>

        <section className="mt-5 flex flex-wrap gap-3">
          <button
            type="button"
            disabled={busy}
            onClick={() => void loadAll()}
            className="rounded-2xl bg-[#2a9d8f] px-5 py-3 font-black text-[#071f21] disabled:opacity-60"
          >
            Обновить
          </button>
          <button
            type="button"
            disabled={busy}
            onClick={() => void run(() => skipCurrent(api))}
            className="rounded-2xl bg-[#e76f51] px-5 py-3 font-black text-[#220b05] disabled:opacity-60"
          >
            Пропустить текущий трек
          </button>
        </section>

        {error ? <Message tone="error" text={error}/> : null}
        {notice ? <Message tone="notice" text={notice}/> : null}

        <section className="mt-6 grid gap-6 xl:grid-cols-[1fr_.75fr]">
          <Panel title="Каталог">
            <div className="mb-4 grid gap-3 md:grid-cols-[1fr_180px_auto]">
              <input
                value={query}
                onInput={(event) => setQuery(event.currentTarget.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter") {
                    void loadAll();
                  }
                }}
                placeholder="Поиск по названию, каналу, youtube id"
                className="rounded-2xl border border-white/20 bg-white/10 px-4 py-3"
              />
              <select
                value={status}
                onChange={(event) => setStatus(event.currentTarget.value)}
                className="rounded-2xl border border-white/20 bg-[#173135] px-4 py-3"
              >
                <option value="downloaded">Скачанные</option>
                <option value="active">Активные</option>
                <option value="missing">Без аудио</option>
                <option value="failed">Ошибки</option>
                <option value="inactive">Отключенные</option>
                <option value="deleted">Бан</option>
                <option value="all">Все</option>
              </select>
              <button
                type="button"
                onClick={() => void loadAll()}
                className="rounded-2xl bg-[#e9c46a] px-5 py-3 font-black text-[#102225]"
              >
                Найти
              </button>
            </div>
            <TrackList
              tracks={tracks.items}
              busy={busy}
              onAction={(action, trackId) => {
                void run(() => performTrackAction(api, action, trackId));
              }}
            />
          </Panel>

          <div className="grid gap-6">
            <Panel title="Очередь">
              <QueueList entries={metrics?.queue?.visible ?? []} empty="Очередь пуста"/>
            </Panel>
            <Panel title="Предложения">
              <OfferList offers={offers}/>
            </Panel>
          </div>
        </section>
      </section>
    </main>
  );
}

function Stat({title, value}: { title: string; value: string }) {
  return (
    <article className="rounded-[1.5rem] border border-white/10 bg-white/10 p-4">
      <p className="text-xs font-black tracking-[0.25em] text-[#e9c46a] uppercase">{title}</p>
      <p className="mt-2 text-lg font-black">{value}</p>
    </article>
  );
}

function Panel({title, children}: { title: string; children: ComponentChildren }) {
  return (
    <section className="rounded-[1.75rem] border border-white/10 bg-[#163034] p-4 shadow-xl">
      <h2 className="mb-4 text-2xl font-black tracking-[-0.05em]">{title}</h2>
      {children}
    </section>
  );
}

function TrackList({
                     tracks,
                     busy,
                     onAction
                   }: {
  tracks: Track[];
  busy: boolean;
  onAction: (action: TrackAction, trackId: number) => void;
}) {
  if (tracks.length === 0) {
    return (
      <p className="rounded-2xl bg-white/10 p-5 text-[#d8caa9]">Нет треков по этому фильтру</p>
    );
  }
  return (
    <div className="grid gap-3">
      {tracks.map((track) => (
        <article
          key={track.id}
          className="grid gap-3 rounded-2xl bg-[#0d2023] p-4 lg:grid-cols-[1fr_auto]"
        >
          <div>
            <p className="text-lg font-black">{trackTitle(track)}</p>
            <p className="mt-1 text-sm text-[#d8caa9]">
              {track.channel ?? "канал неизвестен"} · {formatDuration(track.duration_sec)}
            </p>
            <p className="mt-1 text-xs tracking-[0.2em] text-[#e9c46a] uppercase">
              {track.cache_state ?? "none"} · fails {String(track.fail_count ?? 0)} · #
              {String(track.id)}
            </p>
          </div>
          <div className="flex flex-wrap items-center gap-2 lg:justify-end">
            <Action
              disabled={busy}
              onClick={() => onAction("enqueue", track.id)}
              label="Следующим"
            />
            <Action
              disabled={busy}
              onClick={() => onAction("play-now", track.id)}
              label="Играть сейчас"
              primary
            />
            <Action
              disabled={busy}
              onClick={() => onAction("retry", track.id)}
              label="Перекачать аудио"
            />
            {track.deleted_at ? (
              <Action
                disabled={busy}
                onClick={() => onAction("restore", track.id)}
                label="Вернуть из бана"
              />
            ) : (
              <Action
                disabled={busy}
                onClick={() => onAction("ban", track.id)}
                label="В бан"
                danger
              />
            )}
          </div>
        </article>
      ))}
    </div>
  );
}

function Action({
                  label,
                  disabled,
                  onClick,
                  primary,
                  danger
                }: {
  label: string;
  disabled: boolean;
  onClick: () => void;
  primary?: boolean;
  danger?: boolean;
}) {
  const color = danger
    ? "bg-[#e76f51] text-[#230c06]"
    : primary
      ? "bg-[#e9c46a] text-[#102225]"
      : "bg-white/10 text-[#f5efe0]";
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={onClick}
      className={`rounded-xl px-3 py-2 text-sm font-black ${color} disabled:opacity-60`}
    >
      {label}
    </button>
  );
}

function QueueList({entries, empty}: { entries: QueueEntry[]; empty: string }) {
  if (entries.length === 0) {
    return <p className="rounded-2xl bg-white/10 p-5 text-[#d8caa9]">{empty}</p>;
  }
  return (
    <div className="grid gap-3">
      {entries.map((entry) => (
        <article key={entry.queue_item.id} className="rounded-2xl bg-[#0d2023] p-4">
          <p className="font-black">{trackTitle(entry.track)}</p>
          <p className="text-sm text-[#d8caa9]">{entry.queue_item.status ?? "?"}</p>
        </article>
      ))}
    </div>
  );
}

function OfferList({offers}: { offers: Offer[] }) {
  if (offers.length === 0) {
    return <p className="rounded-2xl bg-white/10 p-5 text-[#d8caa9]">Новых предложений нет</p>;
  }
  return (
    <div className="grid gap-3">
      {offers.map((offer) => (
        <article key={offer.id} className="rounded-2xl bg-[#0d2023] p-4">
          <p className="font-black break-all">{offer.youtube_url}</p>
          <p className="mt-1 text-sm text-[#d8caa9]">
            {offer.submitted_by ?? "аноним"} · {offer.note ?? "без заметки"}
          </p>
        </article>
      ))}
    </div>
  );
}

function Message({tone, text}: { tone: "error" | "notice"; text: string }) {
  const color =
    tone === "error"
      ? "border-[#e76f51] bg-[#35130b] text-[#ffd1c2]"
      : "border-[#2a9d8f] bg-[#0e342f] text-[#bff1e8]";
  return <p className={`mt-5 rounded-2xl border px-4 py-3 font-bold ${color}`}>{text}</p>;
}

function errorMessage(error: unknown): string {
  if (error instanceof MissingAdminTokenError) {
    return "Введите admin token";
  }
  return error instanceof Error ? error.message : String(error);
}

const appRoot = document.getElementById("app");
if (appRoot === null) {
  throw new Error("Missing #app mount point");
}

render(<App/>, appRoot);
