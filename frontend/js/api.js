/**
 * api.js — REST API client
 * All HTTP calls go through here.
 */
const API_BASE = "/api";

async function request(method, path, body = null) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body) opts.body = JSON.stringify(body);

  const res = await fetch(`${API_BASE}${path}`, opts);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    throw new Error(data.detail || `HTTP ${res.status}`);
  }
  return data;
}

export const api = {
  createRoom: (nickname, wordLength, maxAttempts) =>
    request("POST", "/rooms", { nickname, word_length: wordLength, max_attempts: maxAttempts }),

  joinRoom: (roomCode, nickname) =>
    request("POST", `/rooms/${roomCode}/join`, { nickname }),

  getRoom: (roomCode) =>
    request("GET", `/rooms/${roomCode}`),

  health: () =>
    request("GET", "/health"),
};
