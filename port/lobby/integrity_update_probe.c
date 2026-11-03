/* Actual updater with test-only injection at its existing SHA file-read API. */
#include <SDL3/SDL.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "../src/gs/net_update.h"

int __real_UpdSha256_File(const char *, char[65]);
static int injected;
int __wrap_UpdSha256_File(const char *path, char hex[65]) {
    const char *fault = getenv("BT3_TEST_READBACK");
    int result = __real_UpdSha256_File(path, hex);
    if (!injected && fault != NULL &&
        ((!strcmp(fault,"staged") && strstr(path,".new")) ||
         (!strcmp(fault,"installed") && strstr(path,"Tenkaichi3Decomp.exe") && !strstr(path,".new")))) {
        memset(hex,'0',64); hex[64]=0; injected=1;
    }
    return result;
}

static UpdateStatus wait_state(void) {
    UpdateStatus status;
    Uint64 end=SDL_GetTicks()+60000;
    do {
        Update_Status(&status);
        if (status.state!=UPD_CHECKING && status.state!=UPD_DOWNLOADING && status.state!=UPD_VERIFYING && status.state!=UPD_INSTALLING) return status;
        SDL_Delay(5);
    } while(SDL_GetTicks()<end);
    return status;
}
int main(int argc,char **argv) {
    UpdateStatus status;
    int installs=0;
    SDL_Init(0);
    Update_Check(); status=wait_state();
    if (status.state!=UPD_AVAILABLE || !status.canInstall) { fprintf(stderr,"check: %d %s\n",status.state,status.cannot);return 2; }
    Update_Download(); status=wait_state();
    while(status.state==UPD_READY && installs++<4) { Update_Install();status=wait_state(); }
    printf("state=%d version=%s injected=%d installs=%d why=%s\n",status.state,Update_Version(),injected,installs,status.why);
    if (getenv("BT3_TEST_READBACK") && !injected) return 6;
    return argc>1 && !strcmp(argv[1],"fail") ? (status.state==UPD_FAILED?0:5) : (status.state==UPD_INSTALLED?0:4);
}
