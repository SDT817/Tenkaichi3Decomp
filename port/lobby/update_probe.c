/* Exercise the actual updater, including archive install/rollback. No game. */
#include <SDL3/SDL.h>
#include <stdio.h>
#include <string.h>
#include "../src/gs/net_update.h"

static UpdateStatus wait_state(void) {
    UpdateStatus s;
    Uint64 end=SDL_GetTicks()+30000;
    do {
        Update_Status(&s);
        if(s.state!=UPD_CHECKING && s.state!=UPD_DOWNLOADING && s.state!=UPD_VERIFYING && s.state!=UPD_INSTALLING) return s;
        SDL_Delay(5);
    } while(SDL_GetTicks()<end);
    fprintf(stderr,"Timeout state=%d\n",s.state);
    return s;
}
int main(int argc,char **argv) {
    SDL_Init(0);
    fprintf(stderr,"base=%s\n",SDL_GetBasePath());
    Update_Check();
    UpdateStatus s=wait_state();
    if(s.state!=UPD_AVAILABLE || !s.canInstall) {
        fprintf(stderr,"Check state=%d cannot=%s\n",s.state,s.cannot);return 2;
    }
    if(!strstr(Update_Notes(),"测试公告")) return 3;
    Update_Download(); s=wait_state();
    if(s.state==UPD_READY) { Update_Install(); s=wait_state(); }
    printf("state=%d version=%s why=%s\n",s.state,Update_Version(),s.why);
    return argc>1 && !strcmp(argv[1],"fail") ? s.state==UPD_FAILED?0:5 : s.state==UPD_INSTALLED?0:4;
}
