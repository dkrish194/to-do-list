import os
import time
import uuid
import random
import logging
import json
from datetime import datetime, timezone

from flask import Flask, request, jsonify, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# ---------------------------------------------------------------------------
# Config (env vars - set these per-Deployment for k8s rollout practice)
# ---------------------------------------------------------------------------
APP_VERSION = os.environ.get("APP_VERSION", "v1.0.0")
APP_COLOR = os.environ.get("APP_COLOR", "#4F46E5")
APP_COLOR_NAME = os.environ.get("APP_COLOR_NAME", "indigo")
POD_NAME = os.environ.get("HOSTNAME", "local-dev")
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")  # tighten in real deployments

app = Flask(__name__)

# ---------------------------------------------------------------------------
# Structured JSON logging -> stdout (Filebeat/Fluent-bit ships this to ELK)
# ---------------------------------------------------------------------------
class JSONFormatter(logging.Formatter):
    def format(self, record):
        log_obj = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "level": record.levelname,
            "message": record.getMessage(),
            "app": "todo-backend",
            "version": APP_VERSION,
            "pod": POD_NAME,
        }
        if hasattr(record, "extra_fields"):
            log_obj.update(record.extra_fields)
        return json.dumps(log_obj)


logger = logging.getLogger("todo-backend")
logger.setLevel(logging.INFO)
_handler = logging.StreamHandler()
_handler.setFormatter(JSONFormatter())
logger.handlers = [_handler]
logger.propagate = False


def log_event(level, message, **fields):
    record = logging.LogRecord(
        name="todo-backend", level=level, pathname="", lineno=0,
        msg=message, args=(), exc_info=None,
    )
    record.extra_fields = fields
    logger.handle(record)


# ---------------------------------------------------------------------------
# Prometheus metrics
# ---------------------------------------------------------------------------
REQUEST_COUNT = Counter(
    "todo_backend_http_requests_total", "Total HTTP requests",
    ["method", "endpoint", "status"],
)
REQUEST_LATENCY = Histogram(
    "todo_backend_http_request_duration_seconds", "Request duration seconds",
    ["method", "endpoint"],
    buckets=(0.01, 0.05, 0.1, 0.25, 0.5, 1, 2, 5, 10, 20),
)
TODOS_GAUGE = Gauge("todo_backend_todos_total", "Current number of todos")
TODOS_DONE_GAUGE = Gauge("todo_backend_todos_done_total", "Current number of completed todos")
TODOS_CREATED = Counter("todo_backend_todos_created_total", "Total todos created")
TODOS_DELETED = Counter("todo_backend_todos_deleted_total", "Total todos deleted")
TODOS_UPDATED = Counter("todo_backend_todos_updated_total", "Total todos updated")
ERRORS_COUNT = Counter("todo_backend_errors_total", "Total error responses", ["status_code"])
BUILD_INFO = Gauge("todo_backend_build_info", "Build/version info", ["version", "color", "pod"])
BUILD_INFO.labels(version=APP_VERSION, color=APP_COLOR_NAME, pod=POD_NAME).set(1)

# ---------------------------------------------------------------------------
# In-memory store
# ---------------------------------------------------------------------------
todos = {}


def refresh_gauges():
    TODOS_GAUGE.set(len(todos))
    TODOS_DONE_GAUGE.set(sum(1 for t in todos.values() if t["done"]))


def seed():
    for title in ["Apply ServiceMonitor for backend", "Build RED dashboard in Grafana", "Ship logs to ELK"]:
        tid = str(uuid.uuid4())
        todos[tid] = {
            "id": tid, "title": title, "done": False,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
    refresh_gauges()


seed()

# ---------------------------------------------------------------------------
# CORS (manual - frontend runs as a separate Service/origin)
# ---------------------------------------------------------------------------
@app.after_request
def add_cors(response):
    response.headers["Access-Control-Allow-Origin"] = CORS_ORIGIN
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type"
    return response


@app.route("/api/<path:_any>", methods=["OPTIONS"])
def cors_preflight(_any):
    return "", 204


# ---------------------------------------------------------------------------
# Request timing / logging / metrics middleware
# ---------------------------------------------------------------------------
@app.before_request
def before():
    request.start_time = time.time()
    request.request_id = str(uuid.uuid4())[:8]


@app.after_request
def after(response):
    duration = time.time() - getattr(request, "start_time", time.time())
    endpoint = request.url_rule.rule if request.url_rule else request.path

    REQUEST_COUNT.labels(request.method, endpoint, response.status_code).inc()
    REQUEST_LATENCY.labels(request.method, endpoint).observe(duration)
    if response.status_code >= 400:
        ERRORS_COUNT.labels(str(response.status_code)).inc()

    level = logging.INFO
    if response.status_code >= 500:
        level = logging.ERROR
    elif response.status_code >= 400:
        level = logging.WARNING

    log_event(
        level, "http_request",
        request_id=getattr(request, "request_id", ""),
        method=request.method, path=request.path,
        status=response.status_code,
        duration_ms=round(duration * 1000, 2),
        remote_addr=request.remote_addr,
    )
    return response


# ---------------------------------------------------------------------------
# Meta endpoints
# ---------------------------------------------------------------------------
@app.route("/")
def index():
    return jsonify({
        "service": "todo-backend", "version": APP_VERSION, "pod": POD_NAME,
        "endpoints": ["/api/todos", "/health", "/ready", "/metrics", "/version", "/api/simulate/*"],
    }), 200


@app.route("/version")
def version():
    return jsonify({
        "version": APP_VERSION, "color": APP_COLOR,
        "color_name": APP_COLOR_NAME, "pod": POD_NAME,
    }), 200


@app.route("/health")
def health():
    return jsonify({"status": "ok", "version": APP_VERSION, "pod": POD_NAME}), 200


@app.route("/ready")
def ready():
    return jsonify({"status": "ready"}), 200


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------------
# CRUD API - real, used by the frontend
# ---------------------------------------------------------------------------
@app.route("/api/todos", methods=["GET"])
def list_todos():
    items = sorted(todos.values(), key=lambda t: t["created_at"])
    log_event(logging.INFO, "list_todos", count=len(items))
    return jsonify(items), 200


@app.route("/api/todos", methods=["POST"])
def create_todo():
    data = request.get_json(silent=True)
    if not data or not data.get("title", "").strip():
        log_event(logging.WARNING, "create_todo_bad_request")
        return jsonify({"error": "title is required"}), 400
    tid = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()
    todo = {
        "id": tid, "title": data["title"].strip(), "done": bool(data.get("done", False)),
        "created_at": now, "updated_at": now,
    }
    todos[tid] = todo
    refresh_gauges()
    TODOS_CREATED.inc()
    log_event(logging.INFO, "todo_created", todo_id=tid, title=todo["title"])
    return jsonify(todo), 201


@app.route("/api/todos/<todo_id>", methods=["GET"])
def get_todo(todo_id):
    todo = todos.get(todo_id)
    if not todo:
        log_event(logging.WARNING, "todo_not_found", todo_id=todo_id)
        return jsonify({"error": "not found"}), 404
    return jsonify(todo), 200


@app.route("/api/todos/<todo_id>", methods=["PUT"])
def update_todo(todo_id):
    todo = todos.get(todo_id)
    if not todo:
        log_event(logging.WARNING, "todo_not_found", todo_id=todo_id)
        return jsonify({"error": "not found"}), 404
    data = request.get_json(silent=True) or {}
    if "title" in data:
        if not data["title"].strip():
            return jsonify({"error": "title cannot be empty"}), 400
        todo["title"] = data["title"].strip()
    if "done" in data:
        todo["done"] = bool(data["done"])
    todo["updated_at"] = datetime.now(timezone.utc).isoformat()
    refresh_gauges()
    TODOS_UPDATED.inc()
    log_event(logging.INFO, "todo_updated", todo_id=todo_id)
    return jsonify(todo), 200


@app.route("/api/todos/<todo_id>", methods=["DELETE"])
def delete_todo(todo_id):
    if todo_id not in todos:
        log_event(logging.WARNING, "todo_not_found", todo_id=todo_id)
        return jsonify({"error": "not found"}), 404
    del todos[todo_id]
    refresh_gauges()
    TODOS_DELETED.inc()
    log_event(logging.INFO, "todo_deleted", todo_id=todo_id)
    return jsonify({"message": "deleted"}), 200


# ---------------------------------------------------------------------------
# Simulation endpoints for Grafana/PromQL/ELK practice
# ---------------------------------------------------------------------------
ALLOWED_CODES = (200, 201, 204, 400, 401, 403, 404, 409, 422, 429, 500, 502, 503, 504)


@app.route("/api/simulate/slow")
def simulate_slow():
    delay = float(request.args.get("delay", 3))
    delay = max(0, min(delay, 30))
    time.sleep(delay)
    log_event(logging.INFO, "simulated_slow", delay_s=delay)
    return jsonify({"message": f"slept for {delay}s"}), 200


@app.route("/api/simulate/status/<int:code>")
def simulate_status(code):
    if code not in ALLOWED_CODES:
        return jsonify({"error": "unsupported code", "allowed": ALLOWED_CODES}), 400
    if code == 204:
        return "", 204
    return jsonify({"message": f"simulated {code} response"}), code


@app.route("/api/simulate/random")
def simulate_random():
    codes = [200] * 5 + [201] * 2 + [400, 404, 429] + [500, 503]
    code = random.choice(codes)
    if random.random() < 0.15:
        time.sleep(random.uniform(0.5, 2.5))
    return jsonify({"code": code}), code


@app.route("/api/simulate/error")
def simulate_error():
    raise RuntimeError("Intentional exception for 500 testing")


@app.errorhandler(Exception)
def handle_exception(e):
    log_event(logging.ERROR, "unhandled_exception", error=str(e))
    return jsonify({"error": "internal server error"}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 5000)))
