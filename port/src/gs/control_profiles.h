#pragma once
#include "control_bindings.h"
#include <string>
#include <vector>

namespace WiiProfiles {
constexpr size_t MAX_FILE = 1024 * 1024;
constexpr size_t MAX_CODE = (MAX_FILE + 1024) * 4 / 3 + 16;
struct Profile {
    int split = 0;
    int deadzone[2] = {-1, -1}, vibration[2] = {1, 100};
    std::string text[PORT_WII_ACTIONS];
    int range[PORT_WII_ACTIONS];
    std::vector<std::string> skipped; // Import diagnostics only; not part of the preset.
    Profile() { for (int& r : range) { r = 100; } }
};
struct Entry { std::string name, path; };
Profile Capture(int player);
bool Apply(int player, const Profile& profile, std::string& error);
std::string Serialize(const Profile& profile);
bool Parse(const std::string& data, Profile& profile, std::string& error);
bool Read(const std::string& path, Profile& profile, std::string& error);
bool Save(const std::string& name, const Profile& profile, std::string& error);
bool Delete(const std::string& name, std::string& error);
std::vector<Entry> List(bool dolphin = false);
std::string Encode(const Profile& profile);
bool Decode(const std::string& code, Profile& profile, std::string& error);
void Draw(int player, float scale);
void Cancel();
}
