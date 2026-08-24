# Todo App (2-Tier) — Real CRUD + Prometheus / Grafana / ELK / K8s Practice

A real, working to-do list — add, edit (click any task title), check off, and
delete tasks in an actual browser UI — split into two independently
deployable tiers so you can practice multi-service Kubernetes patterns, not
just a single Pod.

```
frontend/   nginx + vanilla JS SPA — the UI you interact with
backend/    Flask API — CRUD, Prometheus metrics, JSON logs, error/latency simulation
k8s/        manifests for both tiers, incl. blue/green versions and a ServiceMonitor
```

## Why two tiers

- Two separate Deployments/Services to practice rolling updates, blue/green,
  and canary **independently per tier**
- Two separate log streams (`todo-backend`, `todo-frontend` via nginx JSON
  access logs) for ELK — good practice for correlating logs across services
  by `request_id`/timestamp
- Realistic CORS, readiness/liveness probe, and Ingress path-routing setup —
  the same shape you'll see in real microservice interviews

---

## Run locally with Docker Compose

```bash
docker-compose up --build
# frontend: http://localhost:8080
# backend:  http://localhost:5000
```

Open `http://localhost:8080` — add tasks, check them off, click a task title
to rename it inline, delete with the ✕. The banner shows frontend version +
color plus which backend pod is serving you (fetched from `/version`).

## Run locally without Docker (fastest inner loop)

```bash
# terminal 1
cd backend
pip install -r requirements.txt
APP_VERSION=v1.0.0 APP_COLOR="#4F46E5" APP_COLOR_NAME=indigo python3 app.py

# terminal 2
cd frontend
cp config.js.template config.js
sed -i 's|${BACKEND_URL}|http://localhost:5000|; s|${FRONTEND_VERSION}|v1.0.0|; s|${FRONTEND_COLOR}|#4F46E5|; s|${FRONTEND_COLOR_NAME}|indigo|' config.js
python3 -m http.server 8080
```

Then open `http://localhost:8080`.

---

## Deploying to EKS

```bash
# build & push both images to ECR (repeat per tier)
docker build -t <ECR_REPO>/todo-backend:v1.0.0 ./backend
docker build -t <ECR_REPO>/todo-frontend:v1.0.0 ./frontend
docker push <ECR_REPO>/todo-backend:v1.0.0
docker push <ECR_REPO>/todo-frontend:v1.0.0

kubectl apply -f k8s/backend-deployment.yaml
kubectl apply -f k8s/frontend-deployment-v1-blue.yaml
kubectl apply -f k8s/ingress.yaml
kubectl apply -f k8s/backend-servicemonitor.yaml   # requires kube-prometheus-stack CRDs
```

**Important:** the frontend runs in the *browser*, not inside the cluster —
its `BACKEND_URL` env var must be a URL reachable from outside the cluster
(your Ingress/ALB host), not the internal `todo-backend.default.svc` DNS
name. Simplest fix: route both tiers under one ALB by path
(`k8s/ingress.yaml` does this) and set `BACKEND_URL` to `https://<alb-host>`
so `/api/...` calls stay same-origin — no CORS headaches either.

### Rollout practice

```bash
# Rolling update - bump image tag on the existing Deployment
kubectl set image deployment/todo-frontend-v1 todo-frontend=<ECR_REPO>/todo-frontend:v1.1.0
kubectl rollout status deployment/todo-frontend-v1

# Blue/Green - deploy v2 alongside v1, then flip the Service
kubectl apply -f k8s/frontend-deployment-v2-green.yaml
kubectl patch service todo-frontend -p '{"spec":{"selector":{"app":"todo-frontend","version":"v2"}}}'

# Canary - both versions live, weight by replica count
kubectl scale deployment todo-frontend-v1 --replicas=4
kubectl scale deployment todo-frontend-v2 --replicas=1
```

Reload the browser between steps — the banner color/version changes tell you
instantly which version served that page load.

---

## curl test suite (backend)

### CRUD

```bash
curl -s localhost:5000/api/todos | jq

curl -s -X POST localhost:5000/api/todos \
  -H "Content-Type: application/json" -d '{"title":"Learn PromQL rate()"}' | jq

curl -s -X PUT localhost:5000/api/todos/<id> \
  -H "Content-Type: application/json" -d '{"done": true}' | jq

curl -s -X PUT localhost:5000/api/todos/<id> \
  -H "Content-Type: application/json" -d '{"title":"renamed task"}' | jq

curl -s -X DELETE localhost:5000/api/todos/<id>
```

### 4xx

```bash
curl -s -o /dev/null -w "%{http_code}\n" -X POST localhost:5000/api/todos -H "Content-Type: application/json" -d '{}'
curl -s -o /dev/null -w "%{http_code}\n" localhost:5000/api/todos/does-not-exist
for c in 400 401 403 404 409 422 429; do curl -s -o /dev/null -w "$c -> %{http_code}\n" localhost:5000/api/simulate/status/$c; done
```

### 5xx

```bash
curl -s -o /dev/null -w "%{http_code}\n" localhost:5000/api/simulate/error
for c in 500 502 503 504; do curl -s -o /dev/null -w "$c -> %{http_code}\n" localhost:5000/api/simulate/status/$c; done
```

### Slow responses

```bash
for d in 0.1 0.5 1 3 6 10 20; do
  curl -s "localhost:5000/api/simulate/slow?delay=$d" -o /dev/null -w "delay=${d}s actual=%{time_total}s\n"
done
```

### Continuous mixed load (for live Grafana panels)

```bash
while true; do
  r=$((RANDOM % 100))
  if   [ $r -lt 60 ]; then curl -s -o /dev/null localhost:5000/api/todos
  elif [ $r -lt 75 ]; then curl -s -o /dev/null localhost:5000/api/simulate/status/$(shuf -e 400 404 429 -n1)
  elif [ $r -lt 85 ]; then curl -s -o /dev/null localhost:5000/api/simulate/status/$(shuf -e 500 503 -n1)
  else                     curl -s -o /dev/null "localhost:5000/api/simulate/slow?delay=$(shuf -e 1 3 6 -n1)"
  fi
  sleep 0.2
done
```

You can also trigger all of the above from inside the UI itself — expand
**"Grafana / Prometheus practice panel"** at the bottom of the page.

---

## Metrics exposed (`/metrics` on the backend)

| Metric | Type | Labels |
|---|---|---|
| `todo_backend_http_requests_total` | counter | method, endpoint, status |
| `todo_backend_http_request_duration_seconds` | histogram | method, endpoint |
| `todo_backend_todos_total` / `_done_total` | gauge | — |
| `todo_backend_todos_created_total` / `_updated_total` / `_deleted_total` | counter | — |
| `todo_backend_errors_total` | counter | status_code |
| `todo_backend_build_info` | gauge | version, color, pod |

## Log shapes

**Backend** (stdout, one JSON object per line):
```json
{"timestamp":"...","level":"INFO","message":"http_request","app":"todo-backend","version":"v1.0.0","pod":"todo-backend-abc123","request_id":"6b8eb62e","method":"POST","path":"/api/todos","status":201,"duration_ms":2.1,"remote_addr":"10.0.1.5"}
```

**Frontend** (nginx access log, JSON via custom `log_format` in `nginx.conf`):
```json
{"timestamp":"2026-08-24T10:00:00+00:00","app":"todo-frontend","remote_addr":"10.0.2.3","method":"GET","path":"/index.html","status":200,"body_bytes_sent":1820,"request_time":0.001,"user_agent":"Mozilla/5.0..."}
```

Both are plain JSON on stdout — point Filebeat/Fluent-bit at container logs
(or `kubectl logs`) with a JSON codec, no grok parsing required.
