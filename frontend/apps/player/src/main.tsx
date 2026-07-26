import {type CurrentResponse, defaultApiBase, RadioApiClient} from "@radio/api";
import {useCallback, useEffect, useReducer, useRef, useState} from "preact/hooks";
import {render} from "preact";

import "../../shared/styles.css";
import {attachHls, type HlsAttachment} from "./hls";
import {updateMediaSession} from "./mediaSession";
import {registerServiceWorker} from "./pwa";
import {initialPlayerState, playerReducer} from "./state";
import {metadataTitle} from "./metadata";

// Use the stable edge-compatible rendition instead of switching to a larger
// fMP4 variant mid-stream and risking a truncated segment on the proxy path.
export const STREAM_URL = "/hls/mp4/v64k/index.m3u8";
const api = new RadioApiClient({baseUrl: defaultApiBase()});

function App() {
  const audioRef = useRef<HTMLAudioElement>(null);
  const hlsRef = useRef<HlsAttachment | null>(null);
  const [state, dispatch] = useReducer(playerReducer, initialPlayerState);
  const [current, setCurrent] = useState<CurrentResponse | null>(null);
  const [volume, setVolume] = useState(1);

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
      updateMediaSession({
        title: metadataTitle(next),
        onPlay: () => {
          void play();
        },
        onPause: pause
      });
    } catch {
      // Metadata is optional; playback remains usable when the API is unavailable.
    }
  }, [pause, play]);

  useEffect(() => {
    registerServiceWorker();
    void loadCurrent();
    const timer = window.setInterval(() => void loadCurrent(), 20_000);
    const handleOffline = () => {
      dispatch({type: "offline"});
    };
    window.addEventListener("offline", handleOffline);
    return () => {
      window.clearInterval(timer);
      window.removeEventListener("offline", handleOffline);
      hlsRef.current?.detach();
    };
  }, [loadCurrent]);

  useEffect(() => {
    if (audioRef.current) {
      audioRef.current.volume = volume;
    }
  }, [volume]);

  const title = metadataTitle(current);

  return (
    <main className="grid min-h-screen place-items-center bg-[#12110d] px-5 text-[#f7f1df]">
      <section
        className="w-full max-w-xl rounded-[2rem] border border-white/15 bg-[linear-gradient(145deg,#20251d,#0e1f23)] p-6 shadow-2xl sm:p-8">
        <h1 className="text-center text-3xl leading-tight font-black tracking-[-0.06em] sm:text-5xl">
          {title}
        </h1>
        <audio
          aria-label="Живой аудиопоток"
          ref={audioRef}
          onPause={() => dispatch({type: "pause"})}
          onPlaying={() => dispatch({type: "play"})}
        />
        <div className="mt-8 flex items-center gap-5">
          <button
            type="button"
            onClick={state.status === "playing" ? pause : () => void play()}
            className="grid size-16 shrink-0 place-items-center rounded-full bg-[#ffd166] text-2xl font-black text-[#12110d] shadow-xl transition hover:scale-105"
            aria-label={state.status === "playing" ? "Пауза" : "Играть"}
          >
            {state.status === "playing" ? "II" : "▶"}
          </button>
          <label className="flex min-w-0 flex-1 items-center gap-3" aria-label="Громкость">
            <span aria-hidden="true" className="text-xs font-black tracking-[0.18em]">
              VOL
            </span>
            <input
              type="range"
              min="0"
              max="1"
              step="0.01"
              value={volume}
              onInput={(event) => setVolume(Number(event.currentTarget.value))}
              className="w-full accent-[#ffd166]"
            />
          </label>
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
