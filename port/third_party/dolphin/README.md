# Dolphin expression parser

Copied from Dolphin 10912, revision 82fd7f576e1dff6b616ff088955c18aa76ed45d5.
Copyright 2013 Dolphin Emulator Project. GPL-2.0-or-later; see license.txt.
Upstream: https://github.com/dolphin-emu/dolphin/tree/82fd7f576e1dff6b616ff088955c18aa76ed45d5

ExpressionParser.cpp/.h are imported from Source/Core/InputCommon/ControlReference.
Changes: relative includes, bounds-safe token access, reject unconsumed tokens.
The caller limits input length and nesting before parsing. Valid-expression
operator behavior and the lexer/AST algorithms are unchanged.
Common/StringUtil.h and InputCommon/ControllerInterface/Device.h are local
minimal adapters, not copies of the full Dolphin device or emulator layers.
The parser is compiled by control_bindings.cpp, which supplies SDL inputs.
The combined distribution uses GPLv3 in combination with the project's AGPLv3
code, as permitted by AGPLv3 section 13; upstream notices remain intact.

The local editor follows DolphinQt/Config/Mapping/IOWindow.cpp and MappingCommon.cpp
(Copyright 2017 Dolphin Emulator Project, GPLv2+): null selection, cursor insertion,
device qualification and input quoting. Mouse smoothing, sensitivity, stale-input
timeout and key aliases follow ControllerInterface/DInput/DInputKeyboardMouse.cpp
and NamedKeys.h (Copyright 2010 Dolphin Emulator Project, GPLv2+), adapted to SDL.

Common/ProfileIni.h contains the read-only profile subset adapted from
Source/Core/Common/IniFile.cpp/.h (Copyright 2008 Dolphin Emulator Project,
GPLv2+): ParseLine, Load's BOM/section/key handling and case-insensitive lookup.
SDL handles UTF-8 file IO; the emulator's other INI features are not included.
Profile UI/load-save behavior follows MappingWindow.cpp and
ControllerEmu/ControlGroup/ControlGroup.cpp. See docs/local-wii-profiles.md for
the exact mappings, unsupported device reporting and the locally added share-code
format, which is not a Dolphin feature.
