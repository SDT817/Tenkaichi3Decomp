/* Integration tests of the actual pad/menu/battle C, with only platform and
 * battle-state services replaced. No controller or game assets required. */
#include "common.h"
#include "sys/pad.h"
#include "sys/game_pad.h"
#include "sys/save.h"
#include "battle/battle.h"
#include "battle/btl_seq.h"
#include "battle/btl_input.h"
#include "port_control_mode.h"
/* Test-helper mode selector; never placed in the real raw button word. */
#define PORT_PAD_WII 0x01000000u

extern int printf(const char *, ...);
extern void exit(int);
extern void *memset(void *, int, u32);
extern s32 BtlInput_TestAction(BtlInputChr *, s32, s32);

Pad gPad[PAD_COUNT];
static SaveData save;
SaveData *gSaveData = &save;
static BattleWork battle;
static BtlSeq sequence;
BtlSeq *gBtlSeq = &sequence;
static u8 packets[2][18];
static int checks, replay, recordCount, replayPos, stopped;
static struct { u32 buttons, commands; u8 stick[2]; int burst; } trace[256];

#define CHECK(cond) do { checks++; if (!(cond)) { printf("FAIL line %d: %s\n", __LINE__, #cond); exit(1); } } while (0)

BattleWork *Battle_GetWork(void) { return &battle; }
s32 BtlChar_TestFlag(BtlInputChr *c, s32 bit) { return bit == 2 || bit == 3; }
void BtlChar_ClearFlag(BtlInputChr *c, s32 bit) { (void)c; (void)bit; }
f32 BtlAct_GetFacingRelCam(BtlInputChr *c) { (void)c; return 0; }
s32 BattleReplay_IsActive(void) { return replay; }
BtlInputSwitchEntry *BtlSuper_GetPromptRow(BtlInputChr *c, s32 arg) {
    static BtlInputSwitchEntry row;
    return &row;
}
s32 BtlChars_IsTimeStopped(void) { return stopped; }
s32 BtlChar_IsStage4Or27(void) { return 0; }
Pad *BtlChar_GetPad(BtlInputChr *c) { return &gPad[c->pad]; }
f32 BtlUtil_WrapAngle(f32 a) { return a; }
int Port_NetActive(void) { return 0; }
s32 BtlPause_GetMenuPad(void) { return 0; }
void BtlReplay_Record(BtlInputChr *c, u32 b, u32 cmd, u8 *s) {
    if (recordCount < 256) {
        trace[recordCount].buttons = b;
        trace[recordCount].commands = cmd;
        trace[recordCount].stick[0] = s[0];
        trace[recordCount].stick[1] = s[1];
        recordCount++;
    }
}
void BtlReplay_Play(BtlInputChr *c, u32 *b, u8 *s) {
    *b = trace[replayPos].buttons;
    s[0] = trace[replayPos].stick[0];
    s[1] = trace[replayPos++].stick[1];
}
s32 scePad2GetState(s32 socket) { return PAD_STATE_STABLE; }
s32 sceDbcInit(void) { return 0; }
s32 scePad2Init(s32 mode) { return 0; }
s32 scePad2CreateSocket(Pad2SocketParam *p, void *work) { return p->port; }
s32 scePad2Read(s32 socket, u8 *data) {
    int i;
    for (i = 0; i < 18; i++) data[i] = packets[socket][i];
    return 18;
}
s32 scePad2GetButtonProfile(s32 socket, void *p) { return 0; }
s32 sceVibGetProfile(s32 socket, u8 *p) { return 0; }
s32 sceVibSetActParam(s32 socket, s32 n, u8 *p, s32 size, void *data) { return 0; }

static void step(BtlInputChr *c, u32 raw) {
    gPad[c->pad].data[PORT_CONTROL_MODE_BYTE] = (raw & PORT_PAD_WII) ? PORT_CONTROL_MODE_WII : 0;
    gPad[c->pad].held = raw & ~PORT_PAD_WII;
    BtlInput_Sample(c);
    BtlInput_Update(c);
}
static void init(BtlInputChr *c, int player, int wii) {
    int i;
    memset(c, 0, sizeof(*c));
    c->player = c->pad = player;
    BtlInput_Init(c);
    for (i = 0; i < 35; i++) step(c, wii ? PORT_PAD_WII : 0);
}
static void test_battle(int player) {
    BtlInputChr c, ps2;
    u32 w = PORT_PAD_WII;
    u32 face[] = {PAD_CROSS, PAD_CIRCLE, PAD_SQUARE, PAD_TRIANGLE};
    u32 mask = BTLB_GUARD | BTLB_DASH | BTLB_RUSH | BTLB_BLAST |
               BTLB_ANY_FACE | BTLB_BLAST2 | BTLB_CROSS | BTLB_CIRCLE | BTLB_SQUARE | BTLB_TRIANGLE;
    int i;
    init(&c, player, 1);
    step(&c, w | PAD_RSTICK_UP);
    CHECK(BtlInput_TestAction(&c, 107, 1));
    CHECK(!(c.input.held & (BTLB_R3 | BTLB_RS_UP2 | BTLB_RS_UP)));
    step(&c, w);
    step(&c, w | PAD_RSTICK_DOWN);
    CHECK(c.input.held & BTLB_R3);
    step(&c, w);
    /* Transform is deliberately on release, as in the original game. */
    init(&c, player, 1);
    step(&c, w | PAD_RSTICK_DOWN);
    step(&c, w);
    CHECK(BtlInput_TestAction(&c, 99, 1));
    step(&c, w | PAD_R3);
    CHECK((c.input.held & BTLB_CHARGE) && !(c.input.held & BTLB_R3));
    step(&c, w);
    CHECK(!BtlInput_TestAction(&c, 99, 1));
    step(&c, w | PAD_L3 | PAD_R3);
    CHECK(!(c.input.held & BTLB_L3R3));
    step(&c, w | PAD_RSTICK_LEFT);
    CHECK((c.input.held & BTLB_RS_UP2) && BtlInput_TestAction(&c, 97, 1));
    CHECK(!(c.input.held & BTLB_CHARGE));
    step(&c, w | PAD_RSTICK_RIGHT);
    CHECK((c.input.held & BTLB_RS_DOWN2) && BtlInput_TestAction(&c, 98, 1));
    init(&c, player, 1);
    step(&c, w | PAD_R1);
    CHECK((c.input.held & BTLB_ASCEND) && !BtlInput_TestAction(&c, 15, 1));
    step(&c, w); step(&c, w | PAD_R1);
    CHECK(!BtlInput_TestAction(&c, 15, 1));
    step(&c, w | PAD_L1);
    CHECK((c.input.held & BTLB_DESCEND) && !(c.input.held & BTLB_LOCKON));
    step(&c, w); step(&c, w | PAD_L1);
    CHECK(!BtlInput_TestAction(&c, 17, 1));
    step(&c, w | PAD_R2);
    CHECK(BtlInput_TestAction(&c, 15, 1) && (c.input.held & BTLB_ASCEND));
    CHECK(!(c.input.held & BTLB_CHARGE));
    step(&c, w | PAD_R2);
    CHECK(!BtlInput_TestAction(&c, 15, 1));
    step(&c, w);
    CHECK(BtlInput_TestAction(&c, 16, 1));
    step(&c, w | PAD_L2);
    CHECK(BtlInput_TestAction(&c, 17, 1) && (c.input.held & BTLB_DESCEND));
    CHECK(!(c.input.held & BTLB_CHARGE));
    step(&c, w); step(&c, w | PAD_L2);
    CHECK(!BtlInput_TestAction(&c, 46, 1));
    for (i = 0; i < 4; i++) {
        init(&c, player, 1); init(&ps2, player, 0);
        step(&c, w | face[i]); step(&ps2, face[i]);
        CHECK((c.input.held & mask) == (ps2.input.held & mask));
        CHECK(c.input.cmdHeld == ps2.input.cmdHeld);
    }
    /* Legacy PS2 shoulders, stick clicks and LT charge remain intact. */
    init(&ps2, player, 0);
    step(&ps2, PAD_R1); step(&ps2, 0); step(&ps2, PAD_R1);
    CHECK(BtlInput_TestAction(&ps2, 15, 1));
    step(&ps2, PAD_R3 | PAD_L3);
    CHECK(BtlInput_TestAction(&ps2, 107, 1));
    step(&ps2, PAD_L2);
    CHECK(ps2.input.held & BTLB_CHARGE);
    /* Injected AI controls ignore the physical player's selected mode. */
    c.injectOn = 1; c.injectButtons = BTLB_R3 | BTLB_ASCEND;
    step(&c, w | PAD_L2);
    CHECK(c.input.held == (BTLB_R3 | BTLB_ASCEND));
}
static void test_burst(void) {
    BtlInputChr c;
    u32 dirs[] = {PAD_RSTICK_LEFT, PAD_RSTICK_RIGHT};
    int dir, gap, i;
    for (dir = 0; dir < 2; dir++) {
        for (gap = 1; gap <= 10; gap++) {
            init(&c, 0, 1);
            step(&c, PORT_PAD_WII | dirs[dir]);
            CHECK(!BtlInput_TestAction(&c, 46, 1));
            for (i = 0; i < gap; i++) step(&c, PORT_PAD_WII);
            step(&c, PORT_PAD_WII | dirs[dir]);
            CHECK(!!BtlInput_TestAction(&c, 46, 1) == (gap < BTL_TAP_FRAMES));
            step(&c, PORT_PAD_WII | dirs[dir]);
            CHECK(!BtlInput_TestAction(&c, 46, 1));
        }
    }
    init(&c, 0, 1);
    step(&c, PORT_PAD_WII | PAD_RSTICK_LEFT); step(&c, PORT_PAD_WII);
    step(&c, PORT_PAD_WII | PAD_RSTICK_RIGHT);
    CHECK(!BtlInput_TestAction(&c, 46, 1));
}
static void test_menus(void) {
    int player, context, i;
    u32 face[] = {PAD_CROSS, PAD_CIRCLE, PAD_SQUARE, PAD_TRIANGLE};
    u32 ps2[] = {PADG_CROSS, PADG_CIRCLE, PADG_SQUARE, PADG_TRIANGLE};
    u32 wii[] = {PADG_TRIANGLE, PADG_CIRCLE, PADG_CROSS, PADG_SQUARE};
    for (player = 0; player < 2; player++) {
        for (context = 0; context < 4; context++) {
            battle.running = context != 0;
            battle.flags = context == 2 ? BATTLE_FLAG_PAUSE_MENU : 0;
            sequence.state = context == 3 ? BTL_SEQ_END : BTL_SEQ_FIGHT;
            for (i = 0; i < 4; i++) {
                gPad[player].gameHeld = 0;
                gPad[player].data[PORT_CONTROL_MODE_BYTE] = PORT_CONTROL_MODE_WII;
                gPad[player].held = face[i];
                Pad_UpdateGameButtons(player);
                CHECK(gPad[player].gamePressed == (context == 1 ? ps2[i] : wii[i]));
                CHECK(gPad[player].held == face[i]);
                Pad_UpdateGameButtons(player);
                CHECK(gPad[player].gamePressed == 0);
                gPad[player].gameHeld = 0;
                gPad[player].data[PORT_CONTROL_MODE_BYTE] = 0;
                gPad[player].held = face[i];
                Pad_UpdateGameButtons(player);
                CHECK(gPad[player].gamePressed == ps2[i]);
            }
        }
    }
    battle.flags = 0;
    sequence.state = BTL_SEQ_FIGHT;
}
static void test_menu_sticks(void) {
    int player, mode, context, dir, frame;
    u8 modes[] = {0, PORT_CONTROL_MODE_WII, PORT_CONTROL_MODE_SPLIT};
    u32 dpad[] = {PAD_LEFT, PAD_RIGHT, PAD_DOWN, PAD_UP};
    u32 stick[] = {PAD_LSTICK_LEFT, PAD_LSTICK_RIGHT, PAD_LSTICK_DOWN, PAD_LSTICK_UP};
    u32 mapped[] = {PADG_LEFT | PADG_LEFT2, PADG_RIGHT | PADG_RIGHT2,
                    PADG_DOWN | PADG_DOWN2, PADG_UP | PADG_UP2};
    u32 mask = PADG_LEFT | PADG_RIGHT | PADG_DOWN | PADG_UP | PADG_LEFT2 | PADG_RIGHT2 | PADG_DOWN2 | PADG_UP2;
    for (player = 0; player < 2; player++) for (mode = 0; mode < 3; mode++) for (context = 0; context < 4; context++) {
        battle.running = context != 0;
        battle.flags = context == 2 ? BATTLE_FLAG_PAUSE_MENU : 0;
        sequence.state = context == 3 ? BTL_SEQ_END : BTL_SEQ_FIGHT;
        int wiiMenu = mode && context != 1;
        for (dir = 0; dir < 4; dir++) {
            Pad *p = &gPad[player];
            p->data[PORT_CONTROL_MODE_BYTE] = modes[mode];
            p->gameHeld = 0; p->held = dpad[dir];
            Pad_UpdateGameButtons(player);
            CHECK((p->gamePressed & mask) == (wiiMenu ? 0 : mapped[dir]));
            p->gameHeld = 0; p->held = stick[dir];
            p->repeatDelay = 20; p->repeatInterval = 1;
            for (frame = 0; frame < 25; frame++) {
                Pad_UpdateGameButtons(player);
                CHECK((p->gameHeld & mask) == (wiiMenu ? mapped[dir] : 0));
                CHECK((p->gameRepeat & mask) == (wiiMenu && (frame == 0 || frame == 21 || frame == 23) ? mapped[dir] : 0));
                CHECK(p->held == stick[dir]);
            }
            p->held = 0; Pad_UpdateGameButtons(player); CHECK(!(p->gameHeld & mask));
        }
    }
    /* The actual raw stick threshold and dominant-axis selection stay in Pad_Update. */
    battle.running = 0; battle.flags = 0;
    for (player = 0; player < 2; player++) {
        for (frame = 0; frame < 18; frame++) packets[player][frame] = frame < 2 ? 255 : 0;
        for (frame = 2; frame < 6; frame++) packets[player][frame] = 128;
        packets[player][PORT_CONTROL_MODE_BYTE] = PORT_CONTROL_MODE_WII;
        gPad[player].socket = player; gPad[player].phase = PAD_PHASE_READ;
    }
    packets[0][PAD_DATA_LX] = 255; packets[1][PAD_DATA_LY] = 0;
    Pad_Update();
    CHECK((gPad[0].gameHeld & mask) == mapped[1]); CHECK((gPad[1].gameHeld & mask) == mapped[3]);
    CHECK(gPad[0].gameLeft[0] == gPad[0].left[0]);
    packets[0][PAD_DATA_LX] = packets[1][PAD_DATA_LY] = 128;
    packets[0][PAD_DATA_BTN_LO] &= ~PAD_UP;
    Pad_Update(); CHECK(!(gPad[0].gameHeld & mask) && !(gPad[1].gameHeld & mask));
    battle.flags = 0; sequence.state = BTL_SEQ_FIGHT;
}
static void test_packet(void) {
    int p, i;
    memset(gPad, 0, sizeof(gPad));
    for (p = 0; p < 2; p++) {
        packets[p][0] = packets[p][1] = 255;
        for (i = 2; i < 6; i++) packets[p][i] = 128;
        gPad[p].socket = p;
        gPad[p].phase = PAD_PHASE_READ;
    }
    packets[1][PORT_CONTROL_MODE_BYTE] = PORT_CONTROL_MODE_WII;
    Pad_Update();
    CHECK(gPad[0].held == 0 && gPad[1].held == 0);
    CHECK(gPad[1].data[PORT_CONTROL_MODE_BYTE] == PORT_CONTROL_MODE_WII);
    packets[1][PORT_CONTROL_MODE_BYTE] = 0;
    Pad_Update();
    CHECK(gPad[1].held == 0);
}
static void test_replay(void) {
    BtlInputChr c;
    int n, i;
    init(&c, 0, 1);
    memset(&c, 0, sizeof(c));
    BtlInput_Init(&c);
    recordCount = 0;
    for (i = 0; i < 70; i++) {
        u32 raw = PORT_PAD_WII;
        if (i == 40 || i == 43) raw |= PAD_RSTICK_LEFT;
        if (i >= 50 && i < 54) raw |= PAD_R2;
        if (i >= 57 && i < 60) raw |= PAD_R3;
        if (i == 62) raw |= PAD_RSTICK_DOWN;
        step(&c, raw);
        trace[i].burst = BtlInput_TestAction(&c, 46, 1);
    }
    n = recordCount;
    memset(&c, 0, sizeof(c));
    BtlInput_Init(&c);
    replay = 1; replayPos = 0;
    for (i = 0; i < n; i++) {
        step(&c, PAD_CROSS); /* deliberately different physical input/mode */
        CHECK(c.input.held == trace[i].buttons);
        CHECK(c.input.cmdHeld == trace[i].commands);
        CHECK(BtlInput_TestAction(&c, 46, 1) == trace[i].burst);
    }
    replay = 0;
}
static void split_step(BtlInputChr *c, u32 raw, u8 extra) {
    gPad[c->pad].data[PORT_CONTROL_MODE_BYTE] = PORT_CONTROL_MODE_SPLIT;
    gPad[c->pad].data[PORT_CONTROL_EXTRA_BYTE] = extra;
    gPad[c->pad].held = raw;
    BtlInput_Sample(c);
    BtlInput_Update(c);
}
static void test_split(void) {
    BtlInputChr c;
    int p, gap, i;
    for (p = 0; p < 2; p++) {
        for (gap = 1; gap <= 10; gap++) {
            init(&c, p, 0);
            for (i = 0; i < 35; i++) split_step(&c, 0, 0);
            split_step(&c, 0, PORT_CONTROL_BURST);
            CHECK(!BtlInput_TestAction(&c, 46, 1));
            CHECK(!(c.input.held & (BTLB_RS_LEFT | BTLB_RS_RIGHT | BTLB_RS_UP2 | BTLB_RS_DOWN2)));
            for (i = 0; i < gap; i++) split_step(&c, 0, 0);
            split_step(&c, 0, PORT_CONTROL_BURST);
            CHECK(!!BtlInput_TestAction(&c, 46, 1) == (gap < BTL_TAP_FRAMES));
            for (i = 0; i < 12; i++) {
                split_step(&c, 0, PORT_CONTROL_BURST);
                CHECK(!BtlInput_TestAction(&c, 46, 1));
            }
        }
        init(&c, p, 0);
        split_step(&c, PAD_RSTICK_LEFT, 0);
        CHECK(BtlInput_TestAction(&c, 97, 1) && !(c.input.held & (BTLB_RS_UP2 | BTLB_RS_DOWN2)));
        split_step(&c, 0, 0); split_step(&c, PAD_RSTICK_LEFT, 0);
        CHECK(!BtlInput_TestAction(&c, 46, 1));
        split_step(&c, 0, PORT_CONTROL_PREV);
        CHECK((c.input.held & BTLB_RS_UP2) && !(c.input.held & (BTLB_RS_LEFT | BTLB_RS_RIGHT)));
        split_step(&c, 0, PORT_CONTROL_NEXT);
        CHECK((c.input.held & BTLB_RS_DOWN2) && !(c.input.held & (BTLB_RS_LEFT | BTLB_RS_RIGHT)));
        split_step(&c, PAD_RSTICK_UP, PORT_CONTROL_BURST);
        CHECK(BtlInput_TestAction(&c, 107, 1));
    }
    /* Replay with different local mode retains split semantics and tap timing. */
    init(&c, 0, 0); recordCount = 0;
    for (i = 0; i < 70; i++) {
        split_step(&c, i >= 55 && i <= 58 ? PAD_RSTICK_LEFT : 0,
                   i == 40 || i == 43 ? PORT_CONTROL_BURST : i == 60 ? PORT_CONTROL_PREV : 0);
        trace[i].burst = BtlInput_TestAction(&c, 46, 1);
    }
    memset(&c, 0, sizeof(c)); BtlInput_Init(&c);
    replay = 1; replayPos = 0;
    for (i = 0; i < 70; i++) {
        step(&c, 0);
        CHECK(c.input.held == trace[i].buttons);
        CHECK(c.input.cmdHeld == trace[i].commands);
        CHECK(BtlInput_TestAction(&c, 46, 1) == trace[i].burst);
    }
    replay = 0;
}
int main(void) {
    int p, i;
    int defaults[] = {2, 1, 0, 3, 4, 5, 6, 7};
    for (p = 0; p < 2; p++) for (i = 0; i < 8; i++) save.key[p][i] = defaults[i];
    test_packet();
    test_battle(0); test_battle(1);
    test_burst(); test_menus(); test_menu_sticks(); test_replay();
    test_split();
    printf("PASS: %d checks (packet, both players, PS2/Wii battle, menu/pause/combat, double taps, AI, replay)\n", checks);
    return 0;
}
