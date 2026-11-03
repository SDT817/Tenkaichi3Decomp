# CN8: official 0.1.39.1 and main-menu prewarming

Verified on 2026-10-29: the official latest release redirects to v0.1.39.1,
commit `7b43a75bd8b0aeabcce0a22c45e1ad66162ac9d7`. The raw official source ZIP
and the response metadata are retained. The previous non-lobby local branch is
r11 ControlsFix/W3, based on official 0.1.38.9. The r13 private lobby branch
is separate and is not included. No commit, push, or PR is made.

The three-way merge retains existing CN7-HD184 translations and audited font,
Wii controls/settings/profiles and accepted I presentation. Upstream UI logic
and translation catalog bounds win their conflicts. Existing Chinese-bank
selection remains; `MenuLabels_ArtSwap` and `ml_mid_hash` are byte-identical to
official 0.1.39.1. The previous local art quick filter is removed. Official
label fingerprints in menu_text.c remain the official algorithm.

The existing 192 MiB/16-entry CPU glyph atlas cache, exact referenced-cell
verification, per-menu-frame glyph warmup, and identical-atlas GPU reuse are
retained. The 24 MiB/256-row menu cache and its eviction policy are unchanged.
The approved rasterizers, glyph metrics, colors, font, text and resolution
remain unchanged. There is no new persistent cache or worker thread.

Only three runtime files implement this task's additional menu optimization:

* `menu_text.c`: identify the 25 main-menu label rows while reading their
  existing catalog IDs; prepare at most one row between menu frames through
  the same rasterizer and bounded cache. Clearing the font cache resets the
  preparation cursor; resolution changes restart it. Existing glyph-plane
  warmup continues after these rows. Cold drawing still works if the player
  reaches the menu before all rows have been prepared.
* `menu_text.h`: update the warmup API comment; no signature change.
* `src/battle/col_c.c`: notify the renderer at Font_SetFont, after all original
  pointer relocation and slot fields have been established. This permits
  glyph preparation before the first Font_Flush. The existing notification
  during texture upload remains, and identical registrations are no-ops.
  The hook does not submit a texture, alter a game field, or change drawing.

`ui.cpp` additionally contains one false local-edition constant and guards
around the official update tick, banner, panel, and checkbox. Existing saved
settings and environment overrides cannot re-enable automatic checking,
downloading, installation or restart through this UI. The updater and all
network source files themselves remain exactly official. Re-enable only
after a future explicit integration decision.

IMPORTANT: upstream itself changed NET_VERSION from 5 to 6 in v0.1.39,
because its lobby flow and mandatory gameplay fingerprint changed. This
edition retains that official value and code. It is not a local protocol
patch, and older 0.1.38 copies cannot join it. All seven network objects were
independently compiled from official source and compared without debug data;
both online UI regions also match official statements apart from text.

Offline CPU measurements on this machine, not live FPS results: all 25 menu
rows at 3x cost about 15.7 ms cold versus 0.0024 ms for prepared cache lookups.
One row's preparation cost at most about 1.14 ms at 3x and 1.87 ms at 4x in
this run. 7,591,720 row bytes and 102,629,376 shared-atlas bytes compare exactly.
Catalog/skill/story lookup and cache invalidation checks pass. The disabled
updater is exercised with BT3_UPDATE_CHECK=1 and BT3_UPDATE_AUTO=1.

Build with `E:\Phyton\python.exe -X utf8 local/build_cn8.py` and the same
existing Windows/SDL toolchain. The official build scripts are unchanged.
The custom local build reports `dev` under the official version-generation
rule; its exact base is recorded here and in CN8-Build.json.

The independent playable test copy and all replay-verified patches, exact
source endpoints, build logs, source/resource hashes and matching EXE/mem/DAT
are under `Chinese-local-analysis-20261022/cn8-upstream-menu-cache-20261029`.
The test copy retains personal settings, profiles and saves; the installed
game is not replaced. Gameplay and GPU/live-FPS tests await the user.

For the eventual cross-branch integration, apply the three-file menu-only
patch and the one-file update-policy patch onto the matching official-based
Chinese/Wii renderer. Do not overwrite official network files with the older
private-lobby branch. The full official-to-local patch is also replay-tested.
