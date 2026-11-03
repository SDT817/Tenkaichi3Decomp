// Reuse the headless lifecycle harness and actual production ImGui/HTTP code.
#define main lifecycle_probe_main
#include "lobby_probe.cpp"
#undef main
#include "imgui_internal.h"

static unsigned long long drawHash() {
    using namespace OnlineLobby;
    ImGui::NewFrame(); ImGui::SetNextWindowPos(ImVec2(0,0)); ImGui::SetNextWindowSize(ImVec2(960,760));
    ImGui::Begin("settings-probe"); Draw("Probe",1); ImGui::End(); ImGui::Render();
    unsigned long long hash=1469598103934665603ULL;
    auto *data=ImGui::GetDrawData();
    for(int i=0;i<data->CmdListsCount;++i) {
        const auto& vertices=data->CmdLists[i]->VtxBuffer;
        const auto *raw=(const unsigned char *)vertices.Data;
        for(int j=0;j<vertices.Size*(int)sizeof(ImDrawVert);++j)hash=(hash^raw[j])*1099511628211ULL;
    }
    return hash;
}

static void directoryWait() {
    using namespace OnlineLobby;
    Uint64 until=SDL_GetTicks()+15000;
    while(directoryJob || !directoryQueuedOp.empty()) { assert(SDL_GetTicks()<until); directoryTick(false); SDL_Delay(5); }
    assert(directoryError.empty());
}

int main(int argc,char **argv) {
    using namespace OnlineLobby;
    assert(argc==4); SDL_Init(0); ImGui::CreateContext();
    auto& io=ImGui::GetIO(); io.DisplaySize=ImVec2(1000,800); io.IniFilename=nullptr; io.DeltaTime=.02f;
    io.MousePos=ImVec2(-1000,-1000); io.Fonts->AddFontDefault(); unsigned char *pixels; int w,h;
    io.Fonts->GetTexDataAsRGBA32(&pixels,&w,&h);
    loaded=directoryLoaded=true; directoryEnabled=false; directoryUrl=argv[1]; directoryKey=argv[2];
    favorites.push_back({"Original",argv[1],argv[3],"","native",false});
    send("list");
    while(job) { response(); SDL_Delay(5); }
    assert(error.empty() && !rooms.empty());
    drawHash(); drawHash(); auto idle=drawHash();
    Job background; background.op="list"; job=&background;
    assert(!busy()); drawHash(); assert(drawHash()==idle);
    Job directoryBackground; directoryBackground.op="list"; directoryJob=&directoryBackground;
    assert(!directoryBusy()); drawHash(); assert(drawHash()==idle);
    directoryJob=nullptr;
    send("enter",",\"room\":\"r0\",\"name\":\"QueuedPlayer\"");
    assert(busy() && queuedOp=="enter"); job=nullptr;
    Tick(false);
    Uint64 until=SDL_GetTicks()+15000;
    while(token.empty()) { assert(SDL_GetTicks()<until); Tick(false); SDL_Delay(5); }
    Close(); while(closing || job) { assert(SDL_GetTicks()<until); Tick(false); SDL_Delay(5); }
    assert(token.empty());
    directorySend("whoami"); directoryWait(); assert(directoryAuthenticated);
    assert(!directoryState["room_settings"]["rooms"].array.empty());
    // Open/render the actual room-rule controls without launching a game window.
    ImGui::NewFrame(); ImGui::Begin("admin"); directoryRooms(); ImGui::End(); ImGui::Render();
    directorySend("save_room",",\"server\":\"native\",\"room\":\"r0\",\"rules\":{\"battle\":3,\"time\":2,\"speed\":100}");
    directoryWait(); assert(directoryState["room_settings"]["rooms"].array[0]["rules"]["battle"].integer()==3);
    directorySend("rename_room",",\"server\":\"native\",\"room\":\"r0\",\"name\":\"改名测试\"");
    directoryWait(); assert(directoryState["room_settings"]["rooms"].array[0]["name"].str()=="改名测试");
    directorySend("add_room",",\"server\":\"native\",\"name\":\"新增测试\"");
    directoryWait(); assert(directoryState["room_settings"]["rooms"].array.size()==2);
    // Rename from ordinary Edit while an automatic directory refresh is pending.
    directorySend("list"); assert(directoryRename(favorites[0],"Renamed server"));
    favorites[0].name="Renamed server"; favorites[0].personal=true; save(); directoryWait();
    assert(favorites[0].name=="Renamed server" && !favorites[0].personal);
    directorySend("list"); directoryWait(); assert(favorites[0].name=="Renamed server");
    loaded=false; favorites.clear(); load(); assert(favorites[0].name=="Renamed server");
    // A local non-admin alias is preserved across subsequent directory refreshes.
    favorites[0].personal=true; favorites[0].name="My local alias";
    directorySend("list"); directoryWait(); assert(favorites[0].name=="My local alias");
    Job stale; stale.url="https://old.invalid/lobby/v1/request"; stale.success=true;
    SDL_SetAtomicInt(&stale.done,1); job=new Job;
    job->url=stale.url; job->success=true; SDL_SetAtomicInt(&job->done,1);
    auto oldName=serverName; response(); assert(!job && serverName==oldName);
    Match_Cancel(); while(!Match_TransportIdle())SDL_Delay(5);
    OnlinePing::Stop(); while(!OnlinePing::Idle())SDL_Delay(5);
    ImGui::DestroyContext();
    printf("refresh_vertex_hash_identical=yes queued_enter=yes queued_rename=yes admin_rules=yes rename_reload=yes stale_response_ignored=yes\n");
    return 0;
}
