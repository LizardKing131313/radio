import type {CurrentResponse} from "@radio/api";
import {trackTitle} from "@radio/ui";

const UNKNOWN_VALUES = new Set([
  "",
  "na",
  "n/a",
  "n.a.",
  "unknown",
  "unknown artist",
  "unknown title",
  "none",
  "null",
  "нет данных",
  "без названия"
]);

function cleanPart(value?: string | null): string {
  return (value ?? "")
    .replace(/#[\p{L}\p{N}_-]+/gu, "")
    .replace(/\s+/g, " ")
    .replace(/\s+([,.;:!?])/g, "$1")
    .replace(/^[\s\-–—|:]+|[\s\-–—|:]+$/g, "")
    .trim();
}

function isUnknown(value: string): boolean {
  return UNKNOWN_VALUES.has(value.toLocaleLowerCase());
}

function cleanComposite(value?: string | null): string {
  const parts = cleanPart(value)
    .split(/\s+[-–—|]\s+/)
    .map(cleanPart)
    .filter((part) => !isUnknown(part));
  return parts.join(" - ");
}

export function metadataTitle(current: CurrentResponse | null): string {
  if (current?.queue?.track) {
    return cleanComposite(trackTitle(current.queue.track)) || "Живой эфир";
  }

  const source = current?.now_playing?.source;
  const title = cleanPart(source?.title);
  const artist = cleanPart(source?.artist);
  if (!isUnknown(artist) && !isUnknown(title)) {
    return `${artist} - ${title}`;
  }
  if (!isUnknown(title)) {
    return title;
  }
  if (!isUnknown(artist)) {
    return artist;
  }

  return cleanComposite(source?.line) || "Живой эфир";
}
