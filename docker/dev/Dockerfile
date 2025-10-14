# FROM muccg/rdrf-builder
FROM python:3.13 as builder

ENV PYTHONUNBUFFERED 1

RUN apt-get update && apt-get install -y --no-install-recommends \
  # TODO check if requirements are needed
  # Base
  gettext \
  libpq5 \
  media-types \
  nodejs \
  unixodbc \
  # Builder
  build-essential \
  git \
  gzip \
  libpq-dev \
  libssl-dev \
  libyaml-dev \
  unixodbc-dev \
  zlib1g-dev \
  ca-certificates \
  && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Update CA certificates
RUN update-ca-certificates

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

WORKDIR /app

# Copy dependency files
COPY pyproject.toml uv.lock ./
COPY clients ./clients

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-install-project --all-extras

VOLUME ["/data"]

FROM python:3.13-slim

ENV PYTHONPATH="/app/rdrf/:${PYTHONPATH}"
ENV DJANGO_SETTINGS_MODULE rdrf.settings
ENV STATIC_ROOT="/data/static"
ENV WRITABLE_DIRECTORY="/data/scratch"
ENV LOCALE_PATHS="/app/translations/locale"
ENV LOG_DIRECTORY="/data/log"
ENV MEDIA_ROOT="/data/static/media"

# RUN apt-get update && apt-get install -y --no-install-recommends \
#    libxml2 \
#   && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

RUN apt-get update && apt-get install -y --no-install-recommends \
  # Base
  # TODO check if requirements are needed
  gettext \
  libpq5 \
  media-types \
  nodejs \
  postgresql-client \
  unixodbc \
  unixodbc-dev \
  build-essential \
  libmagic1 \
  git \
  ca-certificates \
  && apt-get clean && rm -rf /var/lib/apt/lists/* /tmp/* /var/tmp/*

# Update CA certificates
RUN update-ca-certificates

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

# Enable bytecode compilation
ENV UV_COMPILE_BYTECODE=1

# Copy from the cache instead of linking since it's a mounted volume
ENV UV_LINK_MODE=copy

WORKDIR /app

# Copy dependency files and clients
COPY pyproject.toml uv.lock ./
COPY clients ./clients

# Install dependencies
RUN --mount=type=cache,target=/root/.cache/uv \
    GIT_SSL_NO_VERIFY=1 UV_INSECURE_HOST="pypi.org files.pythonhosted.org" uv sync --frozen --no-install-project --all-extras

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

COPY docker/dev/docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

COPY docker/dev/lambda/aws-lambda-rie /
RUN chmod +x /aws-lambda-rie

VOLUME ["/app", "/data"]

ENV HOME /data
WORKDIR /data

EXPOSE 8000

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["runserver_plus"]
