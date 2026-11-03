// Persistent rooms are a control plane outside game state. The existing
// Port_Lobby* functions still own UDP, handshake, fingerprint and socket handoff.
#include "online_lobby.h"
#include "online_json.h"
#include "online_ping.h"
#include "../local_release.h"
#include "update_sign.h"
#include "ui_zh.h"
#include "imgui.h"
#include <SDL3/SDL.h>
#include "../../third_party/dolphin/Common/ProfileIni.h"
#include <algorithm>
#include <cstring>
#include <cstdlib>
#include <string>
#include <vector>
extern "C" {
#include "net_match.h"
int Port_LobbyStartCode(int host, const char *code);
int Port_LobbySpectateCode(const char *code);
int Port_NetMe(void);
int Port_NetSpectating(void);
void Port_NetSpectatorsAllow(int on);
int Port_Setting(const char *name, int def);
void Port_SettingSave(const char *name, int value);
void Port_SettingsWrite(void);
int Port_LobbyPoll(void);
void Port_LobbyCancel(void);
void Port_LobbyLaunch(void);
const char *Port_LobbyError(void);
void Port_NetOptions(int rollback, int delay);
void Port_NetRulesSet(int type, int dp, int time);
void Port_NetSpeedSet(int percent);
void Port_NetNameSet(const char *name);
int Port_NetSession(void);
int Port_NetSessionsEnded(void);
int Port_RollCan(void);
}

extern "C" int Port_DataFingerprintNeed(void);

namespace OnlineLobby {
namespace {
using OnlineJson::Value;
using OnlineJson::Quote;
struct Favorite { std::string name, url, access, room, directory; bool personal = true; };
struct Job {
    SDL_AtomicInt done;
    std::string url, access, body, reply, op;
    Uint64 elapsed = 0;
    bool success = false;
};
std::vector<Favorite> favorites;
int selected = 0;
bool loaded = false, closing = false, connecting = false, launched = false, seenSession = false;
bool forceFocus = false, finishPending = false;
std::string token, pending, session, serverName, error, info, queuedOp, queuedFields;
Value room;
std::vector<Value> rooms;
Job *job = nullptr;
Uint64 nextPoll = 0, launchedAt = 0, elapsed = 0;
int endedAt = 0;
bool relayOnly = false, turnAvailable = false, lastOnline = false;
std::string oldRelay;
bool hadRelay = false, relayChanged = false;
bool splitView = false, matchPause = false;
int primarySide = 0;
Uint64 swapUntil = 0;

// Presentation only; the server owns the matching/start decision.
std::string versionNotice(const Value& state) {
    bool mismatch = state["versions_match"].kind != Value::Null && !state["versions_match"].yes();
    bool old = state["clients_current"].kind != Value::Null && !state["clients_current"].yes();
    if (!mismatch && !old) return "";
    std::string message = "玩家版本不同或版本过旧，无法开始。";
    bool lower = false;
    for (const auto& seat : state["seats"].array) {
        if (seat["name"].str().empty()) continue;
        std::string version = seat["version"].str();
        if (!version.empty()) {
            message += " " + std::to_string(seat["seat"].integer()) + "P：" + version;
            if (UpdateVer_Compare(BT3_LOCAL_VERSION, version.c_str()) == -1) lower = true;
        }
    }
    message += lower ? "\n你的版本较低，请更新游戏后重新进入房间。" : "\n请版本较低的玩家更新游戏后重新进入房间。";
    return message;
}

bool plain(const std::string& s, size_t max) {
    return !s.empty() && s.size() <= max && s.find_first_of("\r\n\t|") == std::string::npos && s.find('\0') == std::string::npos && s.front() != ' ' && s.back() != ' ';
}
bool accessValid(const std::string& s) {
    return s.size() <= 96 && std::all_of(s.begin(), s.end(), [](unsigned char c) { return c >= 33 && c <= 126 && c != '|'; });
}
bool urlValid(const std::string& url) {
    if (!plain(url, 200) || url.find_first_of("?#@\\ \"") != std::string::npos) return false;
    if (url.compare(0, 8, "https://") == 0) return url.size() > 8;
    // Clear-text is deliberately limited to explicit local/LAN demo addresses.
    if (url.compare(0, 7, "http://") != 0) return false;
    std::string host = url.substr(7, url.find_first_of(":/", 7)-7);
    int a=0,b=0,c=0,d=0; char extra=0;
    bool ipv4 = std::sscanf(host.c_str(), "%d.%d.%d.%d%c", &a,&b,&c,&d,&extra) == 4 &&
        a >= 0 && a <= 255 && b >= 0 && b <= 255 && c >= 0 && c <= 255 && d >= 0 && d <= 255;
    return host == "localhost" || (ipv4 && (a == 127 || a == 10 || (a == 192 && b == 168) || (a == 172 && b >= 16 && b <= 31)));
}
std::string configFile() {
    const char *settings = SDL_getenv("BT3_SETTINGS");
    std::string base = settings ? settings : "";
    size_t slash = base.find_last_of("/\\");
    return (slash == std::string::npos ? "" : base.substr(0, slash+1)) + "bt3_online_servers.ini";
}
bool save() {
    std::string data = "; BT3 online server favorites. API 2; battle protocol 6.\n[General]\nSelected = " + std::to_string(selected) + "\n";
    for (size_t i = 0; i < favorites.size(); ++i) {
        const auto& f = favorites[i];
        data += "\n[Server" + std::to_string(i) + "]\nName = " + f.name + "\nURL = " + f.url + "\nAccess = " + f.access + "\nRoom = " + f.room + "\nDirectoryId = " + f.directory + "\nPersonal = " + (f.personal ? "1" : "0") + "\n";
    }
    std::string path = configFile(), tmp = path + ".tmp";
    SDL_IOStream *out = SDL_IOFromFile(tmp.c_str(), "wb");
    if (!out) { error = "服务器收藏保存失败：" + std::string(SDL_GetError()); return false; }
    bool ok = SDL_WriteIO(out, data.data(), data.size()) == data.size();
    ok = SDL_CloseIO(out) && ok;
    if (!ok || !SDL_RenamePath(tmp.c_str(), path.c_str())) { error = "服务器收藏保存失败：" + std::string(SDL_GetError()); return false; }
    return true;
}
void goodbye();

void load() {
    if (loaded) return;
    loaded = true;
    std::atexit(goodbye);
    size_t size = 0;
    void *raw = SDL_LoadFile(configFile().c_str(), &size);
    if (raw && size <= 32768) {
        auto ini = DolphinProfile::Load(std::string((char *)raw, size));
        selected = std::atoi(ini["General"]["Selected"].c_str());
        for (int n = 0; n < 80; ++n) {
            auto sec = ini.find("Server" + std::to_string(n));
            if (sec == ini.end()) continue;
            Favorite f{sec->second["Name"], sec->second["URL"], sec->second["Access"], sec->second["Room"]};
            f.directory = sec->second["DirectoryId"]; f.personal = sec->second["Personal"] != "0";
            if (plain(f.name, 64) && urlValid(f.url) && accessValid(f.access)) favorites.push_back(f);
        }
    }
    SDL_free(raw);
    primarySide = Port_Setting("online_primary_side", 0) == 1 ? 1 : 0;
    if (favorites.empty()) favorites.push_back({"本机演示大厅", "http://127.0.0.1:8787", "", ""});
    if (selected < 0 || selected >= (int)favorites.size()) selected = 0;
}
// The private launcher supplies a loopback TLS bridge for this one endpoint.
// Other servers, matching, TURN and battle packets keep their original paths.
std::string requestUrl(const std::string& url) {
    const char *remote = SDL_getenv("BT3_LOBBY_GATEWAY_REMOTE");
    const char *local = SDL_getenv("BT3_LOBBY_GATEWAY_LOCAL");
    unsigned port = 0; char extra = 0;
    if (!remote || !remote[0] || !local ||
        std::sscanf(local, "http://127.0.0.1:%u%c", &port, &extra) != 1 || !port || port > 65535) return url;
    size_t size = std::strlen(remote);
    if (url.compare(0, size, remote) || (url.size() != size && url[size] != '/')) return url;
    return std::string(local) + url.substr(size);
}
int SDLCALL request(void *arg) {
    Job *j = (Job *)arg;
    char reply[65536] = {};
    Uint64 start = SDL_GetTicks();
    j->success = Match_Http(requestUrl(j->url).c_str(), j->body.c_str(), j->access.c_str(), reply, sizeof(reply)) != 0;
    j->elapsed = SDL_GetTicks() - start;
    j->reply = reply;
    SDL_SetAtomicInt(&j->done, 1); // publishes all job-owned strings
    return 0;
}
// Best-effort immediate release on a normal window/Exit close. A killed process
// cannot run this callback; the server's heartbeat lease handles that case.
void goodbye() {
    OnlinePing::Stop();
    if (!loaded || favorites.empty()) return;
    std::string leaveToken = token;
    if (leaveToken.empty() && job && job->op == "enter") {
        Uint64 until = SDL_GetTicks()+500;
        while (!SDL_GetAtomicInt(&job->done) && SDL_GetTicks()<until) SDL_Delay(5);
        Value answer;
        if (SDL_GetAtomicInt(&job->done) && job->success && OnlineJson::Parse(job->reply, answer))
            leaveToken = answer["token"].str();
    }
    if (leaveToken.empty()) return;
    Job *j = new Job;
    SDL_SetAtomicInt(&j->done, 0);
    j->url = favorites[selected].url+"/lobby/v1/request";
    j->access = favorites[selected].access;
    j->body = "{\"op\":\"leave\",\"token\":"+Quote(leaveToken)+"}";
    SDL_Thread *thread = SDL_CreateThread(request, "bt3-lobby-goodbye", j);
    if (!thread) { delete j; return; }
    SDL_DetachThread(thread);
    Uint64 until = SDL_GetTicks()+1500;
    while (!SDL_GetAtomicInt(&j->done) && SDL_GetTicks()<until) SDL_Delay(5);
    if (SDL_GetAtomicInt(&j->done)) delete j;
    // On timeout the process exits with its worker; no unbounded shutdown wait.
}

void send(const std::string& op, const std::string& fields = "") {
    if (favorites.empty()) return;
    if (job) {
        if ((job->op == "list" || job->op == "poll") && queuedOp.empty() && op != "list" && op != "poll") {
            queuedOp = op; queuedFields = fields;
        }
        return;
    }
    const auto& f = favorites[selected];
    Job *j = new Job;
    SDL_SetAtomicInt(&j->done, 0);
    j->op = op; j->url = f.url + "/lobby/v1/request"; j->access = f.access;
    j->body = "{\"op\":" + Quote(op) + (token.empty() ? "" : ",\"token\":" + Quote(token)) + fields + "}";
    SDL_Thread *thread = SDL_CreateThread(request, "bt3-lobby-http", j);
    if (!thread) { delete j; error = "无法启动大厅请求。"; return; }
    SDL_DetachThread(thread);
    job = j;
}
bool busy() {
    return !queuedOp.empty() || (job && job->op != "list" && job->op != "poll");
}
void relaySet(bool on) {
    if (relayChanged) return;
    const char *value = SDL_getenv("BT3_RELAY_ONLY");
    hadRelay = value != nullptr; oldRelay = value ? value : "";
    if (on) {
        SDL_setenv_unsafe("BT3_RELAY_ONLY", "1", 1);
        SDL_SetEnvironmentVariable(SDL_GetEnvironment(), "BT3_RELAY_ONLY", "1", true);
    } else {
        SDL_unsetenv_unsafe("BT3_RELAY_ONLY");
        SDL_UnsetEnvironmentVariable(SDL_GetEnvironment(), "BT3_RELAY_ONLY");
    }
    relayChanged = true;
}
void relayRestore() {
    if (!relayChanged || !Match_TransportIdle()) return;
    if (hadRelay) {
        SDL_setenv_unsafe("BT3_RELAY_ONLY", oldRelay.c_str(), 1);
        SDL_SetEnvironmentVariable(SDL_GetEnvironment(), "BT3_RELAY_ONLY", oldRelay.c_str(), true);
    } else {
        SDL_unsetenv_unsafe("BT3_RELAY_ONLY");
        SDL_UnsetEnvironmentVariable(SDL_GetEnvironment(), "BT3_RELAY_ONLY");
    }
    relayChanged = false;
}
void stopConnect(const std::string& message) {
    if (connecting) Port_LobbyCancel();
    connecting = false;
    error = message;
    finishPending = !session.empty();
    if (!session.empty()) pending = "cancel";
}
void leaveDone() {
    OnlinePing::Stop();
    token.clear(); room = Value(); closing = false; session.clear(); pending.clear();
    connecting = false; finishPending = false; nextPoll = 0; lastOnline = false;
}
void response() {
    if (!job || !SDL_GetAtomicInt(&job->done)) return;
    Job *j = job; job = nullptr;
    if (j->url != favorites[selected].url+"/lobby/v1/request") { delete j; return; }
    Value answer;
    bool ok = j->success && OnlineJson::Parse(j->reply, answer) && answer["ok"].yes();
    elapsed = j->elapsed;
    if (!ok) {
        lastOnline = false;
        error = j->success ? answer["error"].str("服务器返回了无法识别的数据。") : "无法连接服务器。请确认大厅服务已启动，地址与口令正确。";
        // A lost control-plane request never aborts an established UDP game.
        if (j->op == "leave") leaveDone();
        if (answer["error"].str().find("身份已失效") != std::string::npos) {
            OnlinePing::Stop();
            if (connecting) stopConnect(error);
            token.clear(); room = Value();
            pending.clear(); finishPending = false;
            if (!launched) session.clear();
        }
        if (j->op == "finish" || j->op == "cancel") pending = j->op;
        // A rejected edit/start may have used an old room epoch. Refresh the
        // room before enabling another attempt with the same stale snapshot.
        bool refresh = j->success && !token.empty() && (j->op == "start" || j->op == "seat" || j->op == "mode");
        nextPoll = refresh ? 0 : SDL_GetTicks() + 4000;
        delete j; return;
    }
    lastOnline = true;
    if (j->op != "poll") error.clear();
    if (j->op == "list") {
        if (answer["api"].integer() != 2 || answer["protocol"].integer() != 6) {
            error = "服务器大厅版本不受支持（需要 API 2／战斗协议 6）。"; rooms.clear();
        } else {
            rooms = answer["rooms"].array;
            if (rooms.size() > 32) rooms.resize(32);
            serverName = answer["server"].str("BT3");
            relayOnly = answer["relay_only"].yes(); turnAvailable = answer["turn_available"].yes();
        }
    } else if (j->op == "enter") {
        token = answer["token"].str(); room = answer["room"];
        session.clear(); pending.clear(); finishPending = false;
        favorites[selected].room = room["id"].str(); save();
    } else if (j->op == "leave") leaveDone();
    else if (answer["room"].kind == Value::Object) room = answer["room"];
    if (j->op == "swap") swapUntil = SDL_GetTicks() + 1000;
    else if (answer["room"].kind == Value::Object) swapUntil = SDL_GetTicks() + room["swap_wait_ms"].integer();
    if (!token.empty()) {
        const auto& probe = room["probe"];
        OnlinePing::Start(probe["host"].str(), probe["port"].integer(), probe["key"].str());
    }
    if (j->op == "finish" || j->op == "cancel") finishPending = false;
    nextPoll = SDL_GetTicks() + 2000;
    delete j;
}
const char *phase(const Value& r) {
    const auto p = r["phase"].str();
    if (p == "playing") return "对战中";
    if (p == "starting") return "正在连接";
    int count = 0;
    for (const auto& s : r["seats"].array) if (!s["name"].str().empty()) ++count;
    return count == 0 ? "空闲" : count == 1 ? "等待玩家" : "等待开始";
}
bool directoryRename(const Favorite& f, const char *name);
void editor(bool edit) {
    static char name[96], url[224], access[100];
    if (ImGui::BeginPopupModal("服务器设置", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::InputText("名称", name, sizeof(name));
        ImGui::InputText("地址", url, sizeof(url));
        ImGui::InputText("访问口令", access, sizeof(access), ImGuiInputTextFlags_Password);
        ImGui::TextDisabled("公网服务器使用 https://；本机演示：http://127.0.0.1:8787");
        if (ImGui::Button("保存")) {
            std::string u = url;
            while (!u.empty() && u.back() == '/') u.pop_back();
            if (!plain(name, 64) || !urlValid(u) || !accessValid(access)) error = "请输入有效名称、地址与英文数字访问口令。";
            else {
                Favorite f = edit ? favorites[selected] : Favorite{};
                bool same = edit && f.url == u;
                if (!same) { f.room.clear(); f.directory.clear(); f.personal = true; }
                if (same && f.name != name) { directoryRename(f, name); f.personal = true; }
                f.name = name; f.url = u; f.access = access;
                if (edit) favorites[selected] = f;
                else if (favorites.size() < 80) { favorites.push_back(f); selected = (int)favorites.size()-1; }
                rooms.clear(); serverName.clear(); lastOnline = false; nextPoll = 0; error.clear(); save();
                ImGui::CloseCurrentPopup();
            }
        }
        ImGui::SameLine(); if (ImGui::Button("取消")) ImGui::CloseCurrentPopup();
        ImGui::EndPopup();
    }
    // Set edit fields when opening, before the popup's next frame.
    if (info == "open-add" || info == "open-edit") {
        const auto& f = favorites[selected];
        SDL_strlcpy(name, edit ? f.name.c_str() : "好友服务器", sizeof(name));
        SDL_strlcpy(url, edit ? f.url.c_str() : "https://", sizeof(url));
        SDL_strlcpy(access, edit ? f.access.c_str() : "", sizeof(access));
        info.clear(); ImGui::OpenPopup("服务器设置");
    }
}
#include "online_directory.inl"
} // namespace

int Tick(bool visible) {
    if (!loaded) return 0; // no worker and no requests until the tab has been opened
    response();
    directoryTick(visible && token.empty() && !connecting && !launched);
    if (!connecting && !launched) relayRestore();
    if (launched) {
        if (Port_NetSession()) seenSession = true;
        if (Port_NetSessionsEnded() != endedAt || (seenSession && !Port_NetSession()) ||
            (!seenSession && SDL_GetTicks()-launchedAt > 15000)) {
            launched = false; pending = "finish"; finishPending = true;
            splitView = false; matchPause = false;
            forceFocus = true; nextPoll = 0;
            return 2;
        }
    }
    if (closing && !job) {
        if (!token.empty()) send("leave");
        else leaveDone();
    } else if (!job && !queuedOp.empty()) {
        std::string op = queuedOp, fields = queuedFields;
        queuedOp.clear(); queuedFields.clear(); send(op, fields);
    } else if (!job && !token.empty()) {
        if (!pending.empty() && SDL_GetTicks() >= nextPoll) {
            std::string op = pending; pending.clear();
            send(op, ",\"session\":" + Quote(session));
        } else if (SDL_GetTicks() >= nextPoll) send("poll");
    } else if (!job && visible && SDL_GetTicks() >= nextPoll) send("list");

    if (connecting) {
        if (room["session"].str() != session || room["ended"].yes()) {
            stopConnect("本次连接已取消，请重新开始。");
            return 0;
        }
        int state = Port_LobbyPoll();
        if (state == 2) {
            splitView = room["match_view"].str() == "split";
            matchPause = room["match_pause"].integer() != 0;
            endedAt = Port_NetSessionsEnded(); seenSession = false; launchedAt = SDL_GetTicks();
            connecting = false; launched = true;
            pending = "launch"; nextPoll = 0;
            Port_LobbyLaunch();
            return 1;
        }
        if (state < 0) {
            std::string why = UiZh(Port_LobbyError());
            stopConnect(why.empty() ? "双方连接未成功，请确认中继可用后重新开始。" : "连接失败：" + why);
        }
    } else if (visible && !closing && !launched && !finishPending && !token.empty() && !room["ended"].yes() &&
               (room["phase"].str() == "starting" || room["phase"].str() == "playing") && room["session"].str() != session && Match_TransportIdle()) {
        int seat = room["me"].integer();
        std::string auth = room["match_token"].str(), code = room["code"].str();
        if ((seat == 1 || (seat >= 2 && seat <= 8 && code.size() == 6)) && auth.size() == 64 && Port_DataFingerprintNeed() == 1) {
            session = room["session"].str();
            const auto& rules = room["rules"];
            int battle = rules["battle"].integer();
            Port_NetOptions(Port_RollCan() ? rules["rollback"].integer(8) : 0, rules["delay"].integer(-2));
            Port_NetSpeedSet(rules["speed"].integer(100));
            Port_NetRulesSet(battle < 2 ? battle : 2, battle >= 2 ? battle-2 : 0, rules["time"].integer(4));
            relaySet(relayOnly);
            Match_ConfigurePrivate(requestUrl(favorites[selected].url).c_str(), auth.c_str());
            Port_NetSpectatorsAllow(1); // fixed rooms include the six existing spectator places
            int state = seat > 2 ? Port_LobbySpectateCode(code.c_str()) : Port_LobbyStartCode(seat == 1, code.c_str());
            Match_ConfigurePrivate(nullptr, nullptr);
            connecting = state > 0;
            if (!connecting) stopConnect("无法开始连接，请重新准备。");
        }
    }
    return 0;
}

void Draw(const char *name, float scale) {
    load();
    static bool editing = false;
    ImGui::TextWrapped("目录中的服务器会自动同步。进入同一房间后，任一玩家点击开始即可联机。");
    directoryDraw();
    ImGui::BeginDisabled(!token.empty() || busy() || directoryBusy() || closing || connecting || launched);
    ImGui::SetNextItemWidth(280*scale);
    if (ImGui::BeginCombo("服务器", favorites[selected].name.c_str())) {
        for (size_t i = 0; i < favorites.size(); ++i) {
            if (ImGui::Selectable(favorites[i].name.c_str(), (int)i == selected)) {
                selected = (int)i; rooms.clear(); serverName.clear(); error.clear(); lastOnline = false; nextPoll = 0; save();
            }
        }
        ImGui::EndCombo();
    }
    if (ImGui::Button("添加")) { editing = false; info = "open-add"; }
    ImGui::SameLine(); if (ImGui::Button("编辑")) { editing = true; info = "open-edit"; }
    ImGui::SameLine(); if (ImGui::Button("删除") && favorites.size() > 1) {
        favorites.erase(favorites.begin()+selected); selected = 0; rooms.clear(); serverName.clear(); nextPoll = 0; save();
    }
    ImGui::SameLine(); if (ImGui::Button("复制服务器")) {
        SDL_SetClipboardText(("BT3SERVER1:" + favorites[selected].name + "|" + favorites[selected].url + "|" + favorites[selected].access).c_str());
    }
    ImGui::SameLine(); if (ImGui::Button("粘贴服务器")) {
        char *raw = SDL_GetClipboardText(); std::string s = raw ? raw : ""; SDL_free(raw);
        size_t a = s.find('|', 11), b = a == std::string::npos ? a : s.find('|', a+1);
        if (s.compare(0, 11, "BT3SERVER1:") != 0 || a == std::string::npos || b == std::string::npos || favorites.size() >= 80) error = "剪贴板中没有有效的服务器分享信息。";
        else {
            Favorite f{s.substr(11, a-11), s.substr(a+1, b-a-1), s.substr(b+1), ""};
            if (plain(f.name, 64) && urlValid(f.url) && accessValid(f.access)) {
                favorites.push_back(f); selected = (int)favorites.size()-1; rooms.clear(); serverName.clear(); nextPoll = 0; save();
            } else error = "服务器分享信息无效。";
        }
    }
    ImGui::EndDisabled();
    editor(editing);
    ImGui::TextDisabled("%s", favorites[selected].url.c_str());
    ImGui::Separator();
    if (favorites[selected].url == "http://127.0.0.1:8787") ImGui::TextWrapped("本机演示：先运行测试版旁的 02-Start-local-services.cmd。远程好友需使用同一台已部署的服务器。");
    if (!serverName.empty()) {
        ImGui::Text("%s   ·   %s", favorites[selected].directory.empty() ? serverName.c_str() : favorites[selected].name.c_str(), lastOnline ? "在线" : "连接中断");
        ImGui::TextDisabled("最近 API 请求耗时：%llu ms（不是游戏延迟）   ·   %s", (unsigned long long)elapsed,
            relayOnly ? "固定使用此服务器中继" : turnAvailable ? "直连优先，可用中继" : "本机／局域网直连，无中继");
    }
    if (!error.empty()) ImGui::TextWrapped("%s", error.c_str());
    if (closing) { ImGui::TextUnformatted("正在退出房间…"); return; }
    if (token.empty()) {
        ImGui::BeginDisabled(busy());
        if (ImGui::Button("刷新房间")) { nextPoll = 0; error.clear(); }
        ImGui::EndDisabled();
        if (rooms.empty()) ImGui::TextDisabled(job ? "正在读取房间列表…" : "尚未读到房间。");
        if (ImGui::BeginTable("server_rooms", 4, ImGuiTableFlags_RowBg | ImGuiTableFlags_BordersInnerH | ImGuiTableFlags_SizingStretchProp)) {
            ImGui::TableSetupColumn("常驻房间", ImGuiTableColumnFlags_WidthStretch, 2);
            ImGui::TableSetupColumn("人数"); ImGui::TableSetupColumn("状态"); ImGui::TableSetupColumn("操作"); ImGui::TableHeadersRow();
            for (const auto& r : rooms) {
                int count = 0; for (const auto& seat : r["seats"].array) if (!seat["name"].str().empty()) ++count;
                ImGui::PushID(r["id"].str().c_str());
                ImGui::TableNextRow(); ImGui::TableNextColumn(); ImGui::TextUnformatted(r["name"].str().c_str());
                ImGui::TableNextColumn(); ImGui::Text("%d / 8", count);
                ImGui::TableNextColumn(); ImGui::TextUnformatted(phase(r));
                ImGui::TableNextColumn(); ImGui::BeginDisabled(busy() || count >= 8 || r["phase"].str() != "idle");
                if (ImGui::Button("进入")) {
                    Port_NetNameSet(name);
                    send("enter", ",\"room\":" + Quote(r["id"].str()) + ",\"name\":" + Quote(name) + ",\"sync_pause\":1,\"version\":" + Quote(BT3_LOCAL_VERSION));
                    session.clear(); error.clear();
                }
                ImGui::EndDisabled(); ImGui::PopID();
            }
            ImGui::EndTable();
        }
        return;
    }
    ImGui::Text("%s   ·   %s", room["name"].str().c_str(), phase(room));
    int me = room["me"].integer();
    bool locked = connecting || launched || finishPending || room["phase"].str() != "idle";
    if (ImGui::BeginTable("room_seat_groups", 2, ImGuiTableFlags_SizingStretchSame)) {
      for (int group = 0; group < 2; ++group) {
        ImGui::TableNextColumn(); ImGui::PushID(group);
        if (ImGui::BeginTable("room_seats", 5, ImGuiTableFlags_RowBg | ImGuiTableFlags_BordersInnerH)) {
        ImGui::TableSetupColumn("位置", ImGuiTableColumnFlags_WidthFixed, 60*scale);
        ImGui::TableSetupColumn("玩家", ImGuiTableColumnFlags_WidthStretch);
        ImGui::TableSetupColumn("延迟", ImGuiTableColumnFlags_WidthFixed, 58*scale);
        ImGui::TableSetupColumn("准备状态", ImGuiTableColumnFlags_WidthFixed, 60*scale);
        ImGui::TableSetupColumn("操作", ImGuiTableColumnFlags_WidthFixed, 48*scale);
        ImGui::TableHeadersRow();
        for (const auto& seat : room["seats"].array) {
            int n = seat["seat"].integer();
            if ((n-1)/4 != group) continue;
            ImGui::PushID(n); ImGui::TableNextRow(); ImGui::TableNextColumn();
            ImGui::Text("%dP%s", n, n == me ? "（你）" : "");
            ImGui::TableNextColumn();
            if (seat["name"].str().empty()) {
                ImGui::BeginDisabled(busy() || locked);
                if (ImGui::Button(("坐到 " + std::to_string(n) + "P").c_str())) send("seat", ",\"seat\":" + std::to_string(n));
                ImGui::EndDisabled();
            } else {
                ImGui::TextUnformatted(seat["name"].str().c_str());
                if (!seat["version"].str().empty()) ImGui::SetItemTooltip("版本：%s", seat["version"].str().c_str());
            }
            ImGui::TableNextColumn();
            int ping = seat["ping"].integer(-1);
            if (!seat["name"].str().empty() && ping >= 0) ImGui::Text("%d ms", ping);
            else ImGui::TextDisabled("—");
            if (ImGui::IsItemHovered()) ImGui::SetTooltip("该玩家到当前服务器的 UDP 往返延迟，与 Dolphin 玩家列表的含义一致。不是双方之间的总延迟。");
            ImGui::TableNextColumn();
            ImGui::TextColored(seat["ready"].yes() ? ImVec4(0.4f, 0.95f, 0.6f, 1) : ImVec4(0.7f, 0.7f, 0.7f, 1), "%s", seat["name"].str().empty() ? "—" : n > 2 ? "观战" : seat["ready"].yes() ? "已准备" : "未准备");
            ImGui::TableNextColumn();
            if (n != me && me && !seat["name"].str().empty()) {
                ImGui::BeginDisabled(busy() || locked || SDL_GetTicks() < swapUntil);
                if (ImGui::Button("换座")) send("swap", ",\"seat\":" + std::to_string(n));
                ImGui::EndDisabled();
            }
            ImGui::PopID();
        }
        ImGui::EndTable();
        }
        ImGui::PopID();
      }
      ImGui::EndTable();
    }
    const auto& rules = room["rules"];
    static const char *battles[] = {"单人", "组队", "10 DP", "15 DP", "20 DP"};
    static const char *times[] = {"60 秒", "90 秒", "180 秒", "240 秒", "不限时"};
    ImGui::Text("规则：%s · %s · 速度 %d%% · 回滚 %d 帧", battles[std::clamp(rules["battle"].integer(), 0, 4)],
        times[std::clamp(rules["time"].integer(), 0, 4)], rules["speed"].integer(100), rules["rollback"].integer(8));
    if (rules["delay"].integer(-2) == -2) ImGui::TextDisabled("输入延迟：自动");
    else ImGui::TextDisabled("输入延迟：%d 帧", rules["delay"].integer());
    bool full = room["view"].str("full") == "full";
    int present = 0;
    for (const auto& s : room["seats"].array) if (s["seat"].integer() <= 2 && !s["name"].str().empty()) ++present;
    bool colored = present == 2;
    ImVec4 color = room["mode_match"].yes() ? ImVec4(0.15f,0.6f,0.25f,1) : ImVec4(0.7f,0.15f,0.15f,1);
    ImGui::TextUnformatted("联机模式："); ImGui::SameLine();
    if (colored) {
        ImGui::PushStyleColor(ImGuiCol_Button, color);
        ImGui::PushStyleColor(ImGuiCol_ButtonHovered, color);
        ImGui::PushStyleColor(ImGuiCol_ButtonActive, color);
    }
    ImGui::BeginDisabled(busy() || locked || !me);
    if (ImGui::Button(full ? "全屏##online_view" : "分屏##online_view", ImVec2(110*scale,0)))
        send("mode", std::string(",\"view\":") + Quote(full ? "split" : "full"));
    ImGui::EndDisabled();
    if (colored) ImGui::PopStyleColor(3);
    ImGui::SameLine();
    if (present < 2) ImGui::TextDisabled("等待另一位玩家就位");
    else ImGui::TextColored(room["mode_match"].yes() ? ImVec4(.4f,.95f,.6f,1) : ImVec4(1,.4f,.4f,1), "%s", room["mode_match"].yes() ? "双方模式一致" : "双方模式不一致");
    ImGui::TextUnformatted("主视窗："); ImGui::SameLine();
    ImGui::BeginDisabled(full);
    if (!full) ImGui::PushStyleColor(ImGuiCol_Button, ImVec4(0.15f,0.6f,0.25f,1));
    if (ImGui::Button(primarySide ? "2P（右侧）##primary_view" : "1P（左侧）##primary_view", ImVec2(150*scale,0))) {
        primarySide ^= 1;
        Port_SettingSave("online_primary_side", primarySide);
        Port_SettingsWrite();
    }
    if (!full) ImGui::PopStyleColor();
    ImGui::EndDisabled();
    ImGui::SetItemTooltip("分屏时将自己操作的角色放在左侧或右侧，仅影响本机；观众选择 1P 或 2P 的视窗顺序。");
    bool firstView = true;
    for (const auto& s : room["seats"].array) if (s["seat"].integer() <= 2 && !s["name"].str().empty()) {
        if (!firstView) ImGui::SameLine();
        ImGui::TextDisabled("%dP：%s", s["seat"].integer(), s["view"].str() == "split" ? "分屏" : "全屏");
        firstView = false;
    }
    std::string notice = versionNotice(room);
    if (!notice.empty()) {
        ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1,.3f,.3f,1));
        ImGui::TextWrapped("%s", notice.c_str());
        ImGui::PopStyleColor();
    }
    ImGui::BeginDisabled(busy() || locked || me < 1 || me > 2 || !room["can_start"].yes());
    if (ImGui::Button("开始", ImVec2(150*scale, 0))) {
        error.clear(); session.clear();
        send("start", ",\"epoch\":" + Quote(room["epoch"].str()));
    }
    ImGui::EndDisabled(); ImGui::SameLine();
    ImGui::BeginDisabled(busy() || locked || !me);
    if (ImGui::Button("离开座位")) send("seat", ",\"seat\":0");
    ImGui::EndDisabled(); ImGui::SameLine();
    if (ImGui::Button(connecting ? "取消连接并退出" : "退出房间")) Close();
    ImGui::SameLine();
    bool allowPause = room["allow_pause"].integer(1) != 0;
    ImVec4 pauseColor = allowPause ? ImVec4(.15f,.6f,.25f,1) : ImVec4(.7f,.15f,.15f,1);
    ImGui::TextUnformatted("允许暂停："); ImGui::SameLine();
    ImGui::PushStyleColor(ImGuiCol_Button, pauseColor);
    ImGui::PushStyleColor(ImGuiCol_ButtonHovered, pauseColor);
    ImGui::PushStyleColor(ImGuiCol_ButtonActive, pauseColor);
    ImGui::BeginDisabled(busy() || locked || me < 1 || me > 2 || room["allow_pause"].kind == Value::Null);
    if (ImGui::Button(allowPause ? "是##allow_pause" : "否##allow_pause", ImVec2(64*scale,0)))
        send("pause", std::string(",\"allow\":") + (allowPause ? "0" : "1"));
    ImGui::EndDisabled(); ImGui::PopStyleColor(3);
    ImGui::SetItemTooltip("双方共用的房间选项，开始后锁定。是：原游戏暂停菜单会同时暂停双方；否：保持原联机行为。");
    if (room["allow_pause"].kind == Value::Null) ImGui::TextDisabled("请先升级服务器到 0.14，以启用同步暂停。");
    if (connecting) ImGui::TextUnformatted("正在连接双方，随后进入选人…");
    else if (room["phase"].str() == "starting") ImGui::TextUnformatted("正在检查战斗数据并建立本次对战…");
    else if (room["phase"].str() == "playing") ImGui::TextWrapped("等待双方结束本次对战并返回房间，然后可再次开始。");
    else ImGui::TextDisabled("进房自动准备。1P、2P 就位且模式一致后，任一对战玩家点击开始。3P–8P 为观战位置。");
}

void Open() { forceFocus = true; }

void Close() {
    if (!loaded || launched) return;
    queuedOp.clear(); queuedFields.clear();
    if (connecting) { Port_LobbyCancel(); connecting = false; }
    closing = true; pending.clear(); nextPoll = 0;
}
bool FocusTab() { bool value = forceFocus; forceFocus = false; return value; }
bool Connecting() { return connecting || launched || !token.empty() || closing || relayChanged; }
} // namespace OnlineLobby

extern "C" int Port_OnlineSplitView(void) { return OnlineLobby::splitView ? 1 : 0; }
// The view order is local presentation only: never sent as a rule or an input.
extern "C" int Port_OnlineSplitSwap(void) {
    return OnlineLobby::splitView ? ((Port_NetSpectating() ? 0 : Port_NetMe()) ^ OnlineLobby::primarySide) : 0;
}

/* This immutable session option is shared before either client starts.
   START and all menu inputs still travel through the existing input/rollback path. */
extern "C" int Port_OnlinePauseAllowed(void) {
    return OnlineLobby::launched && OnlineLobby::matchPause;
}
