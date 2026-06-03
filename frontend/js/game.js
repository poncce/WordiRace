/**
 * game.js — in-game logic
 * Wordle board rendering, keyboard input, WebSocket events.
 */
import { GameSocket } from "./websocket.js";

// ── State ─────────────────────────────────────────────────────────────────────

let socket      = null;
let gameState   = {
  wordLength:   5,
  maxAttempts:  6,
  currentRow:   0,
  currentCol:   0,
  guesses:      [],       // [{word, feedback}]
  currentInput: [],
  finished:     false,
  won:          false,
};
let players     = {};     // id → player object
let myPlayerId  = null;

// ── Session ───────────────────────────────────────────────────────────────────

function loadSession() {
  return {
    roomCode: sessionStorage.getItem("roomCode"),
    playerId: sessionStorage.getItem("playerId"),
    nickname: sessionStorage.getItem("nickname"),
  };
}

// ── DOM helpers ────────────────────────────────────────────────────────────────

function $(sel)  { return document.querySelector(sel); }
function $$(sel) { return [...document.querySelectorAll(sel)]; }

function toast(msg, type = "info") {
  const c = document.getElementById("toast-container");
  const t = document.createElement("div");
  t.className = `toast toast--${type}`;
  t.textContent = msg;
  c.appendChild(t);
  setTimeout(() => t.remove(), 3500);
}

// ── Board ──────────────────────────────────────────────────────────────────────

function buildBoard() {
  const board = $("#board");
  board.innerHTML = "";
  for (let r = 0; r < gameState.maxAttempts; r++) {
    const row = document.createElement("div");
    row.className = "board__row";
    row.id = `row-${r}`;
    for (let c = 0; c < gameState.wordLength; c++) {
      const cell = document.createElement("div");
      cell.className = "cell";
      cell.id = `cell-${r}-${c}`;
      row.appendChild(cell);
    }
    board.appendChild(row);
  }
}

function renderCurrentInput() {
  for (let c = 0; c < gameState.wordLength; c++) {
    const cell = $(`#cell-${gameState.currentRow}-${c}`);
    if (!cell) continue;
    const letter = gameState.currentInput[c] ?? "";
    cell.textContent = letter;
    cell.className   = letter ? "cell cell--filled" : "cell";
  }
}

function revealRow(rowIndex, feedback) {
  feedback.forEach((fb, c) => {
    const cell = $(`#cell-${rowIndex}-${c}`);
    if (!cell) return;
    // Stagger via CSS animation-delay already set on nth-child
    setTimeout(() => {
      cell.textContent = fb.letter;
      cell.className   = `cell cell--${fb.result}`;
    }, c * 110);
    // Update keyboard after last letter reveals
    if (c === feedback.length - 1) {
      setTimeout(() => updateKeyboard(feedback), c * 110 + 200);
    }
  });
}

// ── Keyboard ───────────────────────────────────────────────────────────────────

const KEYBOARD_ROWS = [
  ["Q","W","E","R","T","Y","U","I","O","P"],
  ["A","S","D","F","G","H","J","K","L","Ñ"],
  ["ENTER","Z","X","C","V","B","N","M","⌫"],
];

const keyState = {};   // letter → "correct" | "present" | "absent"

function buildKeyboard() {
  const kb = $("#keyboard");
  kb.innerHTML = "";
  KEYBOARD_ROWS.forEach(row => {
    const rowEl = document.createElement("div");
    rowEl.className = "keyboard__row";
    row.forEach(key => {
      const btn = document.createElement("button");
      btn.className = `key${key.length > 1 ? " key--wide" : ""}`;
      btn.textContent = key;
      btn.dataset.key = key;
      btn.addEventListener("click", () => handleKey(key));
      rowEl.appendChild(btn);
    });
    kb.appendChild(rowEl);
  });
}

function updateKeyboard(feedback) {
  const priority = { correct: 3, present: 2, absent: 1 };
  feedback.forEach(fb => {
    const cur = keyState[fb.letter];
    if (!cur || priority[fb.result] > priority[cur]) {
      keyState[fb.letter] = fb.result;
    }
  });
  $$(".key").forEach(btn => {
    const state = keyState[btn.dataset.key];
    btn.className = `key${btn.dataset.key.length > 1 ? " key--wide" : ""}${state ? ` key--${state}` : ""}`;
  });
}

// ── Input handling ─────────────────────────────────────────────────────────────

function handleKey(key) {
  if (gameState.finished) return;

  if (key === "⌫" || key === "Backspace") {
    if (gameState.currentCol > 0) {
      gameState.currentCol--;
      gameState.currentInput.pop();
      renderCurrentInput();
    }
    return;
  }

  if (key === "ENTER" || key === "Enter") {
    submitGuess();
    return;
  }

  // Letter
  if (/^[A-ZÑ]$/i.test(key) && gameState.currentCol < gameState.wordLength) {
    gameState.currentInput.push(key.toUpperCase());
    gameState.currentCol++;
    renderCurrentInput();
  }
}

async function submitGuess() {
  if (gameState.currentInput.length !== gameState.wordLength) {
    shakeRow(gameState.currentRow);
    toast("Completá la palabra", "error");
    return;
  }
  const word = gameState.currentInput.join("");
  const sent = socket.send("submit_guess", { word });
  if (!sent) {
    toast("Sin conexión con el servidor", "error");
  }
}

function shakeRow(rowIndex) {
  const row = $(`#row-${rowIndex}`);
  if (!row) return;
  row.style.animation = "none";
  requestAnimationFrame(() => {
    row.style.animation = "shake 0.4s ease";
  });
}

// ── Players sidebar ─────────────────────────────────────────────────────────────

function renderPlayers() {
  const panel = $("#players-panel");
  if (!panel) return;
  panel.innerHTML = "";
  Object.values(players).forEach(p => {
    const isMe = p.id === myPlayerId;
    const div = document.createElement("div");
    div.className = [
      "player-progress",
      isMe ? "player-progress--you" : "",
      p.won ? "player-progress--won" : "",
      p.finished && !p.won ? "player-progress--finished" : "",
    ].join(" ");

    const dots = Array.from({ length: gameState.maxAttempts }, (_, i) => {
      const cls = i < p.guesses_count
        ? (p.won && i === p.guesses_count - 1 ? "attempt-dot attempt-dot--won" : "attempt-dot attempt-dot--used")
        : "attempt-dot";
      return `<span class="${cls}"></span>`;
    }).join("");

    div.innerHTML = `
      <div class="player-progress__name">
        <span>${p.nickname}${isMe ? " (vos)" : ""}</span>
        <span class="text-dim">${p.finished ? (p.won ? "✓" : "✗") : `${p.guesses_count}/${gameState.maxAttempts}`}</span>
      </div>
      <div class="player-progress__attempts">${dots}</div>
    `;
    panel.appendChild(div);
  });
}

// ── WebSocket events ──────────────────────────────────────────────────────────

function handleRoomState(state) {
  gameState.wordLength  = state.game?.word_length  ?? gameState.wordLength;
  gameState.maxAttempts = state.game?.max_attempts ?? gameState.maxAttempts;
  state.players.forEach(p => { players[p.id] = p; });
  renderPlayers();
  // Rebuild board if game already started (we joined late)
  if (state.game?.status === "playing") {
    buildBoard();
    buildKeyboard();
  }
}

function handleGameStarted(payload) {
  gameState.wordLength  = payload.word_length;
  gameState.maxAttempts = payload.max_attempts;
  buildBoard();
  buildKeyboard();
}

function handleGuessResult(payload) {
  const row = gameState.currentRow;
  revealRow(row, payload.feedback);

  gameState.guesses.push({ word: payload.word, feedback: payload.feedback });
  gameState.currentRow++;
  gameState.currentCol   = 0;
  gameState.currentInput = [];

  if (payload.finished) {
    gameState.finished = true;
    gameState.won      = payload.won;
    // Update my player entry
    const me = players[myPlayerId];
    if (me) {
      me.guesses_count = gameState.currentRow;
      me.finished = true;
      me.won      = payload.won;
    }
  }
}

function handlePlayerGuessMade(payload) {
  const p = players[payload.player_id];
  if (p) {
    p.guesses_count = payload.attempt;
    renderPlayers();
  }
  toast(`${payload.nickname} intentó #${payload.attempt}`, "info");
}

function handlePlayerFinished(payload) {
  players[payload.id] = { ...players[payload.id], ...payload };
  renderPlayers();
  if (payload.won) {
    toast(`🏆 ${payload.nickname} adivinó!`, "success");
  }
}

function handleGameFinished(payload) {
  setTimeout(() => showEndModal(payload), 1000);
}

function showEndModal(payload) {
  const modal = $("#end-modal");
  if (!modal) return;

  const me = players[myPlayerId];
  const won = me?.won;

  $("#modal-title").textContent  = won ? "¡GANASTE!" : "FIN DEL JUEGO";
  $("#modal-word").textContent   = payload.secret_word;
  $("#modal-title").style.color  = won ? "var(--green)" : "var(--danger)";

  const list = $("#modal-ranking");
  list.innerHTML = "";
  (payload.ranking ?? []).forEach((p, i) => {
    const li = document.createElement("li");
    li.className = "ranking-item";
    li.innerHTML = `
      <span class="ranking-item__pos${i === 0 ? " ranking-item__pos--first" : ""}">#${i + 1}</span>
      <span>${p.nickname}</span>
      <span class="text-dim">${p.guesses_count} intentos</span>
    `;
    list.appendChild(li);
  });

  modal.classList.remove("hidden");
}

// ── Keyboard capture (hidden input) ────────────────────────────────────────────
// Using a hidden <input> so the page captures keystrokes even when
// screen-recording overlays (ALT+F9, etc.) steal focus from the document.

const hiddenInput = document.getElementById("hidden-input");

function focusInput() {
  if (hiddenInput && document.activeElement !== hiddenInput) {
    hiddenInput.focus();
  }
}

hiddenInput?.addEventListener("keydown", (e) => {
  if (e.ctrlKey || e.altKey || e.metaKey) return;
  e.preventDefault();
  if (e.key === "Enter")         handleKey("Enter");
  else if (e.key === "Backspace") handleKey("Backspace");
  else if (/^[a-zA-ZñÑ]$/.test(e.key)) handleKey(e.key.toUpperCase());
});

// Keep focus on the hidden input — refocus on any focus loss
hiddenInput?.addEventListener("blur", () => setTimeout(focusInput, 10));
document.addEventListener("focusin", focusInput);

// ── Init ──────────────────────────────────────────────────────────────────────

document.addEventListener("DOMContentLoaded", () => {
  const { roomCode, playerId, nickname } = loadSession();
  if (!roomCode || !playerId) { location.href = "/"; return; }

  myPlayerId = playerId;

  socket = new GameSocket(roomCode, playerId);

  socket.on("__connected__",    () => setStatus("connected"));
  socket.on("__disconnected__", () => setStatus("disconnected"));
  socket.on("__max_retries__",  () => { setStatus("error"); toast("Conexión perdida", "error"); });

  socket.on("room_state",         handleRoomState);
  socket.on("game_started",       handleGameStarted);
  socket.on("guess_result",       handleGuessResult);
  socket.on("player_guess_made",  handlePlayerGuessMade);
  socket.on("player_finished",    handlePlayerFinished);
  socket.on("game_finished",      handleGameFinished);
  socket.on("player_joined",      (p) => { players[p.player_id] = p; renderPlayers(); });
  socket.on("player_left",        (p) => { if (players[p.player_id]) players[p.player_id].connected = false; renderPlayers(); });
  socket.on("error",              (p) => toast(p.detail, "error"));

  socket.connect();

  buildBoard();
  buildKeyboard();

  // Play again button
  $("#play-again-btn")?.addEventListener("click", () => { location.href = "/room.html"; });

  function setStatus(s) {
    const dot   = $("#status-dot");
    const label = $("#status-label");
    if (!dot) return;
    dot.className   = `status-dot status-dot--${s === "connected" ? "connected" : "error"}`;
    label.textContent = s === "connected" ? "Conectado" : "Reconectando...";
  }
});
