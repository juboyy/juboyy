# Deploy

Two planes, because they have **fundamentally different hosting needs**:

| Plane | What | Where it can run | Why |
|-------|------|------------------|-----|
| **Control plane** (backend API) | `backend/` — stateful `ThreadingHTTPServer`, raw **WebSocket** stream, in-memory arming/kill state, capture runner | **Container only** (Docker → any VPS / Fly / Render / Railway) | Long-running socket server + persistent WS + stateful control. **Does not fit serverless.** |
| **Demo plane** (read-only UI) | dashboard UI / mobile **web export** | **Vercel** (static) or any static host | Pure static assets; safe to expose publicly. |

> ⚠️ **Vercel cannot host the backend API.** Vercel is serverless (stateless, no
> persistent sockets, no long-running WebSocket, ~10s function limit). The
> backend holds in-process control/arming/kill state, streams over a raw
> WebSocket, and runs a capture loop — none of that survives serverless. So
> "deploy both to Vercel" is only possible for the **read-only demo**; the live
> API/control plane must be a **container**. This is a hard platform constraint,
> not a preference.

---

## 1. Backend API + dashboard — Docker (the real deploy)

From the **repo root**:

```bash
docker compose -f quant-app/deploy/docker-compose.yml up --build
# backend  API → http://localhost:8787/api/v1
# dashboard UI → http://localhost:8788
```

Environment (set before exposing publicly):

| Var | Purpose |
|-----|---------|
| `BTC5M_API_TOKEN` | **required** bearer token; control endpoints refuse to work without it |
| `BTC5M_API_CONTROL_TOKEN` | optional separate token for control endpoints |
| `PORT` / `HOST` | bind (default 8787 / 0.0.0.0) |
| `BTC5M_RUNTIME` | runtime dir with `captured_snapshots.jsonl` / live data |
| `BTC5M_PROFILE` | `conservative` (default) / `aggressive` |

**Never expose the control endpoints publicly without a strong token + TLS.**
Put it behind a reverse proxy (Caddy/Nginx) with HTTPS, or keep it on a private
network / VPN. It stays **dry-run** and **non-custodial** — no `PM_PRIVATE_KEY`
is needed or read by the API.

### Host it managed (Fly.io example)
```bash
fly launch --dockerfile quant-app/deploy/Dockerfile   # then `fly deploy`
```
Render/Railway: point at this Dockerfile, set the env vars, expose port 8787.

---

## 2. Read-only demo — Vercel (static)

The mobile app runs on its **mock layer** with no backend, so a web export is a
safe public demo. Building the web bundle needs network (Expo) + your Vercel
account, so run it on your machine:

```bash
cd quant-app/mobile
npm install
npx expo export --platform web        # outputs ./dist
npx vercel deploy dist --prod         # or import the repo in the Vercel UI
```

`quant-app/mobile/vercel.json` pins the build (`expo export --platform web`),
static output, and SPA routing. In the Vercel UI, set
**Root Directory = `quant-app/mobile`** (Vercel reads that `vercel.json`).

To point the deployed demo at a **live** backend instead of mock, set the app's
`apiBaseUrl` (see `mobile/src/api`) to your Docker backend's HTTPS URL and flip
`useMock` off in `app.json` — but only expose **read** endpoints publicly.

---

## What I could not do from here
This build sandbox has **no outbound network** (Expo/Vercel/registry calls
return 403) and no Docker daemon, so I prepared and verified the configs and the
server boot locally, but the actual `expo export` / `vercel deploy` / `docker
build` must run in your environment (they need the network and your accounts).
