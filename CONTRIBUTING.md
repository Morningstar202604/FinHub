# Contributing to FinHub

## Working rules for this repository

* Dependency updates: search the whole repository for every occurrence of a dependency (build files, lockfiles, CI workflows, docs) before bumping. A partial bump — declaration updated but the lockfile or a pinned action left behind — is the most common cause of "works locally, CI fails". Keep lockfiles in the same commit as the declaration. Move version-coupled toolchain upgrades (e.g. Gradle/AGP/Kotlin/Hilt or the Python/uv pair) together in one commit.
* Refactoring: pull latest main first, work on a fresh branch, keep commits atomic with messages that state the why, and always run the full check suite before pushing (for this repo: `make test` for backend units and `make test-web` for frontend units, plus `make lint`). A branch left behind main cannot be merged under the repository's branch protection.
* Merge conflicts: resolve conflicts in the working tree against the latest main; never force-push shared branches; never resolve a conflict by blindly taking either side — re-read both sides and keep both changes when they are both valid.
* Versioning: releases follow X.Y.Z starting at 0.0.0. Last digit = fixes, middle digit = feature work, first digit stays 0 until a stable release is declared. Bump the version in code, CHANGELOG.md and the tag in the same change.

Thanks for your interest in contributing to FinHub! This guide covers how to
set up your environment and submit changes.

> **Working language:** English is our preferred language for communication.
> Chinese is also welcome in issues and pull requests — but all code changes and
> docstrings must be written in English.

## Prerequisites

- Docker and Docker Compose

For running on your host instead of containers (optional): Python 3.13+ with
[uv](https://docs.astral.sh/uv/), and Node.js 22+ with pnpm.

## Quick Start

The whole stack — backend, frontend, PostgreSQL, and Redis — runs with Docker
Compose:

```bash
git clone https://github.com/finhub/FinHub.git
cd finhub
cp .env.example .env
make config   # interactive wizard: LLM, data, sandbox, web search, and web fetch
make up       # build + start the full stack
```

- **Backend API** → http://localhost:8000 (hot-reload; `./src` is mounted)
- **Frontend** → http://localhost:5173 (hot-reload)
- **PostgreSQL + Redis** — managed by Compose

Verify the backend is healthy:

```bash
curl http://localhost:8000/health   # → {"status": "healthy"}
```

Stop the stack with `make down` (or `make clean` to also reclaim Docker disk).

No keys are strictly required — see [Data Provider Fallback Chain](README.md#data-provider-fallback-chain).
For the full experience, set `DAYTONA_API_KEY` and `FMP_API_KEY` in `.env`; for
LLM access, set an API key or connect via OAuth in the UI.

<details>
<summary>Running on your host instead of Docker</summary>

```bash
make install    # backend (uv) + frontend (pnpm) dependencies
make setup-db   # PostgreSQL + Redis in Docker + initialize tables
make dev        # backend on :8000 (hot-reload)
make dev-web    # frontend on :5173 (run in a separate terminal)
```

For web crawling on the host, install the browser dependencies (already bundled
in the Docker image):

```bash
source .venv/bin/activate && scrapling install
```

</details>

## Contributing Changes

1. **Please start a feature with an issue.** Before building a feature, we'd
   kindly ask you to open a [GitHub Issue](https://github.com/finhub/FinHub/issues)
   with a short proposal. This lets a maintainer weigh in early and ensures a
   swift follow-up once your pull request lands. Bug fixes are welcome to go
   straight to a PR.
2. **Please check with us before adding a dependency.** We'd kindly ask that you
   not add a new third-party dependency or external service without checking with
   a maintainer first. If you think a library or service would be a good fit, we'd
   love to hear about it — please propose it in an issue before wiring it in.
3. **Please show that your change works.** We'd kindly ask that every change
   demonstrate the intended behavior — the bug fix or new feature — works as
   expected. Please verify it end to end, and add tests that guard against
   regressions in the areas your change touches.
   ```bash
   make test       # backend unit tests
   make test-web   # frontend unit tests
   make lint       # linters
   ```
4. **Open a pull request** against `main` with a clear description of what changed
   and how you verified it. Thank you for contributing!

## Code Style

**Python:**
- Linted with [Ruff](https://docs.astral.sh/ruff/) — `uv run ruff check src/`
- Async-first: use `async def` for handlers and services
- No ORM — raw SQL via psycopg3

**Frontend (TypeScript/React):**
- Linted with ESLint 9 (flat config) — `cd web && pnpm lint`
- Components use shadcn/ui + Tailwind CSS

## Reporting Issues

Open a [GitHub Issue](https://github.com/finhub/FinHub/issues) with what you
expected vs what happened, steps to reproduce, and relevant logs or screenshots.

## Questions?

Open a [GitHub Discussion](https://github.com/FinHub/FinHub/discussions).

## License

FinHub is licensed under the [Apache License 2.0](LICENSE). By submitting a
contribution, you agree that it is licensed under those same Apache-2.0 terms
(the standard "inbound = outbound" model — see Apache-2.0 §5). Please only submit
work you have the right to license under those terms.
