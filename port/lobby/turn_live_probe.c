/* Test the unchanged TURN implementation against a real server. No game. */
#include <SDL3/SDL.h>
#include <winsock2.h>
#include <ws2tcpip.h>
#include <stdio.h>
#include <stdint.h>
#include <string.h>
#include "../src/gs/net_relay.c"

int main(int argc,char **argv) {
    WSADATA ws;struct sockaddr_in local={0},peer={0};int sock,n,received=0;
    unsigned long nonblock=1;char address[64];uint8_t packet[1600];Uint64 until,next=0;
    if(argc!=5)return 2;
    WSAStartup(MAKEWORD(2,2),&ws);SDL_Init(0);
    sock=(int)socket(AF_INET,SOCK_DGRAM,0);local.sin_family=AF_INET;
    if(bind(sock,(struct sockaddr*)&local,sizeof(local)))return 3;
    ioctlsocket(sock,FIONBIO,&nonblock);
    if(!Relay_Allocate(sock,argv[1],argv[2],argv[3],address,sizeof(address)))return 4;
    peer.sin_family=AF_INET;peer.sin_port=htons(atoi(argv[4]));inet_pton(AF_INET,"127.0.0.1",&peer.sin_addr);
    Relay_Permit(sock,&peer);
    until=SDL_GetTicks()+8000;
    while(SDL_GetTicks()<until && received<3) {
        if(SDL_GetTicks()>=next){Relay_Send(sock,"PING",4,&peer);next=SDL_GetTicks()+500;}
        struct sockaddr_in from;int fromlen=sizeof(from),length=0;uint8_t *data=NULL;
        n=(int)recvfrom(sock,(char*)packet,sizeof(packet),0,(struct sockaddr*)&from,&fromlen);
        if(n>0 && Relay_Unwrap(packet,n,&from,&data,&length)==1) {
            if(length!=4 || memcmp(data,"PONG",4) || !Relay_IsPeer(&from))return 5;
            ++received;
        }
        Relay_Tick(sock);SDL_Delay(5);
    }
    int bound=sR.peer[0].chanBound;
    sR.lastRefresh=SDL_GetTicks()-120001;Relay_Tick(sock);
    SDL_Delay(100);Relay_Close(sock);SDL_Delay(100);closesocket(sock);
    printf("real_TURN=ok packets=%d channel_bound=%d refresh=sent close=sent\n",received,bound);
    return received==3 && bound?0:6;
}
