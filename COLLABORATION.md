# Private edition 0.17: collaboration entry point

This repository branch contains the complete source of the currently installed
private edition **0.17 / r22**, based on official **v0.1.39.1**, commit
`7b43a75bd8b0aeabcce0a22c45e1ad66162ac9d7`. It is a source publication of the
accepted build, not a new game update or a merge with a newer upstream release.

- Integration branch: `codex/private-0.17`.
- [中文协作说明](docs/private-edition/README.zh-CN.md).
- [Build and verification](docs/private-edition/BUILDING.md).
- [Feature boundaries](docs/private-edition/FEATURES.md).
- [Recorded source hashes](development/provenance/source-sha256.json).

## Development branches

| Branch | Intended work |
| --- | --- |
| `codex/dev-wii-controls` | Wii/PS2 controls, Dolphin expressions, profiles and settings |
| `codex/dev-chinese` | Chinese text, fonts and localization pipeline |
| `codex/dev-performance` | Accepted I presentation and bounded text/atlas caching |
| `codex/dev-dragon-dash` | First-use Dragon Dash framebuffer sampling fix |
| `codex/dev-lobby` | Private lobby, directory, relay integration, updates and launcher |
| `codex/dev-trunks-test4` | The accepted four-frame Trunks flight-only adjustment |

All six development branches intentionally start at the **same complete 0.17
integration commit**. They are collaboration starting points, not isolated
feature patches and not independently reconstructed historical branches.
Existing features share input, UI and renderer files. Starting everyone from
the accepted complete source avoids dropping those dependencies.

Create new work from the integration branch or the relevant development branch;
submit changes against `codex/private-0.17` in this fork. Do not force-push over
another contributor's work. The upstream `main` and the earlier official PR
branch are not changed by this publication.

## Provenance and scope

The first private-edition commit imports the recorded r22 endpoint. Every
runtime, test and build-adapter file in that endpoint is retained byte for byte.
The publication adds documentation, localization maintenance scripts and ignore
rules; it does not alter gameplay, inputs, rendering, networking or protocols.
Use `python -X utf8 development/verify_recorded_source.py` to verify that claim.

The `local/*CHANGES.md`, `local/CODE_CHANGES.md` and Chinese history document
describe previous development sessions. Statements there such as "not committed"
or "local only" are historical: public Git publication was authorized on
2026-11-03. Their source details and previous test results are not rewritten.

The source publication excludes ISO/disc data, extracted or modified game
archives, saves, personal profiles, administrator credentials, release signing
private keys, server databases and compiled game packages. Chinese disc-derived
resources remain separate inputs: this is source code, not a playable download.
The matching audited Chinese resource pack and an authorized game disc are
required to reproduce the installed game's complete translated appearance.

Public verification keys, the current public server endpoint, original
licenses and third-party attribution remain in the code. Each developer must
use separate local configuration for their own server or signing keys. Keep
the Dolphin GPL notices, font OFL notices and upstream project licenses.
