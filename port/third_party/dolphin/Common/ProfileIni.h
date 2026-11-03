// Copyright 2008 Dolphin Emulator Project
// Licensed under GPLv2+; refer to ../license.txt.
// IniFile.cpp ParseLine/Load and case-insensitive section lookup, reduced to the
// read-only profile subset. SDL supplies UTF-8 file IO in the caller.
#pragma once
#include <map>
#include <string>
#include <sstream>
#include <algorithm>
#include <cctype>

namespace DolphinProfile {
inline std::string StripSpaces(const std::string& value) {
    const auto start = value.find_first_not_of(" \t\r\n");
    return start == std::string::npos ? "" : value.substr(start, value.find_last_not_of(" \t\r\n") - start + 1);
}
inline std::string StripQuotes(std::string value) {
    if (value.size() >= 2 && value.front() == '"' && value.back() == '"') { return value.substr(1, value.size() - 2); }
    return value;
}
struct CaseInsensitiveStringCompare {
    bool operator()(const std::string& a, const std::string& b) const {
        return std::lexicographical_compare(a.begin(), a.end(), b.begin(), b.end(), [](unsigned char l, unsigned char r) {
            return std::tolower(l) < std::tolower(r);
        });
    }
};
using Section = std::map<std::string, std::string, CaseInsensitiveStringCompare>;
using Ini = std::map<std::string, Section, CaseInsensitiveStringCompare>;
inline void ParseLine(const std::string& line, std::string *key, std::string *value) {
    if (line.empty() || line.front() == '#') { return; }
    size_t firstEquals = line.find('=');
    if (firstEquals != std::string::npos) {
        *key = StripSpaces(line.substr(0, firstEquals));
        *value = StripQuotes(StripSpaces(line.substr(firstEquals + 1)));
    }
}
inline Ini Load(const std::string& text) {
    Ini ini;
    std::istringstream in(text);
    Section *section = nullptr;
    bool first = true;
    std::string line;
    while (std::getline(in, line)) {
        if (first && line.substr(0, 3) == "\xEF\xBB\xBF") { line.erase(0, 3); }
        first = false;
        if (!line.empty() && line.back() == '\r') { line.pop_back(); }
        if (line.empty()) { continue; }
        if (line[0] == '[') {
            size_t end = line.find(']');
            if (end != std::string::npos) { section = &ini[line.substr(1, end - 1)]; }
        } else if (section) {
            std::string key, value;
            ParseLine(line, &key, &value);
            if ((!key.empty() || !value.empty()) && line[0] != '$' && line[0] != '+' && line[0] != '*') {
                (*section)[key] = value;
            }
        }
    }
    return ini;
}
}
