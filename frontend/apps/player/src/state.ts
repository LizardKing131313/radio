export type PlayerStatus = "idle" | "loading" | "playing" | "paused" | "offline" | "error";

export interface PlayerState {
  status: PlayerStatus;
  message: string;
}

export type PlayerEvent =
  | { type: "load" }
  | { type: "play" }
  | { type: "pause" }
  | { type: "offline" }
  | { type: "error"; message: string };

export const initialPlayerState: PlayerState = {
  status: "idle",
  message: "Готов к запуску"
};

export function playerReducer(state: PlayerState, event: PlayerEvent): PlayerState {
  switch (event.type) {
    case "load":
      return {status: "loading", message: "Подключаю поток"};
    case "play":
      return {status: "playing", message: "В эфире"};
    case "pause":
      return {status: "paused", message: "Пауза"};
    case "offline":
      return {status: "offline", message: "Нет сети: эфир и метаданные недоступны"};
    case "error":
      return {status: "error", message: event.message};
    default:
      return state;
  }
}
