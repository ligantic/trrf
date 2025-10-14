# Container to build our prod image
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
  unixodbc-dev \
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

# Install dependencies (only main dependencies for production)
RUN --mount=type=cache,target=/root/.cache/uv \
    GIT_SSL_NO_VERIFY=1 UV_INSECURE_HOST="pypi.org files.pythonhosted.org" uv sync --frozen --no-install-project --no-dev

# Actual image we are building
FROM python:3.13-slim

ENV PYTHONUNBUFFERED 1

ENV PYTHONPATH="/app/rdrf/"
ENV DJANGO_SETTINGS_MODULE rdrf.settings

ENV PROJECT_NAME trrf
ENV PROJECT_SOURCE https://github.com/eresearchqut/trrf.git
ENV DEPLOYMENT prod
ENV PRODUCTION 1
ENV DEBUG 0
ENV STATIC_ROOT /data/static
ENV WRITABLE_DIRECTORY /data/scratch
ENV MEDIA_ROOT /data/static/media
ENV LOG_DIRECTORY /data/log
ENV LOCALE_PATHS /data/translations/locale
ENV DJANGO_SETTINGS_MODULE rdrf.settings

RUN mkdir /app

RUN addgroup --gid 1000 django \
  && adduser --disabled-password --home /data --no-create-home --system -q --uid 1000 --ingroup django django \
  && mkdir /data \
  && chown django:django /data \
  && chown django:django /app

RUN apt-get update && apt-get install -y --no-install-recommends \
  # Base
  # TODO check if requirements are needed
  git \
  gettext \
  libpq5 \
  media-types \
  nodejs \
  unixodbc \
  ssl-cert \
  libmagic1 \
  curl \
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

# Install dependencies (only main dependencies for production)
RUN --mount=type=cache,target=/root/.cache/uv \
    GIT_SSL_NO_VERIFY=1 UV_INSECURE_HOST="pypi.org files.pythonhosted.org" uv sync --frozen --no-install-project --no-dev

# Place executables in the environment at the front of the path
ENV PATH="/app/.venv/bin:$PATH"

# The generate snakeoil cert is valid for 10 years, but if you need to
# re-generate it you can use:
# RUN make-ssl-cert generate-default-snakeoil --force-overwrite

RUN chgrp -R django /etc/ssl/private/ \
  && chmod g+r /etc/ssl/private/ssl-cert-snakeoil.key

# Currently just using the dev entrypoint for prod as well
# TODO separate or move one level up
COPY docker/dev/docker-entrypoint.sh /
RUN chmod +x /docker-entrypoint.sh

VOLUME ["/data"]
ENV HOME /data

EXPOSE 9000

COPY --chown=django:django . /app
# RUN chown -R django /app

# COPY --from=nodebuilder /app/root/.cache /root/.cache

USER django
WORKDIR /data

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["uwsgi"]

