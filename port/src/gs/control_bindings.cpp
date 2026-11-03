// Dolphin expression semantics with SDL inputs. See third_party/dolphin/README.md.
#include "control_bindings.h"
#include "ui.h"
#include <algorithm>
#include <map>
#include <memory>
#include <pthread.h>
#include <string>
#include <vector>
#include <cstdio>
#include <cstdlib>
#include <cstring>
#include <cmath>
#include "../../third_party/dolphin/InputCommon/ControlReference/ExpressionParser.cpp"

namespace {
using namespace ciface::Core;
using namespace ciface::ExpressionParser;
struct Sample {
    SDL_Gamepad *pad;
    const bool *keys;
    const unsigned char *sticks;
    int (*blocked)(int);
};
Sample sSample = {};
bool sAnyKey;
float sMouse[13], sMotion[2], sWheel[2];
int sMouseAxis[2], sWheelAxis[2];
Uint64 sMouseUpdate;
const char *const kMouse[] = {"Click 0", "Click 1", "Click 2", "Click 3", "Click 4",
    "Axis X-", "Axis X+", "Axis Y-", "Axis Y+", "Wheel X-", "Wheel X+", "Wheel Y-", "Wheel Y+"};
pthread_mutex_t sLock = PTHREAD_MUTEX_INITIALIZER;
struct Lock { Lock() { pthread_mutex_lock(&sLock); } ~Lock() { pthread_mutex_unlock(&sLock); } };
const char *const kButtons[] = {
    "A", "B", "X", "Y", "Back", "Guide", "Start", "Left stick click", "Right stick click",
    "Left shoulder", "Right shoulder", "D-pad up", "D-pad down", "D-pad left", "D-pad right",
    "Misc 1", "Right paddle 1", "Left paddle 1", "Right paddle 2", "Left paddle 2", "Touchpad"
};
const char *const kAxes[] = {"Left X-", "Left X+", "Left Y-", "Left Y+",
                            "Right X-", "Right X+", "Right Y-", "Right Y+",
                            "Left trigger", "Right trigger"};

class SDLInput : public Device::Input {
    int kind, index;
public:
    SDLInput(int type, int id) : kind(type), index(id) {}
    ControlState GetState() const override {
        if (kind == 0) {
            if (sSample.keys && sSample.keys[index]) { sAnyKey = true; }
            return sSample.keys && ! (sSample.blocked && sSample.blocked(index)) && sSample.keys[index] ? 1.0 : 0.0;
        }
        if (kind == 3) {
            return sSample.keys ? sMouse[index] : 0.0;
        }
        if (!sSample.pad) { return 0.0; }
        if (kind == 1) { return SDL_GetGamepadButton(sSample.pad, (SDL_GamepadButton)index) ? 1.0 : 0.0; }
        if (index >= 8) {
            return std::max(0.0, SDL_GetGamepadAxis(sSample.pad, index == 8 ? SDL_GAMEPAD_AXIS_LEFT_TRIGGER : SDL_GAMEPAD_AXIS_RIGHT_TRIGGER) / 32767.0);
        }
        // Use the port's existing round-deadzone bytes; retain analog magnitudes.
        if (!sSample.sticks) { return 0; }
        const double v = (sSample.sticks[index / 2] - 128) / (index % 2 ? 127.0 : -128.0);
        return std::max(0.0, v);
    }
};
class Inputs : public Device {
    std::map<std::string, std::unique_ptr<SDLInput>> inputs;
public:
    explicit Inputs(bool keyboard) {
        if (keyboard) {
            for (int i = 1; i < SDL_SCANCODE_COUNT; i++) {
                const char *name = SDL_GetScancodeName((SDL_Scancode)i);
                if (name && *name) { inputs.emplace(name, std::make_unique<SDLInput>(0, i)); }
            }
            // Dolphin DInput names used by existing expressions (NamedKeys.h).
            static const struct { const char *name; int sc; } aliases[] = {
                {"LMENU", SDL_SCANCODE_LALT}, {"RMENU", SDL_SCANCODE_RALT},
                {"LSHIFT", SDL_SCANCODE_LSHIFT}, {"RSHIFT", SDL_SCANCODE_RSHIFT},
                {"LCONTROL", SDL_SCANCODE_LCTRL}, {"RCONTROL", SDL_SCANCODE_RCTRL},
                {"LWIN", SDL_SCANCODE_LGUI}, {"RWIN", SDL_SCANCODE_RGUI},
                {"CAPITAL", SDL_SCANCODE_CAPSLOCK}, {"PRIOR", SDL_SCANCODE_PAGEUP},
                {"NEXT", SDL_SCANCODE_PAGEDOWN}, {"BACK", SDL_SCANCODE_BACKSPACE},
                {"SYSRQ", SDL_SCANCODE_PRINTSCREEN}, {"SCROLL", SDL_SCANCODE_SCROLLLOCK},
                {"GRAVE", SDL_SCANCODE_GRAVE}, {"OEM_102", SDL_SCANCODE_NONUSBACKSLASH},
                {"KANA", SDL_SCANCODE_INTERNATIONAL2}, {"YEN", SDL_SCANCODE_INTERNATIONAL3},
                {"CONVERT", SDL_SCANCODE_INTERNATIONAL4}, {"NOCONVERT", SDL_SCANCODE_INTERNATIONAL5},
                {"PREVTRACK", SDL_SCANCODE_MEDIA_PREVIOUS_TRACK}, {"NEXTTRACK", SDL_SCANCODE_MEDIA_NEXT_TRACK},
                {"MEDIASTOP", SDL_SCANCODE_MEDIA_STOP}, {"PLAYPAUSE", SDL_SCANCODE_MEDIA_PLAY_PAUSE},
                {"MEDIASELECT", SDL_SCANCODE_MEDIA_SELECT}, {"WEBBACK", SDL_SCANCODE_AC_BACK},
                {"WEBFORWARD", SDL_SCANCODE_AC_FORWARD}, {"WEBHOME", SDL_SCANCODE_AC_HOME},
                {"WEBREFRESH", SDL_SCANCODE_AC_REFRESH}, {"WEBSEARCH", SDL_SCANCODE_AC_SEARCH},
                {"WEBSTOP", SDL_SCANCODE_AC_STOP}, {"WEBFAVORITES", SDL_SCANCODE_AC_BOOKMARKS}
            };
            for (const auto& a : aliases) { inputs.emplace(a.name, std::make_unique<SDLInput>(0, a.sc)); }
            for (int i = 0; i < 13; i++) { inputs.emplace(kMouse[i], std::make_unique<SDLInput>(3, i)); }
            inputs.emplace("Axis Z-", std::make_unique<SDLInput>(3, 11));
            inputs.emplace("Axis Z+", std::make_unique<SDLInput>(3, 12));
        } else {
            for (unsigned i = 0; i < sizeof(kButtons) / sizeof(*kButtons); i++) {
                inputs.emplace(kButtons[i], std::make_unique<SDLInput>(1, i));
            }
            for (int i = 0; i < 10; i++) { inputs.emplace(kAxes[i], std::make_unique<SDLInput>(2, i)); }
        }
    }
    Device::Input *FindInput(const std::string& name) override {
        auto it = inputs.find(name);
        if (it != inputs.end()) { return it->second.get(); }
        for (const auto& item : inputs) if (!SDL_strcasecmp(item.first.c_str(), name.c_str())) { return item.second.get(); }
        return nullptr;
    }
};
class Devices : public DeviceContainer {
    std::shared_ptr<Device> keyboard = std::make_shared<Inputs>(true);
    std::shared_ptr<Device> controller = std::make_shared<Inputs>(false);
public:
    std::shared_ptr<Device> FindDevice(const DeviceQualifier& q) const override {
        if (q.ToString() == "Keyboard") { return keyboard; }
        if (q.ToString() == "Controller") { return controller; }
        return nullptr;
    }
};
struct Binding {
    std::string text;
    int range = 100;
    std::unique_ptr<Expression> expr;
};
Binding sBindings[2][2][PORT_WII_ACTIONS];
bool sLoaded[2], sLegacy;

bool compile(Binding& binding, int column, const char *text, int range) {
    if (!text || strlen(text) >= PORT_WII_EXPR_SIZE) { return false; }
    int depth = 0, operators = 0;
    bool quoted = false;
    for (const char *p = text; *p; p++) {
        if (*p == '`') { quoted = !quoted; }
        if (!quoted && strchr("!&|+", *p) && ++operators > 1024) { return false; }
        if (!quoted && *p == '(' && ++depth > 64) { return false; }
        if (!quoted && *p == ')' && --depth < 0) { return false; }
    }
    if (depth || quoted) { return false; }
    auto parsed = ParseExpression(text);
    static Devices devices;
    DeviceQualifier device;
    device.FromString(column ? "Controller" : "Keyboard");
    ControlFinder finder(devices, device, true);
    if (parsed.second) { parsed.second->UpdateReferences(finder); }
    if (parsed.first == ParseStatus::SyntaxError &&
        (!parsed.second || parsed.second->CountNumControls() == 0)) { return false; }
    binding.text = text;
    binding.range = std::clamp(range, -500, 500);
    binding.expr = std::move(parsed.second);
    return true;
}

std::string quoted(const char *name) { return name && *name ? "`" + std::string(name) + "`" : ""; }
void defaults(int p, int split, const int *keys, const int *pads) {
    for (int a = 0; a < PORT_WII_ACTIONS; a++) {
        std::string key, pad;
        if (a < PORT_ACTIONS && keys[a] > 0 && keys[a] < SDL_SCANCODE_COUNT) {
            key = quoted(PortWii_InputName(0, keys[a]));
        }
        if (a < PORT_PAD_BUTTONS) {
            int source = pads[a];
            if (source == PORT_PAD_LT || source == PORT_PAD_RT) { pad = quoted(kAxes[source == PORT_PAD_LT ? 8 : 9]); }
            else if (source >= 0 && source < (int)(sizeof(kButtons) / sizeof(*kButtons))) { pad = quoted(kButtons[source]); }
        } else if (a < PORT_ACTIONS) {
            static const int axes[] = {2, 3, 0, 1, 6, 7, 4, 5};
            pad = quoted(kAxes[axes[a - PORT_PAD_BUTTONS]]);
        }
        // One expression per action. Unqualified inputs use Keyboard; pad inputs carry
        // Dolphin's device qualifier (including ambiguous names such as A).
        std::string expr = key;
        if (!pad.empty()) {
            pad.insert(1, "Controller:");
            expr = key.empty() ? pad : key + " | " + pad;
        }
        compile(sBindings[p][split][a], 0, expr.c_str(), 100);
    }
}
std::string path() {
    const char *setting = SDL_getenv("BT3_SETTINGS");
    return !setting ? "bt3_wii_controls.ini" : !*setting ? "" : std::string(setting) + ".wii.ini";
}
// Qualify legacy controller controls without changing Dolphin's operator order.
std::string qualify(const std::string& text) {
    Lexer lexer(text);
    std::string result;
    for (;;) {
        Token tok = lexer.NextToken();
        if (tok.type == TOK_EOF) { return result; }
        if (tok.type == TOK_CONTROL) {
            if (!tok.qualifier.has_device) {
                tok.qualifier.has_device = true;
                tok.qualifier.device_qualifier.FromString("Controller");
            }
            result += "`" + static_cast<std::string>(tok.qualifier) + "`";
        } else if (tok.type != TOK_DISCARD) { result += static_cast<std::string>(tok); }
    }
}
void load(int player) {
    std::string file = path();
    if (file.empty()) { return; }
    size_t size;
    char *data = (char *)SDL_LoadFile(file.c_str(), &size);
    if (!data) { return; }
    bool unified = strstr(data, "# Wii unified expressions v2") != nullptr;
    Binding legacy[2][2][PORT_WII_ACTIONS];
    bool present[2][2][PORT_WII_ACTIONS] = {};
    char *line = data;
    while (line && *line) {
        char *next = strchr(line, '\n');
        if (next) { *next++ = 0; }
        size_t len = strlen(line);
        if (len && line[len - 1] == '\r') { line[len - 1] = 0; }
        int p, split, column = 0, action, range, offset = 0;
        int fields = unified ? sscanf(line, "%d.%d.%d=%d:%n", &p, &split, &action, &range, &offset) :
                              sscanf(line, "%d.%d.%d.%d=%d:%n", &p, &split, &column, &action, &range, &offset);
        if (fields == (unified ? 4 : 5) && offset > 0 && p == player && split >= 0 && split < 2 &&
            column >= 0 && column < 2 && action >= 0 && action < PORT_WII_ACTIONS) {
            if (unified) { compile(sBindings[p][split][action], 0, line + offset, range); }
            else { present[split][column][action] = compile(legacy[split][column][action], column, line + offset, range); }
        }
        line = next;
    }
    if (!unified) {
        sLegacy = true;
        for (int split = 0; split < 2; split++) for (int a = 0; a < PORT_WII_ACTIONS; a++) {
            if (!present[split][0][a] && !present[split][1][a]) { continue; }
            const Binding& key = legacy[split][0][a];
            const Binding& pad = legacy[split][1][a];
            std::string expr = key.text;
            if (!pad.text.empty()) {
                expr = key.text.empty() ? qualify(pad.text) : "(" + key.text + ") | (" + qualify(pad.text) + ")";
            }
            int range = key.text.empty() ? pad.range : key.range;
            if (!key.text.empty() && !pad.text.empty() && key.range != pad.range) {
                fprintf(stderr, "Wii bindings: legacy player %d profile %d action %d used different ranges; "
                                "using keyboard range %d, original preserved in .r1.bak\n", player, split, a, range);
            }
            compile(sBindings[player][split][a], 0, expr.c_str(), range);
        }
    }
    SDL_free(data);
}
// Resolve input settings before taking sLock; first use may initialize bindings.
SDL_Gamepad *preview_sample(int player, unsigned char *sticks) {
    int slot = *PortInput_PadSlot(player), count;
    SDL_JoystickID *ids = SDL_GetGamepads(&count);
    SDL_Gamepad *g = slot >= 0 && slot < count ? SDL_GetGamepadFromID(ids[slot]) : nullptr;
    SDL_free(ids);
    PortStickView view;
    PortInput_StickView(player, &view);
    for (int i = 0; i < 4; i++) { sticks[i] = view.bytes[i / 2][i % 2]; }
    return g;
}
void read(int p, int split, float *values) {
    for (int a = 0; a < PORT_WII_ACTIONS; a++) {
        const Binding& b = sBindings[p][split][a];
        values[a] = b.expr && (sSample.keys || sSample.pad) ?
                    (float)std::clamp(b.expr->GetValue() * b.range / 100.0, 0.0, 1.0) : 0;
    }
}
}

extern "C" void PortWii_Init(int p, const int *keys, const int *pads) {
    Lock lock;
    if (sLoaded[p]) { return; }
    defaults(p, 0, keys, pads);
    defaults(p, 1, keys, pads);
    load(p);
    sLoaded[p] = true;
}
extern "C" void PortWii_Reset(int p, int split, const int *keys, const int *pads) {
    Lock lock;
    defaults(p, split, keys, pads);
}
extern "C" void PortWii_Save(void) {
    Lock lock;
    std::string file = path();
    if (file.empty()) { return; }
    if (sLegacy) {
        SDL_PathInfo info;
        std::string backup = file + ".r1.bak";
        if (!SDL_GetPathInfo(backup.c_str(), &info) && !SDL_CopyFile(file.c_str(), backup.c_str())) {
            fprintf(stderr, "Wii bindings: could not back up original: %s\n", SDL_GetError()); return;
        }
        sLegacy = false;
    }
    std::string text = "# Wii unified expressions v2\n# player.profile.action=range:expression; default device: Keyboard\n";
    for (int p = 0; p < 2; p++) {
        for (int split = 0; split < 2; split++) {
            for (int a = 0; a < PORT_WII_ACTIONS; a++) {
                const Binding& b = sBindings[p][split][a];
                char name[64];
                snprintf(name, sizeof(name), "%d.%d.%d=%d:", p, split, a, b.range);
                std::string expression = b.text;
                for (char& c : expression) if (c == '\n' || c == '\r') c = ' ';
                text += name + expression + "\n";
            }
        }
    }
    std::string temp = file + ".tmp";
    SDL_IOStream *out = SDL_IOFromFile(temp.c_str(), "wb");
    if (!out) { fprintf(stderr, "Wii bindings: %s\n", SDL_GetError()); return; }
    bool ok = SDL_WriteIO(out, text.data(), text.size()) == text.size();
    ok = SDL_CloseIO(out) && ok;
    if (!ok || !SDL_RenamePath(temp.c_str(), file.c_str())) {
        fprintf(stderr, "Wii bindings: could not save %s: %s\n", file.c_str(), SDL_GetError());
    }
}
extern "C" int PortWii_Set(int p, int split, int a, const char *text, int range) {
    Lock lock;
    return compile(sBindings[p][split][a], 0, text, range);
}
extern "C" int PortWii_Validate(const char *text, int range) {
    Lock lock;
    Binding binding;
    return compile(binding, 0, text, range);
}
extern "C" int PortWii_Format(const char *text, int readable, char *out, int size) {
    if (!text || !out || size <= 0 || strlen(text) >= PORT_WII_EXPR_SIZE) { return 0; }
    Lock lock;
    auto control = [](const std::string& name) {
        // Dolphin MappingCommon::GetExpressionForControl: only [a-zA-Z]+ is bare.
        bool letters = !name.empty();
        for (unsigned char c : name) { letters &= (c >= 'A' && c <= 'Z') || (c >= 'a' && c <= 'z'); }
        return letters ? name : "`" + name + "`";
    };
    std::string result;
    static Inputs keyboard(true);
    if (keyboard.FindInput(text)) {
        // Dolphin also accepts a whole unquoted input name, e.g. F1 or Left Shift.
        result = control(std::string(strchr(text, ':') ? "Keyboard:" : "") + text);
    } else {
        Lexer lexer(text);
        bool previous_control = false;
        for (;;) {
            Token tok = lexer.NextToken();
            if (tok.type == TOK_EOF) { break; }
            if (tok.type == TOK_INVALID) { return 0; }
            if (tok.type == TOK_DISCARD) { continue; }
            if (tok.type == TOK_CONTROL) {
                if (previous_control) { result += ' '; } // Never join two barewords.
                result += control((tok.qualifier.has_device ? tok.qualifier.device_qualifier.ToString() + ":" : "") + tok.qualifier.control_name);
            } else {
                bool op = tok.type == TOK_AND || tok.type == TOK_OR || tok.type == TOK_NOT || tok.type == TOK_ADD;
                if (readable && op && !result.empty() && result.back() != ' ' && result.back() != '(') { result += ' '; }
                result += static_cast<std::string>(tok);
                if (readable && op) { result += ' '; }
            }
            previous_control = tok.type == TOK_CONTROL;
        }
        if (!result.empty() && result.back() == ' ') { result.pop_back(); }
    }
    if (result.size() >= (size_t)size) { return 0; }
    memcpy(out, result.c_str(), result.size() + 1);
    return 1;
}
// Reuse Dolphin's lexer: change device/input names, never the expression tree or
// operator order. XInput's vertical stick axes have the opposite sign to SDL.
extern "C" int PortWii_TranslateDolphin(const char *text, const char *device, char *out, int size, char *error, int error_size) {
    Lock lock;
    if (!text || strlen(text) >= PORT_WII_EXPR_SIZE) { return 0; }
    Lexer lexer(text);
    std::string result;
    Inputs keyboard(true), controller(false);
    for (;;) {
        Token tok = lexer.NextToken();
        if (tok.type == TOK_EOF) { break; }
        if (tok.type == TOK_DISCARD) { result += ' '; continue; }
        if (tok.type == TOK_INVALID) { snprintf(error, error_size, "表达式中包含无法识别的字符。"); return 0; }
        if (tok.type != TOK_CONTROL) { result += static_cast<std::string>(tok); continue; }
        std::string source = tok.qualifier.has_device ? tok.qualifier.device_qualifier.ToString() : device;
        std::string name = tok.qualifier.control_name;
        bool key = source.empty() || source == "Keyboard" || source.find("Keyboard") != std::string::npos ||
                   source.find("keyboard") != std::string::npos || source.find("Mouse") != std::string::npos;
        if (key) {
            static const struct { const char *old, *name; } aliases[] = {
                {"RETURN", "Return"}, {"NUMPADENTER", "Keypad Enter"}, {"NUMPADCOMMA", "Keypad ,"},
                {"NUMPADEQUALS", "Keypad ="}, {"ADD", "Keypad +"}, {"SUBTRACT", "Keypad -"},
                {"MULTIPLY", "Keypad *"}, {"DIVIDE", "Keypad /"}, {"DECIMAL", "Keypad ."},
                {"NUMLOCK", "Numlock"}, {"APPS", "Application"}, {"APOSTROPHE", "'"},
                {"BACKSLASH", "\\"}, {"COLON", ":"}, {"COMMA", ","}, {"EQUALS", "="},
                {"MINUS", "-"}, {"PERIOD", "."}, {"LBRACKET", "["},
                {"RBRACKET", "]"}, {"SEMICOLON", ";"}, {"SLASH", "/"},
                {"Axis Z-", "Wheel Y-"}, {"Axis Z+", "Wheel Y+"}
            };
            if (name.size() == 7 && name.substr(0, 6) == "NUMPAD" && name[6] >= '0' && name[6] <= '9') {
                name = "Keypad " + name.substr(6);
            }
            for (const auto& a : aliases) { if (name == a.old) { name = a.name; break; } }
        } else if (source.rfind("XInput/", 0) == 0) {
            static const struct { const char *old, *name; } aliases[] = {
                {"Button A", "A"}, {"Button B", "B"}, {"Button X", "X"}, {"Button Y", "Y"},
                {"Pad N", "D-pad up"}, {"Pad S", "D-pad down"}, {"Pad W", "D-pad left"}, {"Pad E", "D-pad right"},
                {"Shoulder L", "Left shoulder"}, {"Shoulder R", "Right shoulder"},
                {"Thumb L", "Left stick click"}, {"Thumb R", "Right stick click"},
                {"Trigger L", "Left trigger"}, {"Trigger R", "Right trigger"},
                {"Left Y+", "Left Y-"}, {"Left Y-", "Left Y+"},
                {"Right Y+", "Right Y-"}, {"Right Y-", "Right Y+"}
            };
            for (const auto& a : aliases) { if (name == a.old) { name = a.name; break; } }
        } else if (source != "Controller") {
            snprintf(error, error_size, "无法可靠转换设备 %s 的输入 %s；请在移植版中重新绑定此输入。", source.c_str(), name.c_str());
            return -1;
        }
        if (!(key ? keyboard : controller).FindInput(name) || name.find('`') != std::string::npos) {
            snprintf(error, error_size, "无法转换输入 %s（设备 %s）。", name.c_str(), source.c_str());
            return -1;
        }
        result += "`" + std::string(key ? "" : "Controller:") + name + "`";
        if (result.size() >= (size_t)size) { snprintf(error, error_size, "转换后的表达式过长。"); return 0; }
    }
    Binding binding;
    if (result.size() >= (size_t)size || !compile(binding, 0, result.c_str(), 100)) {
        snprintf(error, error_size, "Dolphin 表达式无效或过长。"); return 0;
    }
    snprintf(out, size, "%s", result.c_str());
    return 1;
}
extern "C" void PortWii_Get(int p, int split, int a, char *text, int size, int *range) {
    Lock lock;
    const Binding& b = sBindings[p][split][a];
    snprintf(text, (size_t)size, "%s", b.text.c_str());
    if (range) { *range = b.range; }
}
extern "C" void PortWii_Read(int p, int split, SDL_Gamepad *pad, const bool *keys, const unsigned char *sticks,
                              int (*blocked)(int), float *values) {
    Lock lock;
    sSample = {pad, keys, sticks, blocked};
    read(p, split, values);
    sSample = {};
}
extern "C" int PortWii_KeysHeld(int p, int split, const bool *keys) {
    // Suppress all physical keys referenced by a Wii expression, even in ! / & bindings.
    Lock lock;
    sSample = {nullptr, keys, nullptr, nullptr};
    sAnyKey = false;
    for (int a = 0; a < PORT_WII_ACTIONS; a++) {
        const Binding& b = sBindings[p][split][a];
        if (b.expr) { b.expr->GetValue(); }
    }
    sSample = {};
    return sAnyKey;
}
extern "C" int PortWii_InputCount(int device) { return device ? 31 : SDL_SCANCODE_COUNT + 13; }
extern "C" const char *PortWii_InputName(int device, int i) {
    if (i < 0 || i >= PortWii_InputCount(device)) { return ""; }
    // Backticks delimit Dolphin control names; use its safe name for this key.
    if (!device && i == SDL_SCANCODE_GRAVE) { return "GRAVE"; }
    return device ? i < 21 ? kButtons[i] : kAxes[i - 21] :
                    i < SDL_SCANCODE_COUNT ? SDL_GetScancodeName((SDL_Scancode)i) : kMouse[i - SDL_SCANCODE_COUNT];
}
extern "C" float PortWii_Preview(int player, const char *text, int range) {
    unsigned char sticks[4];
    SDL_Gamepad *g = preview_sample(player, sticks);
    Lock lock;
    Binding b;
    if (!compile(b, 0, text, range) || !b.expr) { return 0; }
    sSample = {g, SDL_GetKeyboardState(nullptr), sticks, nullptr};
    float value = (float)std::clamp(b.expr->GetValue() * b.range / 100.0, 0.0, 1.0);
    sSample = {};
    return value;
}
extern "C" void PortWii_PreviewBindings(int player, int split, float *values) {
    unsigned char sticks[4];
    SDL_Gamepad *g = preview_sample(player, sticks);
    Lock lock;
    sSample = {g, SDL_GetKeyboardState(nullptr), sticks, nullptr};
    read(player, split, values);
    sSample = {};
}
extern "C" void PortWii_MouseEvent(const SDL_Event *ev) {
    Lock lock;
    if (ev->type == SDL_EVENT_MOUSE_MOTION) {
        sMotion[0] += ev->motion.xrel; sMotion[1] += ev->motion.yrel;
    }
    if (ev->type == SDL_EVENT_MOUSE_WHEEL) {
        float sign = ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED ? -1.0f : 1.0f;
        float x = ev->wheel.x * sign, y = ev->wheel.y * sign;
        sWheel[0] += x * 120; sWheel[1] += y * 120;
    }
}
extern "C" void PortWii_MouseFrame(void) {
    Lock lock;
    SDL_MouseButtonFlags buttons = SDL_GetMouseState(nullptr, nullptr);
    const int ids[] = {SDL_BUTTON_LEFT, SDL_BUTTON_RIGHT, SDL_BUTTON_MIDDLE, SDL_BUTTON_X1, SDL_BUTTON_X2};
    for (int i = 0; i < 5; i++) { sMouse[i] = (buttons & SDL_BUTTON_MASK(ids[i])) ? 1.0f : 0.0f; }
    // Dolphin 10912 DInputKeyboardMouse::UpdateInput / Axis::GetState:
    // smooth signed axes as (previous + delta) / 2, sensitivity 8, drop stale input after 250 ms.
    bool stale = SDL_GetTicks() - sMouseUpdate > 250;
    sMouseUpdate = SDL_GetTicks();
    for (int i = 0; i < 2; i++) {
        sMouseAxis[i] = stale ? 0 : (int)((sMouseAxis[i] + sMotion[i]) / 2);
        sWheelAxis[i] = stale ? 0 : (int)((sWheelAxis[i] + sWheel[i]) / 2);
        sMouse[5 + i * 2] = std::max(0.0f, -sMouseAxis[i] / 8.0f);
        sMouse[6 + i * 2] = std::max(0.0f, sMouseAxis[i] / 8.0f);
        sMouse[9 + i * 2] = (float)std::max(0, -sWheelAxis[i]);
        sMouse[10 + i * 2] = (float)std::max(0, sWheelAxis[i]);
        sMotion[i] = sWheel[i] = 0;
    }
}
extern "C" const char *PortWii_ActionLabel(int split, int a) {
    static const char *const labels[] = {
        "方向键上", "方向键下", "方向键左", "方向键右", "飞行", "防御", "攻击", "气弹",
        "下降", "上升", "高速下降", "高速上升", "左摇杆按下", "聚气", "开始 / 暂停", "选择",
        "移动上", "移动下", "移动左", "移动右", "换人", "变身", "左视角", "右视角",
        "上一个角色", "下一个角色", "暴血（双击）"
    };
    if (!split && a == 22) { return "左视角 / 上一个角色 / 双击暴血"; }
    if (!split && a == 23) { return "右视角 / 下一个角色 / 双击暴血"; }
    return labels[a];
}
