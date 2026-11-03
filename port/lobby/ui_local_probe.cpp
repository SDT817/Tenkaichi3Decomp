// Render the actual new UI functions without a game, window or GPU.
#include <cassert>
#include <vector>
#include "../src/gs/ui.cpp"
#include "imgui_internal.h"

extern "C" {
volatile int gUiPresentX, gUiPresentY, gUiPresentW, gUiPresentH;
static int savedX=8,savedY=8;
int Port_Setting(const char *name,int def) { return !strcmp(name,"meter_x")?savedX:!strcmp(name,"meter_y")?savedY:def; }
void Port_SettingSave(const char *name,int value) { if(!strcmp(name,"meter_x"))savedX=value; if(!strcmp(name,"meter_y"))savedY=value; }
void Port_SettingsWrite(void) {}
int Port_NetStats(int *) { return 0; }
int Port_LobbyRelayed(void) { return 0; }
}

static void snapshot(const char *path) {
    ImDrawData *draw = ImGui::GetDrawData();
    SDL_Surface *surface = SDL_CreateSurface((int)draw->DisplaySize.x, (int)draw->DisplaySize.y, SDL_PIXELFORMAT_RGBA32);
    assert(surface);
    SDL_Renderer *renderer = SDL_CreateSoftwareRenderer(surface);
    assert(renderer);
    SDL_SetRenderDrawColor(renderer, 28, 31, 41, 255);
    SDL_RenderClear(renderer);
    unsigned char *pixels; int w, h;
    ImGui::GetIO().Fonts->GetTexDataAsRGBA32(&pixels, &w, &h);
    SDL_Surface *atlas = SDL_CreateSurfaceFrom(w, h, SDL_PIXELFORMAT_RGBA32, pixels, w * 4);
    SDL_Texture *texture = SDL_CreateTextureFromSurface(renderer, atlas);
    assert(texture);
    SDL_SetTextureBlendMode(texture, SDL_BLENDMODE_BLEND);
    SDL_SetTextureScaleMode(texture, SDL_SCALEMODE_LINEAR);
    for (const ImDrawList *list : draw->CmdLists) {
        std::vector<SDL_Vertex> vertices;
        for (const ImDrawVert &v : list->VtxBuffer) {
            SDL_FColor c = {(float)((v.col >> IM_COL32_R_SHIFT) & 255) / 255.0f,
                            (float)((v.col >> IM_COL32_G_SHIFT) & 255) / 255.0f,
                            (float)((v.col >> IM_COL32_B_SHIFT) & 255) / 255.0f,
                            (float)((v.col >> IM_COL32_A_SHIFT) & 255) / 255.0f};
            vertices.push_back({{v.pos.x, v.pos.y}, c, {v.uv.x, v.uv.y}});
        }
        for (const ImDrawCmd &cmd : list->CmdBuffer) {
            assert(!cmd.UserCallback);
            SDL_Rect clip = {(int)cmd.ClipRect.x, (int)cmd.ClipRect.y,
                             (int)(cmd.ClipRect.z - cmd.ClipRect.x), (int)(cmd.ClipRect.w - cmd.ClipRect.y)};
            SDL_SetRenderClipRect(renderer, &clip);
            std::vector<int> indices;
            for (unsigned i = 0; i < cmd.ElemCount; i++) indices.push_back(list->IdxBuffer[cmd.IdxOffset + i] + cmd.VtxOffset);
            assert(SDL_RenderGeometry(renderer, texture, vertices.data(), (int)vertices.size(), indices.data(), (int)indices.size()));
        }
    }
    SDL_RenderPresent(renderer);
    assert(SDL_SaveBMP(surface, path));
    SDL_DestroyTexture(texture);
    SDL_DestroySurface(atlas);
    SDL_DestroyRenderer(renderer);
    SDL_DestroySurface(surface);
}

int main(void) {
    SDL_Init(0);
    ImGui::CreateContext();
    ImGuiIO &io = ImGui::GetIO();
    io.IniFilename = nullptr;
    io.DisplaySize = ImVec2(800, 600);
    ImFont *font = io.Fonts->AddFontFromFileTTF("C:/Windows/Fonts/msyh.ttc", 18.0f, nullptr, io.Fonts->GetGlyphRangesChineseFull());
    assert(font);
    sTitleFont=io.Fonts->AddFontFromFileTTF("E:/PS2 yizhi/Lobby/玩家端/fonts/bt3cn-rounded-bold.ttf",48.0f,nullptr,io.Fonts->GetGlyphRangesChineseFull());
    assert(sTitleFont);
    unsigned char *pixels; int w, h;
    io.Fonts->GetTexDataAsRGBA32(&pixels, &w, &h);
    io.Fonts->SetTexID((ImTextureID)1);
    style();
    for (int frame = 0; frame < 3; frame++) {
        io.DeltaTime = 1.0f / 60.0f;
        ImGui::NewFrame();
        ImGui::SetNextWindowPos(ImVec2(40, 40));
        ImGui::SetNextWindowSize(ImVec2(720, 520));
        ImGui::Begin("关于", nullptr, ImGuiWindowFlags_NoCollapse);
        about_tab();
        ImGui::End();
        ImGui::Render();
    }
    snapshot("about-preview.bmp");
    io.DisplaySize=ImVec2(800,600);
    for(int frame=0;frame<8;frame++) {
        io.AddMousePosEvent(frame<4?30.0f:230.0f,frame<4?20.0f:120.0f);
        if(frame==2)io.AddMouseButtonEvent(0,true);
        if(frame==6)io.AddMouseButtonEvent(0,false);
        ImGui::NewFrame();meter_draw();ImGui::Render();
    }
    assert(savedX>100 && savedY>50 && !sMeterDrag);
    sForceTab = 8;
    for (int frame = 0; frame < 3; frame++) {
        ImGui::NewFrame();
        ImGui::SetNextWindowPos(ImVec2(40, 40));
        ImGui::SetNextWindowSize(ImVec2(720, 520));
        ImGui::Begin("设置", nullptr, ImGuiWindowFlags_NoCollapse);
        if (ImGui::BeginTabBar("tabs")) {
            const char *labels[] = {"画面", "特效", "声音", "界面", "控制", "辅助", "其他", "联机"};
            for (int i = 0; i < 8; i++) if (tab(labels[i], i)) { ImGui::EndTabItem(); }
            ImGui::TabItemButton("大厅");
            if (tab("关于", 8)) { about_tab(); ImGui::EndTabItem(); }
            if (frame == 2) {
                const ImGuiTabBar *bar = ImGui::GetCurrentTabBar();
                assert(bar->Tabs.Size == 10 && bar->WidthAllTabsIdeal <= bar->BarRect.GetWidth());
            }
            ImGui::EndTabBar();
        }
        ImGui::End();
        ImGui::Render();
    }
    snapshot("tabs-preview.bmp");
    const char *texts[] = {kFreeNotice, "原作者：z3xox", "项目地址：", "汉化与其它修改：珍妮-玛-爵旺", "QQ联机群：485869029", "感谢 有操作的水 与 皇叔 的赞助与测试！"};
    for (const char *text : texts) {
        while (*text) {
            unsigned c; int bytes = ImTextCharFromUtf8(&c, text, nullptr);
            assert(bytes > 0 && font->GetFontBaked(18.0f)->FindGlyphNoFallback(c));
            text += bytes;
        }
    }
    const int sizes[][4] = {{640,480,640,480}, {1280,720,1280,720}, {1920,1080,1440,1080}, {3440,1440,1920,1440}, {3840,2160,3840,2160}};
    for (const auto &size : sizes) {
        io.DisplaySize = ImVec2((float)size[0], (float)size[1]);
        gUiPresentW = size[2]; gUiPresentH = size[3];
        gUiPresentX = (size[0] - size[2]) / 2; gUiPresentY = (size[1] - size[3]) / 2;
        ImGui::NewFrame();
        title_notice_draw();
        ImDrawList *list = ImGui::GetBackgroundDrawList();
        assert(list->VtxBuffer.Size > 0);
        float x0 = FLT_MAX, y0 = FLT_MAX, x1 = 0, y1 = 0; bool white = false;
        for (const auto &v : list->VtxBuffer) {
            x0 = std::min(x0, v.pos.x); x1 = std::max(x1, v.pos.x);
            y0 = std::min(y0, v.pos.y); y1 = std::max(y1, v.pos.y);
            white |= v.col == IM_COL32(255,255,255,255);
        }
        assert(white && x0 >= gUiPresentX && x1 <= gUiPresentX + gUiPresentW);
        assert(y0 > gUiPresentY + gUiPresentH * 0.90f && y1 < gUiPresentY + gUiPresentH * 0.98f);
        assert(fabsf((x0 + x1) * 0.5f - (gUiPresentX + gUiPresentW * 0.5f)) < gUiPresentW * 0.02f);
        ImGui::Render();
        if(size[0]==1280) snapshot("title.bmp");
    }
    assert(!strcmp(UiZh("The selected server's TURN relay could not be allocated."), "无法分配所选服务器的战斗中继，请稍后重试。"));
    ImGui::DestroyContext();
    SDL_Quit();
    puts("actual_about_render=ok Chinese_glyph_coverage=ok title_white_text_5_viewports=ok");
    return 0;
}
