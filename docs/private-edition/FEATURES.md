# Feature map for the published 0.17 source

The source baseline is the accepted r22 endpoint. File ownership overlaps;
coordinate before changing `ui.cpp`, `gs_input.c`, `gs_draw.c`, `gs_gpu.c`,
`menu_text.c` or battle input code.

## Wii controls

Primary code: `port/src/gs/control_bindings.*`, `control_editor.cpp`,
`control_profile_ui.cpp`, `control_profiles.*`, `gs_input.c`,
`port/include/port_control_mode.h`, `src/sys/game_pad.c`,
`src/battle/btl_input.c`, `port/src/plat_settings.c` and the control page in
`port/src/gs/ui.cpp`.

Dolphin expression code and its provenance/license are under
`port/third_party/dolphin/`. Input mapping and profiles are local player settings;
do not encode them as changes to packet format, protocol or rollback.
See `docs/local-wii-controls.md`, `docs/local-wii-profiles.md`,
`local/CONTROLS_FIX_CHANGES.md` and `local/tests/`.

## Chinese localization

Runtime code: `menu_labels.*`, `menu_text.*`, `ui_text_translate.*`, `ui_zh.h`,
text paths in `gs_draw.c`, `port/src/a11y_game.c`, `src/battle/btl_script.c`,
`src/battle/btl_seq.c`, `src/battle/col_c.c`, and the translated F1 UI.
Fonts are registered by `port/third_party/fonts/fonts.tsv`.

The latest inherited runtime is included, with the accepted rounded-bold font
layout and prior audited glyph behavior. Disc-derived textures, patched archive
members and Chinese resource packs are deliberately not imported into Git.
`development/analysis-tools/` preserves the resource-builder, mapping-review
and HD184 maintenance source plus its local Python import dependencies.
These scripts need the historical external inputs documented in their code.
See `local/CODE_CHANGES.md` for corrections and resource provenance.

## Performance and presentation

The accepted I presentation and subsequent accepted bounded menu/font cache
work are in `gs_gpu.c`, `gs_draw.c`, `menu_text.c` and `col_c.c`.
Optional diagnostics are in `perf_trace.*`; normal play does not enable them.
See `local/CN7_IMMEDIATE_I_CHANGES.md`, `local/CN8_MENU_CACHE_CHANGES.md` and
`local/LOBBY017_CHANGES.md` in chronological order.

In final 0.17, supported devices retain Immediate even when the saved VSync
option is enabled, falling back to Mailbox/FIFO when necessary. The prior I
record's VSync policy describes that historical version, not this final change.
Do not reintroduce rejected performance experiments from old local folders.

## First-use Dragon Dash rendering fix

`port/src/gs/gs_draw.c`, framebuffer-as-texture selection: a framebuffer with
draws already queued in the current list is eligible for sampling before the
backend has marked it cleared. Keep the VRAM upload-generation check and the
backend's attachment clear. The accepted condition uses
`gsTargets[src].cleared || gsTargets[src].draws`. This is the 0.15 fix retained
by 0.17; it changes rendering, not dash gameplay or network input.

## Lobby, server and updater

UI/client: `online_lobby.*`, `online_directory.inl`, `online_ping.*`,
`online_json.h`, `http_process.h` and `ui.cpp`. View and pause integration also
touches `net.c`, `net_match.*`, `btl_cam.c`, `hud_0.c` and battle/UI hooks.

Services and tooling: `port/lobby/server.py`, `directory_server.py`,
`ping_service.py`, `turn_windows/`, `private_gateway/`, `deploy/`,
`publish_update.py` and the colocated tests.
Launcher integrity is in `private_gateway/integrity.go`; update installation
is in `port/src/gs/net_update.c`. Public trust keys and version identity are in
`update_key.h`, `local_release.h` and the gateway. Signing private keys and
administrator configuration are not part of the repository.

Keep official protocol 6, deterministic rollback and private transport changes
distinct. This complete branch does contain the previously accepted private
lobby/view/pause integration; it is not identical to official networking source.
The 0.17 flight/integrity/presentation delta leaves the 0.16 battle networking,
relay and rollback implementation unchanged.

## Trunks Test4

Only `src/battle/btl_act_d.c` and `src/battle/btl_char_action.c` contain this
accepted battle-mechanic delta. It applies to character 41, slot 3 skill 0x163,
after hit-recovery transition 0x12E into neutral. Flight eligibility waits four
battle decision frames. Direction and every other button retain their original
timing. Original flight and release behavior are retained; do not replace the
original flight handler or delay the entire input mask.

See `local/TRUNKS_FLIGHT_CHANGES.md`, `local/tests/test_trunks_flight.c` and
`local/tests/run_trunks_flight.py`. The latter retains a historical sibling-r20
comparison and local compiler path; those prerequisites are not a second copy
of the code required by the game. They need adapting for a fresh machine.
