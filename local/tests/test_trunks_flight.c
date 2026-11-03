/* Actual neutral handler + actual movement decisions + actual input queries.
   Model/scene services are stubs; these tests do not claim a rendered gameplay test. */
#include "common.h"
#include "battle/btl_act_d.h"
#include "battle/btl_input.h"
extern s32 BtlInput_TestAction(BtlInputChr *, s32, s32);
extern void BtlAct_Update(void *);
extern int printf(const char *, ...);
extern void exit(int);
extern void *memset(void *, int, u32);
extern void *memcpy(void *, const void *, u32);

static int chara, tech, near, checks, attack, forced, freeChr = 1;
static BtlActDChr fighter;
static BtlActDGauge gauge;
static BtlActDMember member;
static f32 lastMoveSpeed;
static s32 motionId, floorFlag;
typedef s32 (*TestHandler)(BtlActDChr *, s32);
TestHandler gBtlActHandlers[0x140];
#define CHECK(x) do { checks++; if (!(x)) { printf("FAIL %d: %s\n", __LINE__, #x); exit(1); } } while (0)

s32 Battle_GetMode(void) { return 1; }
s32 BtlCharApi_GetChara(s32 id) { return chara; }
s32 BtlSuper_GetId(void *c, s32 slot) { return slot == 3 ? tech : -1; }
s32 BtlChar_TestFlag(void *c, s32 n) { return n == 5 || n == 0xE || (n == 0x13 && near) || (n == 0xF && floorFlag); }
void BtlChar_ClearFlag(void *c, s32 n) {}
void BtlChar_SetFlag(void *c, s32 n) {}
void BtlChar_SetHeldFlag(void *c, s32 n) {}
void BtlChar_SetLookEnabled(void *c, s32 n) {}
s32 BtlChar_IsFree(void *c) { return freeChr; }
void BtlAnim_Play(void *c, s32 anim, f32 blend) { motionId = anim; }
void BtlAnim_Request(void *c, s32 anim, f32 blend) { motionId = anim; }
void BtlAnim_RequestKeep(void *c, s32 anim, f32 blend) { motionId = anim; }
void BtlAnim_PlaySub(void *c, s32 anim) {}
void BtlAnim_SetUnkC8C(void *c, f32 amount) {}
void BtlAnim_AdvanceThen(void *c, s32 anim, f32 blend, s32 flags) {}
void BtlAnim_AdvanceLoop(void *c, s32 flags) {}
s32 BtlAnim_GetId(void *c) { return motionId; }
f32 BtlAct_GetHeight(void *c) { return 100.0f; }
f32 BtlAct_GetFacingRelCam(void *c) { return 0.0f; }
s32 BtlAct_GetPrev(BtlActDChr *c) { return c->prev; }
s32 BtlAct_GetIdleMotion(BtlActDChr *c) { return 0x26; }
f32 BtlUtil_WrapAngle(f32 a) { return a; }
s32 BtlAct_GetCurrent(BtlActDChr *c) { return c->action; }
s32 BtlAct_GetRequested(BtlActDChr *c) { return c->request; }
s32 BtlAct_GetQueued(BtlActDChr *c) { return c->queue[0]; }
void BtlAct_SetQueue(BtlActDChr *c, u32 slot, s32 id) { c->queue[slot] = id; }
void BtlAct_Request(BtlActDChr *c, s32 id) { if (id >= 0) c->request = id; }
s32 BtlDecide_Attack(BtlActDChr *c, u32 mask) { if (attack) c->queue[0] = 0x44; return attack; }
s32 BtlDecide_Common(BtlActDChr *c, s32 mask) { if (forced) c->queue[0] = 0xD3; return forced; }
BtlActDPose *BtlChar_GetPos(BtlActDChr *c) { return (BtlActDPose *)((u8 *)c + 0x10); }
BtlActDGauge *BtlMember_GetActiveGauge(void *c) { return &gauge; }
void *BtlMember_GetActive(void *c) { return &member; }
void BtlMove_Step(void *c, s32 a, s32 b, s32 d, f32 speed, f32 accel) { lastMoveSpeed = speed; }
void BtlMove_ApplyGravity(void *c) {}
void BtlMove_MoveVertical(void *c, f32 speed, f32 accel) {}
s32 BtlMove_IsBlockedByOpponent(void *c) { return 0; }
s32 BtlMove_IsBlastIncoming(void *c, s32 a, s32 b, s32 d, f32 limit) { return 0; }
s32 BtlMember_HasHealth(void *c, s32 amount) { return 0; }
s32 BtlMember_HasKi(void *c, s32 amount) { return 1; }
s32 BtlMember_HasBlast(void *c, s32 amount) { return 1; }
s32 BtlMember_IsKiFull(void *c) { return 1; }
s32 BtlParam_GetFlags(void *c) { return 0; }
s32 BtlParam_GetFlags2(void *c) { return 1; }
s32 BtlParam_GetUnk0(void *c) { return 0; }
s32 BtlParam_GetAmountA(void *c) { return 1000; }
s32 BtlParam_GetAmountB(void *c) { return 1000; }
s32 BtlParam_CanFly(void *c) { return 1; }
s32 BtlOpp_GetSeenAction(void *c) { return 0; }
f32 BtlOpp_GetYawFromFacing(void *c) { return 0; }
void BtlColl_AddActionBit(void *c, s32 action) {}
s32 BtlAct_TestPoweredSkill(void *c, u32 mask) { return 0; }
s32 BtlAct_CheckTechniqueInput(void *c) { return 0; }
s32 BtlAct_CheckSkillInput(void *c) { return 0; }
s32 BtlAct_CheckSwitchInput(void *c) { return 0; }
s32 BtlAct_CheckTransformInput(void *c) { return 0; }
s32 BtlAct_CheckFusionInput(void *c) { return 0; }
s32 BtlAct_GetAction14or16(void *c) { return 0x14; }
f32 BtlMoveParam_GetSpeed(void *c, s32 kind) { return 10.0f; }
f32 BtlAct_ScaleSpeedByApproach(void *c, f32 speed, f32 range) { return speed; }
f32 BtlAct_GetRotYRelCam(void *c) { return 0; }
f32 BtlAct_GetVelDirRelCam(void *c) { return 0; }
f32 BtlUtil_ApproachF(f32 a, f32 b, f32 rate) { return b; }
f32 BtlInput_GetStickY(void *c) { return -1; }
f32 Mathf_Sin(f32 x) { return 0; }
void BtlMove_SetDirection(void *c, s32 mode) {}
void BtlMove_RequestOrbit(void *c, f32 a, f32 b) {}
void BtlMove_TurnYaw(void *c, s32 mode, f32 angle) {}
void BtlCharSnd_PlayCommon(void *c, s32 id) {}
void BtlChar_SetStage(void *c, s32 stage) {}
void BtlChar_ClearFlagRange(void *c, s32 a, s32 b) {}
void BtlChar_ApplyRootYaw(void *c) {}
void ChrCam_EndCut(void *c) {}
void BtlAct_CheckForced(void *c) {}
void BtlAct_ApplyFlag94(void *c) {}
void BtlAct_UpdateGauges(void *c) {}
void BtlAct_UpdateTimers(BtlActDChr *c) { c->actionFrame++; }
void BtlAnim_FlushRequest(void *c) {}
void BtlAnim_FlushRequestKeep(void *c) {}
void BtlAnim_FlushSubToMain(void *c) {}
void BtlAct_PopQueue(BtlActDChr *c) {
    int i;
    for (i = 0; i < 3; i++) c->queue[i] = c->queue[i+1];
    c->queue[3] = -1;
}

static void init(int character, int previous, int skill) {
    int i;
    memset(&fighter, 0, sizeof(fighter));
    fighter.action = 0xB; fighter.prev = previous; fighter.request = -1;
    for (i = 0; i < 4; i++) fighter.queue[i] = -1;
    chara = character; tech = skill; near = 1; attack = forced = 0; freeChr = 1; floorFlag = 0;
    BtlAct_NeutralHandler(&fighter, 0);
    /* Original dispatcher runs ENTER, then UpdateTimers, before the first DECIDE. */
    fighter.actionFrame = 1;
    /* The next fighter tick snapshots current into prev before DECIDE.
       Keeping the cinematic ID here would conceal the Test2 regression. */
    fighter.prev = fighter.action;
}

static int frame(u32 held, u32 cmd, u32 cmdPressed, int close) {
    BtlCharInput *in = &((BtlInputChr *)&fighter)->input;
    int i;
    in->pressed = held & ~in->held; in->prev = in->held;
    in->held = held; in->cmdHeld = cmd; in->cmdPressed = cmdPressed;
    near = close; fighter.request = -1;
    for (i = 0; i < 4; i++) fighter.queue[i] = -1;
    gBtlActHandlers[fighter.action](&fighter, 2);
    fighter.actionFrame++;
    return fighter.request;
}

/* Run the actual dispatcher, including LEAVE, scratch reset, ENTER and RUN. */
static int tick(u32 held, u32 cmd, u32 cmdPressed, int close) {
    BtlCharInput *in = &((BtlInputChr *)&fighter)->input;
    int i;
    fighter.prev = fighter.action;
    in->pressed = held & ~in->held; in->prev = in->held;
    in->held = held; in->cmdHeld = cmd; in->cmdPressed = cmdPressed;
    for (i = 4; i < 8; i++) {
        if (held & (1u << i)) in->count.notHeld.n[i] = 0;
        else if (in->count.notHeld.n[i] < 100) in->count.notHeld.n[i]++;
    }
    near = close; lastMoveSpeed = 0;
    BtlAct_Update(&fighter);
    return fighter.action;
}

int main(void) {
    int i;
    BtlActDChr snapshot;
    gBtlActHandlers[0xB] = BtlAct_NeutralHandler;
    gBtlActHandlers[0xD] = BtlAct_MoveHandler;
    gBtlActHandlers[0xE] = BtlAct_CloseMoveHandler;
    /* Captured first post-cinematic command: unmodified branch picks left step. */
    init(41, 0x12E, 0x163);
    CHECK(fighter.actionFrame == 1);
    CHECK(fighter.prev == 0xB && fighter.work[19] == 5);
    for (i = 0; i < 4; i++) {
        CHECK(frame(2, i ? 0x101 : 0x16850105, i ? 0 : 0x16850105, i < 3) == -1);
    }
    CHECK(frame(0x90110052, 0x101, 0, 0) == 0xF);
    /* Other character, form, skill slot and a missed rush retain the original side step. */
    init(40, 0x12E, 0x163); CHECK(frame(0x52, 0x14850105, 0x14850105, 1) == 0x1C);
    init(42, 0x12E, 0x163); CHECK(frame(0x52, 0x14850105, 0x14850105, 1) == 0x1C);
    init(41, 0x12D, 0x163); CHECK(frame(0x52, 0x14850105, 0x14850105, 1) == 0x1C);
    init(41, 0x11C, 0x163); CHECK(frame(0x52, 0x14850105, 0x14850105, 1) == 0x1C);
    init(41, 0x12E, 0x164); CHECK(frame(0x52, 0x14850105, 0x14850105, 1) == 0x1C);
    init(41, 0xB, 0x163); CHECK(frame(0x52, 0x14850105, 0x14850105, 1) == 0x1C);
    init(41, 0xB, 0x163); CHECK(frame(0x52, 0x14850105, 0x14850105, 0) == 0xF);
    /* Release does not reset the existing action frame or rewrite original flight inputs. */
    init(41, 0x12E, 0x163); CHECK(frame(2, 1, 0, 1) == -1);
    CHECK(frame(0, 0, 0, 1) == -1); CHECK(fighter.actionFrame == 3);
    CHECK(frame(2, 0x14850105, 0x14850105, 1) == -1);
    CHECK(frame(2, 0x101, 0, 1) == -1);
    CHECK(frame(0x52, 0x101, 0, 0) == 0xF);
    init(41, 0x12E, 0x163); CHECK(frame(0, 0, 0, 1) == -1);
    for (i = 0; i < 3; i++) CHECK(frame(0, 0, 0, 0) == -1);
    CHECK(frame(0x52, 0x14850105, 0x14850105, 0) == 0xF);
    /* Original in-flight stop query: releasing DASH keeps its grace period;
       a held direction continues flight even after that period. */
    {
        BtlInputChr *chr = (BtlInputChr *)&fighter;
        chr->input.held = 0;
        chr->input.cmdHeld = 0;
        for (i = 0; i < 6; i++) {
            chr->input.cmdCount.notHeld.n[0] = i;
            CHECK(!BtlInput_TestAction(chr, 6, 1));
        }
        chr->input.cmdCount.notHeld.n[0] = 6;
        CHECK(BtlInput_TestAction(chr, 6, 1));
        chr->input.held = BTLB_LEFT;
        CHECK(!BtlInput_TestAction(chr, 6, 1));
    }
    /* Guard, attack, charge dash and forced reactions still use their original paths. */
    init(41, 0x12E, 0x163); CHECK(frame(3, BTLC_DASH_HELD | BTLC_GUARD_H, 0, 1) == 0x38);
    init(41, 0x12E, 0x163); attack = 1; CHECK(frame(0xA, 1, 0, 1) == 0x44);
    init(41, 0x12E, 0x163); CHECK(frame(0x202, 0xA, 2, 1) == 0x19);
    init(41, 0x12E, 0x163); forced = 1; CHECK(frame(2, 1, 0, 1) == 0xD3);
    /* Re-executing a saved fighter state must produce the same countdown and decision. */
    init(41, 0x12E, 0x163); CHECK(frame(2, 1, 0, 1) == -1);
    memcpy(&snapshot, &fighter, sizeof(fighter));
    for (i = 0; i < 3; i++) CHECK(frame(2, 1, 0, i < 2) == -1);
    CHECK(frame(2, 1, 0, 0) == 0xF);
    memcpy(&fighter, &snapshot, sizeof(fighter));
    for (i = 0; i < 3; i++) CHECK(frame(2, 1, 0, i < 2) == -1);
    CHECK(frame(2, 1, 0, 0) == 0xF);
    /* All eight stick directions move on the first frame with DASH held.
       Carrying the remaining delay through the real dispatcher must not restart it. */
    {
        u32 directions[] = {0x10, 0x20, 0x40, 0x80, 0x50, 0x90, 0x60, 0xA0};
        int d;
        for (d = 0; d < 8; d++) {
            init(41, 0x12E, 0x163);
            CHECK(tick(2 | directions[d], 0x16850105, 0x16850105, 1) == 0xE);
            CHECK(lastMoveSpeed > 0 && fighter.work[19] == 4);
            for (i = 0; i < 3; i++) {
                CHECK(tick(2 | directions[d], 0x101, 0, 1) == 0xE);
                CHECK(lastMoveSpeed > 0 && fighter.work[19] == 3-i);
            }
            CHECK(tick(2 | directions[d], 0x101, 0, 0) == 0xF);
            CHECK(fighter.work[19] == 0);
        }
    }
    /* Crossing from close to free movement must preserve the same four-frame window. */
    init(41, 0x12E, 0x163);
    CHECK(tick(0x52, 0x16850105, 0x16850105, 1) == 0xE);
    CHECK(tick(0x52, 0x101, 0, 0) == 0xD);
    CHECK(fighter.work[19] == 3 && lastMoveSpeed > 0);
    CHECK(tick(0x52, 0x101, 0, 0) == 0xD);
    CHECK(tick(0x52, 0x101, 0, 0) == 0xD);
    CHECK(tick(0x52, 0x101, 0, 0) == 0xF);
    /* Releasing DASH keeps directional movement active and does not invent another press. */
    init(41, 0x12E, 0x163);
    CHECK(tick(0x52, 0x16850105, 0x16850105, 1) == 0xE);
    for (i = 0; i < 6; i++) {
        CHECK(tick(0x50, 0x100, 0, 1) == 0xE);
        CHECK(lastMoveSpeed > 0);
    }
    /* Guard, attacks, charge, vertical movement and charge dash respond in the same
       frame as their original masks, including while a direction and DASH are held. */
    {
        struct OtherInput { u32 held, cmd, press; s32 attacks, expected; } cases[] = {
            {0x53, 0x11, 0, 0, 0x38},
            {0x5A, 0x81, 0, 1, 0x44},
            {0x56, 0x201, 0, 1, 0x44},
            {0x252, 0x100, 0, 0, 0x37},
            {0x852, 1, 0, 0, 0x14},
            {0x1052, 1, 0, 0, 0x15},
            {0x200852, 1, 0, 0, 0x17},
            {0x401052, 1, 0, 0, 0x18},
            {0x202, 0xA, 2, 0, 0x19}
        };
        s32 states[] = {0xB, 0xD, 0xE};
        int s, k, original, delayed;
        for (s = 0; s < 3; s++) for (k = 0; k < (int)(sizeof(cases)/sizeof(cases[0])); k++) {
            init(41, 0x12E, 0x163); fighter.action = states[s]; fighter.work[19] = 0;
            attack = cases[k].attacks;
            original = frame(cases[k].held, cases[k].cmd, cases[k].press, 1);
            if (original != cases[k].expected) printf("Other input state=%x case=%d actual=%x expected=%x\n",states[s],k,original,cases[k].expected);
            CHECK(original == cases[k].expected);
            init(41, 0x12E, 0x163); fighter.action = states[s];
            attack = cases[k].attacks;
            delayed = frame(cases[k].held, cases[k].cmd, cases[k].press, 1);
            CHECK(delayed == original);
        }
    }
    /* An attack interrupts immediately and clears the skill's movement-only context. */
    init(41, 0x12E, 0x163); attack = 1;
    CHECK(tick(0x5A, 0x81, 0, 1) == 0x44);
    CHECK(fighter.work[19] == 0);
    /* Replaying a snapshot that is already in close movement has the same outcome. */
    init(41, 0x12E, 0x163);
    CHECK(tick(0x52, 0x16850105, 0x16850105, 1) == 0xE);
    memcpy(&snapshot, &fighter, sizeof(fighter));
    for (i = 0; i < 3; i++) CHECK(tick(0x52, 0x101, 0, 1) == 0xE);
    CHECK(tick(0x52, 0x101, 0, 0) == 0xF);
    memcpy(&fighter, &snapshot, sizeof(fighter));
    for (i = 0; i < 3; i++) CHECK(tick(0x52, 0x101, 0, 1) == 0xE);
    CHECK(tick(0x52, 0x101, 0, 0) == 0xF);
    printf("Trunks flight: %d integration checks passed\n", checks);
    return 0;
}
