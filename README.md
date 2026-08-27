# Todo App (3-Tier: MySQL + Backend + Frontend)

Real CRUD to-do app backed by a real database, split into three
independently scalable tiers - built to practice multi-replica Kubernetes
deployments, HPA, Prometheus/Grafana, and ELK all at once.

```
mysql/       init.sql + custom.cnf (slow query log, error log) for docker-compose
backend/     Flask API - MySQL-backed CRUD, Prometheus metrics, JSON logs
frontend/    nginx + vanilla JS SPA - real add/edit/delete/complete UI
k8s/         manifests: MySQL, backend (+HPA+ServiceMonitor), frontend (+HPA), Ingress
```

## Why this fixes the earlier bugs

- **"Delete comes back / create doesn't show up"** was caused by state
  living in each process's own memory (multiple gunicorn workers / multiple
  Pod replicas each had a separate in-memory list). Now all state lives in
  **MySQL**, a single shared source of truth - verified locally: 2 gunicorn
  workers hammering the API concurrently stayed 100% consistent across every
  request.
- **Liveness probe `connection refused` / CrashLoopBackOff** was caused by
  the app trying to use the DB before it existed and crashing outright.
  Now `/health` (liveness) **never touches MySQL** - it only confirms the
  Flask process itself is alive, so Kubernetes won't kill/restart the pod
  just because the database is briefly unreachable. `/ready` (readiness)
  *does* check MySQL and returns `503` if it's down - which correctly pulls
  that pod out of the Service's routable endpoints without restarting it.
  An `initContainer` also waits for MySQL's TCP port before the backend
  container even starts, and the app retries the schema/connection in a
  background thread regardless - verified locally by pointing the backend
  at a nonexistent DB host: `/health` stayed `200`, `/ready` correctly
  returned `503`, and the process never crashed.
- **"Backend unreachable" in the browser after deploying to k8s** was
  caused by the frontend's JS trying to call an absolute `BACKEND_URL` that
  only worked when hardcoded to a specific server IP - which breaks the
  moment the backend isn't *also* exposed on that same IP/port (and
  shouldn't be, for a real ClusterIP-only backend). Fixed by making the
  frontend's own **nginx reverse-proxy `/api` and `/version` to the
  backend's ClusterIP Service internally** (verified end-to-end locally:
  real nginx proxying real CRUD/status/version calls to a real Flask+MySQL
  backend). The browser now only ever talks to one address - through your
  Ingress - and the backend Service can stay ClusterIP-only forever, never
  exposed externally. This is the real production pattern, not a lab
  shortcut.

---

## Run locally with Docker Compose

```bash
docker-compose up --build
# mysql:    localhost:3306
# backend:  http://localhost:5000
# frontend: http://localhost:8081
```

Open `http://localhost:8081` - real add/edit/delete, backed by MySQL this
time (restart the containers and your todos are still there).

---

## Deploying to EKS

Build and push all three images:

```bash
docker build -t <ECR_REPO>/todo-backend:v1.0.0 ./backend
docker build -t <ECR_REPO>/todo-frontend:v1.0.0 ./frontend
docker push <ECR_REPO>/todo-backend:v1.0.0
docker push <ECR_REPO>/todo-frontend:v1.0.0
# mysql uses the official mysql:8.0 image directly - no build needed
```

Apply in this order:

```bash
kubectl apply -f k8s/mysql-secret.yaml
kubectl apply -f k8s/mysql-configmap.yaml
kubectl apply -f k8s/mysql-deployment.yaml
kubectl rollout status deployment/mysql        # wait for MySQL before backend

kubectl apply -f k8s/backend-deployment.yaml
kubectl rollout status deployment/todo-backend

kubectl apply -f k8s/frontend-deployment.yaml
kubectl apply -f k8s/ingress.yaml

kubectl apply -f k8s/backend-hpa.yaml
kubectl apply -f k8s/frontend-hpa.yaml
kubectl apply -f k8s/backend-servicemonitor.yaml   # requires kube-prometheus-stack CRDs
```

**No CORS setup, no external backend exposure needed:** the frontend's own
nginx proxies `/api` and `/version` to the backend's ClusterIP Service
internally (see `BACKEND_PROXY_HOST` env var on the frontend Deployment -
set to `todo-backend`, the backend Service's DNS name). The browser only
ever talks to the frontend, through your Ingress. Update `k8s/ingress.yaml`
(EKS/ALB) or `k8s/ingress-nginx.yaml` (k3d/nginx-ingress) to match your
cluster's ingress controller.

### Prerequisite for HPA: metrics-server

```bash
kubectl get deployment metrics-server -n kube-system
# if missing:
kubectl apply -f https://github.com/kubernetes-sigs/metrics-server/releases/latest/download/components.yaml
```

---

## HPA practice

Watch scaling live in one terminal:

```bash
kubectl get hpa -w
kubectl get pods -l app=todo-backend -w
```

Generate CPU load against the backend in another terminal to trigger a
scale-up:

```bash
kubectl run load-test --rm -it --image=busybox --restart=Never -- sh -c \
  "while true; do wget -q -O- http://todo-backend/api/simulate/slow?delay=0.05; done"
```

Or, from outside the cluster via your Ingress:

```bash
for i in $(seq 1 20); do
  (for j in $(seq 1 50); do curl -s -o /dev/null https://<alb-host>/api/api/todos; done) &
done
wait
```

Watch `kubectl get hpa` - once average CPU crosses 60%, replicas should
climb toward `maxReplicas: 6`. Stop the load and (after the 60s
`stabilizationWindowSeconds`) replicas will scale back down.

---

## Rollout practice (still available on both tiers)

```bash
kubectl set image deployment/todo-backend todo-backend=<ECR_REPO>/todo-backend:v1.1.0
kubectl rollout status deployment/todo-backend
kubectl rollout undo deployment/todo-backend   # roll back if needed
```

---

## curl test suite (backend)

### CRUD (now MySQL-backed - survives pod restarts)

```bash
curl -s localhost:5000/api/todos | jq
curl -s -X POST localhost:5000/api/todos -H "Content-Type: application/json" -d '{"title":"Learn PromQL rate()"}' | jq
curl -s -X PUT localhost:5000/api/todos/<id> -H "Content-Type: application/json" -d '{"done": true}' | jq
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

### Health vs readiness (test this against a real cluster too)

```bash
curl -s localhost:5000/health   # always 200 while the process is alive
curl -s localhost:5000/ready    # 200 if MySQL reachable, 503 if not
```

Try killing the MySQL pod (`kubectl delete pod -l app=mysql`) and watching
`kubectl get pods -l app=todo-backend` - the backend pods should **stay
Running** (not restart) while `kubectl get endpoints todo-backend` shows
them removed from routing until MySQL comes back and readiness passes again.

---

## Metrics exposed (`/metrics` on the backend)

| Metric | Type | Labels | Notes |
|---|---|---|---|
| `todo_backend_http_requests_total` | counter | method, endpoint, status | traffic/error-rate |
| `todo_backend_http_request_duration_seconds` | histogram | method, endpoint | `histogram_quantile()` practice |
| `todo_backend_todos_total` / `_done_total` | gauge | — | current DB state |
| `todo_backend_todos_created_total` / `_updated_total` / `_deleted_total` | counter | — | churn |
| `todo_backend_errors_total` | counter | status_code | error volume by code |
| `todo_backend_db_up` | gauge | — | 1/0, drives good readiness dashboards |
| `todo_backend_db_query_duration_seconds` | histogram | operation | MySQL latency per operation (list/create/update/delete/ping) |
| `todo_backend_db_errors_total` | counter | operation | MySQL error rate per operation |
| `todo_backend_build_info` | gauge | version, color, pod | which version is serving |

Good RED-method panels to build:
- **Rate:** `sum(rate(todo_backend_http_requests_total[5m])) by (endpoint)`
- **Errors:** `sum(rate(todo_backend_http_requests_total{status=~"5.."}[5m])) / sum(rate(todo_backend_http_requests_total[5m]))`
- **Duration:** `histogram_quantile(0.95, sum(rate(todo_backend_http_request_duration_seconds_bucket[5m])) by (le))`
- **DB health panel:** `todo_backend_db_up` as a single-stat, red/green

---

## Log sources for ELK

1. **Backend** - one JSON object per line on stdout (`kubectl logs` picks it up directly):
   ```json
   {"timestamp":"...","level":"INFO","message":"todo_created","app":"todo-backend","version":"v1.0.0","pod":"todo-backend-abc123","todo_id":"...","title":"..."}
   ```
2. **Frontend** - nginx JSON access log via `nginx.conf.template`'s custom `log_format`.
3. **MySQL** - slow query log + error log, written to files inside the Pod
   and tailed to stdout by the `log-shipper` sidecar container in
   `mysql-deployment.yaml` (`kubectl logs mysql-<pod> -c log-shipper`).
   `long_query_time = 1` in `custom.cnf` means any query over 1 second gets
   logged - fire a few `simulate/slow` requests or a full table scan to see
   entries appear.

Point Filebeat/Fluent-bit at container stdout across all three
Deployments and you'll have three real, differently-shaped log streams to
practice parsing, filtering, and correlating (e.g. by `pod` name or a
shared time window) in Kibana.
