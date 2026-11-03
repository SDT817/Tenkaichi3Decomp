// Profile load/save follows Dolphin 10912 MappingWindow and ControlGroup.
// The portable BT3 format and offline share codes are local additions.
#include "control_profiles.h"
#include "ui.h"
#include "../../third_party/dolphin/Common/ProfileIni.h"
#include <algorithm>
#include <cstdlib>
#include <cmath>
#include <cstdio>
#include <cstring>
#include <zlib.h>

namespace WiiProfiles {
namespace {
bool fail(std::string& error, const std::string& message) { error = message; return false; }
bool valid(const Profile& p, std::string& error) {
    if (p.split < 0 || p.split > 1 || p.vibration[0] < 0 || p.vibration[0] > 1 ||
        p.vibration[1] < 0 || p.vibration[1] > 100) { return fail(error, "预设中的模式或震动设置无效。"); }
    for (int value : p.deadzone) {
        if (value < -1 || value > PORT_DEADZONE_MAX) { return fail(error, "预设中的摇杆死区无效。"); }
    }
    for (int a = 0; a < PORT_WII_ACTIONS; a++) {
        if (a == 12) { continue; } // Retain r3 action indices; L3 has no Wii action.
        if (p.range[a] < -500 || p.range[a] > 500 || p.text[a].find_first_of("\r\n") != std::string::npos ||
            p.text[a].find('\0') != std::string::npos || !PortWii_Validate(p.text[a].c_str(), p.range[a])) {
            return fail(error, std::string("预设表达式无效或过长：") + PortWii_ActionLabel(p.split, a));
        }
    }
    return true;
}
bool integer(const DolphinProfile::Section& sec, const std::string& key, int& value, int fallback, bool required = false) {
    auto it = sec.find(key);
    if (it == sec.end()) { value = fallback; return !required; }
    char *end;
    long number = strtol(it->second.c_str(), &end, 10);
    if (end == it->second.c_str() || *end || number < -100000 || number > 100000) { return false; }
    value = (int)number; return true;
}
bool dolphin(const DolphinProfile::Section& sec, Profile& p, std::string& error) {
    // GameCube classic controls for BT3: A attack, B flight, X guard, Y blast,
    // Z charge; digital L/R fast descent/ascent, analog L/R normal descent/ascent.
    static const char *const keys[PORT_WII_ACTIONS] = {
        "D-Pad/Up", "D-Pad/Down", "D-Pad/Left", "D-Pad/Right",
        "Buttons/B", "Buttons/X", "Buttons/A", "Buttons/Y",
        "Triggers/L-Analog", "Triggers/R-Analog", "Triggers/L", "Triggers/R", "",
        "Buttons/Z", "Buttons/Start", "", "Main Stick/Up", "Main Stick/Down", "Main Stick/Left", "Main Stick/Right",
        "C-Stick/Up", "C-Stick/Down", "C-Stick/Left", "C-Stick/Right", "", "", ""
    };
    auto dev = sec.find("Device");
    std::string device = dev == sec.end() ? "DInput/0/Keyboard Mouse" : dev->second;
    bool found = false;
    for (int a = 0; a < PORT_WII_ACTIONS; a++) {
        if (!*keys[a]) { continue; }
        auto it = sec.find(keys[a]);
        if (it == sec.end()) { continue; }
        found = true;
        char text[PORT_WII_EXPR_SIZE], message[1024] = {};
        int translated = PortWii_TranslateDolphin(it->second.c_str(), device.c_str(), text, sizeof(text), message, sizeof(message));
        if (translated < 0) {
            // Keep the whole affected action empty: removing only an unknown
            // operand could turn e.g. J & !unknown into an unintended binding.
            p.skipped.push_back(std::string(keys[a]) + ": " + message);
            continue;
        }
        if (!translated) {
            return fail(error, std::string(keys[a]) + ": " + message);
        }
        p.text[a] = text;
        auto range = sec.find(std::string(keys[a]) + "/Range");
        if (range != sec.end()) {
            char *end;
            double value = strtod(range->second.c_str(), &end);
            if (end == range->second.c_str() || *end || !std::isfinite(value) || value < -500 || value > 500) {
                return fail(error, "Dolphin 输入范围无效。");
            }
            p.range[a] = (int)std::lround(value);
        }
    }
    // Preserve the port's own deadzone algorithm. Import a numeric dead zone,
    // while calibration/gate settings remain Dolphin-specific.
    for (int i = 0; i < 2; i++) {
        auto it = sec.find(i ? "C-Stick/Dead Zone" : "Main Stick/Dead Zone");
        if (it != sec.end()) {
            char *end;
            double value = strtod(it->second.c_str(), &end);
            if (end == it->second.c_str() || *end || !std::isfinite(value) || value < 0 || value > PORT_DEADZONE_MAX) {
                return fail(error, "Dolphin 摇杆死区超出移植版支持的范围（0–90%）。");
            }
            p.deadzone[i] = (int)std::lround(value);
        }
    }
    return found ? valid(p, error) : fail(error, "文件中没有找到 GameCube 按键配置。");
}
std::string folder(bool dolphin) {
    if (dolphin) {
        const char *appdata = SDL_getenv("APPDATA");
        return appdata && *appdata ? std::string(appdata) + "/Dolphin Emulator/Config/Profiles/GCPad" : "";
    }
    const char *setting = SDL_getenv("BT3_SETTINGS");
    std::string base = setting ? setting : "";
    auto slash = base.find_last_of("/\\");
    return (slash == std::string::npos ? "" : base.substr(0, slash + 1)) + "wii_profiles";
}
bool filename(const std::string& name, std::string& error) {
    if (name.empty() || name.size() > 120 || name == "." || name == ".." ||
        name.find_first_of("/\\:*?\"<>|\r\n") != std::string::npos || name.back() == '.' || name.back() == ' ' ||
        name.find('\0') != std::string::npos) { return fail(error, "请输入有效的预设名称（不含路径或特殊字符）。"); }
    return true;
}
const char *alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_";
// W3 schema 1: fixed action IDs 0..11,13..26; never follow the UI row order.
static_assert(PORT_WII_ACTIONS == 27, "Update the W3 schema before adding Wii actions");
void put_unsigned(std::string& out, Uint32 value) {
    while (value >= 128) { out += (char)((value & 127) | 128); value >>= 7; }
    out += (char)value;
}
void put_signed(std::string& out, int value) { put_unsigned(out, value < 0 ? -value * 2 - 1 : value * 2); }
bool get_unsigned(const std::string& data, size_t& at, Uint32& value) {
    value = 0;
    for (int shift = 0; shift <= 28; shift += 7) {
        if (at == data.size()) { return false; }
        unsigned char c = data[at++];
        if (shift == 28 && (c & 0xf0)) { return false; }
        value |= (Uint32)(c & 127) << shift;
        if (!(c & 128)) { return shift == 0 || c != 0; }
    }
    return false;
}
bool get_signed(const std::string& data, size_t& at, int& value) {
    Uint32 encoded;
    if (!get_unsigned(data, at, encoded)) { return false; }
    value = encoded & 1 ? -(int)(encoded >> 1) - 1 : (int)(encoded >> 1);
    return true;
}
std::string compact(const Profile& p) {
    std::string error;
    if (!valid(p, error)) { return ""; }
    std::string data;
    data += '\1'; data += (char)p.split;
    for (int value : {p.deadzone[0], p.deadzone[1], p.vibration[0], p.vibration[1]}) { put_signed(data, value); }
    int ranges = 0;
    for (int a = 0; a < 27; a++) { if (a != 12 && p.range[a] != 100) { ranges++; } }
    put_unsigned(data, ranges);
    for (int a = 0; a < 27; a++) {
        if (a != 12 && p.range[a] != 100) { put_unsigned(data, a); put_signed(data, p.range[a]); }
    }
    for (int a = 0; a < 27; a++) {
        if (a == 12) { continue; }
        char text[PORT_WII_EXPR_SIZE];
        if (!PortWii_Format(p.text[a].c_str(), 0, text, sizeof(text))) { return ""; }
        size_t length = strlen(text);
        put_unsigned(data, (Uint32)length); data.append(text, length);
    }
    return data;
}
bool expand(const std::string& data, Profile& profile, std::string& error) {
    auto invalid = [&]() { return fail(error, "分享码中的按键数据不完整、版本不支持或参数无效。"); };
    if (data.size() < 2 || data[0] != 1) { return invalid(); }
    Profile p;
    p.split = (unsigned char)data[1];
    size_t at = 2;
    for (int *value : {&p.deadzone[0], &p.deadzone[1], &p.vibration[0], &p.vibration[1]}) {
        if (!get_signed(data, at, *value)) { return invalid(); }
    }
    Uint32 ranges, seen = 0;
    if (!get_unsigned(data, at, ranges) || ranges > 26) { return invalid(); }
    for (Uint32 i = 0; i < ranges; i++) {
        Uint32 a;
        if (!get_unsigned(data, at, a) || a >= 27 || a == 12 || (seen & (1u << a)) ||
            !get_signed(data, at, p.range[a])) { return invalid(); }
        seen |= 1u << a;
    }
    for (int a = 0; a < 27; a++) {
        if (a == 12) { continue; }
        Uint32 length;
        if (!get_unsigned(data, at, length) || length >= PORT_WII_EXPR_SIZE || length > data.size() - at) { return invalid(); }
        p.text[a] = data.substr(at, length); at += length;
        if (p.text[a].find_first_of("\r\n") != std::string::npos || p.text[a].find('\0') != std::string::npos) { return invalid(); }
        char text[PORT_WII_EXPR_SIZE];
        // Keep a maximum-length valid expression if adding display spaces would exceed its limit.
        if (PortWii_Format(p.text[a].c_str(), 1, text, sizeof(text))) { p.text[a] = text; }
    }
    if (at != data.size()) { return invalid(); }
    if (!valid(p, error)) { return false; }
    profile = std::move(p); error.clear(); return true;
}
}
Profile Capture(int player) {
    Profile p;
    p.split = *PortInput_ControlSplit(player) != 0;
    for (int a = 0; a < PORT_WII_ACTIONS; a++) {
        char text[PORT_WII_EXPR_SIZE];
        PortWii_Get(player, p.split, a, text, sizeof(text), &p.range[a]); p.text[a] = text;
        for (char& c : p.text[a]) { if (c == '\r' || c == '\n') { c = ' '; } }
    }
    for (int i = 0; i < 2; i++) {
        p.deadzone[i] = PortInput_Deadzone(player)[i]; p.vibration[i] = PortInput_Vibration(player)[i];
    }
    p.text[12].clear(); p.range[12] = 100;
    return p;
}
bool Apply(int player, const Profile& p, std::string& error) {
    if (player < 0 || player > 1 || !valid(p, error)) { return false; }
    Profile mapped = p;
    mapped.split = *PortInput_ControlSplit(player) != 0;
    if (mapped.split && !p.split) {
        for (int i = 0; i < 2; i++) {
            mapped.text[24 + i] = p.text[22 + i]; mapped.range[24 + i] = p.range[22 + i];
        }
        if (p.text[22].empty()) { mapped.text[26] = p.text[23]; mapped.range[26] = p.range[23]; }
        else if (p.text[23].empty()) { mapped.text[26] = p.text[22]; mapped.range[26] = p.range[22]; }
        else if (p.text[22] == p.text[23]) { mapped.text[26] = p.text[22]; mapped.range[26] = std::max(p.range[22], p.range[23]); }
        else {
            if (p.range[22] != p.range[23]) {
                return fail(error, "左右视角的输入范围不同，无法无损合并暴血按键。请先将两项范围设为相同值再导入。");
            }
            mapped.text[26] = "(" + p.text[22] + ") | (" + p.text[23] + ")";
            mapped.range[26] = p.range[22];
        }
    }
    if (!mapped.split) {
        for (int a = 24; a < PORT_WII_ACTIONS; a++) { mapped.text[a].clear(); mapped.range[a] = 100; }
    }
    if (!valid(mapped, error)) { return false; }
    // Validate the whole document before replacing any live binding.
    PortWii_Cancel();
    for (int a = 0; a < PORT_WII_ACTIONS; a++) { PortWii_Set(player, mapped.split, a, a == 12 ? "" : mapped.text[a].c_str(), mapped.range[a]); }
    *PortInput_ControlMode(player) = 1;
    for (int i = 0; i < 2; i++) {
        PortInput_Deadzone(player)[i] = p.deadzone[i]; PortInput_Vibration(player)[i] = p.vibration[i];
    }
    PortInput_Save();
    return true;
}
std::string Serialize(const Profile& p) {
    std::string result = "[BT3 Wii Profile]\nFormat = 1\nSplit = " + std::to_string(p.split) + "\n";
    for (int i = 0; i < 2; i++) {
        result += "Deadzone" + std::to_string(i) + " = " + std::to_string(p.deadzone[i]) + "\n";
        result += "Vibration" + std::to_string(i) + " = " + std::to_string(p.vibration[i]) + "\n";
    }
    for (int a = 0; a < PORT_WII_ACTIONS; a++) {
        if (a == 12) { continue; }
        result += "Action" + std::to_string(a) + " = \"" + p.text[a] + "\"\n";
        result += "Action" + std::to_string(a) + "/Range = " + std::to_string(p.range[a]) + "\n";
    }
    return result;
}
bool Parse(const std::string& data, Profile& profile, std::string& error) {
    if (data.size() > MAX_FILE || data.find('\0') != std::string::npos) { return fail(error, "配置文件过大或包含无效数据。"); }
    auto ini = DolphinProfile::Load(data);
    Profile p;
    auto local = ini.find("BT3 Wii Profile");
    if (local == ini.end()) {
        auto section = ini.find("Profile");
        if (section == ini.end()) { return fail(error, "文件不是移植版 Wii 预设或 Dolphin GCPad 预设。"); }
        if (!dolphin(section->second, p, error)) { return false; }
    } else {
        auto& sec = local->second;
        int version;
        if (!integer(sec, "Format", version, 0, true) || version != 1) { return fail(error, "不支持此预设版本，请使用相同或更新的改版。"); }
        if (!integer(sec, "Split", p.split, 0, true)) { return fail(error, "预设模式无效。"); }
        for (int i = 0; i < 2; i++) {
            if (!integer(sec, "Deadzone" + std::to_string(i), p.deadzone[i], -1) ||
                !integer(sec, "Vibration" + std::to_string(i), p.vibration[i], i ? 100 : 1)) { return fail(error, "预设参数无效。"); }
        }
        for (int a = 0; a < PORT_WII_ACTIONS; a++) {
            if (a == 12) { continue; }
            std::string key = "Action" + std::to_string(a);
            auto it = sec.find(key);
            if (it == sec.end() || !integer(sec, key + "/Range", p.range[a], 100)) { return fail(error, "预设缺少动作或输入范围无效。"); }
            p.text[a] = it->second;
        }
        if (!valid(p, error)) { return false; }
    }
    profile = std::move(p); error.clear(); return true;
}
bool Read(const std::string& path, Profile& p, std::string& error) {
    SDL_IOStream *in = SDL_IOFromFile(path.c_str(), "rb");
    if (!in) { return fail(error, std::string("无法打开配置：") + SDL_GetError()); }
    Sint64 size = SDL_GetIOSize(in);
    if (size < 0 || size > (Sint64)MAX_FILE) { SDL_CloseIO(in); return fail(error, "配置文件过大或无法读取。"); }
    std::string data((size_t)size, '\0');
    bool ok = SDL_ReadIO(in, data.data(), data.size()) == data.size();
    ok = SDL_CloseIO(in) && ok;
    return ok ? Parse(data, p, error) : fail(error, "读取配置文件失败。");
}
bool Save(const std::string& name, const Profile& p, std::string& error) {
    if (!filename(name, error) || !valid(p, error)) { return false; }
    std::string dir = folder(false), path = dir + "/" + name + ".ini", temp = path + ".tmp";
    if (!SDL_CreateDirectory(dir.c_str())) { return fail(error, SDL_GetError()); }
    SDL_IOStream *out = SDL_IOFromFile(temp.c_str(), "wb");
    if (!out) { return fail(error, SDL_GetError()); }
    std::string data = Serialize(p);
    bool ok = SDL_WriteIO(out, data.data(), data.size()) == data.size();
    ok = SDL_CloseIO(out) && ok;
    if (!ok || !SDL_RenamePath(temp.c_str(), path.c_str())) { return fail(error, std::string("保存预设失败：") + SDL_GetError()); }
    error.clear(); return true;
}
bool Delete(const std::string& name, std::string& error) {
    if (!filename(name, error)) { return false; }
    return SDL_RemovePath((folder(false) + "/" + name + ".ini").c_str()) || fail(error, SDL_GetError());
}
std::vector<Entry> List(bool dolphin) {
    std::vector<Entry> result;
    std::vector<std::string> dirs = {folder(dolphin)};
    if (dolphin) {
        const char *documents = SDL_GetUserFolder(SDL_FOLDER_DOCUMENTS);
        if (documents && *documents) {
            std::string dir = documents;
            while (!dir.empty() && (dir.back() == '/' || dir.back() == '\\')) { dir.pop_back(); }
            dir += "/Dolphin Emulator/Config/Profiles/GCPad";
            auto normalized = [](std::string path) {
                std::replace(path.begin(), path.end(), '\\', '/');
                while (!path.empty() && path.back() == '/') { path.pop_back(); }
                return path;
            };
            if (SDL_strcasecmp(normalized(dir).c_str(), normalized(dirs[0]).c_str())) { dirs.push_back(dir); }
        }
    }
    for (size_t source = 0; source < dirs.size(); source++) {
        const std::string& dir = dirs[source];
        int count = 0;
        if (dir.empty()) { continue; }
        char **paths = SDL_GlobDirectory(dir.c_str(), "*.ini", SDL_GLOB_CASEINSENSITIVE, &count);
        if (!paths) { continue; }
        for (int i = 0; i < count; i++) {
            std::string name = paths[i];
            // SDL_GlobDirectory returns names relative to its directory.
            name.resize(name.size() - 4);
            if (dolphin) { name += source ? "（文档）" : "（AppData）"; }
            result.push_back({name, dir + "/" + paths[i]});
        }
        SDL_free(paths);
    }
    std::sort(result.begin(), result.end(), [](const Entry& a, const Entry& b) { return SDL_strcasecmp(a.name.c_str(), b.name.c_str()) < 0; });
    return result;
}
std::string Encode(const Profile& p) {
    std::string data = compact(p);
    if (data.empty() || data.size() > MAX_FILE) { return ""; }
    uLongf size = compressBound((uLong)data.size());
    std::string packed(size, '\0');
    if (compress2((Bytef *)packed.data(), &size, (const Bytef *)data.data(), (uLong)data.size(), Z_BEST_COMPRESSION) != Z_OK) { return ""; }
    packed.resize(size); data = std::move(packed);
    Uint32 crc = SDL_crc32(0, data.data(), data.size());
    for (int i = 0; i < 4; i++) { data += (char)(crc >> (i * 8)); }
    std::string result = "BT3W3:";
    unsigned bits = 0; int count = 0;
    for (unsigned char c : data) {
        bits = (bits << 8) | c; count += 8;
        while (count >= 6) { count -= 6; result += alphabet[(bits >> count) & 63]; }
    }
    if (count) { result += alphabet[(bits << (6 - count)) & 63]; }
    return result;
}
bool Decode(const std::string& code, Profile& p, std::string& error) {
    if (code.size() > MAX_CODE + 4096) { return fail(error, "分享码过长。"); }
    std::string clean;
    for (unsigned char c : code) { if (!SDL_isspace(c)) { clean += c; } }
    int version = clean.rfind("BT3W3:", 0) == 0 ? 3 : clean.rfind("BT3W2:", 0) == 0 ? 2 : clean.rfind("BT3W1:", 0) == 0 ? 1 : 0;
    bool compressed = version >= 2;
    if (!version || clean.size() > MAX_CODE) { return fail(error, "分享码格式或版本不正确（需要 BT3W1:、BT3W2: 或 BT3W3: 开头）。"); }
    std::string data;
    unsigned bits = 0; int count = 0;
    for (size_t i = 6; i < clean.size(); i++) {
        const char *v = strchr(alphabet, clean[i]);
        if (!v || !clean[i]) { return fail(error, "分享码包含无效字符。"); }
        bits = (bits << 6) | (unsigned)(v - alphabet); count += 6;
        if (count >= 8) { count -= 8; data += (char)(bits >> count); }
    }
    if (count >= 6 || (count && (bits & ((1u << count) - 1))) || data.size() < 5 || data.size() > MAX_FILE + (compressed ? 1024 : 4)) {
        return fail(error, "分享码不完整或长度无效。");
    }
    Uint32 crc = 0;
    for (int i = 0; i < 4; i++) { crc |= (Uint32)(unsigned char)data[data.size() - 4 + i] << (i * 8); }
    data.resize(data.size() - 4);
    if (SDL_crc32(0, data.data(), data.size()) != crc) { return fail(error, "分享码校验失败，请重新完整复制。"); }
    if (compressed) {
        std::string unpacked(MAX_FILE, '\0');
        uLongf size = (uLongf)unpacked.size();
        uLong used = (uLong)data.size();
        if (uncompress2((Bytef *)unpacked.data(), &size, (const Bytef *)data.data(), &used) != Z_OK || used != data.size()) {
            return fail(error, "分享码压缩数据无效或解压后过长。");
        }
        unpacked.resize(size); data = std::move(unpacked);
    }
    if (version == 3) { return expand(data, p, error); }
    if (data.find("[BT3 Wii Profile]") == std::string::npos) { return fail(error, "分享码中没有移植版预设。"); }
    return Parse(data, p, error);
}
}
