# Grid Ops Command Center — the UI/orchestration half.
#
# Deliberately slim: the statevector lives on the GB10 behind an HTTP call, so
# this image carries no CUDA, no cuQuantum, and no Qiskit. It builds on plain
# python:3.12-slim rather than a CUDA base for exactly that reason.
#
# It gets a dmz13 macvlan address so Caddy (10.0.13.3) can reach it — a
# container on a plain bridge is NOT reachable from Caddy and is NOT isolated
# from the LAN. See /data/code/dmz/ONBOARDING.md.
FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    STREAMLIT_SERVER_HEADLESS=true \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS=false

WORKDIR /app

RUN apt-get update \
 && apt-get install -y --no-install-recommends curl \
 && rm -rf /var/lib/apt/lists/*

COPY requirements-ui.txt .
RUN pip install --no-cache-dir -r requirements-ui.txt

COPY app.py ./
COPY .streamlit/ ./.streamlit/
# Our own plotly.min.js, served at /app/static/ so animations work air-gapped.
COPY static/ ./static/
COPY src/ ./src/

EXPOSE 8501

# Streamlit's own health endpoint — proves the script server is up, not merely
# that the port is bound.
HEALTHCHECK --interval=30s --timeout=5s --start-period=25s --retries=3 \
  CMD curl -fsS http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "app.py", \
     "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
