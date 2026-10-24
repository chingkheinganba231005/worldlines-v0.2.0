// Cached JSON loading from the static API (./data/*.json).
const cache = new Map();

export function load(path) {
  if (!cache.has(path)) {
    const request = fetch(`data/${path}`, { cache: path === "latest.json" || path === "meta.json" ? "no-cache" : "default" })
      .then((response) => {
        if (!response.ok) throw new Error(`Could not load ${path} (HTTP ${response.status}).`);
        return response.json();
      })
      .catch((error) => {
        cache.delete(path);
        throw error;
      });
    cache.set(path, request);
  }
  return cache.get(path);
}

export const FAMILY_LABELS = {
  cooperation: "Aid & cooperation", diplomacy: "Diplomacy", statements: "Statements",
  disputes: "Criticism & threats", protest: "Protests", coercion: "Coercion", violence: "Violence",
};
// Display order runs from cooperation to conflict (the diverging axis).
export const FAMILY_ORDER = ["cooperation", "diplomacy", "statements", "disputes", "protest", "coercion", "violence"];
