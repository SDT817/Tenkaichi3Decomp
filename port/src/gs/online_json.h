// Small bounded JSON value reader for the new lobby control plane only.
// UTF-8 stays UTF-8; JSON escapes (including surrogate pairs) are decoded.
#pragma once
#include <string>
#include <vector>
#include <map>
#include <cstdlib>
#include <cstdio>
#include <cmath>

namespace OnlineJson {
struct Value {
    enum Kind { Null, Bool, Number, String, Array, Object } kind = Null;
    bool boolean = false;
    double number = 0;
    std::string text;
    std::vector<Value> array;
    std::map<std::string, Value> object;
    const Value& operator[](const std::string& key) const {
        static Value empty;
        auto it = object.find(key);
        return it == object.end() ? empty : it->second;
    }
    std::string str(const std::string& def = "") const { return kind == String ? text : def; }
    int integer(int def = 0) const { return kind == Number && number >= -1000000000 && number <= 1000000000 ? (int)number : def; }
    bool yes() const { return kind == Bool && boolean; }
};
inline void utf8(std::string& s, unsigned c) {
    if (c < 0x80) s += (char)c;
    else if (c < 0x800) { s += (char)(0xc0 | (c >> 6)); s += (char)(0x80 | (c & 63)); }
    else if (c < 0x10000) { s += (char)(0xe0 | (c >> 12)); s += (char)(0x80 | ((c >> 6) & 63)); s += (char)(0x80 | (c & 63)); }
    else { s += (char)(0xf0 | (c >> 18)); s += (char)(0x80 | ((c >> 12) & 63)); s += (char)(0x80 | ((c >> 6) & 63)); s += (char)(0x80 | (c & 63)); }
}
class Reader {
    const char *p, *end;
    int nodes = 0;
    void ws() { while (p < end && (*p == ' ' || *p == '\t' || *p == '\r' || *p == '\n')) ++p; }
    bool take(char c) { ws(); if (p == end || *p != c) return false; ++p; return true; }
    bool hex(unsigned& c) {
        c = 0;
        for (int n = 0; n < 4; ++n) {
            if (p == end) return false;
            char a = *p++;
            int h = a >= '0' && a <= '9' ? a-'0' : a >= 'a' && a <= 'f' ? a-'a'+10 : a >= 'A' && a <= 'F' ? a-'A'+10 : -1;
            if (h < 0) return false;
            c = c*16 + h;
        }
        return true;
    }
    bool string(std::string& s) {
        if (!take('"')) return false;
        s.clear();
        while (p < end) {
            unsigned char c = (unsigned char)*p++;
            if (c == '"') return true;
            if (c < 32) return false;
            if (c != '\\') { s += (char)c; continue; }
            if (p == end) return false;
            switch (*p++) {
            case '"': s += '"'; break; case '\\': s += '\\'; break; case '/': s += '/'; break;
            case 'b': s += '\b'; break; case 'f': s += '\f'; break; case 'n': s += '\n'; break;
            case 'r': s += '\r'; break; case 't': s += '\t'; break;
            case 'u': {
                unsigned u, lo;
                if (!hex(u) || u == 0) return false;
                if (u >= 0xd800 && u <= 0xdbff) {
                    if (end-p < 6 || *p++ != '\\' || *p++ != 'u' || !hex(lo) || lo < 0xdc00 || lo > 0xdfff) return false;
                    u = 0x10000 + ((u-0xd800)<<10) + lo-0xdc00;
                } else if (u >= 0xdc00 && u <= 0xdfff) return false;
                utf8(s, u); break;
            }
            default: return false;
            }
        }
        return false;
    }
    bool value(Value& v, int depth) {
        if (depth > 12 || ++nodes > 4096) return false;
        ws(); if (p == end) return false;
        if (*p == '{') {
            ++p; v.kind = Value::Object;
            if (take('}')) return true;
            do {
                std::string key; Value child;
                if (!string(key) || !take(':') || !value(child, depth+1) || v.object.count(key)) return false;
                v.object.emplace(key, std::move(child));
                if (take('}')) return true;
            } while (take(','));
            return false;
        }
        if (*p == '[') {
            ++p; v.kind = Value::Array;
            if (take(']')) return true;
            do {
                Value child;
                if (!value(child, depth+1)) return false;
                v.array.push_back(std::move(child));
                if (take(']')) return true;
            } while (take(','));
            return false;
        }
        if (*p == '"') { v.kind = Value::String; return string(v.text); }
        for (const char *literal : {"null", "true", "false"}) {
            std::string word(literal);
            if (end-p >= (int)word.size() && std::string(p, word.size()) == word) {
                p += word.size(); v.kind = word == "null" ? Value::Null : Value::Bool; v.boolean = word == "true"; return true;
            }
        }
        const char *begin = p;
        if (*p == '-') ++p;
        if (p == end || *p < '0' || *p > '9') return false;
        if (*p == '0') ++p; else while (p < end && *p >= '0' && *p <= '9') ++p;
        if (p < end && *p == '.') { ++p; const char *start = p; while (p < end && *p >= '0' && *p <= '9') ++p; if (p == start) return false; }
        if (p < end && (*p == 'e' || *p == 'E')) { ++p; if (p < end && (*p == '+' || *p == '-')) ++p; const char *start = p; while (p < end && *p >= '0' && *p <= '9') ++p; if (p == start) return false; }
        v.kind = Value::Number; v.number = std::strtod(std::string(begin, p).c_str(), nullptr);
        return std::isfinite(v.number);
    }
public:
    Reader(const std::string& s) : p(s.data()), end(s.data()+s.size()) {}
    bool read(Value& v) { if (!value(v, 0)) return false; ws(); return p == end; }
};
inline bool Parse(const std::string& s, Value& out) {
    if (s.size() > 65536) return false;
    Value value;
    if (!Reader(s).read(value)) return false;
    out = std::move(value); return true;
}
inline std::string Quote(const std::string& s) {
    std::string out = "\"";
    for (unsigned char c : s) {
        if (c == '"' || c == '\\') { out += '\\'; out += (char)c; }
        else if (c < 32) { char esc[8]; std::snprintf(esc, sizeof(esc), "\\u%04x", c); out += esc; }
        else out += (char)c;
    }
    return out + '"';
}
}
