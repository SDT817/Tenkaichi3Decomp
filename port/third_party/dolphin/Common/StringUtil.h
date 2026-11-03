// The only StringUtil dependency used by the imported parser.
#pragma once
#include <string>
inline std::string StripSpaces(const std::string& text) {
    const auto first = text.find_first_not_of(" \t\r\n");
    return first == std::string::npos ? std::string() :
        text.substr(first, text.find_last_not_of(" \t\r\n") - first + 1);
}
