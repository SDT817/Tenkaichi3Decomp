// Echo the server's timestamp challenge as Dolphin NetPlayClient::OnData does.
// This uses its own UDP socket; game packets, pacing and rollback are untouched.
#ifdef _WIN32
#include <winsock2.h>
#include <ws2tcpip.h>
#else
#include <arpa/inet.h>
#include <netdb.h>
#include <sys/socket.h>
#include <unistd.h>
#endif
#include <SDL3/SDL.h>
#include <cstring>
#include "online_ping.h"

namespace OnlinePing {
namespace {
struct Probe { SDL_AtomicInt stop; std::string host, key; int port; };
Probe *current = nullptr;
SDL_AtomicInt workers;
const char magic[] = "BT3PING2";
int SDLCALL run(void *data) {
    Probe *p = (Probe *)data;
    bool ready = true;
#ifdef _WIN32
    WSADATA ws;
    ready = WSAStartup(MAKEWORD(2, 2), &ws) == 0;
#endif
    struct addrinfo hints = {}, *found = nullptr;
    hints.ai_family = AF_INET; hints.ai_socktype = SOCK_DGRAM;
    std::string port = std::to_string(p->port);
    bool valid = ready && getaddrinfo(p->host.c_str(), port.c_str(), &hints, &found) == 0;
    int sock = valid ? (int)socket(AF_INET, SOCK_DGRAM, 0) : -1;
    if (sock >= 0 && connect(sock, found->ai_addr, (int)found->ai_addrlen) != 0) {
#ifdef _WIN32
        closesocket(sock);
#else
        close(sock);
#endif
        sock = -1;
    }
    if (found) freeaddrinfo(found);
#ifdef _WIN32
    if (sock >= 0) { unsigned long flag = 1; ioctlsocket(sock, FIONBIO, &flag); }
#endif
    Uint64 next = 0;
    while (!SDL_GetAtomicInt(&p->stop)) {
        if (sock >= 0) {
            if (SDL_GetTicks() >= next) {
                std::string hello = std::string(magic, 8) + "R" + p->key;
                send(sock, hello.data(), (int)hello.size(), 0);
                next = SDL_GetTicks()+2000;
            }
            char packet[256];
#ifdef _WIN32
            int n = recv(sock, packet, sizeof(packet), 0);
#else
            int n = recv(sock, packet, sizeof(packet), MSG_DONTWAIT);
#endif
            if (n == 17 && !memcmp(packet, magic, 8) && packet[8] == 'P') {
                packet[8] = 'O';
                send(sock, packet, n, 0);
            }
        }
        SDL_Delay(2);
    }
    if (sock >= 0) {
#ifdef _WIN32
        closesocket(sock);
#else
        close(sock);
#endif
    }
#ifdef _WIN32
    if (ready) WSACleanup();
#endif
    delete p;
    SDL_AddAtomicInt(&workers, -1);
    return 0;
}
}
void Stop() {
    if (current) SDL_SetAtomicInt(&current->stop, 1);
    current = nullptr;
}
void Start(const std::string& host, int port, const std::string& key) {
    if (current && current->host == host && current->port == port && current->key == key) return;
    Stop();
    if (host.empty() || host.size() > 200 || port < 1 || port > 65535 || key.size() != 64) return;
    Probe *p = new Probe;
    SDL_SetAtomicInt(&p->stop, 0); p->host = host; p->port = port; p->key = key;
    SDL_AddAtomicInt(&workers, 1);
    SDL_Thread *t = SDL_CreateThread(run, "bt3-server-ping", p);
    if (!t) { delete p; SDL_AddAtomicInt(&workers, -1); return; }
    current = p; SDL_DetachThread(t);
}
bool Idle() { return SDL_GetAtomicInt(&workers) == 0; }
}
