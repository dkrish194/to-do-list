import os
import time
import uuid
import random
import logging
import json
import threading
from datetime import datetime, timezone
from functools import wraps

import pymysql
from flask import Flask, request, jsonify, Response
from prometheus_client import Counter, Histogram, Gauge, generate_latest, CONTENT_TYPE_LATEST

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
APP_VERSION = os.environ.get("APP_VERSION", "v1.0.0")
APP_COLOR = os.environ.get("APP_COLOR", "#4F46E5")
APP_COLOR_NAME = os.environ.get("APP_COLOR_NAME", "indigo")
POD_NAME = os.environ.get("HOSTNAME", "local-dev")
CORS_ORIGIN = os.environ.get("CORS_ORIGIN", "*")

DB_HOST = os.environ.get("DB_HOST", "mysql")
DB_PORT = int(os.environ.get("DB_PORT", 3306))
DB_USER = os.environ.get("DB_USER", "todo")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "todopass")
DB_NAME = os.environ.get("DB_NAME", "tododb")
DB_CONNECT_TIMEOUT = int(os.environ.get("DB_CONNECT_TIMEOUT", 5))

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

DB_UP = Gauge("todo_backend_db_up", "1 if MySQL was reachable on the last check, else 0")
DB_QUERY_LATENCY = Histogram(
    "todo_backend_db_query_duration_seconds", "MySQL query duration seconds",
    ["operation"], buckets=(0.001, 0.005, 0.01, 0.05, 0.1, 0.5, 1, 2, 5),
)
DB_ERRORS = Counter("todo_backend_db_errors_total", "Total MySQL errors", ["operation"])
DB_UP.set(0)  # unknown until first check

# ---------------------------------------------------------------------------
# MySQL access layer
# ---------------------------------------------------------------------------
def get_conn():
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, connect_timeout=DB_CONNECT_TIMEOUT, autocommit=True,
        cursorclass=pymysql.cursors.DictCursor,
    )


def db_op(operation_name):
    """Decorator: times the call, updates DB_UP/DB_ERRORS, retries transient
    connection failures once (covers brief MySQL restarts/network blips)."""
    def decorator(fn):
        @wraps(fn)
        def wrapper(*args, **kwargs):
            last_exc = None
            for attempt in (1, 2):
                start = time.time()
                try:
                    result = fn(*args, **kwargs)
                    DB_QUERY_LATENCY.labels(operation_name).observe(time.time() - start)
                    DB_UP.set(1)
                    return result
                except (pymysql.err.OperationalError, pymysql.err.InterfaceError) as e:
                    last_exc = e
                    DB_QUERY_LATENCY.labels(operation_name).observe(time.time() - start)
                    DB_ERRORS.labels(operation_name).inc()
                    DB_UP.set(0)
                    log_event(logging.WARNING, "db_operation_retry",
                              operation=operation_name, attempt=attempt, error=str(e))
                    time.sleep(0.3)
            raise last_exc
        return wrapper
    return decorator


@db_op("ping")
def db_ping():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT 1")
    finally:
        conn.close()


@db_op("init_schema")
def db_init_schema():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("""
                CREATE TABLE IF NOT EXISTS todos (
                    id VARCHAR(36) PRIMARY KEY,
                    title VARCHAR(255) NOT NULL,
                    done TINYINT(1) NOT NULL DEFAULT 0,
                    created_at DATETIME NOT NULL,
                    updated_at DATETIME NOT NULL
                ) ENGINE=InnoDB
            """)
    finally:
        conn.close()


@db_op("seed")
def db_seed_if_empty():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS c FROM todos")
            if cur.fetchone()["c"] == 0:
                now = datetime.now(timezone.utc)
                for title in ["Apply ServiceMonitor for backend", "Build RED dashboard in Grafana", "Ship logs to ELK"]:
                    cur.execute(
                        "INSERT INTO todos (id, title, done, created_at, updated_at) VALUES (%s,%s,%s,%s,%s)",
                        (str(uuid.uuid4()), title, 0, now, now),
                    )
    finally:
        conn.close()


@db_op("list")
def db_list_todos():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM todos ORDER BY created_at")
            return cur.fetchall()
    finally:
        conn.close()


@db_op("get")
def db_get_todo(todo_id):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM todos WHERE id = %s", (todo_id,))
            return cur.fetchone()
    finally:
        conn.close()


@db_op("create")
def db_create_todo(title, done=False):
    conn = get_conn()
    try:
        tid = str(uuid.uuid4())
        now = datetime.now(timezone.utc)
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO todos (id, title, done, created_at, updated_at) VALUES (%s,%s,%s,%s,%s)",
                (tid, title, int(done), now, now),
            )
        return {"id": tid, "title": title, "done": bool(done),
                "created_at": now.isoformat(), "updated_at": now.isoformat()}
    finally:
        conn.close()


@db_op("update")
def db_update_todo(todo_id, title=None, done=None):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM todos WHERE id = %s", (todo_id,))
            existing = cur.fetchone()
            if not existing:
                return None
            new_title = title if title is not None else existing["title"]
            new_done = int(done) if done is not None else existing["done"]
            now = datetime.now(timezone.utc)
            cur.execute(
                "UPDATE todos SET title=%s, done=%s, updated_at=%s WHERE id=%s",
                (new_title, new_done, now, todo_id),
            )
            cur.execute("SELECT * FROM todos WHERE id = %s", (todo_id,))
            return cur.fetchone()
    finally:
        conn.close()


@db_op("delete")
def db_delete_todo(todo_id):
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM todos WHERE id = %s", (todo_id,))
            if not cur.fetchone():
                return False
            cur.execute("DELETE FROM todos WHERE id = %s", (todo_id,))
        return True
    finally:
        conn.close()


@db_op("counts")
def db_counts():
    conn = get_conn()
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) AS total, SUM(done) AS done FROM todos")
            row = cur.fetchone()
            return int(row["total"] or 0), int(row["done"] or 0)
    finally:
        conn.close()


def refresh_todo_gauges():
    try:
        total, done = db_counts()
        TODOS_GAUGE.set(total)
        TODOS_DONE_GAUGE.set(done)
    except Exception as e:
        log_event(logging.WARNING, "gauge_refresh_failed", error=str(e))


def db_init_background():
    """Runs in a background thread so gunicorn can bind the port and serve
    /health immediately, even while MySQL is still starting up (e.g. right
    after a fresh Deployment or a MySQL pod restart). Retries forever."""
    while True:
        try:
            db_init_schema()
            db_seed_if_empty()
            refresh_todo_gauges()
            log_event(logging.INFO, "db_schema_ready")
            return
        except Exception as e:
            log_event(logging.WARNING, "db_not_ready_retrying", error=str(e))
            time.sleep(3)


threading.Thread(target=db_init_background, daemon=True).start()

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
    # LIVENESS: only checks the Flask process itself is alive and serving.
    # Deliberately does NOT check MySQL - a slow/unreachable DB should not
    # cause Kubernetes to kill and restart this Pod.
    return jsonify({"status": "ok", "version": APP_VERSION, "pod": POD_NAME}), 200


@app.route("/ready")
def ready():
    # READINESS: actually checks MySQL connectivity. If the DB is down,
    # return 503 so Kubernetes removes this Pod from the Service's endpoints
    # (stops routing user traffic here) without restarting the container.
    try:
        db_ping()
        return jsonify({"status": "ready", "db": "up"}), 200
    except Exception as e:
        log_event(logging.WARNING, "readiness_db_check_failed", error=str(e))
        return jsonify({"status": "not_ready", "db": "down"}), 503


@app.route("/metrics")
def metrics():
    return Response(generate_latest(), mimetype=CONTENT_TYPE_LATEST)


# ---------------------------------------------------------------------------
# CRUD API - backed by MySQL
# ---------------------------------------------------------------------------
@app.route("/api/todos", methods=["GET"])
def list_todos():
    try:
        rows = db_list_todos()
        todos = [_serialize(r) for r in rows]
        refresh_todo_gauges()
        log_event(logging.INFO, "list_todos", count=len(todos))
        return jsonify(todos), 200
    except Exception as e:
        log_event(logging.ERROR, "list_todos_failed", error=str(e))
        return jsonify({"error": "database unavailable"}), 503


@app.route("/api/todos", methods=["POST"])
def create_todo():
    data = request.get_json(silent=True)
    if not data or not data.get("title", "").strip():
        log_event(logging.WARNING, "create_todo_bad_request")
        return jsonify({"error": "title is required"}), 400
    try:
        todo = db_create_todo(data["title"].strip(), bool(data.get("done", False)))
        refresh_todo_gauges()
        TODOS_CREATED.inc()
        log_event(logging.INFO, "todo_created", todo_id=todo["id"], title=todo["title"])
        return jsonify(todo), 201
    except Exception as e:
        log_event(logging.ERROR, "create_todo_failed", error=str(e))
        return jsonify({"error": "database unavailable"}), 503


@app.route("/api/todos/<todo_id>", methods=["GET"])
def get_todo(todo_id):
    try:
        row = db_get_todo(todo_id)
        if not row:
            log_event(logging.WARNING, "todo_not_found", todo_id=todo_id)
            return jsonify({"error": "not found"}), 404
        return jsonify(_serialize(row)), 200
    except Exception as e:
        log_event(logging.ERROR, "get_todo_failed", error=str(e))
        return jsonify({"error": "database unavailable"}), 503


@app.route("/api/todos/<todo_id>", methods=["PUT"])
def update_todo(todo_id):
    data = request.get_json(silent=True) or {}
    if "title" in data and not data["title"].strip():
        return jsonify({"error": "title cannot be empty"}), 400
    try:
        row = db_update_todo(
            todo_id,
            title=data["title"].strip() if "title" in data else None,
            done=data.get("done") if "done" in data else None,
        )
        if not row:
            log_event(logging.WARNING, "todo_not_found", todo_id=todo_id)
            return jsonify({"error": "not found"}), 404
        refresh_todo_gauges()
        TODOS_UPDATED.inc()
        log_event(logging.INFO, "todo_updated", todo_id=todo_id)
        return jsonify(_serialize(row)), 200
    except Exception as e:
        log_event(logging.ERROR, "update_todo_failed", error=str(e))
        return jsonify({"error": "database unavailable"}), 503


@app.route("/api/todos/<todo_id>", methods=["DELETE"])
def delete_todo(todo_id):
    try:
        deleted = db_delete_todo(todo_id)
        if not deleted:
            log_event(logging.WARNING, "todo_not_found", todo_id=todo_id)
            return jsonify({"error": "not found"}), 404
        refresh_todo_gauges()
        TODOS_DELETED.inc()
        log_event(logging.INFO, "todo_deleted", todo_id=todo_id)
        return jsonify({"message": "deleted"}), 200
    except Exception as e:
        log_event(logging.ERROR, "delete_todo_failed", error=str(e))
        return jsonify({"error": "database unavailable"}), 503


def _serialize(row):
    return {
        "id": row["id"], "title": row["title"], "done": bool(row["done"]),
        "created_at": row["created_at"].isoformat() if hasattr(row["created_at"], "isoformat") else row["created_at"],
        "updated_at": row["updated_at"].isoformat() if hasattr(row["updated_at"], "isoformat") else row["updated_at"],
    }


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
