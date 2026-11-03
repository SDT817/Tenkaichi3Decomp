/* Actual upstream UDP/fingerprint handshake. No game state, GPU or game assets. */
#include "../src/gs/net.c"

int Port_DataFingerprintNeed(void) { return 1; }
int Port_DataFingerprint(unsigned long long *fp) { if (fp) *fp=0x1122334455667788ull; return 1; }
int Port_DataFingerprintOriginal(void) { return 1; }
const char *Port_DataFingerprintText(void) { return "probe"; }
int Port_DataFingerprintPart(int part,unsigned long long *fp) { if(fp)*fp=(unsigned)part;return 1; }
void Port_UiNotice(const char *text) { (void)text; }
void Port_UiBanner(const char *text,int ms) { (void)text;(void)ms; }
const char *MenuTranslation_PortText(const char *id) { return id; }
int gPortResim;
unsigned gPortPaceShiftNs;
const char *Port_GetEnv(const char *name) { return SDL_getenv(name); }
int Port_Setting(const char *name,int def) { (void)name;return def; }
void Port_SettingSave(const char *name,int value) { (void)name;(void)value; }
void Port_SettingText(const char *name,const char *def,char *out,int size) { (void)name;SDL_strlcpy(out,def,(size_t)size); }
void Port_SettingTextSave(const char *name,const char *value) { (void)name;(void)value; }
void Port_SettingsWrite(void) {}
int Update_BlocksOnline(void) { return 0; }
int Port_OnlineSplitView(void) { return 0; }
int Port_OnlineSplitSwap(void) { return 0; }
int Port_RollCan(void) { return 0; }
int Port_SessionCan(void) { return 0; }
int Port_SessionAsked(void) { return 0; }
void Port_SessionRequest(int role,const char *address,int port) { abort(); }
void Port_SessionReturn(void) { abort(); }
int Port_RollSave(void) { abort(); }
void Port_RollBack(int k) { abort(); }
int Port_PadRead(int socket,unsigned char *data) { abort(); }
unsigned long long Port_NetDigest(void) { abort(); }
void Gs_HoldFrame(void) { abort(); }
void PortSe_BlankBegins(unsigned tick) { abort(); }
void PortSe_RunAgainEnds(unsigned first,unsigned live) { abort(); }
int Port_BattleOutcome(int *winner) { abort(); }
int Port_BattleSeqState(void) { abort(); }

int main(int argc,char **argv) {
    if(argc<4)return 2;
    SDL_Init(0);
    Port_NetNameSet("WireProbe");
    Match_ConfigurePrivate(argv[2],argv[3]);
    int state=Port_LobbyStartCode(!strcmp(argv[1],"host"),argc>4?argv[4]:"");
    Match_ConfigurePrivate(NULL,NULL);
    Uint64 until=SDL_GetTicks()+45000;
    while(state>0 && state!=2 && SDL_GetTicks()<until) {
        state=Port_LobbyPoll();
        if(sCodeText[0]) { printf("code=%s\n",sCodeText);fflush(stdout); }
        SDL_Delay(10);
    }
    printf("state=%d fingerprint_heard=%d data_bad=%d relay=%d error=%s\n",state,sFpHeard,sDataBad,sCodeVia,Port_LobbyError());
    fflush(stdout);
    /* Keep answering so that the peer's last acknowledgement is not lost. */
    if(state==2) { until=SDL_GetTicks()+700;while(SDL_GetTicks()<until){Port_LobbyPoll();SDL_Delay(10);} }
    Port_LobbyCancel();while(!Match_TransportIdle())SDL_Delay(10);
    return state==2 && !sDataBad?0:3;
}
