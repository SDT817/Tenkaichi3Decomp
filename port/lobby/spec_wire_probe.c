/* Existing spectator readiness/fingerprint packets over the real TURN path.
   The host's session-ready flag is supplied; no battle/replay is run. */
#define main two_player_probe_main
#include "wire_probe.c"
#undef main

int main(int argc,char **argv) {
    if(argc<4)return 2;
    SDL_Init(0);
    int host=!strcmp(argv[1],"host"),watch=!strcmp(argv[1],"watch");
    Port_NetNameSet(watch?"Spectator":"WireProbe");
    Match_ConfigurePrivate(argv[2],argv[3]);
    int state=watch?Port_LobbySpectateCode(argv[4]):Port_LobbyStartCode(host,argc>4?argv[4]:"");
    Match_ConfigurePrivate(NULL,NULL);
    Uint64 end=SDL_GetTicks()+45000;
    while(state>0&&state!=2&&SDL_GetTicks()<end) {state=Port_LobbyPoll();SDL_Delay(5);}
    printf("ready=%d host=%d watch=%d relay=%d fingerprint=%d\n",state,host,watch,sCodeVia,sFpHeard);fflush(stdout);
    if(state!=2)return 3;
    if(host) {
        sMode=1;sSession=1;sSpecOpen=1;
        struct sockaddr_in seen[6];int count=0;
        uint8_t packet[2048];struct sockaddr_in from;int n;
        end=SDL_GetTicks()+20000;
        while(SDL_GetTicks()<end&&count<6) {
            watch_service();Relay_Tick(sSock);
            while((n=net_recv(packet,sizeof(packet),&from))>=8) {
                uint32_t magic,type;memcpy(&magic,packet,4);memcpy(&type,packet+4,4);
                if(magic==MAGIC&&type==T_SPEC_HELLO) {
                    int i;for(i=0;i<count&&!same_addr(&seen[i],&from);i++);
                    if(i==count&&count<6&&spec_check(packet,n)==0)seen[count++]=from;
                    spec_hello(packet,n,&from);
                }
            }
            SDL_Delay(5);
        }
        printf("six_authorized_fingerprint_validated_spectators=%d\n",count);fflush(stdout);
        SDL_Delay(500);
        Port_LobbyCancel();while(!Match_TransportIdle())SDL_Delay(10);
        return count==6?0:4;
    }
    if(!watch) {end=SDL_GetTicks()+700;while(SDL_GetTicks()<end){Port_LobbyPoll();SDL_Delay(5);}}
    Port_LobbyCancel();while(!Match_TransportIdle())SDL_Delay(10);
    return 0;
}
