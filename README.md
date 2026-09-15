<div align="center">

<img src="assets/banner.svg" alt="Repo Stats — a self-hosted dashboard for GitHub repository statistics" width="100%">

# Repo Stats

**A self-hosted dashboard for everything GitHub knows about your repositories — and for the numbers it throws away after two weeks.**

*[Deutsche Fassung](README.de.md)*

[![Image](https://github.com/sphings79/repostats/actions/workflows/docker.yml/badge.svg)](https://github.com/sphings79/repostats/actions/workflows/docker.yml)
[![Check](https://github.com/sphings79/repostats/actions/workflows/check.yml/badge.svg)](https://github.com/sphings79/repostats/actions/workflows/check.yml)
[![Container](https://img.shields.io/badge/ghcr.io-repostats-41BDF5?logo=docker&logoColor=white)](https://github.com/sphings79/repostats/pkgs/container/repostats)
[![Licence](https://img.shields.io/badge/licence-AGPL--3.0-3DDC97)](LICENSE)
[![Stars](https://img.shields.io/github/stars/sphings79/repostats?color=FFC107)](https://github.com/sphings79/repostats/stargazers)

</div>

---

GitHub shows traffic per repository, for fourteen days, one repository at a
time. There is no overview across repositories, no history, and no download
count anywhere. **Repo Stats collects all of it into one SQLite file and draws
it** — self-hosted, in a single container, on your own network.

<div align="center">

<img src="assets/overview.svg" alt="The overview: tiles for stars, visitors, clones and installs, a traffic chart, and a sortable table of repositories" width="100%">

</div>

## Contents

- [Why it exists](#why-it-exists)
- [What it shows](#what-it-shows)
- [Running it](#running-it)
- [Configuration](#configuration)
- [Behind a reverse proxy](#behind-a-reverse-proxy)
- [How it works](#how-it-works)
- [Questions](#questions)
- [Contributing](#contributing)

## Why it exists

**GitHub deletes traffic data after fourteen days.** Views, unique visitors,
clones, referrers — gone, with no way to get them back. If you want to know
whether that post last month actually brought anyone, the answer no longer
exists.

**There is no view across repositories.** With fifty repositories, finding out
where your visitors come from means opening fifty Insights pages.

**Release downloads are not shown at all.** GitHub counts them per asset and
shows the number nowhere in the interface.

A daily collection solves all three. Each run returns the full fourteen-day
window, so downtime shorter than two weeks heals by itself.

## What it shows

**Across the account** — stars, forks, watchers, open issues, release
downloads, visitors and clones over every repository you follow, where those
visitors come from, and how it all moves over time.

**Per repository** — the same figures in detail, plus contributors, commits,
open and merged pull requests, CI success rate and duration, the most visited
pages, downloads per release file, and the open issues with links to them.

**A star curve that reaches back to the first star**, reconstructed from the
dates GitHub keeps per stargazer — so the history is there from the first run
instead of starting flat.

**For Home Assistant integrations**, the installation count from
`analytics.home-assistant.io`, split by version: an integration domain belongs
to everyone shipping it, and only the versions released from your repository
are counted as yours.

Every tile opens a breakdown showing which repositories the number is made of,
and every figure carries a note explaining what it actually counts — because
"2,592 clones" mostly means your own CI, not people.

## Running it

```bash
git clone https://github.com/sphings79/repostats.git
cd repostats
cp .env.example .env     # put your token and account in
docker compose up -d
```

Then open `http://<host>:8377`. The first visit asks for a user name and a
password — that account is the login from then on. Pick the repositories to
follow under *Settings* and press *Collect everything now*.

The image is published for **amd64 and arm64**, so nothing is compiled on your
host. Data lives in one SQLite file inside a volume — a backup is one file
copy.

## Configuration

| Variable | Default | Meaning |
|---|---|---|
| `GITHUB_TOKEN` | — | personal access token, required |
| `GITHUB_LOGIN` | — | the account to collect, required |
| `GITHUB_TOKEN_STARS` | — | classic token with `public_repo`, for the star history |
| `PORT` | `8377` | port on the host |
| `FULL_RUN_HOUR` | `4` | hour (UTC) of the daily full run |
| `QUICK_RUN_MINUTES` | `60` | how often the cheap counters refresh |

**The token needs the right permissions**, and one of them is easy to miss:

- Fine-grained: read access to **Administration** (this is what unlocks the
  traffic figures), Contents, Issues, Metadata, Pull requests, and Actions for
  the CI numbers.
- Classic: the `repo` scope.

**The login is set up in the browser, not in the environment.** On the first
start the dashboard has no account and sends every visitor to a setup page, so
do that step right after `docker compose up` — until it is done, whoever
reaches the port first can claim the account. The dashboard lists your private
repositories, and the container holds a token that can read every one of them.
User name and password can be changed later under *Account*.

**Forgotten the password?** Drop the account and set it up again:

```bash
docker compose exec repostats python -c "import sqlite3; c = sqlite3.connect('/data/repostats.db'); c.execute('DELETE FROM account'); c.commit()"
```

**The star history needs a second token.** GitHub refuses fine-grained tokens
on the stargazers endpoint, over REST and GraphQL alike, and serves nothing to
anonymous callers. `GITHUB_TOKEN_STARS` takes a classic token with
`public_repo`; keeping it separate means the main token never needs write
access to anything. Without it the star curve simply starts at your first
collection run.

## Behind a reverse proxy

`docs/traefik.yaml.example` shows a route with two locks: restricted to the
local network, and the dashboard's own login on top.
`compose.override.yaml.example` puts the container on the proxy network
without publishing a port.

## How it works

One container, one SQLite file, no external services.

- **Hourly** — the cheap counters: stars, forks, watchers, release downloads.
- **Daily** — everything else: traffic, referrers, popular paths, issues, CI
  runs, contributors, commits, Home Assistant installations.

Charts are SVG drawn on the server. No charting library, no build step, no CDN
— the pages render on their own and work offline.

Nothing leaves your network except the calls to the GitHub API and to the Home
Assistant analytics endpoint.

## Questions

**Why are my clone numbers so high?**
Because most of them are machines. Every `actions/checkout` in a workflow is a
clone to GitHub — one per job in a matrix build. Bots and mirroring services
add more. That is why the tile leads with distinct cloners and keeps the raw
count underneath.

**Why does an integration show installations I do not recognise?**
Home Assistant reports per integration domain, and a domain belongs to
everyone shipping that integration. Repo Stats splits the count by version and
counts only the versions released from your repository.

**Does it work without a token?**
Partly. Stars, forks and downloads are public. Traffic and clones are not —
those need a token, which is the whole reason this runs server-side.

**Can it follow somebody else's repositories?**
Only for the public figures. Traffic is available to the owner alone.

**Does it phone home?**
No. There is no telemetry, no analytics, no update check.

## Contributing

Issues and pull requests are welcome — especially for figures worth adding.

If this saves you from opening fifty Insights pages, a ⭐ helps others find it.

<a href="https://buymeacoffee.com/sphings"><img src="https://img.shields.io/badge/Buy%20me%20a%20coffee-FFC107?logo=buymeacoffee&logoColor=black" alt="Buy me a coffee"></a>

## Licence

**AGPL-3.0** — see [LICENSE](LICENSE).

Use it, change it, run it wherever you like. The one condition: if you offer
it to others over a network, they get the source of your version too. That is
what separates the AGPL from the GPL, and for something that runs as a service
it is the case that matters.

---

<sub>github statistics dashboard · repository analytics · traffic history ·
clone tracking · star history · release download counter · self-hosted ·
docker · fastapi · sqlite · home assistant analytics</sub>
