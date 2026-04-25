# Third-Party Notices

This repository bundles or references several third-party resources.  This
document inventories them and the licence under which each is used.  If any
rights holder wishes for their material to be removed, please open an issue.

---

## Bundled in this repository

### Platform artwork - CC BY-NC-SA 4.0

**Paths:**
- `frontend/public/platforms/icons/*` (188 platform icons)
- `frontend/public/platforms/names/*` (206 platform name logos, SVG)
- `frontend/public/platforms/fanart/*` (204 fanart images, WebP)

**Source:** Colorful Pop and Elementerial EmulationStation themes by **RobZombie9043**

**Licence:** Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International (CC BY-NC-SA 4.0)

**Attribution required:** yes (see LICENSE-ASSETS)

**Commercial use:** not permitted while bundled - see LICENSE-ASSETS

---

## Metadata service icons - trademark / nominative use

**Path:** `frontend/public/icons/*.ico` and `*.svg`

The following icons are trademarks of their respective owners.  They appear
in the application to identify metadata sources, not to imply endorsement:

| Icon                | Owner                  | Purpose                     |
|---------------------|------------------------|-----------------------------|
| `gog.ico`           | CD PROJEKT S.A.        | GOG.com identifier          |
| `igdb.ico`          | Twitch Interactive     | IGDB ratings / metadata     |
| `RAWG.ico`          | RAWG.io                | RAWG ratings                |
| `Steam.ico`         | Valve Corporation      | Steam store metadata        |
| `metacritic.svg`    | Red Ventures           | Metacritic scores           |
| `ScreenScraper.ico` | screenscraper.fr       | ROM metadata provider       |
| `steamgriddb.ico`   | SteamGridDB community  | Cover / hero artwork API    |
| `launchbox.ico`     | Unbroken Software, LLC | LaunchBox GamesDB metadata  |
| `RetroAchievements.ico` | RetroAchievements  | Achievement tracking        |
| `srl.ico`           | System Requirements Lab| PC requirements analyser    |
| `os-linux.svg`      | public domain (Tux)    | Linux OS indicator          |

These icons are not covered by this project's licence.  They remain property
of their respective owners and are used for identification purposes only
under nominative fair-use doctrine.

---

## Application logo

**Path:** `frontend/public/GDLOGO.png`, `frontend/public/GDLOGO+TEXT.png`

Created for this project.  Licensed under the same terms as the source code
(AGPL-3.0) unless re-licensed explicitly.

---

## External services and APIs

The application fetches data at runtime from the following APIs.  None of
this data is bundled in the repository, but the project depends on these
services to deliver its features:

- **GOG.com embed & v1/v2 APIs** (https://api.gog.com)
- **IGDB API** (https://api.igdb.com) - requires free client credentials
- **RAWG API** (https://rawg.io/apidocs) - requires free API key
- **Steam Store API** (https://store.steampowered.com)
- **HowLongToBeat** (via unofficial scraper)
- **SystemRequirementsLab** (via HTML scraper)
- **ScreenScraper** (https://www.screenscraper.fr/api2) - requires free account
- **SteamGridDB API** (https://www.steamgriddb.com/api/v2) - requires free API key
- **LaunchBox GamesDB** - bundled as on-disk SQLite index, built from the
  publicly-released LaunchBox Metadata.zip

Users are responsible for reading and complying with each service's terms
of use.

---

## Bundled binary dependencies (via Docker image)

Fetched at build time, not in the git repository:

- **EmulatorJS** v4.2.3 (https://github.com/EmulatorJS/EmulatorJS) -
  GPL-3.0, includes RetroArch cores (various licences per core)
- **MariaDB** 11.3 - GPL-2.0
- **Valkey** 8 (Redis-compatible) - BSD-3-Clause
- **ClamAV** - GPL-2.0
- **Transmission** - GPL-2.0

Each Docker image pulls upstream releases under their respective licences.

---

## Frontend dependencies

See `frontend/package.json` for the full list.  Notable:

- **Vue 3** - MIT
- **Vite** - MIT
- **Pinia** - MIT
- **Vuetify** - MIT
- **socket.io-client** - MIT
- **axios** - MIT
- **@vueuse/core** - MIT
- **vue-i18n** - MIT

---

## Python dependencies

See `backend/requirements.txt`.  Notable:

- **FastAPI** - MIT
- **SQLAlchemy** - MIT
- **Pydantic** - MIT
- **httpx** - BSD-3-Clause
- **pluggy** - MIT
- **Pillow** - HPND (Historical Permission Notice and Disclaimer)
- **beautifulsoup4** - MIT

---

## Credits & Acknowledgments

GamesDownloader V3 was inspired by several outstanding open-source projects:

- **[RomM](https://github.com/rommapp/romm)** - ROM management platform that
  inspired the emulation library architecture, metadata scraping approach,
  and platform organisation.
- **[Gameyfin](https://github.com/grimsi/gameyfin)** - Self-hosted game
  library manager that inspired the original concept of a personal game
  vault with automatic metadata fetching.

**NEON HORIZON** Couch Mode plugin (shipped separately via the plugin store)
uses assets from EmulationStation community themes by **RobZombie9043**:

- **Colorful Pop** - platform artwork, SVG logos, coloured icons, platform
  metadata with 15-language descriptions, video positioning data, system
  colour palettes.
- **Elementerial** - additional design inspiration.

These themes are licensed under Creative Commons BY-NC-SA and the bundled
assets are included for non-commercial, personal use (see LICENSE-ASSETS).
All credit for original artwork goes to RobZombie9043.

Special thanks to the teams behind EmulatorJS, ScreenScraper, SteamGridDB,
LaunchBox, HowLongToBeat, and the dozens of other projects this codebase
stands on.

---

## Reporting

If you believe this repository contains your copyrighted material used
without authorisation, or if you want attribution amended, please open
an issue at https://github.com/60plus/GamesDownloader/issues with:

- The specific file(s) in question
- Proof of ownership or the upstream source
- Desired remedy (removal, amended attribution, or licence negotiation)

Claims will be handled in good faith as quickly as possible.
