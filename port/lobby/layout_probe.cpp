
#define main unused_lobby_probe_main
#include "lobby_probe.cpp"
#undef main
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


int main(){
 using namespace OnlineLobby;
 SDL_Init(0);ImGui::CreateContext();auto& io=ImGui::GetIO();
 io.IniFilename=nullptr;io.DisplaySize=ImVec2(1180,760);
 io.Fonts->AddFontFromFileTTF("C:/Windows/Fonts/msyh.ttc",18,nullptr,io.Fonts->GetGlyphRangesChineseFull());
 unsigned char *pixels;int w,h;io.Fonts->GetTexDataAsRGBA32(&pixels,&w,&h);io.Fonts->SetTexID((ImTextureID)1);
 loaded=directoryLoaded=true;directoryEnabled=false;favorites.push_back({"测试服务器","https://example.invalid","",""});
 serverName="测试服务器";lastOnline=relayOnly=true;elapsed=35;token="fixture";
 assert(OnlineJson::Parse(R"({"id":"r","name":"测试房间","phase":"idle","me":1,"view":"split","mode_match":true,"clients_current":true,"versions_match":true,"allow_pause":1,"can_start":true,
 "rules":{"battle":3,"time":4,"speed":100,"rollback":8,"delay":-2},
 "seats":[{"seat":1,"name":"Player A","version":"0.15","ping":27,"view":"split","ready":true},{"seat":2,"name":"Player B","version":"0.15","ping":36,"view":"split","ready":true},
 {"seat":3,"name":"观众","version":"0.15","ping":30,"ready":true},{"seat":4,"name":"","ready":false},
 {"seat":5,"name":"","ready":false},{"seat":6,"name":"","ready":false},{"seat":7,"name":"","ready":false},{"seat":8,"name":"","ready":false}]})",room));
 assert(versionNotice(room).empty());
 room.object["versions_match"].boolean=false;
 room.object["can_start"].boolean=false;
 ImGui::StyleColorsDark();
 for(int lower=0;lower<2;lower++){
   room.object["seats"].array[1].object["version"].text=lower?"0.16":"0.14";
   std::string notice=versionNotice(room);
   assert(notice.find("玩家版本不同")!=std::string::npos);
   assert((notice.find("你的版本较低")!=std::string::npos)==(lower!=0));
   for(int f=0;f<3;f++){
     io.DeltaTime=1.f/60;ImGui::NewFrame();
     ImGui::SetNextWindowPos(ImVec2(25,20));ImGui::SetNextWindowSize(ImVec2(1130,720));
     ImGui::Begin("服务器大厅",nullptr,ImGuiWindowFlags_NoCollapse);
     Draw("Player A",1);ImGui::End();ImGui::Render();
   }
   snapshot(lower?"lobby-version-local-lower.bmp":"lobby-version-peer-lower.bmp");
 }
 ImGui::DestroyContext();puts("Version notice: same, peer older, local older OK; lobby drawn.");return 0;
}
