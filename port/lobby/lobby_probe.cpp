// Headless ImGui + real HTTP lifecycle; session hooks are explicitly simulated.
// No SDL window, GPU, gameplay process, input automation or screenshot is used.
#include <SDL3/SDL.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <cstdio>
#include <cstring>
#include <cassert>
#include "../src/gs/online_lobby.cpp"

static int fpChecks;
static int ended, active, role, sock=-1, actualSpeed, actualBattle, actualDp, actualTime;
static char playerName[20]="Probe";
static Uint64 simulatedEnd;
extern "C" {
int Port_Setting(const char *,int def) { return def; }
void Port_SettingSave(const char *,int) {}
void Port_SettingsWrite(void) {}
int Port_NetMe(void) { return role==2; }
int Port_NetSpectating(void) { return role==4; }
void Port_NetSpectatorsAllow(int) {}
int Port_LobbySpectateCode(const char *) { abort(); }
int Port_DataFingerprintNeed(void) { return ++fpChecks < 6 ? 0 : 1; }
int Port_LobbyStartCode(int host,const char *code) {
    assert(fpChecks >= 6);
    WSADATA ws;WSAStartup(MAKEWORD(2,2),&ws);
    struct sockaddr_in local={}; int len=sizeof(local); unsigned long nonblock=1;
    if(sock>=0)closesocket(sock);
    sock=(int)socket(AF_INET,SOCK_DGRAM,0);local.sin_family=AF_INET;
    if(bind(sock,(struct sockaddr*)&local,sizeof(local)))return -1;
    ioctlsocket(sock,FIONBIO,&nonblock);getsockname(sock,(struct sockaddr*)&local,&len);
    role=host?1:2;Match_Begin(role,sock,ntohs(local.sin_port),code,playerName,6);return 3;
}
int Port_LobbyPoll(void) { MatchStatus status;Match_Poll(&status);return status.state==3?2:status.state<0?-3:3; }
void Port_LobbyCancel(void) { Match_Cancel(); }
void Port_LobbyLaunch(void) { Match_Cancel();active=1;simulatedEnd=SDL_GetTicks()+1500; }
const char *Port_LobbyError(void) { return "probe lookup failed"; }
void Port_NetOptions(int,int) {}
void Port_NetRulesSet(int battle,int dp,int time) { actualBattle=battle;actualDp=dp;actualTime=time; }
void Port_NetSpeedSet(int speed) { actualSpeed=speed; }
void Port_NetNameSet(const char *name) { SDL_strlcpy(playerName,name,sizeof(playerName)); }
int Port_NetSession(void) { return active; }
int Port_NetSessionsEnded(void) { return ended; }
int Port_RollCan(void) { return 1; }
}

int main(int argc,char **argv) {
    using namespace OnlineLobby;
    if(argc<5)return 2;
    SDL_Init(0);
    assert(!FocusTab()); Open(); assert(FocusTab()); assert(!FocusTab());
    ImGui::CreateContext();auto& io=ImGui::GetIO();io.DisplaySize=ImVec2(1000,800);io.IniFilename=nullptr;
    io.Fonts->AddFontDefault();unsigned char *pixels;int w,h;io.Fonts->GetTexDataAsRGBA32(&pixels,&w,&h);
    int seat=std::atoi(argv[3]);
    {
        Value parsed;
        assert(OnlineJson::Parse("{\"text\":\"\\u4e2d\\u6587\\ud83d\\ude00\\\"\",\"array\":[true,false,null,-2,1.25e2]}",parsed));
        assert(parsed["text"].str()=="中文😀\"");
        assert(parsed["array"].array.size()==5 && parsed["array"].array[4].integer()==125);
        for(const char *bad:{"", "{", "[1,]", "{\"a\":1,\"a\":2}","\"\\ud800\"", "\"\\u0000\"", "01", "1e", "true false"})
            assert(!OnlineJson::Parse(bad,parsed));
        assert(!OnlineJson::Parse(std::string(20,'[')+"0"+std::string(20,']'),parsed));
        assert(!OnlineJson::Parse(std::string(65537,' '),parsed));
        std::string quoted=OnlineJson::Quote("行\n\"\\text");
        assert(OnlineJson::Parse(quoted,parsed) && parsed.str()=="行\n\"\\text");
        assert(urlValid("http://127.0.0.1:8787") && urlValid("https://friends.example"));
        assert(!urlValid("http://172.evil.example") && !urlValid("http://example.com") && !urlValid("https://user:pass@example.com"));
        const char *remote = SDL_getenv("BT3_LOBBY_GATEWAY_REMOTE");
        const char *local = SDL_getenv("BT3_LOBBY_GATEWAY_LOCAL");
        if (remote && local) {
            assert(requestUrl(remote) == local);
            assert(requestUrl(std::string(remote)+"/lobby/v1/request") == std::string(local)+"/lobby/v1/request");
            assert(requestUrl(std::string(remote)+".evil/lobby/v1/request") == std::string(remote)+".evil/lobby/v1/request");
            assert(requestUrl("https://unrelated.example/v1/host") == "https://unrelated.example/v1/host");
        }
    }
    loaded=true;favorites.push_back({"Probe",argv[1],argv[2],""});
    std::string name="Probe"+std::to_string(seat);
    Port_NetNameSet(name.c_str());
    int stage=0,launches=0,returns=0; bool sawPing=false;
    std::string previousState;
    directoryLoaded=true; directoryEnabled=argc>5; if(argc>5)directoryUrl=argv[5];
    Uint64 until=SDL_GetTicks()+80000;
    while(SDL_GetTicks()<until) {
        if(active && SDL_GetTicks()>=simulatedEnd){active=0;++ended;}
        int event=Tick(true);
        for(const auto& peer:room["seats"].array)if(peer["ping"].integer(-1)>=0)sawPing=true;
        if(event==1){++launches;assert(splitView == (launches==2));assert(Port_OnlinePauseAllowed());assert(actualSpeed==100);}
        if(event==2)++returns;
        std::string state=std::to_string(stage)+":"+room["phase"].str()+":"+std::to_string(room["me"].integer())+":"+std::to_string(room["seats"].array.size())+":"+(room["can_start"].yes()?"can_start":"wait")+":"+error;
        if(state!=previousState){fprintf(stderr,"probe stage %s launches=%d returns=%d\n",state.c_str(),launches,returns);fflush(stderr);previousState=state;}
        io.DeltaTime=0.02f;ImGui::NewFrame();ImGui::SetNextWindowSize(ImVec2(1120,700));ImGui::Begin("headless");Draw(name.c_str(),1);ImGui::End();ImGui::Render();
        if(!job) {
            if(stage==0 && !rooms.empty()) {send("enter",",\"room\":\"r0\",\"name\":"+Quote(name)+",\"seat\":"+std::to_string(seat)+",\"sync_pause\":1,\"version\":"+Quote(BT3_LOCAL_VERSION));stage=1;}
            else if(stage==1 && !token.empty()) {send("seat",",\"seat\":"+std::to_string(seat));stage=2;}
            else if(stage==2 && room["me"].integer()==seat && room["phase"].str()=="idle") {
                int count=0;for(const auto& s:room["seats"].array)if(!s["name"].str().empty())++count;
                if(returns>=2){Close();stage=3;}
                else if(launches==1 && room["view"].str()=="full")send("mode",",\"view\":\"split\"");
                else if(count==2 && seat==1 && room["can_start"].yes() && sawPing) {session.clear();send("start",",\"epoch\":"+Quote(room["epoch"].str()));}
            } else if(stage==3 && token.empty() && !closing)break;
        }
        SDL_Delay(20);
    }
    if(job){while(!SDL_GetAtomicInt(&job->done))SDL_Delay(10);response();}
    Match_Cancel();while(!Match_TransportIdle())SDL_Delay(10);
    if(directoryJob){while(!SDL_GetAtomicInt(&directoryJob->done))SDL_Delay(10);directoryTick(false);}
    OnlinePing::Stop();while(!OnlinePing::Idle())SDL_Delay(10);
    assert(sawPing && fpChecks > 0);
    if(argc>5){bool synced=false;for(const auto& f:favorites)if(f.directory=="native")synced=true;assert(synced);}
    if(sock>=0)closesocket(sock);
    ImGui::DestroyContext();
    printf("headless_UI=ok launches=%d returns=%d seat=%d clean_leave=%d error=%s\n",launches,returns,seat,token.empty(),error.c_str());
    printf("applied_speed=%d battle=%d dp=%d time=%d\n",actualSpeed,actualBattle,actualDp,actualTime);
    return launches==2 && returns==2 && token.empty()?0:3;
}
