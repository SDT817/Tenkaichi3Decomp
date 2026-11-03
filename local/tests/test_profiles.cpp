#include "../../port/src/gs/control_profiles.h"
#include "../../port/src/gs/ui.h"
#include <cassert>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <zlib.h>
extern "C" void PortWii_Cancel(void) {}
// Isolate known-folder tests from the user's real Documents presets.
extern "C" const char *SDLCALL SDL_GetUserFolder(SDL_Folder folder) {
    return folder == SDL_FOLDER_DOCUMENTS ? SDL_getenv("BT3_TEST_DOCUMENTS") : nullptr;
}
static int checks;
#define CHECK(x) do { ++checks; if (!(x)) { fprintf(stderr, "FAIL %d: %s\n", __LINE__, #x); abort(); } } while (0)
using namespace WiiProfiles;
static bool equal(const Profile& a, const Profile& b) { return Serialize(a) == Serialize(b); }
static bool share_equal(Profile a, Profile b) {
    for (int action = 0; action < PORT_WII_ACTIONS; action++) {
        if (action == 12) { continue; }
        char x[PORT_WII_EXPR_SIZE], y[PORT_WII_EXPR_SIZE];
        if (!PortWii_Format(a.text[action].c_str(), 0, x, sizeof(x)) ||
            !PortWii_Format(b.text[action].c_str(), 0, y, sizeof(y))) { return false; }
        a.text[action] = x; b.text[action] = y;
    }
    return equal(a, b);
}
static std::string share(const std::string& payload, const char *version) {
    const char *alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
    std::string data = payload, code = version;
    Uint32 crc = SDL_crc32(0, data.data(), data.size());
    for (int i = 0; i < 4; i++) { data += (char)(crc >> (i * 8)); }
    unsigned bits = 0; int count = 0;
    for (unsigned char c : data) {
        bits = (bits << 8) | c; count += 8;
        while (count >= 6) { count -= 6; code += alphabet[(bits >> count) & 63]; }
    }
    if (count) { code += alphabet[(bits << (6 - count)) & 63]; }
    return code;
}
static std::string compressed_share(const std::string& data, const char *version) {
    uLongf size = compressBound((uLong)data.size());
    std::string packed(size, '\0');
    CHECK(compress2((Bytef *)packed.data(), &size, (const Bytef *)data.data(), (uLong)data.size(), 9) == Z_OK);
    packed.resize(size);
    return share(packed, version);
}
static void compact_checks() {
    char text[PORT_WII_EXPR_SIZE];
    CHECK(PortWii_Format("  `J` | (`K` & !`SPACE`)  ", 0, text, sizeof(text)) && !strcmp(text, "J|(K&!SPACE)"));
    CHECK(PortWii_Format(text, 1, text, sizeof(text)) && !strcmp(text, "J | (K & ! SPACE)"));
    CHECK(PortWii_Format("`1` | `F1` | `Left Shift` | `Axis X-` | `Controller:A`", 0, text, sizeof(text)) &&
          !strcmp(text, "`1`|`F1`|`Left Shift`|`Axis X-`|`Controller:A`"));
    CHECK(PortWii_Format("F1", 0, text, sizeof(text)) && !strcmp(text, "`F1`"));
    CHECK(PortWii_Format("Left Shift", 0, text, sizeof(text)) && !strcmp(text, "`Left Shift`"));
    CHECK(PortWii_Format("J K", 0, text, sizeof(text)) && !strcmp(text, "J K"));
    CHECK(PortWii_Format("Keypad :", 0, text, sizeof(text)) && !strcmp(text, "`Keyboard:Keypad :`"));
    CHECK(!PortWii_Format("J | K", 1, text, 3));
    // Preserve the physical input behind every SDL keyboard name, including fallback-only names.
    for (int key = 1; key < SDL_SCANCODE_COUNT; key++) {
        const char *name = PortWii_InputName(0, key);
        if (!name || !*name || !PortWii_Validate(name, 100)) { continue; }
        CHECK(PortWii_Format(name, 0, text, sizeof(text)));
        CHECK(PortWii_Set(0, 1, 6, name, 100) && PortWii_Set(0, 1, 7, text, 100));
        bool held[SDL_SCANCODE_COUNT] = {}; held[key] = true;
        unsigned char sticks[4] = {128, 128, 128, 128}; float values[PORT_WII_ACTIONS];
        PortWii_Read(0, 1, nullptr, held, sticks, nullptr, values);
        CHECK(values[6] == values[7]);
    }
    std::string error;
    Profile p, q;
    p.split = 1; p.deadzone[0] = 0; p.deadzone[1] = 90; p.vibration[0] = 0; p.vibration[1] = 73;
    for (int action = 0; action < PORT_WII_ACTIONS; action++) {
        if (action == 12) { continue; }
        p.text[action] = std::string(action + 1, '(') + "`J` | `Controller:A`" + std::string(action + 1, ')');
        p.range[action] = action * 37 - 500;
    }
    CHECK(Decode(Encode(p), q, error) && share_equal(p, q));
    CHECK(Encode(p) == Encode(q));
    // Verify evaluation, including Dolphin's left-to-right binary operations.
    const char *expressions[] = {"`J` | `K` & !`SPACE`", "`J` | (`K` & !`SPACE`)",
        "(`J` + `K`) & !`SPACE`", "`1` | `F1` | `Left Shift`", "`Keypad :` | `J`"};
    const int keys[] = {SDL_SCANCODE_J, SDL_SCANCODE_K, SDL_SCANCODE_SPACE,
        SDL_SCANCODE_1, SDL_SCANCODE_F1, SDL_SCANCODE_LSHIFT, SDL_SCANCODE_KP_COLON};
    for (const char *expression : expressions) {
        p = Profile(); p.text[6] = expression; p.range[6] = -250;
        CHECK(Decode(Encode(p), q, error));
        CHECK(PortWii_Set(0, 1, 6, expression, p.range[6]));
        CHECK(PortWii_Set(0, 1, 7, q.text[6].c_str(), q.range[6]));
        for (int mask = 0; mask < 128; mask++) {
            bool held[SDL_SCANCODE_COUNT] = {};
            for (int i = 0; i < 7; i++) { held[keys[i]] = (mask & (1 << i)) != 0; }
            unsigned char sticks[4] = {128, 128, 128, 128}; float values[PORT_WII_ACTIONS];
            PortWii_Read(0, 1, nullptr, held, sticks, nullptr, values);
            CHECK(values[6] == values[7]);
        }
    }
    p = Profile(); p.text[7] = "`测试按键` | `Controller:Right Y-`";
    CHECK(Decode(Encode(p), q, error) && share_equal(p, q));
    // Display spaces must not invalidate an otherwise valid maximum-length binding.
    p.text[7] = "`0" + std::string(PORT_WII_EXPR_SIZE - 6, 'A') + "`|J";
    CHECK(p.text[7].size() == PORT_WII_EXPR_SIZE - 1);
    CHECK(Decode(Encode(p), q, error) && share_equal(p, q));
    CHECK(q.text[7] == p.text[7]);
    // Schema tests use valid compression/CRC so failures reach the binary reader.
    const std::string head("\1\0\1\1\2\310\1", 7);
    const std::string empty = head + std::string(27, '\0');
    CHECK(Decode(compressed_share(empty, "BT3W3:"), q, error) && equal(q, Profile()));
    Profile before = q;
    for (size_t length = 0; length < empty.size(); length++) {
        CHECK(!Decode(compressed_share(empty.substr(0, length), "BT3W3:"), q, error) && equal(q, before));
    }
    const std::string invalid[] = {std::string("\2") + empty.substr(1), empty + "x",
        head.substr(0, 1) + "\2" + head.substr(2) + std::string(27, '\0'),
        head + std::string("\1\14\0", 3) + std::string(26, '\0'), // reserved action 12
        head + std::string("\2\0\0\0\0", 5) + std::string(26, '\0'), // duplicate range
        head + std::string("\0\200\200\1", 4), // oversized expression
        head + std::string("\0\200\0", 3), // non-canonical integer
        head + std::string("\200\200\200\200\20", 5)}; // overflowing integer
    for (const auto& data : invalid) { CHECK(!Decode(compressed_share(data, "BT3W3:"), q, error) && equal(q, before)); }
    p.text[7] = "J &"; CHECK(Encode(p).empty());
}
int main() {
    CHECK(SDL_Init(SDL_INIT_GAMEPAD));
    for (int i = 0; i < 2; i++) { PortInput_ControlMode(i); }
    std::string error;
    for (int player = 0; player < 2; player++) for (int split = 0; split < 2; split++) {
        Profile p; p.split = split; p.deadzone[0] = 0; p.deadzone[1] = 37; p.vibration[1] = 73;
        for (int a = 0; a < PORT_WII_ACTIONS; a++) {
            if (a == 12) { continue; }
            p.text[a] = "  (`J` | `Controller:A`) & !`Left Alt`  "; p.range[a] = 100 + a;
        }
        p.text[26] = "`Controller:Back`";
        if (!split) for (int a = 24; a < PORT_WII_ACTIONS; a++) { p.text[a].clear(); p.range[a] = 100; }
        auto serialized = Serialize(p);
        CHECK(serialized.find("Action12") == std::string::npos);
        Profile parsed;
        CHECK(Parse(serialized, parsed, error)); CHECK(equal(p, parsed));
        CHECK(Decode(Encode(p), parsed, error)); CHECK(share_equal(p, parsed));
        CHECK(Decode("\r\n " + Encode(p) + " \r\n", parsed, error)); CHECK(share_equal(p, parsed));
        CHECK(Save("中文预设-test", p, error));
        auto entries = List(); CHECK(entries.size() == 1 && entries[0].name == "中文预设-test");
        CHECK(Read(entries[0].path, parsed, error)); CHECK(equal(p, parsed));
        Profile other = Capture(1 - player);
        *PortInput_ControlSplit(player) = !split;
        Profile inactive = Capture(player);
        *PortInput_ControlSplit(player) = split;
        *PortInput_ControlMode(player) = 0;
        int ps2key = PortInput_Keys(player)[4];
        CHECK(Apply(player, p, error)); CHECK(equal(p, Capture(player)));
        CHECK(equal(other, Capture(1 - player)));
        *PortInput_ControlMode(player) = 0; CHECK(PortInput_Keys(player)[4] == ps2key);
        for (int i = 0; i < 2; i++) { inactive.deadzone[i] = p.deadzone[i]; inactive.vibration[i] = p.vibration[i]; }
        *PortInput_ControlSplit(player) = !split; CHECK(equal(inactive, Capture(player)));
        *PortInput_ControlSplit(player) = split;
        Profile bad = p; bad.text[26] = "J &";
        CHECK(!Apply(player, bad, error)); CHECK(equal(p, Capture(player)));
        std::string code = Encode(p);
        for (size_t i = 6; i < code.size(); i += 17) {
            std::string broken = code; broken[i] = broken[i] == 'A' ? 'B' : 'A';
            CHECK(!Decode(broken, parsed, error));
        }
        CHECK(!Decode(code + "A", parsed, error));
        CHECK(!Decode(code.substr(0, code.size() - 2), parsed, error));
        CHECK(!Decode("BT3W4:" + code.substr(6), parsed, error));
        CHECK(!Decode(code + "=", parsed, error));
        CHECK(!Save("../escape", p, error)); CHECK(!Delete("../escape", error));
        CHECK(Delete("中文预设-test", error)); CHECK(List().empty());
    }
    const std::string dolphin = "\xEF\xBB\xBF[Profile]\r\nDevice = DInput/0/Keyboard Mouse\r\n"
        "Buttons/A = J | F\r\nButtons/B = `NUMPAD2`\r\nButtons/X = L\r\nButtons/Y = I | LMENU | Z\r\n"
        "Buttons/Z = SPACE\r\nButtons/Start = C\r\n"
        "Main Stick/Up = W &! LMENU | F | `Axis Y-`\r\nC-Stick/Up = CAPITAL\r\nC-Stick/Down = LSHIFT\r\n"
        "C-Stick/Left = Q\r\nC-Stick/Right = E\r\nTriggers/L = N &! SPACE\r\nTriggers/R = H &! SPACE\r\n"
        "Triggers/L-Analog = O &! SPACE\r\nTriggers/R-Analog = U &! SPACE\r\nButtons/A/Range = 75.0\r\n";
    Profile p;
    CHECK(Parse(dolphin, p, error)); CHECK(p.text[6] == "`J` | `F`" && p.range[6] == 75);
    CHECK(p.text[4] == "`Keypad 2`" && p.text[5] == "`L`" && p.text[13] == "`SPACE`");
    CHECK(p.text[16] == "`W` &! `LMENU` | `F` | `Axis Y-`");
    CHECK(p.text[10] == "`N` &! `SPACE`" && p.text[8] == "`O` &! `SPACE`");
    CHECK(p.split == 0 && p.text[24].empty() && p.text[26].empty());
    CHECK(Parse("[Profile]\nDevice=XInput/0/Gamepad\nButtons/A=`Button X` & `DInput/0/Keyboard Mouse:LSHIFT`\n"
                "Main Stick/Up=`Left Y+`\nMain Stick/Down=`Left Y-`\nButtons/Z=`Trigger R`\n", p, error));
    CHECK(p.text[6] == "`Controller:X` & `LSHIFT`");
    CHECK(p.text[16] == "`Controller:Left Y-`" && p.text[17] == "`Controller:Left Y+`");
    CHECK(p.text[13] == "`Controller:Right trigger`");
    CHECK(Parse("[Profile]\nDevice=DInput/0/Unknown Controller\nButtons/A=`Button 0`\n", p, error));
    CHECK(p.text[6].empty() && p.skipped.size() == 1);
    CHECK(!Parse("[Profile]\nButtons/A=J &\n", p, error));
    CHECK(Parse("[Profile]\nButtons/A=`Unknown Keyboard Input`\nButtons/B=J\n", p, error));
    CHECK(p.text[6].empty() && p.text[4] == "`J`" && p.skipped.size() == 1);
    CHECK(Parse("[Profile]\nButtons/A=J & !`Unknown Keyboard Input`\nButtons/B=GRAVE\nButtons/X=APOSTROPHE\n", p, error));
    CHECK(p.text[6].empty() && p.text[4] == "`GRAVE`" && p.text[5] == "`'`" && p.skipped.size() == 1);
    CHECK(!strcmp(PortWii_InputName(0, SDL_SCANCODE_GRAVE), "GRAVE"));
    CHECK(PortWii_Validate("`GRAVE` | (`Controller:A` & !GRAVE)", 100));
    CHECK(PortWii_Set(0, 1, 14, p.text[4].c_str(), 100));
    bool specialKeys[SDL_SCANCODE_COUNT] = {}; unsigned char neutral[4] = {128,128,128,128}; float specialValues[PORT_WII_ACTIONS];
    specialKeys[SDL_SCANCODE_GRAVE] = true;
    PortWii_Read(0, 1, nullptr, specialKeys, neutral, nullptr, specialValues); CHECK(specialValues[14] == 1);
    specialKeys[SDL_SCANCODE_GRAVE] = false;
    PortWii_Read(0, 1, nullptr, specialKeys, neutral, nullptr, specialValues); CHECK(specialValues[14] == 0);
    for (const char *key : {"SEMICOLON", "BACKSLASH", "MINUS", "NUMPADENTER", "NUMPADCOMMA", "MULTIPLY", "PLAYPAUSE", "MEDIASTOP", "`OEM_102`"}) {
        CHECK(Parse(std::string("[Profile]\nButtons/Start=") + key + "\nButtons/A=J\n", p, error));
        if (p.text[14].empty()) { fprintf(stderr, "Special key not imported: %s\n", key); }
        CHECK(!p.text[14].empty() && p.skipped.empty() && p.text[6] == "`J`");
    }
    const char *realProfile = SDL_getenv("BT3_TEST_DOLPHIN");
    CHECK(realProfile && Read(realProfile, p, error));
    CHECK(p.text[14] == "`GRAVE`" && p.skipped.empty() && p.text[6] == "`J` | `C`");
    Profile roundtrip;
    std::string oldCode = share(Serialize(p), "BT3W1:"), newCode = Encode(p);
    CHECK(Decode(oldCode, roundtrip, error) && equal(p, roundtrip));
    CHECK(Decode(compressed_share(Serialize(p), "BT3W2:"), roundtrip, error) && equal(p, roundtrip));
    CHECK(Decode(newCode, roundtrip, error) && share_equal(p, roundtrip));
    CHECK(Encode(p) == newCode && newCode.rfind("BT3W3:", 0) == 0 && newCode.size() < oldCode.size() / 2);
    CHECK(newCode.size() == 145); // Existing 1.ini fixture: compacted expressions, all parameters retained.
    CHECK(roundtrip.text[6] == "J | C" && roundtrip.text[14] == "GRAVE");
    printf("Actual Dolphin 1.ini: imported GRAVE; serialized INI %zu bytes, old code %zu chars, compressed code %zu chars\n", Serialize(p).size(), oldCode.size(), newCode.size());
    CHECK(!Decode(share("not zlib", "BT3W2:"), roundtrip, error));
    std::string bomb(MAX_FILE + 1, 'a'), packed(compressBound((uLong)bomb.size()), '\0'); uLongf packedSize = (uLongf)packed.size();
    CHECK(compress2((Bytef *)packed.data(), &packedSize, (const Bytef *)bomb.data(), (uLong)bomb.size(), 9) == Z_OK);
    packed.resize(packedSize); CHECK(!Decode(share(packed, "BT3W2:"), roundtrip, error));
    CHECK(!Parse("[Profile]\nButtons/A=J\nButtons/A/Range=nan\n", p, error));
    CHECK(!Parse("[Profile]\nButtons/A=J\nMain Stick/Dead Zone=99\n", p, error));
    CHECK(!Parse("[Profile]\nCalibration=100\n", p, error));
    CHECK(!Parse("[BT3 Wii Profile]\nFormat=2\n", p, error));
    CHECK(!Parse("[BT3 Wii Profile]\nFormat=1\nSplit=0\n", p, error));
    CHECK(!Parse(std::string(MAX_FILE + 1, 'x'), p, error));
    CHECK(!Decode(std::string(MAX_CODE + 4097, 'A'), p, error));
    CHECK(!Parse(std::string("[Profile]\nButtons/A=J\0bad", 25), p, error));
    // All import entry points call Apply: respect the destination switch and
    // retain the inactive bindings, other player, and PS2 controls.
    for (int player = 0; player < 2; player++) for (int source = 0; source < 2; source++) for (int dest = 0; dest < 2; dest++) {
        Profile input; input.split = source;
        input.text[22] = "`Q` & !`L`"; input.text[23] = "`E` | `Controller:A`";
        input.range[22] = input.range[23] = 125;
        if (source) { input.text[24] = "`J`"; input.text[25] = "`K`"; input.text[26] = "`Z`"; }
        *PortInput_ControlSplit(player) = !dest;
        Profile inactive = Capture(player), other = Capture(1 - player);
        *PortInput_ControlSplit(player) = dest;
        CHECK(Apply(player, input, error)); CHECK(*PortInput_ControlSplit(player) == dest);
        Profile actual = Capture(player);
        CHECK(actual.text[22] == input.text[22] && actual.text[23] == input.text[23]);
        CHECK(actual.range[22] == 125 && actual.range[23] == 125);
        if (dest) {
            CHECK(actual.text[24] == (source ? "`J`" : input.text[22]));
            CHECK(actual.text[25] == (source ? "`K`" : input.text[23]));
            CHECK(actual.text[26] == (source ? "`Z`" : "(`Q` & !`L`) | (`E` | `Controller:A`)"));
            bool keys[SDL_SCANCODE_COUNT] = {}; unsigned char sticks[4] = {128,128,128,128}; float values[PORT_WII_ACTIONS];
            for (int key : {SDL_SCANCODE_Q, SDL_SCANCODE_E}) {
                keys[key] = true;
                PortWii_Read(player, dest, nullptr, keys, sticks, nullptr, values);
                if (!source) { CHECK(values[26] > 0.5f); }
                keys[key] = false;
            }
            PortWii_Read(player, dest, nullptr, keys, sticks, nullptr, values); CHECK(values[26] == 0);
        } else for (int a = 24; a < PORT_WII_ACTIONS; a++) { CHECK(actual.text[a].empty()); }
        CHECK(equal(other, Capture(1 - player)));
        Profile shared;
        CHECK(Decode(Encode(input), shared, error));
        CHECK(Apply(player, shared, error) && *PortInput_ControlSplit(player) == dest);
        CHECK(share_equal(actual, Capture(player)));
        for (int i = 0; i < 2; i++) { inactive.deadzone[i] = actual.deadzone[i]; inactive.vibration[i] = actual.vibration[i]; }
        *PortInput_ControlSplit(player) = !dest; CHECK(equal(inactive, Capture(player)));
    }
    *PortInput_ControlSplit(0) = 1;
    Profile combined; combined.text[22] = "`Q`"; combined.range[22] = 75;
    CHECK(Apply(0, combined, error)); CHECK(Capture(0).text[26] == "`Q`" && Capture(0).range[26] == 75);
    combined.text[22].clear(); combined.text[23] = "`E`"; combined.range[23] = 125;
    CHECK(Apply(0, combined, error)); CHECK(Capture(0).text[26] == "`E`" && Capture(0).range[26] == 125);
    combined.text[22] = "`E`";
    CHECK(Apply(0, combined, error)); CHECK(Capture(0).range[26] == 125);
    combined.text[22] = "`Q`";
    Profile before = Capture(0);
    CHECK(!Apply(0, combined, error)); CHECK(equal(before, Capture(0)));
    combined.range[22] = combined.range[23];
    for (int i = 0; i < 500; i++) { combined.text[22] += " | `Q`"; combined.text[23] += " | `E`"; }
    CHECK(Apply(0, combined, error)); CHECK(Capture(0).text[26].size() > 5000);
    before = Capture(0);
    for (int i = 0; i < 100; i++) { combined.text[22] += " | `Q`"; combined.text[23] += " | `E`"; }
    CHECK(!Apply(0, combined, error)); CHECK(equal(before, Capture(0)));
    // Automatic discovery checks both locations, distinguishes names and
    // avoids listing the same folder twice when both roots coincide.
    auto dolphinEntries = List(true); CHECK(dolphinEntries.size() == 2);
    CHECK(dolphinEntries[0].name != dolphinEntries[1].name);
    bool appdata = false, documents = false;
    for (const auto& entry : dolphinEntries) {
        appdata |= entry.name.find("AppData") != std::string::npos;
        documents |= entry.name.find("文档") != std::string::npos;
        Profile found; CHECK(Read(entry.path, found, error));
    }
    CHECK(appdata && documents);
    std::string oldAppdata = SDL_getenv("APPDATA");
    SDL_Environment *env = SDL_GetEnvironment();
    CHECK(SDL_SetEnvironmentVariable(env, "APPDATA", SDL_getenv("BT3_TEST_DOCUMENTS"), true));
    CHECK(List(true).size() == 1);
    CHECK(SDL_SetEnvironmentVariable(env, "APPDATA", "", true)); CHECK(List(true).size() == 1);
    CHECK(SDL_SetEnvironmentVariable(env, "BT3_TEST_DOCUMENTS", "", true)); CHECK(List(true).empty());
    CHECK(SDL_SetEnvironmentVariable(env, "APPDATA", oldAppdata.c_str(), true));
    *PortInput_ControlSplit(0) = 1;
    CHECK(PortWii_Set(0, 1, 7, "J\n| `Controller:A`", 100));
    CHECK(Capture(0).text[7] == "J | `Controller:A`");
    // Preserve a long mixed-device expression and range exactly through file/code round trips.
    p = Profile(); p.split = 1;
    for (int i = 0; i < 180; i++) { p.text[7] += i ? " | (`K` & !`Controller:B`)" : "(`J` & `Controller:A`)"; }
    p.range[7] = -250;
    CHECK(Parse(Serialize(p), p, error));
    Profile q; CHECK(Decode(Encode(p), q, error)); CHECK(share_equal(p, q));
    CHECK(Save("跨进程保存", p, error));
    if (const char *fixture = SDL_getenv("BT3_TEST_NATIVE_PROFILE")) {
        Profile current;
        CHECK(Read(fixture, current, error));
        std::string code = Encode(current);
        CHECK(Decode(code, q, error) && share_equal(current, q));
        CHECK(q.text[6] == "J | F" && q.text[10] == "N & ! SPACE");
        CHECK(code.size() == 192);
        printf("Current player 1 split profile: W3 %zu chars; readable operators restored; metadata retained\n", code.size());
    }
    compact_checks();
    printf("PASS profiles: %d checks; Dolphin keyboard/mouse/mixed XInput, INI/save/load/delete, W1/W2/W3 long expression/share roundtrip, corrupt input rejection, player/profile/PS2 isolation\n", checks);
    SDL_Quit();
}
