// Real ImGui selection must apply the preset without a separate read button.
#include "../../port/src/gs/control_profile_ui.cpp"
#include "imgui_internal.h"
#include <cassert>
#include <iostream>
extern "C" void PortWii_Cancel(void) {}
static void frame(bool open = false) {
    ImGui::NewFrame();
    ImGui::SetNextWindowPos(ImVec2(0, 0)); ImGui::SetNextWindowSize(ImVec2(900, 600));
    ImGui::Begin("host"); ImGui::TextUnformatted("control mode");
    if (open) { ImGui::PushID("wii_profiles"); ImGui::OpenPopup("list"); ImGui::PopID(); }
    WiiProfiles::Draw(0, 1);
    ImGui::End(); ImGui::Render();
}
int main() {
    using namespace WiiProfiles;
    assert(SDL_Init(SDL_INIT_GAMEPAD)); PortInput_ControlMode(0);
    ImGui::CreateContext(); auto& io = ImGui::GetIO();
    io.IniFilename = nullptr; io.DisplaySize = ImVec2(1280, 900); io.DeltaTime = 1.0f / 60;
    unsigned char *pixels; int width, height; io.Fonts->GetTexDataAsRGBA32(&pixels, &width, &height);
    Profile p; p.text[6] = "GRAVE"; p.range[6] = 125;
    std::string error; assert(Save("auto-load", p, error));
    *PortInput_ControlSplit(0) = 1;
    assert(PortWii_Set(0, 1, 6, "J", 100));
    frame(); frame(true); frame();
    assert(!GImGui->OpenPopupStack.empty());
    ImGuiWindow *popup = GImGui->OpenPopupStack.back().Window; assert(popup);
    assert(sEntries.size() == 1);
    io.AddMousePosEvent(popup->DC.CursorStartPos.x + 8, popup->DC.CursorStartPos.y + ImGui::GetTextLineHeight() / 2);
    frame(); io.AddMouseButtonEvent(0, true); frame(); io.AddMouseButtonEvent(0, false); frame();
    assert(Capture(0).text[6] == "GRAVE" && Capture(0).range[6] == 125);
    assert(*PortInput_ControlSplit(0) == 1 && !strcmp(sName[0], "auto-load") && !sError);
    // Read and display partial-import diagnostics through the real UI handler.
    const char *fixture = SDL_getenv("BT3_TEST_PARTIAL"); assert(fixture);
    import_file(0, fixture, true);
    assert(!sError && Capture(0).text[6].empty() && Capture(0).text[14] == "`GRAVE`");
    assert(sMessage.find("Buttons/A") != std::string::npos);
    frame();
    ImGui::DestroyContext(); SDL_Quit();
    std::cout << "PASS: real ImGui preset selection applies immediately, current split retained, partial-import warning shown\n";
}
