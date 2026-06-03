/**
 * room.js — Lobby management
 */
import { GameSocket } from "./websocket.js";
import { api }        from "./api.js";

// ── Session helpers ─────────────────────────────────────────────────────────

function saveSession(roomCode, playerId, nickname) {
  sessionStorage.setItem("roomCode",  roomCode);
  sessionStorage.setItem("playerId",  playerId);
  sessionStorage.setItem("nickname",  nickname);
}

function loadSession() {
  return {
    roomCode: sessionStorage.getItem("roomCode"),
    playerId: sessionStorage.getItem("playerId"),
    nickname: sessionStorage.getItem("nickname"),
  };
}

// ── Toast ─────────────────────────────────────────────────────────────────────

function toast(msg, type = "info") {
  const c = document.getElementById("toast-container");
  const t = document.createElement("div");
  t.className = `toast toast--${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ── DOM helpers ───────────────────────────────────────────────────────────────

function $(sel) { return document.querySelector(sel); }

// ── Main ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const createForm = $("#create-form");
  const joinForm   = $("#join-form");

  // ── Create room ───────────────────────────────────────────────────────────
  createForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nickname    = $("#create-nickname").value.trim();
    const wordLength  = parseInt($("#word-length").value);
    const maxAttempts = parseInt($("#max-attempts").value);

    if (!nickname) { toast("Ingresá tu apodo", "error"); return; }

    const btn = createForm.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      const { room_code, player_id } = await api.createRoom(nickname, wordLength, maxAttempts);
      saveSession(room_code, player_id, nickname);
      location.href = `/room.html`;
    } catch (err) {
      toast(err.message, "error");
    } finally {
      btn.disabled = false;
    }
  });

  // ── Join room ─────────────────────────────────────────────────────────────
  joinForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    const nickname = $("#join-nickname").value.trim();
    const code     = $("#room-code-input").value.trim().toUpperCase();

    if (!nickname) { toast("Ingresá tu apodo", "error"); return; }
    if (!code)     { toast("Ingresá el código de sala", "error"); return; }

    const btn = joinForm.querySelector("button[type=submit]");
    btn.disabled = true;
    try {
      const { room_code, player_id } = await api.joinRoom(code, nickname);
      saveSession(room_code, player_id, nickname);
      location.href = `/room.html`;
    } catch (err) {
      toast(err.message, "error");
    } finally {
      btn.disabled = false;
    }
  });

  // ── Check URL for ?code= param (invite link) ──────────────────────────────
  const urlCode = new URLSearchParams(location.search).get("code");
  if (urlCode) {
    const input = $("#room-code-input");
    if (input) input.value = urlCode.toUpperCase();
  }
});

// ── Lobby (room.html) ─────────────────────────────────────────────────────────

export function initLobby() {
  const { roomCode, playerId, nickname } = loadSession();
  if (!roomCode || !playerId) { location.href = "/"; return; }

  let socket = null;
  let roomState = null;

  // Display room code
  $("#room-code-display").textContent = roomCode;

  // Copy / share
  $("#copy-code").addEventListener("click", () => {
    const url = `${location.origin}/?code=${roomCode}`;
    navigator.clipboard.writeText(url).then(() => toast("¡Enlace copiado!", "success"));
  });

  // Connect WebSocket
  socket = new GameSocket(roomCode, playerId);

  socket.on("__connected__",     () => setStatus("connected"));
  socket.on("__disconnected__",  () => setStatus("disconnected"));
  socket.on("__max_retries__",   () => { setStatus("error"); toast("No se pudo reconectar", "error"); });

  socket.on("room_state",            (p) => renderRoom(p));
  socket.on("player_joined",         (p) => toast(`${p.nickname} se unió`, "info"));
  socket.on("player_left",           (p) => toast(`${p.nickname} salió`, "info"));
  socket.on("player_reconnected",    (p) => toast(`${p.nickname} volvió`, "info"));
  socket.on("host_changed",          (p) => { toast(`${p.nickname} es el nuevo host`, "info"); renderHostControls(); });
  socket.on("room_settings_updated", (p) => { toast("Configuración actualizada", "info"); });

  socket.on("game_starting", (p) => {
    // Navigate to game when countdown finishes
    setTimeout(() => { location.href = "/game.html"; }, (p.countdown + 0.5) * 1000);
    showCountdown(p.countdown);
  });

  socket.connect();

  // Start game (host only)
  $("#start-btn")?.addEventListener("click", () => {
    socket.send("start_game");
  });

  // Settings (host only)
  $("#settings-form")?.addEventListener("submit", (e) => {
    e.preventDefault();
    socket.send("update_settings", {
      word_length:  parseInt($("#s-word-length").value),
      max_attempts: parseInt($("#s-max-attempts").value),
    });
  });

  function renderRoom(state) {
    roomState = state;
    const list = $("#player-list");
    list.innerHTML = "";
    state.players.forEach(p => {
      const li = document.createElement("li");
      li.className = `player-item${p.id === playerId ? " player-item--you" : ""}`;
      li.innerHTML = `
        <span class="player-item__dot ${p.connected ? "player-item__dot--online" : "player-item__dot--offline"}"></span>
        <span class="player-item__name">${p.nickname}${p.id === playerId ? " (vos)" : ""}</span>
        ${p.is_host ? '<span class="player-item__badge player-item__badge--host">host</span>' : ""}
      `;
      list.appendChild(li);
    });
    renderHostControls(state);
  }

  function renderHostControls(state = roomState) {
    if (!state) return;
    const isHost = state.players.find(p => p.id === playerId)?.is_host;
    const startBtn = $("#start-btn");
    const settingsPanel = $("#settings-panel");
    if (startBtn) startBtn.classList.toggle("hidden", !isHost);
    if (settingsPanel) settingsPanel.classList.toggle("hidden", !isHost);
  }

  function setStatus(s) {
    const dot   = $("#status-dot");
    const label = $("#status-label");
    if (!dot) return;
    dot.className   = `status-dot status-dot--${s === "connected" ? "connected" : "error"}`;
    label.textContent = s === "connected" ? "Conectado" : "Reconectando...";
  }

  function showCountdown(seconds) {
    const overlay = $("#countdown-overlay");
    if (!overlay) return;
    overlay.classList.remove("hidden");
    const num = overlay.querySelector(".countdown-overlay__number");
    let remaining = seconds;
    num.textContent = remaining;
    const iv = setInterval(() => {
      remaining--;
      num.textContent = remaining > 0 ? remaining : "¡Ya!";
      if (remaining <= 0) clearInterval(iv);
    }, 1000);
  }
}
