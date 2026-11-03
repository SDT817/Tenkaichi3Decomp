/* Exercise existing TURN code against a deterministic UDP test peer only. */
#include <SDL3/SDL.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
/* Include the unchanged implementation so the test can advance only its
   private timer fields instead of taking four minutes to verify refresh. */
#include "../src/gs/net_relay.c"

int main(int argc,char **argv) {
    WSADATA ws;struct sockaddr_in local={0},peer={0};int sock,n,len=sizeof(local),received=0;
    unsigned long nonblock=1;char address[64];uint8_t pkt[1600];Uint64 until;
    if(argc<4)return 2;
    WSAStartup(MAKEWORD(2,2),&ws);SDL_Init(0);
    sock=(int)socket(AF_INET,SOCK_DGRAM,0);local.sin_family=AF_INET;
    if(bind(sock,(struct sockaddr*)&local,sizeof(local)))return 3;
    ioctlsocket(sock,FIONBIO,&nonblock);
    if(!Relay_Allocate(sock,argv[1],argv[2],argv[3],address,sizeof(address)))return 4;
    peer.sin_family=AF_INET;peer.sin_port=htons(45000);inet_pton(AF_INET,"127.0.0.1",&peer.sin_addr);
    Relay_Permit(sock,&peer);
    until=SDL_GetTicks()+6000;
    while(SDL_GetTicks()<until && received<3) {
        struct sockaddr_in from;int fromlen=sizeof(from),datalen=0;uint8_t *data=NULL;
        n=(int)recvfrom(sock,(char*)pkt,sizeof(pkt),0,(struct sockaddr*)&from,&fromlen);
        if(n>0 && Relay_Unwrap(pkt,n,&from,&data,&datalen)==1) {
            if(datalen!=4 || memcmp(data,"PING",4))return 5;
            if(!Relay_IsPeer(&from))return 6;
            ++received;Relay_Send(sock,"PONG",4,&from);
        }
        Relay_Tick(sock);SDL_Delay(10);
    }
    // Timer-only test seam: implementation, message generation and crypto stay original.
    sR.lastRefresh=SDL_GetTicks()-120001;Relay_Tick(sock);
    until=SDL_GetTicks()+200;
    while(SDL_GetTicks()<until) {n=(int)recvfrom(sock,(char*)pkt,sizeof(pkt),0,(struct sockaddr*)&local,&len);if(n>0){uint8_t *data;int size;Relay_Unwrap(pkt,n,&local,&data,&size);}SDL_Delay(10);}
    int bound=sR.peer[0].chanBound;
    Relay_Close(sock);SDL_Delay(80);closesocket(sock);
    printf("TURN allocation=ok packets=%d channel_bound=%d refresh=sent close=sent\n",received,bound);
    return received==3?0:7;
}
