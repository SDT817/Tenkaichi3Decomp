/* CPU/socket harness only: never loads game assets or starts the game. */
#include <SDL3/SDL.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <stdio.h>
#include <string.h>
#include "../src/gs/net_match.h"

int main(int argc, char **argv) {
    WSADATA ws;
    SOCKET sock;
    struct sockaddr_in local;
    int len=sizeof(local), state=0;
    unsigned long nonblock=1;
    Uint64 until;
    MatchStatus st;
    if (argc < 4) return 2;
    WSAStartup(MAKEWORD(2,2), &ws);
    SDL_Init(0);
    if (!strcmp(argv[1], "http")) {
        char out[65536]={0};
        if (!Match_Http(argv[2], argv[3], argc > 4 ? argv[4] : "", out, sizeof(out))) return 3;
        printf("%s\n",out);
        return 0;
    }
    sock=socket(AF_INET,SOCK_DGRAM,0);
    memset(&local,0,sizeof(local)); local.sin_family=AF_INET; local.sin_addr.s_addr=htonl(INADDR_ANY);
    if (sock==INVALID_SOCKET || bind(sock,(struct sockaddr*)&local,sizeof(local))) return 4;
    ioctlsocket(sock,FIONBIO,&nonblock);
    getsockname(sock,(struct sockaddr*)&local,&len);
    Match_ConfigurePrivate(argv[2],argv[3]);
    Match_Begin(!strcmp(argv[1],"host") ? 1 : 2, (int)sock, ntohs(local.sin_port), argc>4?argv[4]:"", "Probe", 6);
    Match_ConfigurePrivate(NULL,NULL);
    until=SDL_GetTicks()+45000;
    do {
        Match_Poll(&st);
        if (st.state != state) { state=st.state; printf("state=%d code=%s peer=%s count=%d error=%s\n",st.state,st.code,st.peerName,st.peerCount,st.error); fflush(stdout); }
        if (!strcmp(argv[1],"cancel") && SDL_GetTicks()+44000>=until) { Match_Cancel(); break; }
        if (state==3 || state<0) break;
        SDL_Delay(10);
    } while(SDL_GetTicks()<until);
    if (state==3) {
        for(int i=0;i<st.peerCount;i++) printf("addr=%s\n",st.peerAddr[i]);
    }
    Match_Cancel();
    until=SDL_GetTicks()+15000;
    while(!Match_TransportIdle() && SDL_GetTicks()<until) SDL_Delay(10);
    closesocket(sock);
    printf("transport_idle=%d\n",Match_TransportIdle());
    return state==3 || !strcmp(argv[1],"cancel") ? 0 : 5;
}
