FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim AS runtime
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy TARIFF_RADAR_DB=/data/tariff-radar.db
COPY pyproject.toml uv.lock README.md ./
COPY src ./src
RUN uv sync --locked --no-dev
EXPOSE 8000
VOLUME ["/data"]
CMD ["uv", "run", "tariff-radar", "serve", "--host", "0.0.0.0", "--port", "8000"]
