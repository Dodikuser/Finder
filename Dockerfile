# Finder: web UI + API on top of the official Hermes Agent image.
#
#   docker compose up -d --build      → http://localhost:8000

ARG HERMES_IMAGE=nousresearch/hermes-agent:latest

# ---- frontend build ---------------------------------------------------------
FROM node:22.11.0-bookworm-slim AS web
WORKDIR /web
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci --no-audit --no-fund
COPY frontend/ ./
RUN npm run build

# ---- runtime: Hermes Agent + Finder -----------------------------------------
FROM ${HERMES_IMAGE}

USER root
WORKDIR /opt/finder

# Separate interpreter env for Finder (Hermes keeps its own sealed venv untouched),
# plus the headless Chromium used for pages that block plain HTTP clients.
# Fonts for PDF reports and rendered pages (Cyrillic, Latin, symbols).
RUN apt-get -o Acquire::Retries=3 update \
 && apt-get install -y --no-install-recommends fonts-dejavu-core fonts-liberation2 fonts-noto-core \
 && rm -rf /var/lib/apt/lists/*

# Debian's own Python 3.13 on purpose: plain `python3` in this image is Hermes' 3.14, which some of
# Finder's pinned dependencies do not support yet.
COPY backend/requirements.txt backend/requirements.txt
RUN /usr/bin/python3 -m venv /opt/finder/.venv \
 && /opt/finder/.venv/bin/pip install --no-cache-dir --upgrade pip \
 && /opt/finder/.venv/bin/pip install --no-cache-dir -r backend/requirements.txt \
 && PLAYWRIGHT_BROWSERS_PATH=/opt/finder/ms-playwright /opt/finder/.venv/bin/python -m playwright install chromium

# Google Gemini subscription (optional): Google's Antigravity CLI + its Hermes plugin.
# Neither step may break the build: when one is unavailable, Finder simply does not offer
# "Google Gemini (Antigravity)" on the Accounts page.
ARG ANTIGRAVITY_PLUGIN_REPO=https://github.com/neerazz/hermes-antigravity-oauth
ARG ANTIGRAVITY_PLUGIN_REF=f9f2e389a6875ce468c5e76bb533ff4ac55b85f9
RUN (git clone --quiet "$ANTIGRAVITY_PLUGIN_REPO" /opt/finder/hermes-plugins/antigravity-oauth \
      && git -C /opt/finder/hermes-plugins/antigravity-oauth checkout --quiet "$ANTIGRAVITY_PLUGIN_REF" \
      && rm -rf /opt/finder/hermes-plugins/antigravity-oauth/.git) \
     || (echo "WARN: Antigravity plugin not installed" && rm -rf /opt/finder/hermes-plugins/antigravity-oauth)
RUN mkdir -p /opt/agy \
 && (curl -fsSL --retry 2 https://antigravity.google/cli/install.sh -o /tmp/agy-install.sh \
      && HOME=/opt/agy bash /tmp/agy-install.sh \
      && AGY="$(find /opt/agy -type f -name agy -perm -u+x | head -n 1)" \
      && test -n "$AGY" && ln -sf "$AGY" /usr/local/bin/agy && chmod -R a+rX /opt/agy \
      && echo "agy installed: $AGY") \
     || echo "WARN: Antigravity CLI (agy) not installed" ; rm -f /tmp/agy-install.sh

COPY backend/app backend/app
COPY backend/hermes_entry backend/hermes_entry
COPY reach_mcp reach_mcp
COPY skills skills
COPY agents agents
COPY docker/start.sh docker/start.sh
COPY --from=web /web/dist frontend/dist

RUN chmod 0755 docker/start.sh && chown -R hermes:hermes /opt/finder

# Hermes runs from its sealed venv; profiles (one per Finder user) live in the data volume.
ENV FINDER_HERMES_PYTHON=/opt/hermes/.venv/bin/python \
    FINDER_HERMES_AGENT_DIR=/opt/hermes \
    FINDER_HERMES_ROOT=/opt/data \
    FINDER_DATA_DIR=/opt/data/finder \
    FINDER_MCP_PYTHON=/opt/finder/.venv/bin/python \
    FINDER_ANTIGRAVITY_PLUGIN_DIR=/opt/finder/hermes-plugins/antigravity-oauth \
    PLAYWRIGHT_BROWSERS_PATH=/opt/finder/ms-playwright \
    FINDER_BROWSER_NO_SANDBOX=1 \
    PYTHONUNBUFFERED=1 \
    PORT=8000

USER hermes
EXPOSE 8000
VOLUME ["/opt/data"]
HEALTHCHECK --interval=30s --timeout=5s --start-period=30s CMD curl -fsS http://127.0.0.1:${PORT}/api/health || exit 1

# Bypass the image's s6 supervisor (it would start Hermes' own gateway/dashboard):
# Finder starts `hermes acp` per user itself. Run with `init: true` to reap child processes.
ENTRYPOINT ["/opt/finder/docker/start.sh"]
