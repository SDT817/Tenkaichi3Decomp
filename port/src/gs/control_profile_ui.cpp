// Dolphin MappingWindow's editable preset selector, load/save/delete, in ImGui.
#include "control_profiles.h"
#include "ui.h"
#include "imgui.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <memory>
#include <mutex>

extern "C" SDL_Window *GsDraw_Window(void);
namespace WiiProfiles {
namespace {
char sName[2][128] = {};
std::vector<Entry> sEntries, sDolphin;
std::vector<char> sCode(MAX_CODE + 1);
std::string sMessage;
bool sError, sReady, sShare;
int sPopup, sOwner = -1;
unsigned sEpoch;
struct Request { int player; unsigned epoch; };
std::mutex sDialogLock;
std::string sDialogPath, sDialogError;
Request sResult = {-1, 0};
bool sDialogDone, sDialogBusy;

void message(bool ok, const std::string& text) { sError = !ok; sMessage = text; }
void refresh() { sEntries = List(); sReady = true; }
void name(int player, const std::string& value) { snprintf(sName[player], sizeof(sName[player]), "%s", value.c_str()); }
void loaded(int player, const Profile& p) {
    std::string error;
    bool ok = Apply(player, p, error);
    message(ok, ok ? "已读取 Wii 预设。" : error);
}
void import_file(int player, const std::string& path, bool from_dolphin) {
    Profile p;
    std::string error;
    if (!Read(path, p, error)) { message(false, error); return; }
    auto slash = path.find_last_of("/\\");
    std::string title = path.substr(slash == std::string::npos ? 0 : slash + 1);
    auto dot = title.find_last_of('.');
    if (dot != std::string::npos) { title.resize(dot); }
    if (from_dolphin) { title = "Dolphin - " + title; }
    if (!Save(title, p, error)) { message(false, error); return; }
    name(player, title); refresh(); loaded(player, p);
    if (!sError) {
        sMessage = "已导入并读取；预设已保存到列表。";
        if (!p.skipped.empty()) {
            sMessage += "\n以下动作含不支持的按键，已留空，请手动设置：";
            for (const std::string& item : p.skipped) { sMessage += "\n" + item; }
        }
    }
}
void SDLCALL selected(void *userdata, const char *const *files, int) {
    std::unique_ptr<Request> request((Request *)userdata);
    std::lock_guard<std::mutex> lock(sDialogLock);
    sResult = *request;
    sDialogPath = files && files[0] ? files[0] : "";
    sDialogError = files ? "" : SDL_GetError();
    sDialogDone = true; sDialogBusy = false;
}
void manual(int player) {
    static const SDL_DialogFileFilter filters[] = {{"Dolphin / BT3 Wii profiles", "ini"}, {"All files", "*"}};
    {
        std::lock_guard<std::mutex> lock(sDialogLock);
        if (sDialogBusy) { return; }
        sDialogBusy = true;
    }
    SDL_ShowOpenFileDialog(selected, new Request{player, sEpoch}, GsDraw_Window(), filters, 2, nullptr, false);
}
void finish_dialog(int player) {
    std::string path, error;
    {
        std::lock_guard<std::mutex> lock(sDialogLock);
        if (!sDialogDone) { return; }
        sDialogDone = false;
        if (sResult.epoch != sEpoch || sResult.player != player) { return; }
        path = sDialogPath; error = sDialogError;
    }
    if (!error.empty()) { message(false, "打开文件选择器失败：" + error); }
    else if (!path.empty()) { import_file(player, path, false); }
}
void code_popup(int player, float scale) {
    const char *popup = "分享码##wii_profile_code";
    if (sPopup == 1) {
        sPopup = 0;
        sMessage.clear();
        if (sShare) {
            std::string code = Encode(Capture(player));
            snprintf(sCode.data(), sCode.size(), "%s", code.c_str());
        } else { sCode[0] = 0; }
        ImGui::OpenPopup(popup);
    }
    ImVec2 display = ImGui::GetIO().DisplaySize;
    ImGui::SetNextWindowSize(ImVec2(std::min(660 * scale, display.x * 0.94f), 0), ImGuiCond_Always);
    if (ImGui::BeginPopupModal(popup, nullptr, ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoSavedSettings)) {
        ImGui::TextWrapped(sShare ? "复制当前玩家的 Wii 配置分享给其他改版玩家。包括逻辑按键、控制分离、死区和震动设置。" :
                                   "粘贴其他改版玩家的完整分享码。导入使用当前的控制分离设置，只替换当前玩家正在使用的 Wii 配置。");
        if (!sShare && ImGui::Button("从剪贴板粘贴")) {
            char *text = SDL_GetClipboardText();
            if (text) {
                if (strlen(text) < sCode.size()) { snprintf(sCode.data(), sCode.size(), "%s", text); }
                else { message(false, "剪贴板中的分享码过长。"); }
                SDL_free(text);
            }
        }
        ImGui::InputTextMultiline("##code", sCode.data(), sCode.size(), ImVec2(-1, 160 * scale),
                                   sShare ? ImGuiInputTextFlags_ReadOnly : ImGuiInputTextFlags_None);
        if (sShare) {
            if (ImGui::Button("复制分享码")) {
                bool ok = SDL_SetClipboardText(sCode.data());
                message(ok, ok ? "分享码已复制。" : SDL_GetError());
            }
        } else if (ImGui::Button("导入")) {
            Profile p; std::string error;
            if (Decode(sCode.data(), p, error)) {
                loaded(player, p);
                if (!sError) { name(player, "分享的预设"); sMessage = "分享码已导入。可在预设栏命名并保存。"; ImGui::CloseCurrentPopup(); }
            } else { message(false, error); }
        }
        ImGui::SameLine();
        if (ImGui::Button("关闭") || ImGui::IsKeyPressed(ImGuiKey_Escape, false)) { ImGui::CloseCurrentPopup(); }
        if (!sMessage.empty()) { ImGui::TextWrapped("%s", sMessage.c_str()); }
        ImGui::EndPopup();
    }
}
}
void Cancel() {
    ++sEpoch; sOwner = -1; sPopup = 0;
}
void Draw(int player, float scale) {
    if (!sReady) { refresh(); }
    if (sOwner != player) { ++sEpoch; sOwner = player; sMessage.clear(); }
    finish_dialog(player);
    float width = 430 * scale;
    float right = ImGui::GetWindowPos().x + ImGui::GetWindowSize().x - ImGui::GetStyle().WindowPadding.x;
    if (right - ImGui::GetItemRectMax().x > width + 12 * scale) { ImGui::SameLine(0, 18 * scale); }
    ImGui::PushID("wii_profiles");
    ImGui::AlignTextToFramePadding(); ImGui::TextUnformatted("预设"); ImGui::SameLine();
    ImGui::SetNextItemWidth(130 * scale);
    ImGui::InputText("##name", sName[player], sizeof(sName[player]));
    ImGui::SameLine(0, 2 * scale);
    if (ImGui::ArrowButton("list", ImGuiDir_Down)) { refresh(); ImGui::OpenPopup("list"); }
    if (ImGui::BeginPopup("list")) {
        if (sEntries.empty()) { ImGui::TextDisabled("暂无预设；输入名称后保存。"); }
        for (const Entry& entry : sEntries) {
            if (ImGui::Selectable(entry.name.c_str(), entry.name == sName[player])) {
                Profile p; std::string error;
                if (Read(entry.path, p, error)) { loaded(player, p); if (!sError) { name(player, entry.name); } }
                else { message(false, error); }
            }
        }
        ImGui::EndPopup();
    }
    ImGui::SameLine();
    if (ImGui::Button("保存")) {
        std::string error;
        bool ok = Save(sName[player], Capture(player), error);
        message(ok, ok ? "预设已保存。相同名称会覆盖。" : error); if (ok) { refresh(); }
    }
    ImGui::SameLine();
    if (ImGui::Button("删除")) { ImGui::OpenPopup("删除预设"); }
    if (ImGui::BeginPopupModal("删除预设", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::Text("删除预设“%s”？", sName[player]);
        if (ImGui::Button("删除")) {
            std::string error; bool ok = Delete(sName[player], error);
            message(ok, ok ? "预设已删除，当前按键保持不变。" : error);
            if (ok) { name(player, ""); refresh(); }
            ImGui::CloseCurrentPopup();
        }
        ImGui::SameLine(); if (ImGui::Button("取消")) { ImGui::CloseCurrentPopup(); }
        ImGui::EndPopup();
    }
    ImGui::SameLine();
    if (ImGui::Button("导入 / 分享")) { ImGui::OpenPopup("import_share"); }
    if (ImGui::BeginPopup("import_share")) {
        if (ImGui::MenuItem("从 Dolphin 导入")) {
            sDolphin = List(true);
            if (sDolphin.empty()) { message(false, "AppData 和文档目录中均未找到 Dolphin GCPad 预设，请使用“手动导入”。"); }
            else if (sDolphin.size() == 1) { import_file(player, sDolphin[0].path, true); }
            else { sPopup = 2; }
        }
        if (ImGui::MenuItem("分享码导入")) { sShare = false; sPopup = 1; }
        if (ImGui::MenuItem("手动导入")) { PortWii_Cancel(); manual(player); }
        if (ImGui::MenuItem("分享")) { sShare = true; sPopup = 1; }
        ImGui::EndPopup();
    }
    if (sPopup == 2) { sPopup = 0; ImGui::OpenPopup("Dolphin 预设"); }
    if (ImGui::BeginPopupModal("Dolphin 预设", nullptr, ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::TextUnformatted("选择从 Dolphin GCPad 导入的预设：");
        for (const Entry& entry : sDolphin) {
            ImGui::PushID(entry.path.c_str());
            if (ImGui::Selectable(entry.name.c_str())) { import_file(player, entry.path, true); ImGui::CloseCurrentPopup(); }
            ImGui::SetItemTooltip("%s", entry.path.c_str());
            ImGui::PopID();
        }
        ImGui::TextDisabled("按 GC 布局导入，沿用当前控制分离设置；另一套配置保留。");
        if (ImGui::Button("取消")) { ImGui::CloseCurrentPopup(); }
        ImGui::EndPopup();
    }
    code_popup(player, scale);
    if (!sMessage.empty()) {
        ImGui::PushTextWrapPos();
        ImGui::TextColored(sError ? ImVec4(1, 0.45f, 0.3f, 1) : ImVec4(0.4f, 0.85f, 0.5f, 1), "%s", sMessage.c_str());
        ImGui::PopTextWrapPos();
    }
    ImGui::PopID();
}
}
