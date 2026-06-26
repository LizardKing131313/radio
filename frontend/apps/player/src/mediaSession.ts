export interface MediaSessionInput {
  title: string;
  artist?: string;
  artwork?: string;
  onPlay: () => void;
  onPause: () => void;
}

export function updateMediaSession(input: MediaSessionInput): void {
  if (!("mediaSession" in navigator)) {
    return;
  }

  navigator.mediaSession.metadata = new MediaMetadata({
    title: input.title,
    artist: input.artist ?? "Radio",
    artwork: input.artwork
      ? [{src: input.artwork, sizes: "512x512", type: "image/svg+xml"}]
      : [{src: "/icons/icon-512.svg", sizes: "512x512", type: "image/svg+xml"}]
  });
  navigator.mediaSession.setActionHandler("play", input.onPlay);
  navigator.mediaSession.setActionHandler("pause", input.onPause);
}
