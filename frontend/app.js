const CFG = window.APP_CONFIG || {};
//const API = "/api";   // same-origin, relative - nginx reverse-proxies this to the backend internally
const API = "";   // same-origin, relative - nginx reverse-proxies /api and /version internally

const listEl = document.getElementById("todo-list");
const formEl = document.getElementById("todo-form");
const inputEl = document.getElementById("new-title");
const statusEl = document.getElementById("status-msg");
const statsEl = document.getElementById("stats");
const logEl = document.getElementById("practice-log");

// ---- banner ----
document.getElementById("banner").style.background = CFG.FRONTEND_COLOR || "#4F46E5";
document.getElementById("version-badge").textContent = `FRONTEND ${CFG.FRONTEND_VERSION || "v1.0.0"}`;
document.getElementById("color-badge").textContent = `COLOR ${CFG.FRONTEND_COLOR_NAME || "indigo"}`;

async function loadBackendVersion() {
  try {
    const res = await fetch(`/version`);
    const data = await res.json();
    document.getElementById("pod-badge").textContent = `BACKEND ${data.version} / ${data.pod}`;
  } catch (e) {
    document.getElementById("pod-badge").textContent = "BACKEND unreachable";
  }
}

// ---- helpers ----
function showError(msg) {
  statusEl.textContent = msg;
  setTimeout(() => { statusEl.textContent = ""; }, 4000);
}

function logLine(msg) {
  const time = new Date().toLocaleTimeString();
  logEl.textContent += `[${time}] ${msg}\n`;
  logEl.scrollTop = logEl.scrollHeight;
}

// ---- CRUD ----
async function fetchTodos() {
  try {
    const res = await fetch(`${API}/api/todos`);
    if (!res.ok) throw new Error(`GET /api/todos -> ${res.status}`);
    const todos = await res.json();
    renderTodos(todos);
  } catch (e) {
    showError("Could not load todos - is the backend reachable?");
  }
}

function renderTodos(todos) {
  listEl.innerHTML = "";
  let doneCount = 0;

  todos.forEach((todo) => {
    if (todo.done) doneCount++;

    const li = document.createElement("li");
    li.className = "todo-item" + (todo.done ? " done" : "");

    const checkbox = document.createElement("input");
    checkbox.type = "checkbox";
    checkbox.checked = todo.done;
    checkbox.addEventListener("change", () => toggleDone(todo.id, checkbox.checked));

    const title = document.createElement("span");
    title.className = "title";
    title.textContent = todo.title;
    title.contentEditable = "true";
    title.addEventListener("blur", () => {
      const newTitle = title.textContent.trim();
      if (newTitle && newTitle !== todo.title) {
        updateTitle(todo.id, newTitle);
      } else {
        title.textContent = todo.title;
      }
    });
    title.addEventListener("keydown", (e) => {
      if (e.key === "Enter") { e.preventDefault(); title.blur(); }
    });

    const delBtn = document.createElement("button");
    delBtn.className = "delete-btn";
    delBtn.textContent = "✕";
    delBtn.title = "Delete task";
    delBtn.addEventListener("click", () => deleteTodo(todo.id));

    li.append(checkbox, title, delBtn);
    listEl.appendChild(li);
  });

  statsEl.textContent = `${todos.length} task(s) total · ${doneCount} done · ${todos.length - doneCount} pending`;
}

async function addTodo(title) {
  try {
    const res = await fetch(`${API}/api/todos`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) throw new Error(`POST /api/todos -> ${res.status}`);
    await fetchTodos();
  } catch (e) {
    showError("Could not create task");
  }
}

async function toggleDone(id, done) {
  try {
    const res = await fetch(`${API}/api/todos/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ done }),
    });
    if (!res.ok) throw new Error(`PUT /api/todos/${id} -> ${res.status}`);
    await fetchTodos();
  } catch (e) {
    showError("Could not update task");
  }
}

async function updateTitle(id, title) {
  try {
    const res = await fetch(`${API}/api/todos/${id}`, {
      method: "PUT",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ title }),
    });
    if (!res.ok) throw new Error(`PUT /api/todos/${id} -> ${res.status}`);
    await fetchTodos();
  } catch (e) {
    showError("Could not rename task");
  }
}

async function deleteTodo(id) {
  try {
    const res = await fetch(`${API}/api/todos/${id}`, { method: "DELETE" });
    if (!res.ok) throw new Error(`DELETE /api/todos/${id} -> ${res.status}`);
    await fetchTodos();
  } catch (e) {
    showError("Could not delete task");
  }
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  const title = inputEl.value.trim();
  if (!title) return;
  addTodo(title);
  inputEl.value = "";
});

// ---- practice panel: fire test traffic at the backend ----
document.querySelectorAll(".btn-row button").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const action = btn.dataset.action;
    try {
      if (action === "status") {
        const code = btn.dataset.code;
        const res = await fetch(`${API}/api/simulate/status/${code}`);
        logLine(`GET /api/simulate/status/${code} -> ${res.status}`);
      } else if (action === "error") {
        const res = await fetch(`${API}/api/simulate/error`);
        logLine(`GET /api/simulate/error -> ${res.status}`);
      } else if (action === "slow") {
        const delay = btn.dataset.delay;
        logLine(`GET /api/simulate/slow?delay=${delay} ... waiting`);
        const start = performance.now();
        const res = await fetch(`${API}/api/simulate/slow?delay=${delay}`);
        const took = Math.round(performance.now() - start);
        logLine(`GET /api/simulate/slow?delay=${delay} -> ${res.status} (${took}ms)`);
      } else if (action === "burst") {
        logLine("Firing 50 mixed requests...");
        for (let i = 0; i < 50; i++) {
          fetch(`${API}/api/simulate/random`)
            .then((res) => logLine(`  random -> ${res.status}`))
            .catch(() => logLine("  random -> failed"));
          await new Promise((r) => setTimeout(r, 60));
        }
      }
    } catch (e) {
      logLine(`Request failed: ${e.message}`);
    }
  });
});

// ---- init ----
loadBackendVersion();
fetchTodos();
setInterval(fetchTodos, 15000); // light auto-refresh so multiple browser tabs stay in sync
