# Backend API (control plane). Build context = repo root:
#   docker build -f quant-app/deploy/Dockerfile -t btc5m-backend .
FROM python:3.12-slim

WORKDIR /app
# Engine + crypto + backend + dashboard (all stdlib, no pip install needed).
COPY quant-app/ /app/quant-app/
COPY dashboard/ /app/dashboard/

WORKDIR /app/quant-app
ENV HOST=0.0.0.0 \
    PORT=8787 \
    BTC5M_PROFILE=conservative
EXPOSE 8787

# Read-only + dry-run by default; set BTC5M_API_TOKEN to enable control endpoints.
CMD ["python", "-m", "backend.server"]
