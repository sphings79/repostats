# Repo Stats

*[Deutsche Fassung](README.de.md)*

A small self-hosted dashboard for everything GitHub knows about your own
repositories — and for the numbers it throws away after two weeks.

GitHub shows traffic per repository, for fourteen days, one repository at a
time. There is no overview across repositories, no history, and no download
count anywhere. This collects all of it into one SQLite file and draws it.

## What it shows

**Per account:** stars, forks, watchers, open issues, release downloads,
views and clones across every repository you follow, where visitors come
from, and how it all moves over time.

**Per repository:** the same figures in detail, plus contributors, commits,
open and merged pull requests, the success rate and duration of the CI runs,
the most visited pages, the open issues with links to them, downloads per
release asset, and a star curve that reaches back to the first star — reconstructed
from the dates GitHub keeps per stargazer, so the history is there from the
first run instead of starting flat.

**For Home Assistant integrations** it additionally reads the installation
count from `analytics.home-assistant.io`. That is the only figure here that
counts people actually running something rather than people looking at it.

## Why it has to collect

Traffic and clone figures are private to the repository owner, so they need a
token — which is why this runs server-side rather than in the browser. And
GitHub deletes those figures after fourteen days: whatever is not collected
before then is gone for good. A daily run is enough, because each run returns
the full fourteen-day window, so downtime shorter than two weeks heals by
itself.

## Running it

```bash
cp .env.example .env    # put your token and login in
docker compose up -d
```

Then open `http://<host>:8377`, pick the repositories to follow under
*Verwaltung*, and press *Jetzt alles sammeln*.

The token needs the `repo` scope (classic), or read access to Actions,
Administration, Contents, Issues, Metadata and Pull requests (fine-grained).
Without it everything works except the traffic figures, which stay empty.

Set `AUTH_PASSWORD` unless you are running this on a laptop for a minute. The
dashboard lists your private repositories, and the container holds a token
that can read every one of them.

| Variable | Default | Meaning |
|---|---|---|
| `GITHUB_TOKEN` | — | personal access token, required |
| `GITHUB_LOGIN` | — | the account to collect, required |
| `AUTH_USER` | `admin` | user for the dashboard login |
| `AUTH_PASSWORD` | — | password; empty turns the login off |
| `PORT` | `8377` | port on the host |
| `FULL_RUN_HOUR` | `4` | hour (UTC) of the daily full run |
| `QUICK_RUN_MINUTES` | `60` | how often the cheap counters refresh |

Data lives in the `repostats-data` volume as a single SQLite file, so a backup
is one file copy.

## Notes

- The interface speaks German and English; the switch sits in the header.
- Code and comments are in English.
- Nothing leaves your network. The only outbound calls go to the GitHub API
  and to the Home Assistant analytics endpoint.
- The dashboard has its own login. Behind a reverse proxy, restrict it to
  your own network as well — `docs/traefik.yaml.example` shows both locks
  together, and `compose.override.yaml.example` puts the container on the
  proxy network without publishing a port.

## Licence

MIT
