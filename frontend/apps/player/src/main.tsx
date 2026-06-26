import {type CurrentResponse, defaultApiBase, RadioApiClient} from "@radio/api";
import {queueLabel, trackTitle} from "@radio/ui";
import {useCallback, useEffect, useReducer, useRef, useState} from "preact/hooks";
import {render} from "preact";

import "../../shared/styles.css";
import {attachHls, type HlsAttachment} from "./hls";
import {updateMediaSession} from "./mediaSession";
import {registerServiceWorker} from "./pwa";
import {initialPlayerState, playerReducer} from "./state";

const STREAM_URL = "/hls/mp4/playlist.m3u8";
const api = new RadioApiClient({baseUrl: defaultApiBase()});

function metadataTitle(current: CurrentResponse | null): string {
  if (current?.queue?.track) {
    return trackTitle(current.queue.track);
  }
  const line = current?.now_playing?.source?.line?.trim();
  return line === undefined || line === "" ? "Живой эфир" : line;
}

function App() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const hlsRef = useRef<HlsAttachment | null>(null);
  const [state, dispatch] = useReducer(playerReducer, initialPlayerState);
  const [current, setCurrent] = useState<CurrentResponse | null>(null);
  const [metadataError, setMetadataError] = useState<string | null>(null);
  const [online, setOnline] = useState(navigator.onLine);

  const play = useCallback(async () => {
    const audio = audioRef.current;
    if (!audio) {
      return;
    }
    if (!navigator.onLine) {
      dispatch({type: "offline"});
      return;
    }
    try {
      dispatch({type: "load"});
      hlsRef.current ??= await attachHls(audio, STREAM_URL);
      await audio.play();
      dispatch({type: "play"});
    } catch (error) {
      dispatch({
        type: "error",
        message: error instanceof Error ? error.message : "Не удалось запустить эфир"
      });
    }
  }, []);

  const pause = useCallback(() => {
    audioRef.current?.pause();
    dispatch({type: "pause"});
  }, []);

  const loadCurrent = useCallback(async () => {
    try {
      const next = await api.current();
      setCurrent(next);
      setMetadataError(null);
      updateMediaSession({
        title: metadataTitle(next),
        onPlay: () => {
          void play();
        },
        onPause: pause
      });
    } catch (error) {
      setMetadataError(error instanceof Error ? error.message : String(error));
    }
  }, [pause, play]);

  useEffect(() => {
    registerServiceWorker();
    void loadCurrent();
    const timer = window.setInterval(() => void loadCurrent(), 20_000);
    const handleOnline = () => setOnline(true);
    const handleOffline = () => {
      setOnline(false);
      dispatch({type: "offline"});
    };
    window.addEventListener("online", handleOnline);
    window.addEventListener("offline", handleOffline);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("online", handleOnline);
      window.removeEventListener("offline", handleOffline);
      hlsRef.current?.detach();
    };
  }, [loadCurrent]);

  const title = metadataTitle(current);
  const queue = queueLabel(current?.queue ?? null);
  const hls = current?.now_playing?.hls;

  return (
    <main className="relative min-h-screen overflow-hidden bg-[#12110d] text-[#f7f1df]">
      <div
        className="absolute inset-0 z-0 bg-[radial-gradient(circle_at_15%_10%,rgba(231,111,81,.45),transparent_28%),radial-gradient(circle_at_85%_20%,rgba(42,157,143,.38),transparent_24%),linear-gradient(145deg,#12110d_0%,#20251d_48%,#0e1f23_100%)]"/>
      <section
        className="relative z-10 mx-auto flex min-h-screen max-w-6xl flex-col justify-between px-5 py-6 sm:px-8 lg:px-10">
        <header className="flex items-center justify-between gap-4">
          <div>
            <p className="text-xs tracking-[0.42em] text-[#ffd166] uppercase">online radio</p>
            <h1 className="mt-2 text-4xl font-black tracking-[-0.08em] sm:text-6xl">
              Громкий эфир
            </h1>
          </div>
          <div
            className={`rounded-full px-4 py-2 text-sm ${online ? "bg-[#2a9d8f]" : "bg-[#b42318]"}`}
          >
            {online ? "online" : "offline"}
          </div>
        </header>

        <div className="grid gap-6 py-10 lg:grid-cols-[1.15fr_.85fr] lg:items-end">
          <article className="rounded-[2rem] border border-white/15 bg-black/25 p-6 shadow-2xl backdrop-blur md:p-8">
            <p className="text-sm tracking-[0.32em] text-[#ffd166] uppercase">сейчас играет</p>
            <h2 className="mt-5 text-5xl leading-[0.9] font-black tracking-[-0.08em] sm:text-7xl">
              {title}
            </h2>
            <p className="mt-5 max-w-2xl text-lg text-[#d9d0b8]">{queue}</p>
            {metadataError ? (
              <p className="mt-4 rounded-xl border border-[#ffb088] bg-[#3a1710] px-4 py-3 text-[#ffd1c2]">
                Метаданные недоступны: {metadataError}
              </p>
            ) : null}
          </article>

          <aside className="rounded-[2rem] bg-[#f7f1df] p-6 text-[#12110d] shadow-2xl">
            <audio
              aria-label="Живой аудиопоток"
              ref={audioRef}
              onPause={() => dispatch({type: "pause"})}
              onPlaying={() => dispatch({type: "play"})}
            />
            <div className="flex items-center justify-between gap-4">
              <div>
                <p className="text-sm font-bold tracking-[0.25em] text-[#e76f51] uppercase">
                  player
                </p>
                <p className="mt-2 text-2xl font-black">{state.message}</p>
              </div>
              <button
                type="button"
                onClick={state.status === "playing" ? pause : () => void play()}
                className="grid size-24 place-items-center rounded-full bg-[#12110d] text-3xl font-black text-[#ffd166] shadow-xl transition hover:scale-105"
                aria-label={state.status === "playing" ? "Пауза" : "Играть"}
              >
                {state.status === "playing" ? "II" : "▶"}
              </button>
            </div>
            <dl className="mt-8 grid grid-cols-2 gap-4 text-sm">
              <div className="rounded-2xl bg-[#eadfbd] p-4">
                <dt className="tracking-[0.18em] text-[#735d2a] uppercase">HLS offset</dt>
                <dd className="mt-2 text-2xl font-black">{hls?.live_offset_sec ?? "?"}s</dd>
              </div>
              <div className="rounded-2xl bg-[#eadfbd] p-4">
                <dt className="tracking-[0.18em] text-[#735d2a] uppercase">age</dt>
                <dd className="mt-2 text-2xl font-black">{hls?.age_sec ?? "?"}s</dd>
              </div>
            </dl>
            <button
              type="button"
              onClick={() => void loadCurrent()}
              className="mt-6 w-full rounded-2xl border border-[#12110d] px-4 py-3 font-bold"
            >
              Обновить метаданные
            </button>
          </aside>
        </div>
      </section>
    </main>
  );
}

const appRoot = document.getElementById("app");
if (appRoot === null) {
  throw new Error("Missing #app mount point");
}

render(<App/>, appRoot);
