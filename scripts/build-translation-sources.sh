#!/bin/bash

set -euo pipefail

# Creates the translation source from the app source code, and the supplied registry definition
# Used as input for crowdin translation platform
#
# And contain registry definition file named $APPLICATION_NAME.yaml in the project root

if [ -z "$1" ]
then
    echo "Registry definition argument"
    exit 1
fi

REGISTRY_DEFINITION=$(realpath "$1")
RDRF_ROOT=$(git rev-parse --show-toplevel)
REPOSITORY_ROOT=$(dirname "$RDRF_ROOT")
if [ -f "$REPOSITORY_ROOT/angelman.yaml" ] && [ -f "$REPOSITORY_ROOT/angelman/manage.py" ]
then
    TRANSLATION_ROOT="$REPOSITORY_ROOT"
    WORK_DIR=$(mktemp -d)
    trap 'rm -rf "$WORK_DIR"' EXIT

    LOCALE_PATHS="$WORK_DIR/rdrf/locale" PYTHONPATH="$RDRF_ROOT/rdrf:$REPOSITORY_ROOT/angelman" \
        DJANGO_SETTINGS_MODULE=rdrf.settings python3 "$RDRF_ROOT/rdrf/manage.py" \
        makemessages -d django -l en
    LOCALE_PATHS="$WORK_DIR/rdrf/locale" PYTHONPATH="$RDRF_ROOT/rdrf:$REPOSITORY_ROOT/angelman" \
        DJANGO_SETTINGS_MODULE=rdrf.settings python3 "$RDRF_ROOT/rdrf/manage.py" \
        makemessages -d djangojs -l en -i '*node_modules*' -i '*yarn*'
    (
        cd "$REPOSITORY_ROOT/angelman"
        LOCALE_PATHS="$WORK_DIR/angelman/locale" PYTHONPATH="$RDRF_ROOT/rdrf:$REPOSITORY_ROOT/angelman" \
            DJANGO_SETTINGS_MODULE=angelman.settings python3 manage.py \
            makemessages -d django -l en
    )

    mkdir -p "$TRANSLATION_ROOT/translations/locale/en/LC_MESSAGES"
    msgcat \
        "$WORK_DIR/rdrf/locale/en/LC_MESSAGES/django.po" \
        "$WORK_DIR/angelman/locale/en/LC_MESSAGES/django.po" \
        > "$TRANSLATION_ROOT/translations/locale/en/LC_MESSAGES/django.po"
    cp "$WORK_DIR/rdrf/locale/en/LC_MESSAGES/djangojs.po" \
        "$TRANSLATION_ROOT/translations/locale/en/LC_MESSAGES/djangojs.po"

    LOCALE_PATHS="$TRANSLATION_ROOT/translations/locale" PYTHONPATH="$RDRF_ROOT/rdrf:$REPOSITORY_ROOT/angelman" \
        DJANGO_SETTINGS_MODULE=angelman.settings python3 "$REPOSITORY_ROOT/angelman/manage.py" \
        create_translation_file --yaml_file "$REGISTRY_DEFINITION" \
        --system_po_file "$TRANSLATION_ROOT/translations/locale/en/LC_MESSAGES/django.po" \
        >> "$TRANSLATION_ROOT/translations/locale/en/LC_MESSAGES/django.po"
else
    COMPOSE_ROOT="$RDRF_ROOT"
    export HOST_WORKSPACE_FOLDER="$RDRF_ROOT"
    docker compose -f "$COMPOSE_ROOT/docker-compose.yml" --project-directory "$COMPOSE_ROOT" run --rm -w "/app" runserver django-admin makemessages -d django -l en
    docker compose -f "$COMPOSE_ROOT/docker-compose.yml" --project-directory "$COMPOSE_ROOT" run --rm -w "/app" runserver django-admin makemessages -d djangojs -l en -i "*node_modules*" -i "*yarn*"
    docker compose -f "$COMPOSE_ROOT/docker-compose.yml" --project-directory "$COMPOSE_ROOT" run --rm -w "/app" -e REGISTRY_DEFINITION="$REGISTRY_DEFINITION" runserver bash -c 'django-admin create_translation_file --yaml_file "$REGISTRY_DEFINITION" --system_po_file "translations/locale/en/LC_MESSAGES/django.po" >> "translations/locale/en/LC_MESSAGES/django.po"'
fi