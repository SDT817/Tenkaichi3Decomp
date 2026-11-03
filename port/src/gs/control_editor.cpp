// Dolphin 10912 IOWindow / MappingCommon interaction, adapted to SDL and ImGui.
// Dolphin Emulator Project (2017), GPLv2+; see third_party/dolphin.
#include "control_bindings.h"
#include "ui.h"
#include "imgui.h"
#include <algorithm>
#include <cstdio>
#include <cstring>
#include <string>
#include <vector>
namespace {
int sPlayer, sSplit, sAction, sDevice, sSelected = -1;
bool sOpen, sOpening, sDetect, sError, sScroll, sFocus;
Uint64 sUntil, sArm;
char sText[PORT_WII_EXPR_SIZE], sFilter[96];
int sRange = 100, sCursor, sStart, sEnd;
std::string sReplacement;
const char *kPopup = "设置输入逻辑##wii_expression";
void cancel_detect() { sDetect = false; gPortInputCapture = sOpen; }
void context(int p, int split, int a) {
    sPlayer = p; sSplit = split; sAction = a; sDevice = 0;
    sSelected = -1; sFilter[0] = 0; sError = sScroll = sFocus = false;
    PortWii_Get(p, split, a, sText, sizeof(sText), &sRange);
    sCursor = sStart = sEnd = (int)strlen(sText);
}
void detect() {
    sDetect = true; sUntil = SDL_GetTicks() + 5000; sArm = SDL_GetTicks() + 150;
    gPortInputCapture = 1;
}
SDL_Gamepad *pad() {
    int count;
    SDL_JoystickID *ids = SDL_GetGamepads(&count);
    int slot = *PortInput_PadSlot(sPlayer);
    SDL_Gamepad *g = slot >= 0 && slot < count ? SDL_GetGamepadFromID(ids[slot]) : nullptr;
    SDL_free(ids); return g;
}
// MappingCommon::GetExpressionForControl: qualify non-default devices; quote
// names unless they consist entirely of ASCII letters.
std::string token(const char *name) {
    std::string value = std::string(sDevice ? "Controller:" : "") + name;
    return value.find_first_not_of("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ") == std::string::npos ? value : "`" + value + "`";
}
void selected(int device, const char *name) {
    if (!name || !*name) { return; }
    sDevice = device;
    if (sOpen) {
        sSelected = -1;
        for (int i = 0; i < PortWii_InputCount(sDevice); i++) {
            if (!strcmp(name, PortWii_InputName(sDevice, i))) { sSelected = i; break; }
        }
        sFilter[0] = 0; sScroll = true;
    } else {
        std::string expr = token(name);
        PortWii_Set(sPlayer, sSplit, sAction, expr.c_str(), 100); PortWii_Save();
        PortInput_Swallow(); PortInput_SwallowKeys();
    }
    cancel_detect();
}
bool apply() {
    if (!PortWii_Set(sPlayer, sSplit, sAction, sText, sRange)) { sError = true; return false; }
    PortWii_Save(); sError = false; return true;
}
void append(const char *prefix) {
    if (sSelected < 0) { return; } // Dolphin: no currentItem means no insertion.
    std::string value = sText, insert = std::string(prefix) + token(PortWii_InputName(sDevice, sSelected));
    int start = std::clamp(sStart == sEnd ? sCursor : std::min(sStart, sEnd), 0, (int)value.size());
    int end = std::clamp(sStart == sEnd ? sCursor : std::max(sStart, sEnd), start, (int)value.size());
    value.replace(start, end - start, insert);
    if (value.size() < sizeof(sText)) {
        snprintf(sText, sizeof(sText), "%s", value.c_str());
        sReplacement = value;
        sCursor = sStart = sEnd = start + (int)insert.size(); sFocus = true;
    }
}
int cursor(ImGuiInputTextCallbackData *data) {
    if (sFocus) {
        data->DeleteChars(0, data->BufTextLen);
        data->InsertChars(0, sReplacement.c_str());
        data->CursorPos = sCursor; data->SelectionStart = data->SelectionEnd = sCursor; sFocus = false;
    }
    sCursor = data->CursorPos; sStart = data->SelectionStart; sEnd = data->SelectionEnd; return 0;
}
}
extern "C" void PortWii_Cancel(void) { sOpen = sOpening = sDetect = false; gPortInputCapture = 0; }
extern "C" void PortWii_BindingButton(int p, int split, int action, float value) {
    char text[PORT_WII_EXPR_SIZE], label[PORT_WII_EXPR_SIZE + 40];
    PortWii_Get(p, split, action, text, sizeof(text), nullptr);
    bool waiting = sDetect && !sOpen && sPlayer == p && sSplit == split && sAction == action;
    if (value > 0.5f) {
        ImGui::PushStyleColor(ImGuiCol_Button, ImVec4(0.14f, 0.52f, 0.30f, 1));
        ImGui::PushStyleColor(ImGuiCol_ButtonHovered, ImVec4(0.20f, 0.65f, 0.38f, 1));
        ImGui::PushStyleColor(ImGuiCol_ButtonActive, ImVec4(0.12f, 0.46f, 0.25f, 1));
    }
    snprintf(label, sizeof(label), "%s##wii%d", waiting ? "请按键…" : *text ? text : "未设置", action);
    if (ImGui::Button(label, ImVec2(-FLT_MIN, 0))) { context(p, split, action); detect(); }
    if (value > 0.5f) { ImGui::PopStyleColor(3); }
    if (ImGui::IsItemClicked(ImGuiMouseButton_Right)) { context(p, split, action); sOpening = true; }
    if (ImGui::IsItemClicked(ImGuiMouseButton_Middle)) { PortWii_Set(p, split, action, "", 100); PortWii_Save(); }
    ImGui::SetItemTooltip("左键：检测键盘、鼠标或手柄；中键：清除；右键：设置逻辑表达式。\n输入 %.0f%%（超过 50%% 时触发）\n%s", value * 100, *text ? text : "未设置");
    if (value > 0) {
        ImVec2 at = ImGui::GetItemRectMin(), end = ImGui::GetItemRectMax();
        ImGui::GetWindowDrawList()->AddRectFilled(ImVec2(at.x, end.y - 2), ImVec2(at.x + (end.x - at.x) * value, end.y), ImGui::GetColorU32(ImVec4(0.35f, 0.95f, 0.55f, 1)));
    }
}
extern "C" int PortWii_Event(const SDL_Event *ev) {
    if (!sDetect) { return 0; }
    if (ev->type == SDL_EVENT_KEY_DOWN && !ev->key.repeat) {
        if (ev->key.scancode == SDL_SCANCODE_ESCAPE) { cancel_detect(); return 1; }
        if (!sOpen && ev->key.scancode == SDL_SCANCODE_DELETE) { PortWii_Set(sPlayer, sSplit, sAction, "", 100); PortWii_Save(); cancel_detect(); return 1; }
        if ((!sOpen || sDevice == 0) && SDL_GetTicks() >= sArm) { selected(0, PortWii_InputName(0, ev->key.scancode)); }
        return 1;
    }
    if ((!sOpen || sDevice == 0) && SDL_GetTicks() >= sArm) {
        if (ev->type == SDL_EVENT_MOUSE_MOTION) {
            if (abs(ev->motion.xrel) > 8) { selected(0, PortWii_InputName(0, SDL_SCANCODE_COUNT + 5 + (ev->motion.xrel > 0))); }
            else if (abs(ev->motion.yrel) > 8) { selected(0, PortWii_InputName(0, SDL_SCANCODE_COUNT + 7 + (ev->motion.yrel > 0))); }
        }
        if (ev->type == SDL_EVENT_MOUSE_BUTTON_DOWN) {
            const int buttons[] = {SDL_BUTTON_LEFT, SDL_BUTTON_RIGHT, SDL_BUTTON_MIDDLE, SDL_BUTTON_X1, SDL_BUTTON_X2};
            for (int i = 0; i < 5; i++) if (ev->button.button == buttons[i]) { selected(0, PortWii_InputName(0, SDL_SCANCODE_COUNT + i)); break; }
        }
        if (ev->type == SDL_EVENT_MOUSE_WHEEL) {
            float sign = ev->wheel.direction == SDL_MOUSEWHEEL_FLIPPED ? -1.0f : 1.0f;
            if (ev->wheel.y) { selected(0, PortWii_InputName(0, SDL_SCANCODE_COUNT + 11 + (ev->wheel.y * sign > 0))); }
            else if (ev->wheel.x) { selected(0, PortWii_InputName(0, SDL_SCANCODE_COUNT + 9 + (ev->wheel.x * sign > 0))); }
        }
    }
    if ((!sOpen || sDevice == 1) && SDL_GetTicks() >= sArm) {
        SDL_Gamepad *g = pad(); SDL_JoystickID id = g ? SDL_GetGamepadID(g) : 0;
        if (ev->type == SDL_EVENT_GAMEPAD_BUTTON_DOWN && ev->gbutton.which == id && ev->gbutton.button < 21) { selected(1, PortWii_InputName(1, ev->gbutton.button)); return 1; }
        if (ev->type == SDL_EVENT_GAMEPAD_AXIS_MOTION && ev->gaxis.which == id) {
            int axis = ev->gaxis.axis, value = ev->gaxis.value;
            if (axis < 4 && (value > 16384 || value < -16384)) { selected(1, PortWii_InputName(1, 21 + axis * 2 + (value > 0))); return 1; }
            if (axis >= 4 && axis < 6 && value > 16384) { selected(1, PortWii_InputName(1, 29 + axis - 4)); return 1; }
        }
    }
    return ev->type == SDL_EVENT_KEY_UP || ev->type == SDL_EVENT_TEXT_INPUT || ev->type == SDL_EVENT_KEY_DOWN || ev->type == SDL_EVENT_GAMEPAD_BUTTON_DOWN ||
           ev->type == SDL_EVENT_GAMEPAD_BUTTON_UP || ev->type == SDL_EVENT_GAMEPAD_AXIS_MOTION || ev->type == SDL_EVENT_MOUSE_BUTTON_DOWN ||
           ev->type == SDL_EVENT_MOUSE_BUTTON_UP || ev->type == SDL_EVENT_MOUSE_WHEEL;
}
extern "C" void PortWii_DrawEditor(void) {
    if (sDetect && SDL_GetTicks() > sUntil) { cancel_detect(); }
    if (sOpening) { sOpening = false; sOpen = true; gPortInputCapture = 1; ImGui::OpenPopup(kPopup); }
    ImVec2 display = ImGui::GetIO().DisplaySize;
    ImGui::SetNextWindowSize(ImVec2(std::min(display.x - 24, 680.0f), std::min(display.y - 24, 740.0f)), ImGuiCond_Appearing);
    if (ImGui::BeginPopupModal(kPopup, nullptr, ImGuiWindowFlags_NoSavedSettings)) {
        ImGui::Text("玩家 %d · %s · 键鼠 / 手柄共用表达式", sPlayer + 1, PortWii_ActionLabel(sSplit, sAction));
        const char *devices[] = {"键盘 / 鼠标", "当前玩家的手柄"};
        if (ImGui::Combo("输入设备", &sDevice, devices, 2)) { sSelected = -1; sFilter[0] = 0; cancel_detect(); }
        ImGui::SliderInt("范围（%）", &sRange, -500, 500);
        ImGui::InputText("搜索按键", sFilter, sizeof(sFilter));
        if (ImGui::BeginTable("expression_inputs", 2, ImGuiTableFlags_SizingStretchProp)) {
            ImGui::TableSetupColumn("inputs", ImGuiTableColumnFlags_WidthStretch, 4);
            ImGui::TableSetupColumn("operators", ImGuiTableColumnFlags_WidthStretch, 1);
            ImGui::TableNextColumn();
            if (ImGui::BeginListBox("##inputs", ImVec2(-1, 220))) {
                std::vector<int> inputs; int target = -1;
                for (int i = 0; i < PortWii_InputCount(sDevice); i++) {
                    const char *name = PortWii_InputName(sDevice, i);
                    if (!*name || (*sFilter && !strstr(name, sFilter))) { continue; }
                    if (i == sSelected) { target = (int)inputs.size(); }
                    inputs.push_back(i);
                }
                ImGuiListClipper clipper; clipper.Begin((int)inputs.size());
                if (sScroll && target >= 0) { clipper.IncludeItemByIndex(target); }
                while (clipper.Step()) for (int row = clipper.DisplayStart; row < clipper.DisplayEnd; row++) {
                    int i = inputs[row];
                    if (ImGui::Selectable(PortWii_InputName(sDevice, i), i == sSelected)) { sSelected = i; }
                    if (sScroll && row == target) { ImGui::SetScrollHereY(0.5f); sScroll = false; }
                }
                ImGui::EndListBox();
            }
            ImGui::TableNextColumn(); ImGui::BeginDisabled(sSelected < 0);
            if (ImGui::Button("选择", ImVec2(-1, 0))) { append(""); }
            ImGui::EndDisabled();
            if (ImGui::Button(sDetect ? "请按键…" : "检测", ImVec2(-1, 0))) { detect(); }
            const char *labels[] = {"| 或", "& 与", "+ 加", "! 非"}, *prefix[] = {" | ", " & ", " + ", "!"};
            ImGui::BeginDisabled(sSelected < 0);
            for (int i = 0; i < 4; i++) if (ImGui::Button(labels[i], ImVec2(-1, 0))) { append(prefix[i]); }
            ImGui::EndDisabled(); ImGui::EndTable();
        }
        ImGui::TextWrapped("| 任一键；& 同时按；+ 相加（最多 1）；! 取反。二元运算从左向右，可用括号分组。键鼠与手柄可混用，逻辑插入光标处。");
        if (sFocus) { ImGui::SetKeyboardFocusHere(); }
        ImGui::InputTextMultiline("##expression", sText, sizeof(sText), ImVec2(-1, std::max(70.0f, ImGui::GetContentRegionAvail().y - 100)), ImGuiInputTextFlags_CallbackAlways, cursor);
        float value = PortWii_Preview(sPlayer, sText, sRange);
        char progress[64]; snprintf(progress, sizeof(progress), "当前输入 %.0f%% · %s", value * 100, value > 0.5f ? "已触发" : "未触发");
        ImGui::ProgressBar(value, ImVec2(-1, 0), progress);
        if (sError) { ImGui::TextColored(ImVec4(1, 0.4f, 0.3f, 1), "表达式无效，请检查运算符、反引号和括号。"); }
        if (ImGui::Button("确定", ImVec2(95, 0)) && apply()) { PortWii_Cancel(); PortInput_Swallow(); PortInput_SwallowKeys(); ImGui::CloseCurrentPopup(); }
        ImGui::SameLine();
        if (ImGui::Button("清除", ImVec2(95, 0))) { sText[0] = 0; sCursor = sStart = sEnd = 0; }
        ImGui::SameLine(); if (ImGui::Button("应用", ImVec2(95, 0))) { apply(); }
        ImGui::SameLine();
        if (ImGui::Button("取消", ImVec2(95, 0)) || ImGui::IsKeyPressed(ImGuiKey_Escape, false)) { PortWii_Cancel(); PortInput_Swallow(); PortInput_SwallowKeys(); ImGui::CloseCurrentPopup(); }
        ImGui::EndPopup();
    }
}
