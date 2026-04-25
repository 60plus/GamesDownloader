# Contributing to GamesDownloader

Thanks for taking the time to contribute. This document covers what you need to know before opening an issue or sending a pull request.

## Community

- **Discord:** [GamesDownloader server](https://discord.gg/Hz8BNNQrMu) for real-time help, library showcase, plugin development talk.
- **GitHub Discussions:** [Discussions tab](https://github.com/60plus/GamesDownloader/discussions) for searchable Q&A and ideas.

## Before you open an issue

1. Search the existing [issues](https://github.com/60plus/GamesDownloader/issues?q=) and [discussions](https://github.com/60plus/GamesDownloader/discussions) for duplicates.
2. Make sure you are running the latest release from `main`.
3. Reproduce the bug at least twice on a fresh page reload (Ctrl+Shift+R) to rule out browser cache.
4. Use the issue template that matches your situation:
   - Bug Report for confirmed bugs with reproducible steps.
   - Feature Request for new functionality with a clear problem statement.
   - For "how do I" or "is this possible" questions, try [Discord](https://discord.gg/Hz8BNNQrMu) first or use Discussions.

Issues without reproducible steps will be closed.

## Local development setup

```
git clone https://github.com/60plus/GamesDownloader.git
cd GamesDownloader
docker compose up --build
```

Open `http://localhost:8080` and walk through the Setup Wizard. Default ports:
- `8080` GamesDownloader UI / API
- `9091` Transmission daemon (torrent seeding)
- `51413` BitTorrent listen port

For frontend hot reload during UI work:
```
cd frontend
npm install
npm run dev
```

## Branching and commits

This repository (`github.com/60plus/GamesDownloader`) holds release-ready commits only. Active development happens on a private mirror with full WIP history; only clean, reviewed changes land here.

When you submit a PR:
- Branch off `main`, name it `fix/<short>` or `feat/<short>`.
- Keep commits focused. Squash WIP, "fix typo", "try again" commits before opening the PR.
- Write commit messages in the imperative mood: "Fix GOG sync hang", not "Fixed" or "Fixes".
- No AI co-author trailers (`Co-Authored-By: Claude` etc.) and no em-dashes in commit messages or text - use plain hyphens.

## Code style

- **Backend (Python)**: follow existing style; `snake_case` for functions and variables, `CamelCase` for classes. Run `python -m py_compile backend/**/*.py` before pushing.
- **Frontend (Vue 3 + TypeScript)**: existing components use `<script setup lang="ts">` + scoped CSS. Pull design tokens (`--pl`, `--space-*`, `--fs-*`) instead of hardcoded values. See `docs/design-system.md`.
- No new dependencies without a comment explaining why.

## Testing

Manual test steps in the PR description are required. Automated tests are welcome for any backend logic that touches scrapers, file system layout, or scoring - place them under `backend/tests/`.

## License

By contributing you agree that your contributions are licensed under [AGPL-3.0](LICENSE) (code) and [CC BY-NC-SA 4.0](LICENSE-ASSETS) (bundled platform artwork). See [NOTICE.md](NOTICE.md) for third-party attribution.
