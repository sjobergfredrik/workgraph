FROM python:3.12-slim

WORKDIR /app

# Install deps first for layer caching.
COPY pyproject.toml ./
COPY src ./src
RUN pip install --no-cache-dir .

# Config is mounted at /config by docker-compose; WORKGRAPH_CONFIG points there.
ENV WORKGRAPH_CONFIG=/config/workgraph.yaml

ENTRYPOINT []
CMD ["workgraph", "--help"]
