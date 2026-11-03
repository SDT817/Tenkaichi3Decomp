// Exercise the real ImGui editor, including the clipped input list and cursor insertion.
#include "../../port/src/gs/control_editor.cpp"
#include "imgui_internal.h"
#include <cassert>
#include <cmath>
#include <cstdlib>
#include <iostream>
extern "C" {
int gPortInputCapture;
static int slot = -1;
int *PortInput_PadSlot(int) { return &slot; }
void PortInput_StickView(int, PortStickView *v) { memset(v, 0, sizeof(*v)); memset(v->bytes, 128, sizeof(v->bytes)); }
void PortInput_Swallow(void) {}
void PortInput_SwallowKeys(void) {}
}
void frame() {
    ImGui::NewFrame();
    ImGui::SetNextWindowPos(ImVec2(0, 0)); ImGui::SetNextWindowSize(ImVec2(1120, 760));
    ImGui::Begin("host"); PortWii_DrawEditor(); ImGui::End(); ImGui::Render();
}
int main() {
    SDL_Init(SDL_INIT_GAMEPAD);
    int keys[PORT_ACTIONS] = {}, pads[PORT_PAD_BUTTONS];
    for (int &p : pads) p = -1;
    PortWii_Init(0, keys, pads);
    ImGui::CreateContext(); auto &io = ImGui::GetIO();
    io.IniFilename = nullptr; io.DisplaySize = ImVec2(1280, 900); io.DeltaTime = 1.0f / 60;
    unsigned char *pixels; int width, height;
    io.Fonts->GetTexDataAsRGBA32(&pixels, &width, &height);
    context(0, 1, 7); sOpen = true; sDetect = true; sDevice = 0; sArm = SDL_GetTicks() - 1;
    SDL_Event mouse = {}; mouse.type = SDL_EVENT_MOUSE_MOTION; mouse.motion.xrel = -12;
    PortWii_Event(&mouse); assert(sSelected == SDL_SCANCODE_COUNT + 5 && !sDetect);
    sOpen = false;
    context(0, 1, 7); assert(sSelected == -1);
    append(" | "); assert(!*sText);
    sOpening = true; frame(); frame();
    selected(0, "Z"); assert(sSelected == SDL_SCANCODE_Z);
    frame(); frame();
    ImGuiWindow *list = nullptr;
    for (ImGuiWindow *window : GImGui->Windows) if (window->ParentWindow && window->Size.y == 220) list = window;
    assert(list && list->Scroll.y > 200 && !sScroll);
    // A late keyboard input is selected and actually visible after the clipper's forced inclusion.
    int row = 0;
    for (int i = 0; i < sSelected; i++) if (*PortWii_InputName(0, i)) row++;
    float item_y = row * ImGui::GetTextLineHeightWithSpacing();
    assert(item_y >= list->Scroll.y && item_y < list->Scroll.y + list->InnerRect.GetHeight());
    append(""); assert(!strcmp(sText, "Z")); frame(); frame();
    // Switch device and combine keyboard with controller in one saved expression.
    selected(1, "A"); append(" & "); assert(!strcmp(sText, "Z & `Controller:A`"));
    frame(); frame(); assert(apply());
    char text[PORT_WII_EXPR_SIZE]; PortWii_Get(0, 1, 7, text, sizeof(text), nullptr);
    assert(!strcmp(text, sText));
    // Insert at the saved caret / replace selected text, rather than appending at the end.
    sCursor = sStart = sEnd = 1; selected(0, "F"); append(" | ");
    assert(!strcmp(sText, "Z | F & `Controller:A`")); frame(); frame();
    sStart = 4; sEnd = 5; selected(0, "G"); append("");
    assert(!strcmp(sText, "Z | G & `Controller:A`")); frame(); frame();
    // stb_textedit leaves the empty selection anchor behind when typing. The
    // caret, rather than that empty selection, is the insertion point.
    context(0, 1, 7); snprintf(sText, sizeof(sText), "W"); sOpen = true;
    sFocus = true; sReplacement = sText; sCursor = sStart = sEnd = (int)strlen(sText); frame(); frame();
    io.AddInputCharactersUTF8(" &!"); frame(); frame();
    assert(!strcmp(sText, "W &!"));
    assert(sCursor == 4 && sStart == sEnd && sStart < sCursor);
    selected(0, "Z"); append("");
    assert(!strcmp(sText, "W &!Z"));
    frame(); frame();
    io.AddInputCharactersUTF8(" &!"); frame(); frame();
    assert(!strcmp(sText, "W &!Z &!"));
    assert(sCursor == 8 && sStart == sEnd && sStart < sCursor);
    selected(0, "Z"); append("");
    assert(!strcmp(sText, "W &!Z &!Z")); frame(); frame();
    selected(0, "F24"); frame(); frame(); assert(list->Scroll.y > 500);
    // The key that is also Dolphin's quoting delimiter must use a safe name,
    // both when selected in the list and when detected from SDL events.
    context(0, 1, 14); sOpen = true; selected(0, PortWii_InputName(0, SDL_SCANCODE_GRAVE));
    append(""); assert(!strcmp(sText, "GRAVE")); assert(apply());
    sDetect = true; sArm = SDL_GetTicks() - 1;
    SDL_Event grave = {}; grave.type = SDL_EVENT_KEY_DOWN; grave.key.scancode = SDL_SCANCODE_GRAVE;
    PortWii_Event(&grave); assert(!sDetect && sSelected == SDL_SCANCODE_GRAVE);
    sOpen = false; sDetect = true; sArm = SDL_GetTicks() - 1; PortWii_Event(&grave);
    PortWii_Get(0, 1, 14, text, sizeof(text), nullptr); assert(!strcmp(text, "GRAVE"));
    PortWii_Cancel(); ImGui::DestroyContext(); SDL_Quit();
    std::cout << "PASS: mouse-axis detection, real ImGui default empty selection, no-op insertion, Z/F24 detection visibility, clipping, mixed-device expressions, caret insertion and selection replacement\n";
}
