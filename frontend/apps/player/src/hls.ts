export interface HlsAttachment {
  detach: () => void;
}

const HLS_MIME = "application/vnd.apple.mpegurl";

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
    lowLatencyMode: true,
    liveSyncDurationCount: 2,
    liveMaxLatencyDurationCount: 4,
    maxLiveSyncPlaybackRate: 1.25,
    backBufferLength: 10
  });
  hls.loadSource(streamUrl);
  hls.attachMedia(audio);
  return {
    detach: () => hls.destroy()
  };
}
