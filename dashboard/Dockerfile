FROM python:3.11-slim

WORKDIR /app
COPY . /app

# PyYAML is optional but lets the dashboard read the real profiles YAML.
RUN pip install --no-cache-dir pyyaml || true

ENV HOST=0.0.0.0 \
    PORT=8787 \
    BTC5M_RUNTIME=/app/runtime

EXPOSE 8787

# Default: demo mode so the container shows data out of the box.
# Override CMD (or set BTC5M_RUNTIME to a mounted volume) for live monitoring.
CMD ["python", "app.py", "--demo", "--host", "0.0.0.0", "--port", "8787"]
