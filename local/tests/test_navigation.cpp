#include "../../port/src/gs/ui.cpp"
#include "imgui_internal.h"
#include <cassert>
#include <iostream>
float frame() {
    gamepad_navigation();
    ImGui::NewFrame(); ImGui::SetNextWindowPos(ImVec2(0, 0)); ImGui::SetNextWindowSize(ImVec2(400, 300));
    ImGui::Begin("scrolling"); ImGui::SetWindowFocus();
    for (int i = 0; i < 80; i++) ImGui::Text("row %d", i);
    float scroll = ImGui::GetScrollY();
    ImGui::End(); ImGui::Render(); return scroll;
}
int main() {
    ImGui::CreateContext(); auto &io = ImGui::GetIO();
    io.IniFilename = nullptr; io.DisplaySize = ImVec2(1280, 900); io.DeltaTime = 1.0f / 60;
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad;
    io.BackendFlags |= ImGuiBackendFlags_HasGamepad;
    unsigned char *pixels; int width, height; io.Fonts->GetTexDataAsRGBA32(&pixels, &width, &height);
    sOpen = true; sTab = 4; frame(); frame();
    io.AddKeyAnalogEvent(ImGuiKey_GamepadLStickDown, true, 1);
    io.AddKeyEvent(ImGuiKey_GamepadL1, true); io.AddKeyEvent(ImGuiKey_GamepadFaceRight, true);
    for (int i = 0; i < 30; i++) {
        assert(frame() == 0); assert(!(io.ConfigFlags & ImGuiConfigFlags_NavEnableGamepad));
        assert(!pad_pressed(ImGuiKey_GamepadL1) && !pad_pressed(ImGuiKey_GamepadFaceRight));
    }
    // The same held stick scrolls again once another settings tab is selected.
    sTab = 3; for (int i = 0; i < 30; i++) frame();
    assert(io.ConfigFlags & ImGuiConfigFlags_NavEnableGamepad); assert(frame() > 0);
    sForceTab = 4; gamepad_navigation(); assert(!(io.ConfigFlags & ImGuiConfigFlags_NavEnableGamepad));
    ImGui::DestroyContext(); std::cout << "PASS: real ImGui stick scrolling blocked in Controls, gamepad back/tab shortcuts blocked, other-tab scrolling restored\n";
}
