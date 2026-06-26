export function registerServiceWorker(): void {
  if (!("serviceWorker" in navigator)) {
    return;
  }

  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {
      // PWA installability is useful but playback must not depend on it.
    });
  });
}
