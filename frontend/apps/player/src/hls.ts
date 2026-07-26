export interface HlsAttachment {
  detach: () => void;
}

const HLS_MIME = "application/vnd.apple.mpegurl";

export const HLS_OPTIONS = {
  lowLatencyMode: false,
  liveSyncDurationCount: 6,
  liveMaxLatencyDurationCount: 14,
  maxLiveSyncPlaybackRate: 1.25,
  maxBufferLength: 30,
  backBufferLength: 30
} as const;

export function recoverFatalHlsError(
  hls: { startLoad: () => void; recoverMediaError: () => void; destroy: () => void },
  audio: HTMLAudioElement,
  data: { fatal?: boolean; type: string },
  errorTypes: { NETWORK_ERROR: string; MEDIA_ERROR: string }
) {
  if (!data.fatal) {
    return;
  }
  if (data.type === errorTypes.NETWORK_ERROR) {
    hls.startLoad();
    return;
  }
  if (data.type === errorTypes.MEDIA_ERROR) {
    hls.recoverMediaError();
    return;
  }
  hls.destroy();
  audio.removeAttribute("src");
  audio.load();
}

export async function attachHls(
  audio: HTMLAudioElement,
  streamUrl: string
): Promise<HlsAttachment> {
  if (audio.canPlayType(HLS_MIME)) {
    audio.src = streamUrl;
    return {
      detach: () => {
        audio.removeAttribute("src");
        audio.load();
      }
    };
  }

  const Hls = (await import("hls.js")).default;
  if (!Hls.isSupported()) {
    throw new Error("Этот браузер не поддерживает HLS playback");
  }

  const hls = new Hls({
    // Keep enough live buffer for the edge/Cloudflare hop; ultra-low latency
    // stalls when a playlist refresh arrives a little late.
    ...HLS_OPTIONS
  });
  hls.on(Hls.Events.ERROR, (_event, data) => {
    recoverFatalHlsError(hls, audio, data, Hls.ErrorTypes);
  });
  hls.loadSource(streamUrl);
  hls.attachMedia(audio);
  return {
    detach: () => hls.destroy()
  };
}
