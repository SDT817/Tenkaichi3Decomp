# R15 private lobby on official v0.1.39.1

Base: exact R14 CN8 endpoint, official commit 7b43a75bd8b0aeabcce0a22c45e1ad66162ac9d7.
Previous private endpoint: R13 LobbySettings, including installer recovery fix1.

The only existing runtime sources changed relative to R14 are gs/ui.cpp,
gs/net_match.c/h and the display selection in gs/net.c. New runtime modules are
online_lobby, online_directory, online_json and online_ping, retained from R13.
The native build reuses all R14 game/data/renderer/input/font/rollback objects;
only gs_net, gs_net_match and cxx_ui are rebuilt and two lobby objects are added.

Match tasks retain their private endpoint/authorization and socket parameters
across cancellation and upstream matchmaking changes. Official protocol 6,
fingerprint requirements and packet processing remain unchanged. Private
connections wait until the official fingerprint is ready before configuring the
transport, so delayed official startup cannot revert to public matching.

Administrator room creation and name overrides persist in room_names, alongside
the existing room_rules table. Transactional operations reject non-admins,
active matches and stale epochs. Added rooms start at 100% speed; maximum 32.
The gateway health check now requires protocol 6. No TLS identities, TURN
configuration, credentials or public endpoints are regenerated.

Build: E:\Phyton\python.exe -X utf8 local\build_online_lobby.py
See port/lobby/README.md for service, native UI, real handshake and TURN tests.
Output: Chinese-local-analysis-20261022/online-lobby5-official1391-20261029.
No GitHub commit, push or PR. Exact before/after sources and binary-safe patches
from R13, R14 and official .39.1 are independently replayed and byte-compared.
