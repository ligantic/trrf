# Local Browser Access

Use this runbook when opening the local TRRF registry in the built-in browser.

## Start the Registry

Run the **Django: Prepare local database** task once, then start the registry with **Django: Run development server** or the **Django: Development server** launch configuration. Django runs in the devcontainer and listens on port `8000`.

## Local Environment

The tracked `.env.example` supplies non-secret development defaults, including
smtp4dev. Copy it to `.env_local` for machine-specific overrides; `.env_local`
is ignored by Git and is read by Docker Compose.

The devcontainer includes direnv and the recommended VS Code extension. From
the workspace root, run `direnv allow` once to load `.env.example` and then
apply values from `rdrf/.env_local` when it exists.

## Open the Login Page

Open `http://localhost:8000/account/login` in the built-in browser. VS Code forwards port `8000` from the devcontainer automatically.

## Debug Outgoing Email

The local Compose stack starts smtp4dev alongside the devcontainer. It captures development emails instead of delivering them externally.

Open the smtp4dev message UI at:

```
http://localhost:18500
```

Query captured messages through its API at:

```
http://localhost:18500/api/messages
```

Within Docker Compose, Django sends email to `smtp4dev:25`. smtp4dev's published host ports default to `18500` (web/API), `18525` (SMTP), and `18543` (IMAP). Override them before starting the stack with `SMTP4DEV_WEB_PORT`, `SMTP4DEV_SMTP_PORT`, or `SMTP4DEV_IMAP_PORT` if one is already in use.

To verify delivery and assert the API recorded the message, run from the devcontainer:

```sh
cd /workspaces/fast-au/gasr/rdrf
set -a && . ./.env_local && . ./docker/dev/envs/postgres && . ./docker/dev/envs/runserver && set +a
python rdrf/manage.py shell --settings=rdrf.settings -c "from django.core.mail import send_mail; assert send_mail('smtp4dev smoke test', 'Local SMTP capture is working.', 'test@xxx.local', ['recipient@example.local']) == 1"
python -c "from urllib.request import urlopen; assert 'smtp4dev smoke test' in urlopen('http://smtp4dev/api/messages').read().decode()"
```

## Development Administrator

The local administrator is configured with:

- Username: `admin`
- Email: `admin@localhost`
- Password: `admin`

The registry login page labels its identifier field **Email Address**.