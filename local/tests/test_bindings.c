/* Real SDL/input implementation, virtual controller, and cross-process persistence. */
#include <assert.h>
#include <stdlib.h>
#include <string.h>
#include <SDL3/SDL.h>
const bool *Test_KeyboardState(int *count);
#define SDL_GetKeyboardState Test_KeyboardState
#include "../../port/src/gs/gs_input.c"
#undef SDL_GetKeyboardState
#undef getenv
static bool keyboard[SDL_SCANCODE_COUNT];
const bool *Test_KeyboardState(int *count) { if (count) *count = SDL_SCANCODE_COUNT; return keyboard; }
int GsGpu_Enabled(void) { return 1; }
/* The upstream render-thread/lag hooks are outside this input unit test. */
int Gs_RenderThreaded(void) { return 0; }
int Gs_OnRenderThread(void) { return 0; }
void Port_LagNote(int what, unsigned long long value) { (void)what; (void)value; }
SDL_Window *GsDraw_Window(void) { return NULL; }
int gPortResim;
unsigned gGsFrame, gPortVBlanks;
unsigned char gPad[0x380];
const char *Port_GetEnv(const char *name) { return getenv(name); }
int Port_NetActive(void) { return 0; }
int Port_NetSpectating(void) { return 0; }
int Port_NetMe(void) { return 0; }
void Port_UiNotice(const char *text) { (void)text; }
void *BtlChar_FindByObjId(int id) { return NULL; }
int BtlAct_GetCurrent(void *chr) { return 0; }
static int checks;
#define CHECK(x) do { checks++; if (!(x)) { fprintf(stderr, "FAIL %d: %s\n", __LINE__, #x); exit(1); } } while (0)
static void clear(int p, int split) {
    int a;
    for (a = 0; a < PORT_WII_ACTIONS; a++) CHECK(PortWii_Set(p, split, a, "", 100));
}
static unsigned held(unsigned char *data) { return (~(data[0] | data[1] << 8)) & 65535; }
static void read_pad(unsigned char *data) { CHECK(Port_PadRead(0, data) == 18); }
int main(int argc, char **argv) {
    int p, s, a, range;
    char text[PORT_WII_EXPR_SIZE];
    unsigned char data[18];
    CHECK(SDL_Init(SDL_INIT_GAMEPAD));
    for (p = 0; p < 2; p++) PortInput_ControlMode(p);
    if (argc == 2 && !strcmp(argv[1], "migration")) {
        PortWii_Get(0, 1, 7, text, sizeof(text), &range);
        CHECK(!strcmp(text, "(J | (K & !L)) | (`Controller:A`&`Controller:Left trigger`)") && range == 100);
        PortWii_Get(1, 1, 26, text, sizeof(text), &range);
        CHECK(!strcmp(text, "`Controller:Right trigger`") && range == 75);
        PortInput_Save();
        printf("PASS migration: %d checks, old bindings merged and ranges retained\n", checks);
        return 0;
    }
    if (argc == 2 && (!strcmp(argv[1], "write") || !strcmp(argv[1], "reload"))) {
        for (p = 0; p < 2; p++) for (s = 0; s < 2; s++) for (a = 0; a < PORT_WII_ACTIONS; a++) {
            char expected[100];
            snprintf(expected, sizeof(expected), "J | (K & !L) | `Controller:A`");
            int expected_range = 30 + p * 100 + s * 40 + a;
            if (!strcmp(argv[1], "write")) CHECK(PortWii_Set(p, s, a, expected, expected_range));
            PortWii_Get(p, s, a, text, sizeof(text), &range);
            CHECK(!strcmp(text, expected) && range == expected_range);
        }
        if (!strcmp(argv[1], "write")) {
            *PortInput_ControlSplit(0) = 1; *PortInput_ControlSplit(1) = 0;
            PortInput_Save();
        } else CHECK(*PortInput_ControlSplit(0) == 1 && *PortInput_ControlSplit(1) == 0);
        printf("PASS %s: %d checks; both players, both unified profiles, all 27 actions\n", argv[1], checks);
        return 0;
    }
    for (p = 0; p < 2; p++) for (s = 0; s < 2; s++) clear(p, s);
    sControlMode[0] = 1; sControlSplit[0] = 1; sPadSlot[0] = -1;
    CHECK(PortWii_Set(0, 1, 24, "Q & !E", 100));
    CHECK(PortWii_Set(0, 1, 25, "W | R", 100));
    CHECK(PortWii_Set(0, 1, 26, "T", 100));
    keyboard[SDL_SCANCODE_Q] = true; read_pad(data);
    CHECK(data[17] == PORT_CONTROL_MODE_SPLIT && data[6] == PORT_CONTROL_PREV && held(data) == 0 && data[2] == 128);
    keyboard[SDL_SCANCODE_E] = true; read_pad(data); CHECK(data[6] == 0);
    keyboard[SDL_SCANCODE_W] = true; keyboard[SDL_SCANCODE_T] = true;
    read_pad(data); CHECK(data[6] == (PORT_CONTROL_NEXT | PORT_CONTROL_BURST) && data[2] == 128);
    memset(keyboard, 0, sizeof(keyboard));
    CHECK(PortWii_Set(0, 1, 4, "(J | K) & !L", 100));
    keyboard[SDL_SCANCODE_J] = true; read_pad(data); CHECK(held(data) == B_CROSS);
    keyboard[SDL_SCANCODE_L] = true; read_pad(data); CHECK(held(data) == 0);
    CHECK(PortWii_Set(0, 1, 4, "J | K & !L", 100));
    read_pad(data); CHECK(held(data) == 0); /* Dolphin equal precedence, left associative. */
    CHECK(PortWii_Set(0, 1, 4, "J + K", 50));
    keyboard[SDL_SCANCODE_K] = true; read_pad(data); CHECK(held(data) == 0); /* > 0.5, not >= */
    CHECK(PortWii_Set(0, 1, 4, "J + K", 51)); read_pad(data); CHECK(held(data) == B_CROSS);
    CHECK(PortWii_Set(0, 1, 4, "!J", 100));
    gPortOverlayOpen = 1; memset(keyboard, 0, sizeof(keyboard)); read_pad(data); CHECK(held(data) == 0 && data[6] == 0);
    gPortOverlayOpen = 0; gPortChatTyping = 1; read_pad(data); CHECK(held(data) == 0); gPortChatTyping = 0;
    CHECK(!PortWii_Set(0, 1, 4, "J &", 100));
    CHECK(!PortWii_Set(0, 1, 4, "(J", 100));
    CHECK(!PortWii_Set(0, 1, 4, "`J", 100));
    CHECK(!PortWii_Set(0, 1, 4, "J K", 100));
    CHECK(PortWii_Set(0, 1, 4, "J", 100));
    keyboard[SDL_SCANCODE_J] = true; CHECK(PortWii_KeysHeld(0, 1, keyboard));
    keyboard[SDL_SCANCODE_J] = false; CHECK(!PortWii_KeysHeld(0, 1, keyboard));
    CHECK(PortWii_Set(0, 1, 4, "!J", 100));
    keyboard[SDL_SCANCODE_J] = true; CHECK(PortWii_KeysHeld(0, 1, keyboard));
    memset(keyboard, 0, sizeof(keyboard));
    clear(0, 1);
    SDL_VirtualJoystickDesc desc;
    SDL_INIT_INTERFACE(&desc); desc.type = SDL_JOYSTICK_TYPE_GAMEPAD;
    desc.naxes = SDL_GAMEPAD_AXIS_COUNT; desc.nbuttons = SDL_GAMEPAD_BUTTON_COUNT; desc.name = "Split binding test";
    SDL_JoystickID id = SDL_AttachVirtualJoystick(&desc); CHECK(id != 0);
    SDL_Gamepad *pad = SDL_OpenGamepad(id); CHECK(pad != NULL);
    SDL_Joystick *joy = SDL_GetGamepadJoystick(pad);
    sIds[0] = id; sIdCount = 1; sPadSlot[0] = 0; sDeadzone[0][0] = sDeadzone[0][1] = -1;
    sOpen[0].id = id; sOpen[0].pad = pad;
    SDL_SetJoystickVirtualAxis(joy, SDL_GAMEPAD_AXIS_LEFT_TRIGGER, -32768);
    SDL_SetJoystickVirtualAxis(joy, SDL_GAMEPAD_AXIS_RIGHT_TRIGGER, -32768); SDL_UpdateJoysticks();
    CHECK(PortWii_Set(0, 1, 24, "`Controller:Left shoulder` & `Controller:A`", 100));
    CHECK(PortWii_Set(0, 1, 26, "`Controller:Right trigger`", 100));
    CHECK(PortWii_Set(0, 1, 22, "`Controller:Right X-`", 100));
    CHECK(PortWii_Set(0, 1, 18, "`Controller:Left X-`", 100));
    SDL_SetJoystickVirtualButton(joy, SDL_GAMEPAD_BUTTON_LEFT_SHOULDER, true); SDL_UpdateJoysticks();
    read_pad(data); CHECK(data[6] == 0 && held(data) == 0);
    SDL_SetJoystickVirtualButton(joy, SDL_GAMEPAD_BUTTON_SOUTH, true); SDL_UpdateJoysticks();
    read_pad(data);
    if (data[6] != PORT_CONTROL_PREV || held(data)) fprintf(stderr, "virtual sample extra=%d held=%x A=%d LB=%d slot=%d swallow=%d\n", data[6], held(data), SDL_GetGamepadButton(pad, SDL_GAMEPAD_BUTTON_SOUTH), SDL_GetGamepadButton(pad, SDL_GAMEPAD_BUTTON_LEFT_SHOULDER), sPadSlot[0], sSwallow);
    CHECK(data[6] == PORT_CONTROL_PREV && held(data) == 0);
    SDL_SetJoystickVirtualAxis(joy, SDL_GAMEPAD_AXIS_RIGHT_TRIGGER, 32767);
    SDL_SetJoystickVirtualAxis(joy, SDL_GAMEPAD_AXIS_LEFTX, -32768);
    SDL_SetJoystickVirtualAxis(joy, SDL_GAMEPAD_AXIS_RIGHTX, -32768); SDL_UpdateJoysticks();
    read_pad(data); CHECK(data[6] == (PORT_CONTROL_PREV | PORT_CONTROL_BURST) && data[2] == 0 && data[4] == 0);
    gPortInputCapture = 1; read_pad(data); CHECK(held(data) == 0 && data[6] == 0 && data[2] == 128); gPortInputCapture = 0;
    /* One shared expression genuinely combines keyboard and physical pad state. */
    clear(0, 1);
    CHECK(PortWii_Set(0, 1, 7, "(J & `Controller:A`) | (K & !`Controller:B`)", 100));
    read_pad(data); CHECK(held(data) == 0);
    keyboard[SDL_SCANCODE_J] = true; read_pad(data); CHECK(held(data) == B_TRIANGLE);
    SDL_SetJoystickVirtualButton(joy, SDL_GAMEPAD_BUTTON_SOUTH, false); SDL_UpdateJoysticks();
    read_pad(data); CHECK(held(data) == 0);
    keyboard[SDL_SCANCODE_K] = true; read_pad(data); CHECK(held(data) == B_TRIANGLE);
    SDL_SetJoystickVirtualButton(joy, SDL_GAMEPAD_BUTTON_EAST, true); SDL_UpdateJoysticks();
    read_pad(data); CHECK(held(data) == 0);
    memset(keyboard, 0, sizeof(keyboard));
    /* Long expressions, many unary operators and multiline persistence are bounded. */
    strcpy(text, "J");
    for (a = 0; a < 250; a++) strcat(text, " | (K & !`Controller:B`)");
    CHECK(strlen(text) > 512 && PortWii_Set(0, 1, 7, text, 100));
    keyboard[SDL_SCANCODE_J] = true; read_pad(data); CHECK(held(data) == B_TRIANGLE);
    memset(text, '!', 1100); text[1100] = 'J'; text[1101] = 0;
    CHECK(!PortWii_Set(0, 1, 7, text, 100));
    /* Mouse movement and wheel share the keyboard/mouse device, with frame reset. */
    CHECK(PortWii_Set(0, 1, 7, "`Axis Y-`", 100));
    PortWii_MouseFrame();
    SDL_Event motion = {0}; motion.type = SDL_EVENT_MOUSE_MOTION; motion.motion.yrel = -100;
    PortWii_MouseEvent(&motion); PortWii_MouseFrame(); read_pad(data); CHECK(held(data) == B_TRIANGLE);
    for (a = 0; a < 10; a++) PortWii_MouseFrame(); read_pad(data); CHECK(held(data) == 0);
    CHECK(PortWii_Set(0, 1, 7, "`Wheel Y+`", 100));
    motion.type = SDL_EVENT_MOUSE_WHEEL; motion.wheel.y = 1;
    PortWii_MouseEvent(&motion); PortWii_MouseFrame(); read_pad(data); CHECK(held(data) == B_TRIANGLE);
    gPortTboTyping = 1; read_pad(data); CHECK(held(data) == B_TRIANGLE); gPortTboTyping = 0;
    gPortOverlayOpen = 1; read_pad(data); CHECK(held(data) == 0); gPortOverlayOpen = 0;
    for (a = 0; a < 10; a++) PortWii_MouseFrame();
    CHECK(PortWii_Set(0, 1, 7, "W & !LMENU | F | `Axis Y-`", 100));
    memset(keyboard, 0, sizeof(keyboard)); keyboard[SDL_SCANCODE_W] = true;
    read_pad(data); CHECK(held(data) == B_TRIANGLE);
    keyboard[SDL_SCANCODE_LALT] = true; read_pad(data); CHECK(held(data) == 0);
    keyboard[SDL_SCANCODE_F] = true; read_pad(data); CHECK(held(data) == B_TRIANGLE);
    memset(keyboard, 0, sizeof(keyboard));
    CHECK(PortInput_UiButton(pad, SDL_GAMEPAD_BUTTON_EAST) == SDL_GAMEPAD_BUTTON_SOUTH);
    sPadBtn[0][4] = SDL_GAMEPAD_BUTTON_NORTH;
    CHECK(PortWii_Set(0, 0, 4, "E", 100));
    PortInput_ResetDefaults(0);
    CHECK(sPadBtn[0][4] == SDL_GAMEPAD_BUTTON_NORTH);
    PortWii_Get(0, 0, 4, text, sizeof(text), NULL); CHECK(!strcmp(text, "E"));
    sControlMode[0] = 0; sPadSlot[0] = -1; sKeys[0][4] = SDL_SCANCODE_Q;
    keyboard[SDL_SCANCODE_Q] = true; read_pad(data); CHECK(held(data) == B_CROSS && data[17] == 0 && data[6] == 0);
    SDL_CloseGamepad(pad); SDL_DetachVirtualJoystick(id); SDL_Quit();
    printf("PASS bindings: %d checks, real pad samples, expressions, input gating, virtual controller and reset isolation\n", checks);
}
