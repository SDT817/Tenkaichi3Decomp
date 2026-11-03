# Local Wii controls edition

This branch is local only; it must not be pushed to PR #139.

Current r3 base: official `559f85b2bb06c1d7200e8a87b9a5b346925e13de` (0.1.37.1).
The original r1/r2 base was `ec3c85a98cffd9cd22c22ac14cd62fb584d23664` (0.1.37),
plus the tested minimal Wii commits `8176099` and `e034229`. The r2 worktree is retained.
The requester confirmed remote UU netplay works with that minimal edition on 2026-10-19.

## Dolphin source analysis (before implementation)

Source supplied by the requester: Dolphin 10912,
`D:/dolphin-82fd7f576e1dff6b616ff088955c18aa76ed45d5`.

- `Source/Core/InputCommon/ControlReference/ExpressionParser.cpp` / `.h`:
  lexer, recursive-descent parser and expression tree. `&` is min, `|` is max,
  `+` is addition saturated at 1, `!` is 1 minus the operand. Binary operators
  have equal precedence and associate left to right; parentheses override it.
  Backticks quote device/control names. Bare controls are preferred when found.
- `ControlReference.cpp`: an expression is parsed when edited, its resolved
  input references are cached, and its result is multiplied by range / 100.
- `ControllerEmu/ControlGroup/Buttons.h`: a digital action activates above 0.5.
- `DolphinQt/Config/Mapping/IOWindow.cpp`: device/input list, selection and
  detection, operator insertion, range, expression editor, Clear/Apply/OK.
- `MappingButton.cpp`: left click detects, middle click clears, right click
  opens the expression editor. `MappingCommon.cpp` quotes non-letter names.
- `ControllerEmu/ControlGroup/ControlGroup.cpp`: stores the expression and
  range separately for each control.

Reuse the parser and evaluator with attribution (GPL-2.0-or-later) and a small
SDL input adapter, rather than introduce Qt or Dolphin's device/core layers.
Preserve operator order, thresholds and range behavior. Bound malformed input
to avoid reading past the token stream or unbounded recursion.

## Scope and update policy

- Wii-only per-player control separation, independent camera/teammate/burst
  actions, and Dolphin expressions. Burst remains a double tap within the
  original battle-frame window; no wall-clock tap timer.
- Keep PS2 settings and the existing combined Wii mode. Combined and separated
  Wii profiles each have one shared keyboard/mouse/controller expression per action.
- Chinese F1 overlay with a Chinese-capable system/font fallback.
- No edits to networking, matchmaking, protocol, rollback, or raw pad report
  size. Verify these source files against the official base before packaging.
- Keep changes uncommitted in this dedicated local worktree, with full source,
  patches, verification results and build notes. Do not commit or push them.
  Future updates should apply the patch with three-way merging onto the updated
  upstream in a new worktree, resolve only control/UI conflicts, rerun checks
  and compare networking sources with that new upstream.

## r2 editor and grouped layout

Dolphin 10912 IOWindow.cpp / MappingCommon.cpp behavior was reviewed before the
editor update. A null selection inserts nothing; controls are qualified when
they come from a non-default device; detection selects and reveals the matching
input. The ImGui version uses `ImGuiListClipper::IncludeItemByIndex` and
`SetScrollHereY`, and inserts at the expression caret or replaces its selection.
An InputText callback synchronizes inserted text with ImGui's edit buffer.

One expression now resolves bare names against Keyboard / Mouse and
`Controller:` names against the selected player's gamepad. Legacy two-column
files are backed up before rewrite and merged by OR; controller controls receive
an explicit device qualifier. If the former columns used different ranges, the
non-empty keyboard column's range applies to the merged expression; both
original values remain in `.r1.bak`.

Mouse event behavior follows Dolphin's `DInputKeyboardMouse.cpp`: integer axes
use `(previous + delta) / 2`, sensitivity 8, and stale input expires after
250 ms. Common `NamedKeys.h` aliases are accepted. SDL supplies events and
device state; Qt and DirectInput device implementations are not included.

The Wii screen groups button actions, movement stick, character / camera stick,
and trigger / flight / vibration controls. Each binding button uses the same
runtime expression evaluator and range as the game and lights above the Dolphin
0.5 digital threshold. The Controls page disables gamepad navigation before
`NewFrame`, blocks the custom back / shoulder shortcuts, and restores navigation
on other tabs. Binding capture and live gamepad sampling remain active.

## r3 upstream merge and caret fix

The full r2 controls are merged onto v0.1.37.1, including the new upstream
network diagnostics and the original protocol 5. Protected networking and
related files are checked against that new official base, and all five network
objects are rebuilt from the base before comparing them with the local build.

The expression editor previously treated a collapsed selection's anchor as the
caret. ImGui/stb_textedit can leave that anchor behind after typing. In
`append()`, an empty selection now uses `sCursor`; a non-empty selection still
uses its endpoints. Actual ImGui text events and the game-window interaction
check `W &!` followed by Select Z gives `W &!Z`, plus repeated insertion.
Only the two insertion-boundary lines change in the runtime editor.

See `local/CODE_CHANGES.md` for the file/function map and update boundaries.
`local/save_code_history.py` saves full-index Git patches, per-file patches,
r2-to-r3 source deltas and hashes, and both exact source bases. It actually
applies each patch in a temporary directory and compares the resulting source.
No commit or remote update is needed to preserve these code records.
