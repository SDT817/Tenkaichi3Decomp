#include "ui_zh.h"
// The settings window of the PC build: Dear ImGui over the finished picture. F1 opens and closes it, or START + SELECT
// of a controller, or the key and button of its Controls list (gs_input.c: PortInput_Hotkey).
// Everything it shows lives elsewhere (ui.h): the renderer's settings in gs_gpu.c, the bindings in gs_input.c.
// It runs on the render thread, which owns the window and its events.
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <stdint.h>
#include "imgui.h"
#include "imgui_impl_sdl3.h"
#include "imgui_impl_sdlgpu3.h"
#include "imgui_impl_opengl3.h"
#include "ui.h"
#include "control_bindings.h"
#include "control_profiles.h"
#include <algorithm>
#include "namefont.h"
#include "../port_release.h"
#include "menu_text.h"
#include "menu_translation.h"
#include "../quit_dialog.h"
#include "net_chat.h"
#include "online_lobby.h"
#include "net_lobby.h"
#include "net_update.h"

static int sMeter = -1; // the meter (frame rate, connection): -1 not read yet
static bool meter_on(void);
static int sGL; // 1: the OpenGL back end draws the window (ImGui's OpenGL3 backend, no SDL GPU device)
static char sGpuName[256];

extern "C" {
extern volatile int gPortNetMenuRequest;
void Port_NetOptions(int rollback, int delay); // gs/net.c
void Port_NetRulesSet(int type, int dp, int time); // gs/net.c: the host's battle type, DP limit row, time limit
void Port_NetSpeedSet(int percent);                // ... and the match's speed, 100..200 (set before the rules)
int Port_NetSpeedStandard(void);                   // what a quick match runs at
void Port_NetNameSet(const char *name);         // gs/net.c: this player's name for the match
int Port_IsWide(void);                         // plat_stub.c: the picture is wider than 4:3
int Port_AspectMilli(void);
extern "C" int gPortTboTyping;                     // gs_input.c: a keypad of Tenkaichi Budokai Online takes text
extern "C" int PortInput_TboEvent(const SDL_Event *ev);
extern "C" void PortInput_TboClipboard(void);      // ... and its "Copy Code": onto the clipboard, from this thread
int Port_GameMode(void);                       // a11y_game.c: the game's progress mode (4 the main menu, 80 the port's screens)
const char *Port_OnlineBlocked(void);          // gs/net.c: an update is under way, no new online session (the line), or NULL
int Lobby_Active(void);                        // gs/net_lobby.c: this copy is in a lobby
int Port_Menus43(void);                       // plat_stub.c: the menus are shown at 4:3 in a wider picture
int Port_LateInput(void);                     // plat_stub.c: "Low input lag", the blanks are waited for before the pad read
void Port_LateInputSet(int on);
void Port_Menus43Set(int on);
int Port_HudLayout(void);                      // gs_draw.c: 2 = the HUD is about the middle of the screen
int GsDraw_HudShown(void);                     // ... and 1 while the game is drawing the HUD's side panels
const char *Port_NetName(int player);          // the name of the player of side 0 or 1 ("" outside a match)
int Port_TitleNoticeVisible(void);
int Port_HudSwap(void);                        // the two sides of the HUD are in each other's places on this copy
int Port_NetActive(void);
int Port_NetMe(void);                          // gs/net.c: this copy's side, 0 or 1
void *BtlChar_FindByObjId(int objId);          // the game: the fighter of a side, NULL outside a fight
int Port_NetStats(int *out);                   // gs/net.c: the meter's numbers of an online match
int Port_LobbyOther(void);
extern unsigned gPortLiveBlanks;               // plat_stub.c: vertical blanks the game has gone through
int Port_RollCan(void);                        // gs/state.c
const char *Port_FileRoot(void);               // plat_file.c: the game's data folder
unsigned GsGl_StripTexture(const void *rgba, int w, int h); // gs_gl.c
void GsGl_StripTextureFree(unsigned id);
const char *PortStages_Dir(void);                          // plat_stages.c
const char *PortStages_Name(int index);
int PortStages_Count(void);
const char *PortSongs_Dir(void);                           // plat_songs.c
const char *PortSongs_Name(int index);
int PortSongs_Count(void);
int Port_Setting(const char *name, int def);   // plat_settings.c
void Port_SettingSave(const char *name, int value);
void Port_SettingText(const char *name, const char *def, char *out, int size);
void Port_SettingTextSave(const char *name, const char *value);
void Port_SettingsWrite(void);
int Port_ClashSquare(void);                    // gs_input.c: Square counts as a direction in clashes
void Port_ClashSquareSet(int on);
int Port_ClashSquareX(void);                   // what a press is worth, in quarters of a point (4, 6, 7, 8)
void Port_ClashSquareXSet(int quarters);
extern int gsInterp;                           // gs_draw.c: in-between pictures on (1) / off (0); -1 before the first frame
void Port_SettingsWrite(void);
int Port_LobbyStartCode(int host, const char *code);         // gs/net.c: a code of the matchmaking service (a lobby's)
int Port_LobbyStartQuick(int queue);                         // a quick match: 0 single, 1 team, 2..4 DP battle of 10 / 15 / 20
void Port_LobbyQueuesAsk(void);                              // asks the service how many wait in each queue
void Port_LobbyHelloAsk(void);                               // asks it whether this release is new enough
int Port_LobbyRelease(int *min, int *latest);                // this release's number; the oldest let in and the newest (0: not known)
int Port_LobbyQueueWaiting(int queue);                       // ... as last heard, -1 if not known
const char *Port_LobbyCode(void);                            // the host's room code, "" until it is known
const char *Port_LobbyError(void);                           // why the matchmaking failed (state -3)
int Port_LobbyRelayed(void);                                 // the other player was reached through the relay
int Port_LobbyPoll(void);
int Port_LobbyCheckingData(void);                           // a start waits for this game's gameplay fingerprint
const char *Port_LobbyQuickRefusal(void);                   // why no quick match: NULL none, "" data being checked
void Port_LobbyCancel(void);
void Port_LobbyLaunch(void);
int Port_NetSpectating(void);                                // this copy watches a match
void Port_NetSpecLeave(void);                                // ... stop watching (at the game's next blank)
void Port_NetSpecViewSet(int view);                          // ... 0 player 1's view, 1 player 2's, 2 both (split)
int Port_NetSpecView(void);
int Port_NetSpecStatus(int *out);                            // ... catching up (%), waiting, desync blank
int Port_NetWatchers(void);                                  // how many watch this match (the players)
const char *Port_NetWatcher(int i);                          // ... their names
}
static bool sReady, sOpen;
static MenuTranslationOption sLanguages[256];
static int sLanguageCount, sLanguageChoice;
static bool sLanguageRestartPending;
static bool sNet;                              // the open window is the online screen (Dragon Net Battle), not the settings
// A spectator's own pause menu is the game's (src/menu/port_tbo.c, PortTbo_SpecDraw): Esc, or the test's moment, asks
// for it here; the controller's START and the key bound to it reach it through the pad.
extern "C" volatile int gPortSpecMenuAsk;
volatile int gPortSpecMenuAsk;
extern "C" void Port_UiNotice(const char *text);
static void spec_view_next(void);               // watching a match: the next view (player 1, player 2, both)
static const char *spec_view_name(int view);
static int sForceTab = -1;                     // BT3_UI_OPEN=<tab>: open at start on that tab (testing)
static int sCapKind, sCapPlayer, sCapAction;   // waiting for a key (1) or a controller button (2) to bind
static Uint64 sCapUntil;                       // ... until then: a controller has no button that is not a binding, so the wait ends by itself
static bool sQuit;                             // the question before the game closes is up
static bool sQuitNo;                           // ... and Esc answered it: no
static bool sPadHold;                          // the controller does not work the window: a binding is waited for, or its button is still down
static int sTab;                               // the settings tab that is open (the shoulder buttons go to its neighbours)
static int sControlPlayer;
static bool sPadTab;                           // the shoulder buttons changed the tab this frame
static SDL_GPUDevice *sDevice;
// The online chat (net_chat.c): its key opens a line to type, Enter sends it, Esc puts it away.
static bool sChat;                             // a line is being typed
static bool sChatFocus;                        // ... and its field takes the keyboard next frame
static bool sChatKeyHeld;                      // ... and the key that opened it is still down (its letter is not typed)
static bool sChatSoon;                         // the last Enter came within a second of the line before: not sent
static char sChatBuf[CHAT_TEXT + 1];
static void chat_close(void);

/* Name strips (gamedata/stages/names.rgba and gamedata/songs/names.rgba): the names of the stages and tracks added
   from outside the disc, drawn by the port over the menu in the game's own lettering. Raw RGBA, a 12-byte header
   (w, h, count) and then `count` images of w x h stacked. */
static SDL_GPUTexture *sNameTex, *sSongTex;
static uint32_t sNameW, sNameH, sNameCount, sSongW, sSongH, sSongCount;

static uint8_t *read_strip(const char *path, size_t *bytes, uint32_t *w, uint32_t *h, uint32_t *count) {
    FILE *fp = fopen(path, "rb");
    uint32_t hdr[3];
    uint8_t *pix;

    if (fp == NULL) {
        return NULL;
    }
    if (fread(hdr, sizeof(hdr), 1, fp) != 1 || hdr[0] == 0 || hdr[1] == 0 || hdr[2] == 0) {
        fclose(fp);
        return NULL;
    }
    *w = hdr[0];
    *h = hdr[1];
    *count = hdr[2];
    *bytes = (size_t)hdr[0] * hdr[1] * hdr[2] * 4;
    pix = (uint8_t *)malloc(*bytes);
    if (pix == NULL || fread(pix, 1, *bytes, fp) != *bytes) {
        free(pix);
        fclose(fp);
        return NULL;
    }
    fclose(fp);
    return pix;
}

static SDL_GPUTexture *make_strip(uint8_t *pix, size_t bytes, uint32_t w, uint32_t h, uint32_t count) {
    SDL_GPUTextureCreateInfo ci;
    SDL_GPUTransferBufferCreateInfo tbi;
    SDL_GPUTransferBuffer *tb;
    SDL_GPUCommandBuffer *cmd;
    SDL_GPUCopyPass *cp;
    SDL_GPUTextureTransferInfo src;
    SDL_GPUTextureRegion dst;
    SDL_GPUTexture *tex;
    void *map;

    if (sGL) { // the OpenGL back end: a GL texture, its name carried in the pointer (ImGui's OpenGL3 backend takes it so)
        unsigned id = GsGl_StripTexture(pix, (int)w, (int)(h * count));
        free(pix);
        return (SDL_GPUTexture *)(intptr_t)id;
    }
    SDL_zero(ci);
    ci.type = SDL_GPU_TEXTURETYPE_2D;
    ci.format = SDL_GPU_TEXTUREFORMAT_R8G8B8A8_UNORM;
    ci.width = w;
    ci.height = h * count;
    ci.layer_count_or_depth = 1;
    ci.num_levels = 1;
    ci.usage = SDL_GPU_TEXTUREUSAGE_SAMPLER;
    tex = SDL_CreateGPUTexture(sDevice, &ci);
    if (tex == NULL) {
        free(pix);
        return NULL;
    }
    SDL_zero(tbi);
    tbi.usage = SDL_GPU_TRANSFERBUFFERUSAGE_UPLOAD;
    tbi.size = (Uint32)bytes;
    tb = SDL_CreateGPUTransferBuffer(sDevice, &tbi);
    map = SDL_MapGPUTransferBuffer(sDevice, tb, false);
    memcpy(map, pix, bytes);
    SDL_UnmapGPUTransferBuffer(sDevice, tb);
    free(pix);
    cmd = SDL_AcquireGPUCommandBuffer(sDevice);
    cp = SDL_BeginGPUCopyPass(cmd);
    SDL_zero(src);
    src.transfer_buffer = tb;
    src.pixels_per_row = w;
    src.rows_per_layer = h * count;
    SDL_zero(dst);
    dst.texture = tex;
    dst.w = w;
    dst.h = h * count;
    dst.d = 1;
    SDL_UploadToGPUTexture(cp, &src, &dst, false);
    SDL_EndGPUCopyPass(cp);
    SDL_SubmitGPUCommandBuffer(cmd);
    SDL_ReleaseGPUTransferBuffer(sDevice, tb);
    return tex;
}

static SDL_GPUTexture *load_strip(const char *env, const char *rel, uint32_t *w, uint32_t *h, uint32_t *count,
                                  const char *what) {
    const char *paths[3];
    uint8_t *pix = NULL;
    size_t bytes = 0;
    SDL_GPUTexture *tex;
    uint32_t i;

    char inData[600];
    // in the stages / songs folder (plat_extras.c); the environment variable names another file
    snprintf(inData, sizeof(inData), "%s", rel);
    paths[0] = getenv(env);
    paths[1] = inData;
    paths[2] = NULL;
    for (i = 0; i < 3 && pix == NULL; i++) {
        if (paths[i] != NULL) {
            pix = read_strip(paths[i], &bytes, w, h, count);
        }
    }
    if (pix == NULL) {
        return NULL;
    }
    tex = make_strip(pix, bytes, *w, *h, *count);
    if (tex != NULL) {
        fprintf(stderr, "bt3: %s overlay: %u names, %ux%u each\n", what, *count, *w, *h);
    }
    return tex;
}

// ---- the side bars ----
// Where the picture is narrower than the window (a 4:3 picture, or "菜单使用 4:3 比例", in a wide window) the sides are
// black, or with "Side bars: Border" a panel with a border along the picture. Two pictures: the border (trim.png),
// kept in proportion at the picture's edge and as high as the picture, and the plain panel (fill.png), stretched
// over the rest, so a bar of any width looks right. Both are drawn as they are on the left and mirrored on the right.
// The program carries a gold set (port/assets/bars, art by the project's owner: 34 x 720 and 126 x 720). A player
// replaces it by putting a trim.png and / or a fill.png of any size into a folder "bars" next to the game.
#include "bars_png.h"
static SDL_GPUTexture *sBarTrim, *sBarFill;
static int sBars = -1; // 0 black, 1 the border, 2 the border with the fight panels; -1 not read yet
static int sBarsTried;
static int sChatSize = -1; // 0 = compact, 1 = normal, 2 = large; -1 = not read yet

static float sBarTrimShape = 34.0f / 720.0f; // the border's width over its height

static SDL_GPUTexture *bar_texture(const char *file, const unsigned char *png, size_t size, float *shape) {
    SDL_Surface *s = SDL_LoadPNG(file), *rgba; // the player's own picture, if there is one
    if (s != NULL) {
        fprintf(stderr, "bt3: side bars: %s, %d x %d\n", file, s->w, s->h);
    } else {
        s = SDL_LoadPNG_IO(SDL_IOFromConstMem(png, size), true);
    }
    uint8_t *pix;
    size_t bytes;
    if (s == NULL) {
        return NULL;
    }
    rgba = SDL_ConvertSurface(s, SDL_PIXELFORMAT_RGBA32);
    SDL_DestroySurface(s);
    if (rgba == NULL) {
        return NULL;
    }
    if (shape != NULL && rgba->h > 0) {
        *shape = (float)rgba->w / (float)rgba->h;
    }
    bytes = (size_t)rgba->w * rgba->h * 4;
    pix = (uint8_t *)malloc(bytes);
    for (int y = 0; pix != NULL && y < rgba->h; y++) {
        memcpy(pix + (size_t)y * rgba->w * 4, (const uint8_t *)rgba->pixels + (size_t)y * rgba->pitch, (size_t)rgba->w * 4);
    }
    SDL_GPUTexture *tex = pix != NULL ? make_strip(pix, bytes, (uint32_t)rgba->w, (uint32_t)rgba->h, 1) : NULL;
    SDL_DestroySurface(rgba);
    return tex;
}

static bool bars_on(void) {
    if (sBars < 0) {
        sBars = Port_Setting("side_bars", 0);
        sBars = sBars < 0 ? 0 : sBars > 2 ? 2 : sBars;
    }
    return sBars != 0 && gUiPresentX > 0 && gUiPresentW > 0 && gUiPresentH > 0;
}

// For the fight panels (fight_panels_ui.cpp): textures of their own and the display faces.
static ImFont *sFontBold, *sTitleFont;
static bool sMeterHover, sMeterDrag;
static bool meter_on(void);
SDL_GPUTexture *Ui_Texture(uint8_t *pix, uint32_t w, uint32_t h) {
    return make_strip(pix, (size_t)w * h * 4, w, h, 1);
}
void Ui_TextureFree(SDL_GPUTexture *tex) {
    if (tex == NULL) {
        return;
    }
    if (sGL) {
        GsGl_StripTextureFree((unsigned)(intptr_t)tex);
    } else {
        SDL_ReleaseGPUTexture(sDevice, tex);
    }
}
ImFont *Ui_FontBold(void) { return sFontBold; }
bool FightPanels_Draw(ImDrawList *dl, float lx, float rx, float y0, float y1, float bar, float trim);

// The fight panels' two faces ("姓名字体", "形态字体" in the settings): fonts of the game's own list (fonts.tsv,
// as the Menu font and the Dialogue / UI font), checked as those are (menu_text.c) and saved by their id; "默认"
// is the first of the list that can be used. A choice is loaded into the font atlas between two frames (fonts_apply).
struct PanelFont {
    const char *setting;
    ImFont *font;
    int choice;  // in use (0: Default)
    int pending; // chosen, loaded before the next frame (-1: nothing)
};
static PanelFont sPanelFont[2] = {{"panel_name_font_id", NULL, 0, -1}, {"panel_form_font_id", NULL, 0, -1}};
ImFont *Ui_FontName(void) { return sPanelFont[0].font; }
ImFont *Ui_FontForm(void) { return sPanelFont[1].font; }

// A choice of the list as an ImGui font (NULL: none can be used).
static ImFont *panel_font_load(int choice) {
    char path[1400];
    ImGuiIO &io = ImGui::GetIO();
    for (int i = choice > 0 ? choice : 1; i < MenuText_FontCount(); i++) {
        if (MenuText_FontFile(i, path, sizeof(path))) {
            return io.Fonts->AddFontFromFileTTF(path, 48.0f);
        }
        if (choice > 0) {
            break;
        }
    }
    return NULL;
}

static void fonts_apply(void) {
    for (PanelFont &pf : sPanelFont) {
        if (pf.pending < 0) {
            continue;
        }
        ImFont *f = panel_font_load(pf.pending);
        if (f != NULL) {
            if (pf.font != NULL) {
                ImGui::GetIO().Fonts->RemoveFont(pf.font);
            }
            pf.font = f;
            pf.choice = pf.pending;
            Port_SettingSave(pf.setting, MenuText_FontId(pf.choice));
            Port_SettingsWrite();
        }
        pf.pending = -1;
    }
}

// A combo of the game's fonts; the choice is loaded before the next frame.
static void font_picker(const char *label, PanelFont &pf, const char *tip) {
    if (ImGui::BeginCombo(label, pf.choice > 0 ? MenuText_FontName(pf.choice) : "默认")) {
        if (ImGui::Selectable("默认", pf.choice == 0)) {
            pf.pending = 0;
        }
        for (int i = 1; i < MenuText_FontCount(); i++) {
            ImGui::PushID(i);
            if (ImGui::Selectable(MenuText_FontName(i), pf.choice == i)) {
                pf.pending = i;
            }
            ImGui::PopID();
        }
        ImGui::EndCombo();
    }
    ImGui::SetItemTooltip("%s", tip);
}

static void bars_draw(void) {
    if (!sBarsTried) {
        sBarsTried = 1;
        sBarTrim = bar_texture("bars/trim.png", kBarsTrimPng, sizeof(kBarsTrimPng), &sBarTrimShape);
        sBarFill = bar_texture("bars/fill.png", kBarsFillPng, sizeof(kBarsFillPng), NULL);
    }
    if (sBarTrim == NULL || sBarFill == NULL) {
        return;
    }
    ImDrawList *dl = ImGui::GetBackgroundDrawList();
    float y0 = (float)gUiPresentY, y1 = y0 + (float)gUiPresentH;
    float bar = (float)gUiPresentX; // the width of each side
    float trim = (float)gUiPresentH * sBarTrimShape;
    float u0 = 0.0f;
    if (trim > bar) { // a bar narrower than the border: the border's inner part
        u0 = 1.0f - bar / trim;
        trim = bar;
    }
    float lx = (float)gUiPresentX, rx = lx + (float)gUiPresentW; // the picture's two edges
    ImTextureRef tt((ImTextureID)(intptr_t)sBarTrim), ft((ImTextureID)(intptr_t)sBarFill);
    if (bar > trim) {
        dl->AddImage(ft, ImVec2(lx - bar, y0), ImVec2(lx - trim, y1), ImVec2(0.0f, 0.0f), ImVec2(1.0f, 1.0f));
        dl->AddImage(ft, ImVec2(rx + trim, y0), ImVec2(rx + bar, y1), ImVec2(1.0f, 0.0f), ImVec2(0.0f, 1.0f));
        // In a fight: each side's fighter over the plain panel, with the border along the picture at half its size
        // (in proportion, twice down the height) so the fighter has more room (asked for).
        const int tiles = 2;
        float thin = trim / tiles;
        if (sBars == 2 && FightPanels_Draw(dl, lx, rx, y0, y1, bar, thin)) {
            float th = (y1 - y0) / tiles;
            for (int i = 0; i < tiles; i++) {
                float a = y0 + th * i, b = a + th;
                dl->AddImage(tt, ImVec2(lx - thin, a), ImVec2(lx, b), ImVec2(u0, 0.0f), ImVec2(1.0f, 1.0f));
                dl->AddImage(tt, ImVec2(rx, a), ImVec2(rx + thin, b), ImVec2(1.0f, 0.0f), ImVec2(u0, 1.0f));
            }
            return;
        }
    }
    dl->AddImage(tt, ImVec2(lx - trim, y0), ImVec2(lx, y1), ImVec2(u0, 0.0f), ImVec2(1.0f, 1.0f));
    dl->AddImage(tt, ImVec2(rx, y0), ImVec2(rx + trim, y1), ImVec2(1.0f, 0.0f), ImVec2(u0, 1.0f));
}

static void load_strips(void) {
    char path[600];
    // The names of added stages and songs are drawn by this overlay, over the menu: from a strip of pre-rendered
    // names if the install script made one (names.rgba in the folder), else as text (frame_build). Either way the
    // game leaves the name to the overlay, so the flags are set whenever the overlay exists.
    snprintf(path, sizeof(path), "%s/names.rgba", PortStages_Dir());
    sNameTex = PortStages_Dir()[0] != '\0' ? load_strip("BT3_STAGE_NAMES", path, &sNameW, &sNameH, &sNameCount, "stage-name") : NULL;
    snprintf(path, sizeof(path), "%s/names.rgba", PortSongs_Dir());
    sSongTex = PortSongs_Dir()[0] != '\0' ? load_strip("BT3_SONG_NAMES", path, &sSongW, &sSongH, &sSongCount, "song-name") : NULL;
    if (sNameTex == NULL) { sNameCount = 0; }
    if (sSongTex == NULL) { sSongCount = 0; }
    gUiNameReady = 1;
    gUiSongReady = 1;
}

// The size of the windows drawn here: the style below and every width written in this file are for a picture 1080
// pixels high, and a taller one makes them that much larger (2880 x 1800: 1.67), times the player's "Menu size"
// (setting ui_scale, in percent, 100 by default). U() is a width or height of this file at that size.
static float sUiScale = 1.0f;
static int sUiScalePct = -1;  // (the setting, read once)
static ImGuiStyle sBaseStyle; // (as style() makes it)
static inline float U(float v) { return v * sUiScale; }

static void ui_scale_apply(void) {
    ImGuiIO &io = ImGui::GetIO();
    float s = io.DisplaySize.y > 1080.0f ? io.DisplaySize.y / 1080.0f : 1.0f;
    if (sUiScalePct < 0) {
        sUiScalePct = Port_Setting("ui_scale", 100);
    }
    s *= (float)sUiScalePct / 100.0f;
    s = s < 0.5f ? 0.5f : s > 4.0f ? 4.0f : s;
    if (s != sUiScale) {
        ImGuiStyle &st = ImGui::GetStyle();
        float base = st.FontSizeBase;
        sUiScale = s;
        st = sBaseStyle;
        st.FontSizeBase = base;
        st.ScaleAllSizes(s);
        st.FontScaleMain = s;
    }
}

static void style() {
    ImGuiStyle &st = ImGui::GetStyle();
    ImGui::StyleColorsDark();
    st.WindowRounding = 10.0f;
    st.FrameRounding = 6.0f;
    st.GrabRounding = 6.0f;
    st.TabRounding = 6.0f;
    st.PopupRounding = 6.0f;
    st.WindowPadding = ImVec2(18.0f, 16.0f);
    st.FramePadding = ImVec2(10.0f, 6.0f);
    st.ItemSpacing = ImVec2(10.0f, 9.0f);
    st.WindowBorderSize = 0.0f;
    st.WindowTitleAlign = ImVec2(0.5f, 0.5f);
    ImVec4 *c = st.Colors;
    const ImVec4 accent(0.96f, 0.55f, 0.13f, 1.0f), accentDim(0.96f, 0.55f, 0.13f, 0.55f);
    c[ImGuiCol_WindowBg] = ImVec4(0.07f, 0.08f, 0.11f, 0.96f);
    c[ImGuiCol_TitleBg] = c[ImGuiCol_TitleBgActive] = ImVec4(0.10f, 0.12f, 0.17f, 1.0f);
    c[ImGuiCol_FrameBg] = ImVec4(0.15f, 0.17f, 0.23f, 1.0f);
    c[ImGuiCol_FrameBgHovered] = ImVec4(0.21f, 0.24f, 0.32f, 1.0f);
    c[ImGuiCol_FrameBgActive] = ImVec4(0.26f, 0.29f, 0.38f, 1.0f);
    c[ImGuiCol_Button] = ImVec4(0.17f, 0.20f, 0.27f, 1.0f);
    c[ImGuiCol_ButtonHovered] = accentDim;
    c[ImGuiCol_ButtonActive] = accent;
    c[ImGuiCol_CheckMark] = c[ImGuiCol_SliderGrab] = c[ImGuiCol_SliderGrabActive] = accent;
    c[ImGuiCol_Header] = ImVec4(0.96f, 0.55f, 0.13f, 0.30f);
    c[ImGuiCol_HeaderHovered] = accentDim;
    c[ImGuiCol_HeaderActive] = accent;
    c[ImGuiCol_Tab] = ImVec4(0.13f, 0.15f, 0.20f, 1.0f);
    c[ImGuiCol_TabHovered] = accentDim;
    c[ImGuiCol_TabSelected] = ImVec4(0.96f, 0.55f, 0.13f, 0.80f);
    c[ImGuiCol_PopupBg] = ImVec4(0.09f, 0.10f, 0.14f, 0.98f);
    c[ImGuiCol_TableRowBgAlt] = ImVec4(1.0f, 1.0f, 1.0f, 0.03f);
    sBaseStyle = st;
    sUiScale = 1.0f;
}

static void language_init() {
    const char *override = getenv("BT3_MENU_LANG");
    char saved[16];
    Port_SettingText("menu_lang", "", saved, sizeof(saved));
    sLanguageCount = MenuTranslation_Available(sLanguages, (int)(sizeof(sLanguages) / sizeof(sLanguages[0])));
    sLanguageChoice = 0;
    const char *preferred = override != NULL && override[0] != '\0' ? override : saved[0] != '\0' ? saved : "en";
    for (int i = 0; i < sLanguageCount; i++) if (strcmp(sLanguages[i].locale, preferred) == 0) sLanguageChoice = i;
}

extern "C" void Ui_LanguageChosen(const char *locale) {
    if (locale == NULL) return;
    for (int i = 0; i < sLanguageCount; i++) {
        if (strcmp(sLanguages[i].locale, locale) == 0) {
            sLanguageChoice = i;
            sLanguageRestartPending = false;
            break;
        }
    }
}

static void language_choose(int choice) {
    if (choice < 0 || choice >= sLanguageCount) return;
    MenuTranslation_SaveChoice(sLanguages[choice].locale);
    sLanguageChoice = choice;
    sLanguageRestartPending = true;
}

int Ui_Init(SDL_Window *window, SDL_GPUDevice *device, void *gl_context, const char *gpu_name) {
    static const char *fonts[] = { // a proportional system font if there is one; else the library's built-in font
        "C:\\Windows\\Fonts\\msyh.ttc", "C:\\Windows\\Fonts\\simhei.ttf",
        "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
        "/usr/share/fonts/TTF/DejaVuSans.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/noto/NotoSans-Regular.ttf", "/usr/share/fonts/truetype/noto/NotoSans-Regular.ttf",
        "/usr/share/fonts/liberation/LiberationSans-Regular.ttf", "C:\\Windows\\Fonts\\segoeui.ttf",
    };
    ImGui_ImplSDLGPU3_InitInfo info;

    snprintf(sGpuName, sizeof(sGpuName), "%s", gpu_name && gpu_name[0] ? gpu_name : "不可用");

    IMGUI_CHECKVERSION();
    ImGui::CreateContext();
    ImGuiIO &io = ImGui::GetIO();
    io.IniFilename = NULL; // no window-layout file next to the game
    io.ConfigFlags |= ImGuiConfigFlags_NavEnableKeyboard | ImGuiConfigFlags_NavEnableGamepad; // (a controller opens it too: START + SELECT)
    style();
    Update_Cleanup(); // (the files the last update replaced, kept until this start: gs/net_update.c)
    for (size_t i = 0; i < sizeof(fonts) / sizeof(fonts[0]); i++) {
        FILE *fp = fopen(fonts[i], "rb");
        if (fp != NULL) {
            fclose(fp);
            io.Fonts->AddFontFromFileTTF(fonts[i], 18.0f);
            break;
        }
    }
    { // the fight panels' faces: the two chosen ones (sPanelFont), and the list's first where one cannot be had
        if (io.Fonts->Fonts.Size == 0) {
            io.Fonts->AddFontDefault(); // (the window's font stays the first)
        }
        sFontBold = panel_font_load(0);
        {
            char path[1400];
            snprintf(path, sizeof(path), "%sfonts/bt3cn-rounded-bold.ttf", SDL_GetBasePath());
            sTitleFont = io.Fonts->AddFontFromFileTTF(path, 48.0f);
        }
        for (PanelFont &pf : sPanelFont) {
            pf.choice = MenuText_FontChoice(Port_Setting(pf.setting, 0));
            pf.font = panel_font_load(pf.choice);
        }
    }
    if (device == NULL) { // the OpenGL back end (gs_gl.c), with its context current
        sGL = 1;
        if (!ImGui_ImplSDL3_InitForOpenGL(window, (SDL_GLContext)gl_context) || !ImGui_ImplOpenGL3_Init("#version 330 core")) {
            return 0;
        }
    } else {
        if (!ImGui_ImplSDL3_InitForSDLGPU(window)) {
            return 0;
        }
        info.Device = device;
        info.ColorTargetFormat = SDL_GetGPUSwapchainTextureFormat(device, window);
        info.MSAASamples = SDL_GPU_SAMPLECOUNT_1;
        if (!ImGui_ImplSDLGPU3_Init(&info)) {
            return 0;
        }
    }
    ImGui_ImplSDL3_SetGamepadMode(ImGui_ImplSDL3_GamepadMode_AutoAll, NULL, 0); // any connected controller works the window
    sDevice = device;
    sReady = true;
    language_init();
    load_strips(); /* the stage- and song-name overlays; the ready flags stay 0 if there is no strip */
    if (getenv("BT3_UI_OPEN") != NULL && !MenuTranslation_BootPending()) {
        sForceTab = atoi(getenv("BT3_UI_OPEN"));
        if (sForceTab == 9) { // testing: the online screen
            sForceTab = -1;
            gPortNetMenuRequest = 1;
        }
        if (sForceTab == 8) { // testing: the exit question
            sForceTab = -1;
            sQuit = true;
            PortQuit_Request();
        }
        if (sForceTab == 10) { sForceTab = 8; } // testing: About (8 and 9 retain their earlier meanings)
        sOpen = !sQuit;
        gPortOverlayOpen = 1;
    }
    return 1;
}

// The game gets nothing from keyboard or controller while the window or the exit question is up; and the button
// that closed either is not the game's.
static void input_owner(void) {
    int up = sOpen || sQuit;
    if (gPortOverlayOpen && !up) {
        PortInput_Swallow();
    }
    gPortOverlayOpen = up;
}

static void set_open(bool open) {
    WiiProfiles::Cancel();
    PortWii_Cancel();
    if (open && sChat) {
        chat_close();
    }
    sOpen = open;
    sNet = false;
    sCapKind = 0;
    gPortInputCapture = 0;
    input_owner();
}

static void capture(int kind, int player, int action) {
    sCapKind = kind; sCapPlayer = player; sCapAction = action; gPortInputCapture = 1;
    sCapUntil = SDL_GetTicks() + 5000;
    sPadHold = true;
}

// The Controls page uses keyboard/mouse navigation while physical pad input stays
// available to the binding editor and live tests. Restore navigation on other pages.
static void gamepad_navigation(void) {
    if (sPadHold || (sChat && !sOpen) || (sOpen && !sNet && (sTab == 4 || sForceTab == 4))) {
        ImGui::GetIO().ConfigFlags &= ~ImGuiConfigFlags_NavEnableGamepad;
    } else {
        ImGui::GetIO().ConfigFlags |= ImGuiConfigFlags_NavEnableGamepad;
    }
}

// A controller button pressed in the window (not while it waits for a binding, a list is open or a field is edited).
static bool pad_pressed(ImGuiKey key) {
    return !(sOpen && !sNet && (sTab == 4 || sForceTab == 4)) && sCapKind == 0 && !sPadHold && !sQuit && !ImGui::IsAnyItemActive() &&
           !ImGui::IsPopupOpen("", ImGuiPopupFlags_AnyPopupId | ImGuiPopupFlags_AnyPopupLevel) && ImGui::IsKeyPressed(key, false);
}

extern "C" void PortA11y_Say(const char *text, int flags);
extern "C" const char *PortA11y_Label(const char *label);
static void say_quit_button(int which, int flags);

int Ui_QuitAsk(void) {
    if (!sReady) {
        return 0;
    }
    if (sQuit) { return 1; }
    if (sOpen) { set_open(false); }
    sQuit = true;
    PortQuit_Request();
    input_owner();
    const char *translated = MenuTranslation_PortText(PORT_TEXT_QUIT_CONFIRM);
    PortA11y_Say(translated ? translated : PortA11y_Label("要退出游戏吗？未保存的进度将丢失。"), 1);
    say_quit_button(1, 0);
    PortA11y_Say(PortA11y_Label("Left and right choose, Enter confirms, Escape goes back to the game"), 0);
    return 1;
}

// The screen reader (a11y.c): it cannot see this window's question, which is drawn and not one of the game's screens,
// so the question, the button under the keyboard's focus and the keys are said here. Nothing while it is off.
static void say_quit_button(int which, int flags) {
    char text[128], pos[32];
    snprintf(pos, sizeof(pos), PortA11y_Label(", %d of %d"), which + 1, 2);
    snprintf(text, sizeof(text), "%s%s", PortA11y_Label(which == 0 ? "退出" : "取消"), pos);
    PortA11y_Say(text, flags);
}

static void build_quit(void) {
    static int said = -1; // the button last said: 0 Exit, 1 Cancel
    ImGuiIO &io = ImGui::GetIO();
    bool stay = sQuitNo;
    int focus = -1;

    sQuitNo = false;
    if (!ImGui::IsPopupOpen("退出游戏")) {
        ImGui::OpenPopup("退出游戏");
    }
    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.5f), ImGuiCond_Always, ImVec2(0.5f, 0.5f));
    if (ImGui::BeginPopupModal("退出游戏", NULL, ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoMove | ImGuiWindowFlags_NoSavedSettings)) {
        const char *translated = MenuTranslation_PortText(PORT_TEXT_QUIT_CONFIRM);
        const char *kAsk = translated ? translated : "Close the game?\nUnsaved progress will be lost.";
        // the two buttons under the middle of the question (the window is as wide as its text)
        float line = ImGui::CalcTextSize(kAsk).x, pair = U(140.0f) * 2.0f + ImGui::GetStyle().ItemSpacing.x;
        ImGui::TextUnformatted(kAsk);
        ImGui::Spacing();
        if (line > pair) {
            ImGui::SetCursorPosX(ImGui::GetCursorPosX() + (line - pair) * 0.5f);
        }
        if (ImGui::Button("退出", ImVec2(U(140.0f), 0.0f))) {
            exit(0);
        }
        focus = ImGui::IsItemFocused() ? 0 : focus;
        ImGui::SameLine();
        if (ImGui::Button("取消", ImVec2(U(140.0f), 0.0f)) || ImGui::IsKeyPressed(ImGuiKey_GamepadFaceRight, false)) {
            stay = true;
        }
        focus = ImGui::IsItemFocused() ? 1 : focus;
        if (ImGui::IsWindowAppearing()) {
            ImGui::SetItemDefaultFocus(); // (on Cancel: a second press of the same button does not close the game)
            PortA11y_Say(translated ? translated : PortA11y_Label("要退出游戏吗？未保存的进度将丢失。"), 1);
            say_quit_button(1, 0);
            PortA11y_Say(PortA11y_Label("Left and right choose, Enter confirms, Escape goes back to the game"), 0);
            said = 1;
        } else if (focus >= 0 && focus != said) {
            say_quit_button(focus, 1);
            said = focus;
        }
        if (stay) {
            ImGui::CloseCurrentPopup();
        }
        ImGui::EndPopup();
    }
    if (stay) {
        sQuit = false;
        PortQuit_Dismiss();
        input_owner();
        PortA11y_Say(PortA11y_Label("Back to the game"), 1);
    }
}

// Dragon Net Battle: the first online window of the port, behind the main menu's item 4. Tenkaichi Budokai Online's
// screens (src/menu/port_tbo.c) do everything it does; it is opened from F1 > Online > Advanced, and listed in the
// main menu only when the player asks for it there (setting net_dnb_menu). Since 0.1.39 a match with a friend is a
// lobby's (gs/net_lobby.c), as on the screens: the Host tab opens a lobby (with a code, or on a port) with its rules,
// the Join tab joins one (its code, or its owner's address); the lobby itself is the screens' page, which the main
// menu opens as soon as this game is in one. There is no room of two and no "Watch" any more: a spectator is a
// lobby's member in a spectator's place. Quick match is as it was.
extern "C" {
extern volatile int gPortNetMenuRequest;
extern volatile int gPortNetWindowClose; // gs/state.c
}

static void net_open(void) {
    set_open(true);
    sNet = true;
    Port_LobbyHelloAsk(); // (once per opening: is there a newer release, and is this one still let in)
    gPortInputCapture = 1; // the game takes no input at all while this is open (it sits on the main menu behind it)
}

// Quick match (the third tab of the online screen): what stands under the queues.
static bool sServerTab = true; // persistent private servers
static bool sNetBusy;   // the lobby is waiting or connecting
static int sQueue = -1; // the queue chosen: 0 single, 1 team, 2..4 DP battle of 10 / 15 / 20 DP

static void quick_status(int state, int &lastState, const char *name) {
    // A search ends by itself after three minutes: a window left open does not go on asking the service for hours,
    // and the player is told that nobody was there instead of being left to wonder. One press searches again.
    static const Uint64 kSearchMs = 180000;
    static Uint64 since;
    if (state == 3 && since != 0 && SDL_GetTicks() - since > kSearchMs) {
        Port_LobbyCancel();
        lastState = -5;
        state = 0;
    }
    if (state == 3 || state == 1) {
        ImGui::TextUnformatted(Port_LobbyCheckingData() ? "正在检查游戏数据，完成后开始搜索…"
                               : state == 1 ? "已找到玩家，正在连接…" : "正在此队列中搜索玩家…");
        if (state == 3 && since != 0 && !Port_LobbyCheckingData()) {
            Uint64 left = kSearchMs - (SDL_GetTicks() - since);
            ImGui::TextDisabled("还将搜索 %d:%02d，请保持窗口开启。", (int)(left / 60000), (int)(left / 1000 % 60));
        }
        if (ImGui::Button("取消", ImVec2(U(120.0f), 0.0f))) {
            Port_LobbyCancel();
            lastState = 0;
        }
        return;
    }
    if (lastState == -3) {
        ImGui::TextWrapped("%s", UiZh(Port_LobbyError()));
    } else if (lastState == -4) {
        ImGui::TextWrapped("直连和中继均未能连接双方，请重新搜索其他玩家。");
    } else if (lastState == -2) {
        ImGui::TextWrapped("对方游戏版本不同，请重新搜索。");
    } else if (lastState == -5) {
        ImGui::TextWrapped("过去三分钟此队列中没有其他玩家。请重新搜索或更换队列。");
    }
    // Quick match is with strangers: the original disc's data only (gs/net.c refuses the search otherwise; said here
    // before it is asked for). With friends, by code or address, the same data on both sides is enough.
    const char *refused = Port_LobbyQuickRefusal();
    if (refused != NULL && refused[0] != '\0' && lastState != -3) {
        ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1.0f, 0.55f, 0.35f, 1.0f));
        ImGui::TextWrapped("%s", UiZh(refused));
        ImGui::PopStyleColor();
    } else if (refused != NULL) {
        ImGui::TextDisabled("正在检查游戏数据…");
    }
    ImGui::BeginDisabled(refused != NULL && refused[0] != '\0');
    bool search = ImGui::Button(lastState == -5 ? "重新搜索" : "搜索对手", ImVec2(U(200.0f), 0.0f));
    ImGui::EndDisabled();
    if (search) {
        since = SDL_GetTicks() + 1;
        // The same for everyone in a quick match, whoever turns out to be the host: rollback of up to 8 frames and
        // the input delay measured from the connection. (The Host tab's own choices are for matches with someone
        // you can agree them with; a stranger's saved ones were not to be inherited unseen.)
        Port_NetOptions(Port_RollCan() ? 8 : 0, -2);
        Port_NetSpeedSet(Port_NetSpeedStandard()); // (every quick match: the competitive standard)
        Port_NetRulesSet(sQueue == 0 ? 0 : sQueue == 1 ? 1 : 2, sQueue >= 2 ? sQueue - 2 : 0, 4);
        Port_NetNameSet(name);
        Port_SettingTextSave("net_name", name);
        Port_SettingSave("net_queue", sQueue);
        Port_SettingsWrite();
        lastState = 0;
        Port_LobbyStartQuick(sQueue);
    }
}

static void build_net(void) {
    static char name[17] = "Player", address[64] = "", port[8] = "7000";
    static int tab = 3, roll = -1, delay = 1, battle = -1, timeLimit = 3, speed = -1;
    static bool useCode = true;       // a lobby with a code (no port forwarding) or on a port
    static char roomCode[8] = "";     // the code to join with
    static int lastState = 0;         // what the search said last (for its messages after a failure)
    ImGuiIO &io = ImGui::GetIO();
    bool open = true;

    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.5f), ImGuiCond_Appearing, ImVec2(0.5f, 0.5f));
    ImGui::SetNextWindowSize(ImVec2(std::min(U(1120.0f), io.DisplaySize.x * 0.96f), 0.0f), ImGuiCond_Appearing);
    if (pad_pressed(ImGuiKey_GamepadFaceRight)) { // Circle / B: out of the window, as its close button
        open = false;
    }
    if (ImGui::Begin("龙网对战", &open, ImGuiWindowFlags_NoCollapse | ImGuiWindowFlags_AlwaysAutoResize)) {
        {
            int min = 0, latest = 0, mine = Port_LobbyRelease(&min, &latest);
            if (min > mine) {
                ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1.0f, 0.55f, 0.35f, 1.0f));
                ImGui::TextWrapped("有可用更新，请先更新游戏再连接联机服务器。");
                ImGui::PopStyleColor();
                ImGui::TextDisabled("当前版本 0.%d.%d，需要 0.%d.%d 或更新版本。github.com/z3xox/Tenkaichi3Decomp/releases", mine / 100, mine % 100, min / 100, min % 100);
                ImGui::Separator();
            } else if (latest > mine) {
                ImGui::TextColored(ImVec4(1.0f, 0.85f, 0.3f, 1.0f), "发现新版本：0.%d.%d。", latest / 100, latest % 100);
                ImGui::TextDisabled("按 F1 查看更新，或访问 github.com/z3xox/Tenkaichi3Decomp/releases");
                ImGui::Separator();
            }
            if (Port_OnlineBlocked() != NULL) { // an update is under way (gs/net_update.c): no new session starts
                ImGui::PushStyleColor(ImGuiCol_Text, ImVec4(1.0f, 0.55f, 0.35f, 1.0f));
                ImGui::TextWrapped("%s", UiZh(Port_OnlineBlocked()));
                ImGui::PopStyleColor();
                ImGui::Separator();
            }
        }
        ImGui::TextWrapped("与其他电脑上的玩家对战。一人创建大厅，其他人通过房间码或房主地址加入；进入主菜单的联机模式后，可选择位置、设置规则并开始对战。");
        ImGui::Spacing();
        ImGui::SetNextItemWidth(U(260.0f));
        {
            static bool read;
            if (!read) { // the name used last time
                read = true;
                Port_SettingText("net_name", "Player", name, sizeof(name));
            }
        }
        ImGui::InputText("玩家名称", name, sizeof(name));
        if (ImGui::IsItemDeactivatedAfterEdit()) {
            Port_SettingTextSave("net_name", name);
            Port_SettingsWrite();
        }
        ImGui::Spacing();
        bool focusServers = OnlineLobby::FocusTab();
        if (ImGui::BeginTabBar("net")) {
            ImGui::BeginDisabled(sNetBusy);
            if (ImGui::BeginTabItem("服务器大厅", NULL, focusServers ? ImGuiTabItemFlags_SetSelected : 0)) {
                tab = 3;
                OnlineLobby::Draw(name, U(1.0f));
                ImGui::EndTabItem();
            }
            ImGui::EndDisabled();
            ImGui::BeginDisabled(OnlineLobby::Connecting());
            // BT3_UI_NET_TAB=host|quick|join (testing, with BT3_UI_OPEN=9): the online screen opens on that tab
            static const char *firstTab = getenv("BT3_UI_NET_TAB");
            static int firstFrames = 10; // (not on the tab bar's first frame alone: it has no tabs yet then)
            auto tabFlags = [](const char *which) {
                ImGuiTabItemFlags f = firstTab != NULL && strcmp(firstTab, which) == 0 ? ImGuiTabItemFlags_SetSelected : 0;
                return f;
            };
            if (ImGui::BeginTabItem("创建", NULL, tabFlags("host"))) {
                static const char *const kRoll[] = {"关闭（等待对方）", "最多 2 帧", "最多 4 帧", "最多 6 帧", "最多 8 帧"};
                tab = 0;
                ImGui::Checkbox("使用房间码（无需端口转发）", &useCode);
                ImGui::SetItemTooltip("创建一个可告知其他玩家的房间码，通过匹配服务建立连接，适用于大多数家用路由器。\n关闭后使用指定端口，其他玩家必须能够访问此端口（端口转发或虚拟局域网）。");
                ImGui::BeginDisabled(useCode);
                ImGui::SetNextItemWidth(U(120.0f));
                ImGui::InputText("端口", port, sizeof(port), ImGuiInputTextFlags_CharsDecimal);
                ImGui::EndDisabled();
                if (roll < 0) { // the choices of last time (new names: the first ones' defaults were 4 frames and delay 1)
                    roll = Port_RollCan() ? Port_Setting("net_rollback2", 8) / 2 : 0;
                    delay = Port_Setting("net_delay2", -1) + 1; // 0 = automatic, else the delay + 1
                    if (roll < 0 || roll > 4) { roll = 4; }
                    if (delay < 0 || delay > 7) { delay = 0; }
                }
                ImGui::BeginDisabled(!Port_RollCan());
                ImGui::SetNextItemWidth(U(260.0f));
                ImGui::Combo("回滚", &roll, kRoll, 5);
                ImGui::EndDisabled();
                if (ImGui::IsItemHovered(ImGuiHoveredFlags_AllowWhenDisabled)) {
                    ImGui::SetTooltip("开启回滚后，本地操作立即响应，收到对方输入后再校正游戏状态。\n"
                                      "更高的回滚帧数适合延迟较大的连接，也会消耗更多处理器资源。\n"
                                      "关闭时，双方每帧等待彼此的输入。");
                }
                ImGui::SetNextItemWidth(U(260.0f));
                {
                    static const char *const kDelay[] = {"自动（根据连接状况）", "0 帧", "1 帧", "2 帧", "3 帧",
                                                         "4 帧", "5 帧", "6 帧"};
                    ImGui::Combo("输入延迟", &delay, kDelay, 8);
                }
                if (ImGui::IsItemHovered()) {
                    ImGui::SetTooltip("设置按下按键到动作生效的等待时间。连接较慢时需要更高的延迟，\n"
                                      "否则过多预测可能导致卡顿。自动模式在比赛开始时测量连接状况：\n"
                                      "连接良好时为 1 帧，连接较慢时增加。");
                }
                {
                    // The match's rules: the game's own versus menu is not shown online, so they are chosen here.
                    static const char *const kBattle[] = {"单人对战", "组队对战", "DP 对战（10 DP）", "DP 对战（15 DP）", "DP 对战（20 DP）"};
                    static const char *const kTime[] = {"60 秒", "90 秒", "180 秒", "240 秒", "不限时"};
                    if (battle < 0) {
                        battle = Port_Setting("net_battle", 0);
                        timeLimit = Port_Setting("net_time", 3);
                        if (battle < 0 || battle > 4) { battle = 0; }
                        if (timeLimit < 0 || timeLimit > 4) { timeLimit = 3; }
                    }
                    ImGui::Spacing();
                    ImGui::SetNextItemWidth(U(260.0f));
                    ImGui::Combo("对战模式", &battle, kBattle, 5);
                    ImGui::SetNextItemWidth(U(260.0f));
                    ImGui::Combo("时间限制", &timeLimit, kTime, 5);
                    {
                        if (speed < 0) {
                            speed = Port_Setting("net_speed_host", Port_NetSpeedStandard()) /* (a new name with 0.1.31: the standard went from 120 to 114) */;
                        }
                        ImGui::SetNextItemWidth(U(260.0f));
                        ImGui::SliderInt("游戏速度", &speed, 100, 150, "%d%%", ImGuiSliderFlags_AlwaysClamp);
                        ImGui::SetItemTooltip("设置双方的游戏速度，声音音调保持不变。\n"
                                              "100%% 为原版速度；%d%% 为竞技标准，\n"
                                              "快速匹配也使用此速度。\n"
                                              "与 0.1.29 版本联机时仅支持 100%% 或 120%%；\n"
                                              "与更早版本联机时仅支持 100%%。", Port_NetSpeedStandard());
                    }
                }
                ImGui::TextDisabled("这些是大厅的初始规则，房主可在大厅页面修改。所有玩家需使用相同游戏数据。");
                ImGui::EndTabItem();
            }
            if (ImGui::BeginTabItem("快速匹配", NULL, tabFlags("quick"))) {
                static const char *const kQueue[] = {"单人对战", "组队对战", "DP 对战（10 DP）", "DP 对战（15 DP）", "DP 对战（20 DP）"};
                static Uint64 asked;
                bool busy = sNetBusy; // (a search is under way: the queue is not changed under it)
                tab = 2;
                if (sQueue < 0) {
                    sQueue = Port_Setting("net_queue", 0);
                    if (sQueue < 0 || sQueue > 4) { sQueue = 0; }
                }
                {
                    // How many wait: asked when the tab is opened and then every thirty seconds, but only while the
                    // player is doing something here (a window left open all day asks nothing after two minutes),
                    // and not during a search (the search hears from the service anyway).
                    static Uint64 active;
                    bool moved = io.MouseDelta.x != 0.0f || io.MouseDelta.y != 0.0f || ImGui::IsAnyItemActive();
                    for (int k = ImGuiKey_NamedKey_BEGIN; k < ImGuiKey_NamedKey_END && !moved; k++) {
                        moved = ImGui::IsKeyDown((ImGuiKey)k);
                    }
                    if (moved || active == 0) {
                        active = SDL_GetTicks() + 1;
                    }
                    if (!sNetBusy && (asked == 0 || (SDL_GetTicks() - asked > 30000 && SDL_GetTicks() - active < 120000))) {
                        asked = SDL_GetTicks() + 1;
                        Port_LobbyQueuesAsk();
                    }
                }
                ImGui::TextWrapped("与同一队列中正在搜索的玩家匹配。快速匹配不限时，速度为 %d%%，双方均需使用原版镜像的游戏数据。", Port_NetSpeedStandard());
                ImGui::BeginDisabled(busy);
                for (int i = 0; i < 5; i++) {
                    char label[80];
                    int n = Port_LobbyQueueWaiting(i);
                    if (n < 0) {
                        snprintf(label, sizeof(label), "%s", kQueue[i]);
                    } else {
                        snprintf(label, sizeof(label), "%s   （%d 人搜索中）###q%d", kQueue[i], n, i);
                    }
                    ImGui::RadioButton(label, &sQueue, i);
                }
                ImGui::EndDisabled();
                ImGui::TextDisabled("与多数联机格斗游戏一样，条件允许时双方直接连接。");
                ImGui::TextDisabled("查看网络流量的玩家可以看到对方地址。");
                ImGui::EndTabItem();
            }
            if (ImGui::BeginTabItem("加入", NULL, tabFlags("join"))) {
                tab = 1;
                ImGui::SetNextItemWidth(U(120.0f));
                ImGui::InputText("房间码", roomCode, sizeof(roomCode), ImGuiInputTextFlags_CharsUppercase | ImGuiInputTextFlags_CharsNoBlank);
                ImGui::SameLine();
                if (ImGui::Button("粘贴")) { // the letters and digits of what was copied, as capitals
                    char *clip = SDL_GetClipboardText();
                    size_t n = 0;
                    for (const char *c = clip; c != NULL && *c != '\0' && n + 1 < sizeof(roomCode); c++) {
                        if ((*c >= '0' && *c <= '9') || (*c >= 'A' && *c <= 'Z') || (*c >= 'a' && *c <= 'z')) {
                            roomCode[n++] = (char)(*c >= 'a' ? *c - 32 : *c);
                        }
                    }
                    roomCode[n] = '\0';
                    SDL_free(clip);
                }
                ImGui::TextDisabled("或不使用房间码，填写房主地址和端口：");
                ImGui::BeginDisabled(roomCode[0] != '\0');
                ImGui::SetNextItemWidth(U(260.0f));
                ImGui::InputText("房主地址", address, sizeof(address));
                ImGui::SetNextItemWidth(U(120.0f));
                ImGui::InputText("端口", port, sizeof(port), ImGuiInputTextFlags_CharsDecimal);
                ImGui::EndDisabled();
                ImGui::EndTabItem();
            }
            ImGui::EndDisabled();
            ImGui::EndTabBar();
            if (firstTab != NULL && --firstFrames <= 0) {
                firstTab = NULL;
            }
        }
        sServerTab = tab == 3;
        ImGui::Spacing();
        if (tab != 3) {
            int state = Port_LobbyPoll();
            sNetBusy = state == 1 || state == 3;
            if (state == 5) { // the code or address was a lobby's: this game is its member; its screen is the game's
                Port_LobbyCancel(); // (the lobby has the socket now)
                const char *said = MenuTranslation_PortText(PORT_TEXT_LOBBY_JOINED);
                Port_UiNotice(said != NULL ? said : "已加入大厅，可从主菜单的联机模式进入大厅页面。");
                set_open(false);
                ImGui::End();
                return;
            }
            if (state == 2) {
                Port_LobbyLaunch(); // the other player is there: the game turns into the session at its next blank
                set_open(false);
                sNet = false;
            }
            bool byCode = tab == 0 ? useCode : roomCode[0] != '\0';
            if (state != 0) {
                lastState = state;
            }
            if (tab == 2) {
                quick_status(state, lastState, name);
            } else if (state == 3 || state == 1) { // joining a code: asking the service, then reaching the lobby's owner
                ImGui::TextUnformatted(Port_LobbyCheckingData() ? "正在检查游戏数据，完成后开始连接…"
                                       : state == 1 ? "已找到大厅，正在连接房主…" : "正在查找大厅…");
                if (ImGui::Button("取消", ImVec2(U(120.0f), 0.0f))) {
                    Port_LobbyCancel();
                    lastState = 0;
                }
            } else {
                if (lastState == -3) {
                    ImGui::TextWrapped("%s", UiZh(Port_LobbyError()));
                } else if (lastState == -4) {
                    ImGui::TextWrapped("直连和中继均未能连接双方。"
                                       "仍可使用指定端口创建房间（端口转发，或 Tailscale 等虚拟局域网）。");
                }
                bool can = Port_OnlineBlocked() == NULL && (byCode ? (tab == 0 || strlen(roomCode) == 6) : atoi(port) > 0 && atoi(port) < 65536 && (tab == 0 || address[0] != '\0'));
                bool lobby = false; // a lobby was opened or joined: its page is the screens' (the main menu opens it)
                ImGui::BeginDisabled(!can);
                if (ImGui::Button(tab == 0 ? "创建大厅" : "加入大厅", ImVec2(U(200.0f), 0.0f))) {
                    Port_NetNameSet(name);
                    Port_SettingTextSave("net_name", name);
                    lastState = 0;
                    if (tab == 0) {
                        if (roll < 0) {
                            roll = Port_RollCan() ? 4 : 0;
                        }
                        if (battle < 0) {
                            battle = 0;
                        }
                        if (speed < 0) {
                            speed = Port_NetSpeedStandard();
                        }
                        Port_SettingSave("net_speed_host", speed);
                        Port_SettingSave("net_battle", battle);
                        Port_SettingSave("net_time", timeLimit);
                        Port_SettingSave("net_rollback2", roll * 2);
                        Port_SettingSave("net_delay2", delay - 1);
                        Port_LobbyCancel();
                        Port_LobbyCreate(useCode ? 1 : 0, useCode ? 0 : atoi(port), battle, timeLimit, speed, roll * 2, delay); // (the lobby's delay: 0 automatic, else frames + 1, as here)
                        lobby = true;
                    } else if (byCode) {
                        Port_NetOptions(-1, -1);
                        Port_LobbyStartCode(0, roomCode); // (a lobby's code: Port_LobbyPoll says 5, below, and this game is its member)
                    } else {
                        Port_LobbyCancel();
                        Port_LobbyJoin(address, atoi(port));
                        lobby = true;
                    }
                    Port_SettingsWrite();
                }
                ImGui::EndDisabled();
                ImGui::SameLine();
                if (ImGui::Button("返回", ImVec2(U(120.0f), 0.0f))) {
                    open = false;
                }
                if (lobby) {
                    const char *said = MenuTranslation_PortText(PORT_TEXT_LOBBY_JOINED);
                    Port_UiNotice(said != NULL ? said : "已加入大厅，可从主菜单的联机模式进入大厅页面。");
                    set_open(false);
                    ImGui::End();
                    return;
                }
                if (state == -2) {
                    ImGui::TextWrapped("对方游戏版本不同，所有玩家需使用相同版本。");
                } else if (state < 0) {
                    ImGui::TextWrapped("无法开始搜索。");
                }
            }
        }
        ImGui::Spacing();
        ImGui::TextDisabled("联机时双方使用相同的完整角色列表，所有内容均已解锁，个人存档保持不变。");
        ImGui::TextDisabled("比赛结束后，所有玩家返回大厅页面。");
    }
    ImGui::End();
    if (!open) {
        OnlineLobby::Close();
        Port_LobbyCancel();
        set_open(false);
    }
}

void Ui_Toggle(void) {
    if (sReady && !sQuit) {
        if (sOpen && sNet) { OnlineLobby::Close(); Port_LobbyCancel(); }
        set_open(!sOpen);
    }
}

static void bind(int value) {
    if (sCapAction == PORT_ACTIONS) { // the row "打开设置窗口"
        if (sCapKind == 1) {
            *PortInput_OverlayKey() = value > 0 ? value : SDL_SCANCODE_F1; // (cleared = F1 again: a keyboard always has a way in)
        } else if (value < PORT_PAD_LT) { // (a button, not a trigger)
            *PortInput_OverlayPad() = value;
        }
    } else if (sCapAction == PORT_ACTIONS + 1) { // the row "打开联机聊天"
        if (sCapKind == 1) {
            *PortInput_ChatKey() = value > 0 ? value : SDL_SCANCODE_TAB;
        }
    } else if (sCapKind == 1) {
        PortInput_Keys(sCapPlayer)[sCapAction] = value;
    } else {
        PortInput_PadButtons(sCapPlayer)[sCapAction] = value;
    }
    PortInput_Save();
}

static bool chat_can_open(void) {
    return sReady && !sOpen && !sQuit && PortChat_Enabled() && Port_NetActive() && !Port_NetSpectating();
}

static void chat_open(void) {
    sChat = true;
    sChatFocus = true;
    sChatKeyHeld = true;
    sChatSoon = false;
    gPortChatTyping = 1;
    ImGui::GetIO().ClearInputKeys(); // (it saw none of the keys while the line was put away: no key is down for it)
}

static void chat_close(void) {
    sChat = false;
    gPortChatTyping = 0;
    PortInput_SwallowKeys(); // (Enter, which sent the line, is START: not the game's until it is let go)
}

// The chat while a line is typed: the keyboard is the line's; Esc puts it away. 1 = the event was used.
static int chat_event(const SDL_Event *ev) {
    int key = *PortInput_ChatKey();
    if (ev->type == SDL_EVENT_KEY_DOWN && ev->key.scancode == SDL_SCANCODE_ESCAPE) {
        chat_close();
        return 1;
    }
    if (ev->type == SDL_EVENT_KEY_DOWN && !sChatKeyHeld && !ev->key.repeat && key > 0 && (int)ev->key.scancode == key) {
        chat_close();
        return 1;
    }
    if (ev->type == SDL_EVENT_KEY_UP && (int)ev->key.scancode == key) {
        sChatKeyHeld = false;
    }
    if (ev->type == SDL_EVENT_TEXT_INPUT && sChatKeyHeld) { // the letter of the key that opened the line
        return 1;
    }
    if (ev->type == SDL_EVENT_KEY_DOWN || ev->type == SDL_EVENT_KEY_UP || ev->type == SDL_EVENT_TEXT_INPUT || ev->type == SDL_EVENT_TEXT_EDITING ||
        ev->type == SDL_EVENT_MOUSE_BUTTON_DOWN || ev->type == SDL_EVENT_MOUSE_BUTTON_UP || ev->type == SDL_EVENT_MOUSE_WHEEL ||
        ev->type == SDL_EVENT_MOUSE_MOTION) {
        ImGui_ImplSDL3_ProcessEvent(ev);
    }
    return ev->type == SDL_EVENT_KEY_DOWN || ev->type == SDL_EVENT_KEY_UP || ev->type == SDL_EVENT_TEXT_INPUT ||
           ev->type == SDL_EVENT_MOUSE_BUTTON_DOWN || ev->type == SDL_EVENT_MOUSE_BUTTON_UP || ev->type == SDL_EVENT_MOUSE_WHEEL;
}

int Ui_Event(const SDL_Event *ev) {
    PortWii_MouseEvent(ev);
    if (!sReady) {
        return 0;
    }
    if (ev->type == SDL_EVENT_GAMEPAD_ADDED || ev->type == SDL_EVENT_GAMEPAD_REMOVED) { // (also while it is closed: its list of controllers)
        ImGui_ImplSDL3_ProcessEvent(ev);
        return 0;
    }
    if (!sOpen && !sQuit && !sChat && PortInput_TboEvent(ev)) { // typed on a keypad of Tenkaichi Budokai Online
        return 1;
    }
    if (sQuit && PortQuit_Active()) { // game dialog: keyboard and controller operate its native Yes / No plates
        if (ev->type == SDL_EVENT_KEY_DOWN && !ev->key.repeat) {
            SDL_Scancode key = ev->key.scancode;
            if (key == SDL_SCANCODE_ESCAPE) { PortQuit_Action(PORT_QUIT_CANCEL); }
            else if (key == SDL_SCANCODE_RETURN || key == SDL_SCANCODE_KP_ENTER || key == SDL_SCANCODE_SPACE) {
                PortQuit_Action(PORT_QUIT_CONFIRM);
            } else if (key == SDL_SCANCODE_LEFT || key == SDL_SCANCODE_RIGHT ||
                       key == SDL_SCANCODE_UP || key == SDL_SCANCODE_DOWN) {
                if (PortQuit_Ready()) { say_quit_button(1 - PortQuit_Cursor(), 1); }
                PortQuit_Action(PORT_QUIT_MOVE);
            }
        } else if (ev->type == SDL_EVENT_GAMEPAD_BUTTON_DOWN) {
            SDL_GamepadButton button = (SDL_GamepadButton)PortInput_UiButton(SDL_GetGamepadFromID(ev->gbutton.which), ev->gbutton.button);
            if (button == SDL_GAMEPAD_BUTTON_SOUTH) { PortQuit_Action(PORT_QUIT_CONFIRM); }
            else if (button == SDL_GAMEPAD_BUTTON_EAST) { PortQuit_Action(PORT_QUIT_CANCEL); }
            else if (button == SDL_GAMEPAD_BUTTON_DPAD_LEFT || button == SDL_GAMEPAD_BUTTON_DPAD_RIGHT ||
                     button == SDL_GAMEPAD_BUTTON_DPAD_UP || button == SDL_GAMEPAD_BUTTON_DPAD_DOWN) {
                if (PortQuit_Ready()) { say_quit_button(1 - PortQuit_Cursor(), 1); }
                PortQuit_Action(PORT_QUIT_MOVE);
            }
        }
        return 1;
    }
    if (sChat && !sOpen && !sQuit) {
        return chat_event(ev);
    }
    if (!sOpen && !sQuit && Port_NetSpectating() && ev->type == SDL_EVENT_KEY_DOWN && !ev->key.repeat && ev->key.scancode == SDL_SCANCODE_ESCAPE) {
        gPortSpecMenuAsk = 1; // a spectator's own pause menu (the game's, over the match: only on this screen)
        return 1;
    }
    if (!sOpen && !sQuit && Port_NetSpectating() &&
        ((ev->type == SDL_EVENT_KEY_DOWN && !ev->key.repeat && ev->key.scancode == SDL_SCANCODE_V) ||
         (ev->type == SDL_EVENT_GAMEPAD_BUTTON_DOWN && ev->gbutton.button == SDL_GAMEPAD_BUTTON_RIGHT_SHOULDER))) {
        spec_view_next(); // (a spectator's keys and controller play nobody: the view is all they change)
        return 1;
    }
    if (ev->type == SDL_EVENT_KEY_DOWN && !ev->key.repeat && *PortInput_ChatKey() > 0 && (int)ev->key.scancode == *PortInput_ChatKey() &&
        chat_can_open()) {
        chat_open();
        return 1;
    }
    if (sQuit) { // fallback when the native dialog resource cannot be loaded
        if (ev->type == SDL_EVENT_KEY_DOWN && ev->key.scancode == SDL_SCANCODE_ESCAPE) {
            sQuitNo = sQuitNo || !ev->key.repeat; // (taken away where it is drawn)
            return 1;
        }
        ImGui_ImplSDL3_ProcessEvent(ev);
        return ev->type == SDL_EVENT_KEY_DOWN || ev->type == SDL_EVENT_KEY_UP || ev->type == SDL_EVENT_TEXT_INPUT ||
               ev->type == SDL_EVENT_MOUSE_BUTTON_DOWN || ev->type == SDL_EVENT_MOUSE_BUTTON_UP || ev->type == SDL_EVENT_MOUSE_WHEEL;
    }
    if (!sOpen) {
        if (meter_on() && (ev->type == SDL_EVENT_MOUSE_MOTION || ev->type == SDL_EVENT_MOUSE_BUTTON_DOWN || ev->type == SDL_EVENT_MOUSE_BUTTON_UP)) {
            ImGui_ImplSDL3_ProcessEvent(ev);
            return sMeterHover || sMeterDrag;
        }
        return 0;
    }
    if (PortWii_Event(ev)) { return 1; }
    if (sCapKind != 0) { // the next key or button is the binding; Esc leaves it as it was, Delete clears it
        bool done = false;
        if (ev->type == SDL_EVENT_KEY_DOWN) {
            if (ev->key.scancode == SDL_SCANCODE_DELETE || ev->key.scancode == SDL_SCANCODE_BACKSPACE) {
                bind(sCapKind == 1 ? 0 : -1);
            } else if (ev->key.scancode != SDL_SCANCODE_ESCAPE && sCapKind == 1) {
                bind((int)ev->key.scancode);
            }
            done = ev->key.scancode == SDL_SCANCODE_ESCAPE || ev->key.scancode == SDL_SCANCODE_DELETE ||
                   ev->key.scancode == SDL_SCANCODE_BACKSPACE || sCapKind == 1;
        } else if (sCapKind == 2 && ev->type == SDL_EVENT_GAMEPAD_BUTTON_DOWN) {
            bind((int)ev->gbutton.button);
            done = true;
        } else if (sCapKind == 2 && ev->type == SDL_EVENT_GAMEPAD_AXIS_MOTION && ev->gaxis.value > 20000 &&
                   (ev->gaxis.axis == SDL_GAMEPAD_AXIS_LEFT_TRIGGER || ev->gaxis.axis == SDL_GAMEPAD_AXIS_RIGHT_TRIGGER)) {
            bind(ev->gaxis.axis == SDL_GAMEPAD_AXIS_LEFT_TRIGGER ? PORT_PAD_LT : PORT_PAD_RT);
            done = true;
        }
        if (done) {
            sCapKind = 0;
            gPortInputCapture = 0;
        }
        if (ev->type == SDL_EVENT_KEY_DOWN || ev->type == SDL_EVENT_KEY_UP) {
            return 1;
        }
    } else if (!gPortInputCapture && ev->type == SDL_EVENT_KEY_DOWN && ev->key.scancode == SDL_SCANCODE_ESCAPE) {
        set_open(false);
        return 1;
    }
    ImGui_ImplSDL3_ProcessEvent(ev);
    return ev->type == SDL_EVENT_KEY_DOWN || ev->type == SDL_EVENT_KEY_UP || ev->type == SDL_EVENT_TEXT_INPUT ||
           ev->type == SDL_EVENT_MOUSE_BUTTON_DOWN || ev->type == SDL_EVENT_MOUSE_BUTTON_UP || ev->type == SDL_EVENT_MOUSE_WHEEL;
}

static const char *pad_source_name(int src) {
    static const char *names[] = {"A / Cross", "B / Circle", "X / Square", "Y / Triangle", "Back / Select", "Guide", "Start",
                                  "Left stick click", "Right stick click", "Left shoulder", "Right shoulder", "D-pad up",
                                  "D-pad down", "D-pad left", "D-pad right", "Misc 1", "Right paddle 1", "Left paddle 1",
                                  "Right paddle 2", "Left paddle 2", "Touchpad"};
    static char other[24];
    if (src == PORT_PAD_LT) { return "左扳机"; }
    if (src == PORT_PAD_RT) { return "右扳机"; }
    if (src < 0) { return "-"; }
    if (src < (int)(sizeof(names) / sizeof(names[0]))) { return names[src]; }
    snprintf(other, sizeof(other), "Button %d", src);
    return other;
}

static bool tab(const char *label, int index) {
    ImGuiTabItemFlags flags = sForceTab == index ? ImGuiTabItemFlags_SetSelected : 0;
    bool on = ImGui::BeginTabItem(label, NULL, flags);
    if (on && sForceTab < 0) {
        sTab = index;
    }
    return on;
}

static void video_tab(PortVideo &v) {
    static const struct { const char *name; int milli; } aspects[] = {{"4:3（原版）", 1333}, {"16:10", 1600}, {"16:9", 1778}, {"21:9", 2389}, {"32:9", 3556}};
    char label[64];
    int best = 0, count = 0;

    snprintf(label, sizeof(label), "%dx  (%d x %d)", v.scale, 512 * v.scale, 448 * v.scale);
    if (ImGui::BeginCombo("内部分辨率", label)) {
        for (int n = 1; n <= 8; n++) {
            snprintf(label, sizeof(label), "%dx  (%d x %d)", n, 512 * n, 448 * n);
            if (ImGui::Selectable(label, n == v.scale)) { v.scale = n; }
        }
        ImGui::EndCombo();
    }
    ImGui::SetItemTooltip("游戏渲染分辨率。1 倍为 PS2 原始分辨率，越高越清晰，也越占用显存。");
    for (int i = 1; i < (int)(sizeof(aspects) / sizeof(aspects[0])); i++) {
        if (abs(aspects[i].milli - v.aspectMilli) < abs(aspects[best].milli - v.aspectMilli)) { best = i; }
    }
    if (ImGui::BeginCombo("画面比例", aspects[best].name)) {
        for (int i = 0; i < (int)(sizeof(aspects) / sizeof(aspects[0])); i++) {
            if (ImGui::Selectable(aspects[i].name, i == best)) { v.aspectMilli = aspects[i].milli; }
        }
        ImGui::EndCombo();
    }
    ImGui::SetItemTooltip("宽于 4:3 时显示更多战斗场景，菜单会被拉伸。");
    if (ImGui::BeginCombo("2D 滤镜", v.smooth2d ? "平滑" : "锐利（原版）")) {
        if (ImGui::Selectable("锐利（原版）", !v.smooth2d)) { v.smooth2d = 0; }
        if (ImGui::Selectable("平滑", v.smooth2d != 0)) { v.smooth2d = 1; }
        ImGui::EndCombo();
    }
    ImGui::SetItemTooltip("高于 1 倍分辨率时，锐利保留原版像素块，平滑使用模拟器式滤镜。1 倍时没有区别。");
    bool full = v.fullscreen != 0;
    if (ImGui::Checkbox("全屏", &full)) { v.fullscreen = full; }
    ImGui::SameLine();
    ImGui::TextDisabled("(F11)");
    {
        bool vs = v.vsync != 0, fs = v.frameSkip != 0;
        if (ImGui::Checkbox("垂直同步", &vs)) { v.vsync = vs; }
        ImGui::SetItemTooltip("本版本始终优先使用 Immediate 呈现，开启此选项也不会切换为 FIFO。\n不支持 Immediate 时使用兼容模式。");
        if (ImGui::Checkbox("性能不足时跳帧以保持速度", &fs)) { v.frameSkip = fs; }
        ImGui::SetItemTooltip("性能不足时通过跳过画面维持游戏速度，画面可能不连贯；默认开启。");
        {
            bool late = Port_LateInput() != 0;
            if (ImGui::Checkbox("低输入延迟（实验性）", &late)) { Port_LateInputSet(late); }
            ImGui::SetItemTooltip("实验性：先等待再读取输入，缩短输入至画面的延迟。配合平滑运动时，中间帧先响应输入，完整帧在下一次刷新显示。联机时不启用；性能不足时可能卡顿，默认关闭。");
        }
        {
            extern int Port_Setting(const char *name, int def);
            extern void Port_SettingSave(const char *name, int value);
            bool thr = Port_Setting("render_thread", 0) != 0;
            if (ImGui::Checkbox("独立核心渲染（实验性，重启后生效）", &thr)) {
                Port_SettingSave("render_thread", thr ? 1 : 0);
                Port_SettingsWrite(); /* (kept outside the window's own values: written here, or it was lost at the end) */
            }
            ImGui::SetItemTooltip("游戏计算时，由独立核心准备并显示画面。处理器性能受限时可提高速度。\n"
                                  "画面和游戏内容保持一致，重启游戏后生效。\n"
                                  ""
                                  "不适用于 OpenGL 渲染器或仅有两个及更少核心的设备。");
        }
    }
    SDL_DisplayID *displays = SDL_GetDisplays(&count);
    if (v.display > count) { v.display = 0; }
    snprintf(label, sizeof(label), "%s", v.display == 0 ? "跟随桌面" : SDL_GetDisplayName(displays[v.display - 1]));
    if (ImGui::BeginCombo("显示器", label)) {
        if (ImGui::Selectable("跟随桌面", v.display == 0)) { v.display = 0; }
        for (int i = 0; i < count; i++) {
            snprintf(label, sizeof(label), "%d: %s", i + 1, SDL_GetDisplayName(displays[i]));
            if (ImGui::Selectable(label, v.display == i + 1)) { v.display = i + 1; }
        }
        ImGui::EndCombo();
    }
    ImGui::SetItemTooltip("下次启动游戏时生效。");
    SDL_free(displays);
    {   // which renderer draws the game: Vulkan (the default) or OpenGL 3.3, for machines without a working Vulkan
        static const char *const kApi[] = {"Vulkan", "OpenGL"};
        static int api = -1;
        if (api < 0) {
            api = Port_Setting("gpu_api", 0) == 1 ? 1 : 0;
        }
        if (ImGui::Combo("渲染器", &api, kApi, 2)) {
            Port_SettingSave("gpu_api", api);
            Port_SettingsWrite();
        }
        ImGui::SetItemTooltip("下次启动生效。两种渲染器画面相同，Vulkan 通常更快；启动失败时尝试另一种。");
        if (api != (sGL ? 1 : 0)) {
            ImGui::TextDisabled("当前：%s；下次启动使用 %s。", kApi[sGL ? 1 : 0], kApi[api]);
        }
        ImGui::TextWrapped("当前显卡：%s", sGpuName);
    }
    {
        // In-between pictures (gs_draw.c): the fight is computed 30 times a second, as on the console; with this
        // on one more picture is drawn between each two. The game itself, its replays and online play are the same.
        static const char *kSmooth[] = { "关闭（原版 30 帧）", "每秒 60 帧", "每秒 120 帧", "每秒 240 帧" };
        int smooth = gsInterp < 0 ? 0 : gsInterp > 3 ? 3 : gsInterp;
        ImGui::SetNextItemWidth(U(416.0f));
        if (ImGui::Combo("平滑补帧", &smooth, kSmooth, 4)) {
            gsInterp = smooth;
            Port_SettingSave("interp", gsInterp);
            Port_SettingsWrite();
        }
        ImGui::SetItemTooltip("实验性：战斗仍以原版每秒 30 次计算，仅补充画面。60 / 120 / 240 帧分别增加约 17 / 25 / 29 毫秒显示延迟。F9 开关。");
    }
    {
        // The size of these windows, the chat and the notices: larger with a taller picture by itself (sUiScale)
        static int steps = 20; // (in fives of a percent; while it is dragged)
        char shown[16];
        snprintf(shown, sizeof(shown), "%d%%%%", steps * 5);
        ImGui::SetNextItemWidth(U(416.0f));
        ImGui::SliderInt("菜单大小", &steps, 10, 40, shown, ImGuiSliderFlags_AlwaysClamp);
        int pct = steps * 5;
        if (ImGui::IsItemDeactivatedAfterEdit()) { // (applied on letting go: the slider would move under the pointer)
            sUiScalePct = pct;
            Port_SettingSave("ui_scale", pct);
            Port_SettingsWrite();
        } else if (!ImGui::IsItemActive()) {
            steps = (sUiScalePct < 0 ? 100 : sUiScalePct) / 5;
        }
        ImGui::SetItemTooltip("设置窗口、联机窗口、聊天与通知的大小。高于 1080 像素时自动放大；此项在此基础上调整。");
    }
    {
        bool on = meter_on();
        if (ImGui::Checkbox("显示帧率与联机状态", &on)) {
            sMeter = on;
            Port_SettingSave("meter", sMeter);
            Port_SettingsWrite();
        }
    }
    ImGui::Spacing();
    if (v.texPackCount > 0) {
        bool on = v.texPack != 0;
        snprintf(label, sizeof(label), "材质包（%d 个材质）", v.texPackCount);
        if (ImGui::Checkbox(label, &on)) { v.texPack = on; }
        ImGui::SetItemTooltip("读取游戏目录下 textures 文件夹中的替换材质。");
    } else {
        ImGui::BeginDisabled();
        bool off = false;
        ImGui::Checkbox("材质包（未找到）", &off);
        ImGui::EndDisabled();
        ImGui::SetItemTooltip("将 PCSX2 命名的 .dds 或 .png 材质放入游戏目录的 textures 文件夹。");
    }
}

static void effects_tab(PortVideo &v) {
    static const struct { const char *name, *tip; } fx[7] = {
        {"人物描边", "角色周围的黑色轮廓线。"},
        {"遮挡透视颜色", "角色被场景遮挡时显示的颜色。"},
        {"远景色调", "为远处物体添加雾色。"},
        {"眩光与泛光", "明亮物体周围的泛光与天空眩光。"},
        {"远景模糊", "远处场景的柔焦效果。"},
        {"动态模糊", "镜头旋转或快速移动时的场景模糊。"},
        {"天气效果", "部分场景中飘动的沙尘或薄雾，包括沙漠、岩山、神殿，以及冰河、肌肉塔和精神时光屋等。关闭可改善这些场景的性能。"},
    };
    for (int i = 0; i < 7; i++) {
        bool on = !((v.fxOff >> i) & 1);
        if (ImGui::Checkbox(fx[i].name, &on)) { v.fxOff = (v.fxOff & ~(1 << i)) | (on ? 0 : 1 << i); }
        ImGui::SetItemTooltip("%s", fx[i].tip);
        if (i == 6 && on) { /* Weather on: how much of it (fx_off bit 128: half the sprites) */
            static const char *const amount[2] = {"完整", "轻量"};
            int light = (v.fxOff >> 7) & 1;
            ImGui::Indent();
            ImGui::SetNextItemWidth(ImGui::GetFontSize() * 8.0f);
            if (ImGui::Combo("天气效果强度", &light, amount, 2)) { v.fxOff = (v.fxOff & ~128) | (light ? 128 : 0); }
            ImGui::SetItemTooltip("轻量：只绘制一半雾气，效果更淡，性能提升约为完全关闭的一半。");
            ImGui::Unindent();
        }
    }
    ImGui::Spacing();
    ImGui::SliderInt("泛光强度", &v.glow, 0, 200, "%d%%", ImGuiSliderFlags_AlwaysClamp);
    ImGui::SetItemTooltip("角色与物体周围的泛光（如超级赛亚人的头发、气焰）。PS2 原版为 100%%，移植版默认 60%%。");
    ImGui::SliderInt("眩光强度", &v.glare, 0, 200, "%d%%", ImGuiSliderFlags_AlwaysClamp);
    ImGui::SetItemTooltip("天空与场景光源的眩光。PS2 原版为 100%%，移植版默认 60%%。");
    bool sharp = v.sharpBlur != 0;
    if (ImGui::Checkbox("清晰场景模糊", &sharp)) { v.sharpBlur = sharp; }
    ImGui::SetItemTooltip("开启时场景模糊保留内部分辨率的细节；关闭时与 PS2 原版一样柔和。1 倍分辨率下没有区别。");
}

// ---- the automatic update (gs/net_update.c) ----
// (Based on PR #107 by JosephLlacchua: the in-game download, its progress bar, the restart into the new version.)
// A few seconds after start the newest published release is asked of GitHub, unless "Check for updates" is off. If it
// is newer than this build (its full number: 0.1.38.9; a local "dev" build is offered nothing): a line over the main
// menu and the online screens, and at the top of this window Update now / Later / What's new. Update now downloads
// and checks it in the background; Restart now (never during an online session) installs it over the folder and
// starts the new version. Later: no line over the menus until the next start.
// Not when nobody is looking (the offscreen and dummy video drivers); BT3_UPDATE_CHECK=1 / 0 says otherwise.
// BT3_UPDATE_AUTO=1 (testing) presses Update now and Restart now by itself.
static const bool sLocalUpdates = true; // Signed updates published by this edition's administrator.
static int sUpdCheck = -1;   // the setting; -1 not read yet
static bool sUpdAsked;       // the check was started (or decided against)
static Uint64 sUpdSince;     // when the game was first ready (the check waits a few seconds after it)
static bool sUpdLater;       // "稍后": no line over the menus for the rest of this run
static bool sUpdNotes;       // "更新内容" is open
static bool sUpdTold;        // the result of the last start's update was put over the picture
static char sUpdWhy[256];    // Restart now could not be done: why
static void set_notice(const char *text, Uint64 ms);

// {version} and {percent} of a port catalog line put in (the English when the language has none)
static void upd_fill(char *out, size_t size, const char *id, const char *english, const char *version, int percent) {
    const char *line = MenuTranslation_PortText(id);
    char num[16];
    size_t n = 0;

    if (line == NULL || line[0] == '\0') {
        line = english;
    }
    SDL_snprintf(num, sizeof(num), "%d", percent);
    for (size_t i = 0; line[i] != '\0' && n + 1 < size; i++) {
        const char *put = SDL_strncmp(line + i, "{version}", 9) == 0 ? version : SDL_strncmp(line + i, "{percent}", 9) == 0 ? num : NULL;
        if (put != NULL) {
            for (size_t k = 0; put[k] != '\0' && n + 1 < size; k++) {
                out[n++] = put[k];
            }
            i += 8;
        } else {
            out[n++] = line[i];
        }
    }
    out[n] = '\0';
}

static int upd_percent(const UpdateStatus &u) {
    return u.total > 0 ? (int)(u.got * 100 / u.total) : 0;
}

static bool upd_online(void) { // an online session or a lobby is on: it is never interrupted
    return Port_NetActive() || Lobby_Active() || Port_NetSpectating();
}

static void upd_restart(void) {
    sUpdWhy[0] = '\0';
    if (upd_online()) {
        SDL_strlcpy(sUpdWhy, "请先结束联机会话。", sizeof(sUpdWhy));
        return;
    }
    Update_Install(); // (in a thread: update_tick starts the new version when it is done)
}

static void update_tick(void) {
    if (!sLocalUpdates) { sUpdCheck = 0; return; }
    if (sUpdCheck < 0) {
        sUpdCheck = Port_Setting("update_check", 1) != 0;
    }
    if (!sReady) {
        return;
    }
    {
        UpdateStatus u;
        Update_Status(&u);
        if (u.state == UPD_INSTALLED) { // the files are swapped: the new version starts, this one closes
            static bool gone;
            if (!gone) {
                gone = true;
                Port_SettingsWrite();
                if (Update_Relaunch()) {
                    exit(0); // (as closing the window does)
                }
                SDL_strlcpy(sUpdWhy, "更新已安装，但无法启动新版本，请关闭游戏后重新启动。",
                            sizeof(sUpdWhy));
            }
        }
    }
    if (!sUpdTold) { // the update installed before this start
        const char *ver;
        char line[256];
        sUpdTold = true;
        if (Update_LastResult(&ver) > 0) {
            upd_fill(line, sizeof(line), PORT_TEXT_UPDATE_DONE, "已更新至 {version}。", ver, 0);
            set_notice(line, 10000);
        }
    }
    if (!sUpdAsked) {
        if (sUpdSince == 0) {
            sUpdSince = SDL_GetTicks();
        } else if (SDL_GetTicks() - sUpdSince >= 4000) {
            const char *drv = SDL_GetCurrentVideoDriver(), *env = SDL_getenv("BT3_UPDATE_CHECK");
            bool seen = drv == NULL || (SDL_strcmp(drv, "offscreen") != 0 && SDL_strcmp(drv, "dummy") != 0);
            sUpdAsked = true;
            if (env != NULL ? SDL_atoi(env) != 0 : (sUpdCheck != 0 && seen)) {
                Update_Check();
            }
        }
    }
    if (SDL_getenv("BT3_UPDATE_AUTO") != NULL && SDL_atoi(SDL_getenv("BT3_UPDATE_AUTO")) != 0) { // (testing)
        UpdateStatus u;
        Update_Status(&u);
        if (u.state == UPD_AVAILABLE && u.canInstall) {
            Update_Download();
        } else if (u.state == UPD_READY && !upd_online()) {
            upd_restart();
        }
    }
}

// The line over the main menu and the online screens (empty: none now).
static void update_line(char *out, size_t size) {
    UpdateStatus u;
    int mode = Port_GameMode();

    out[0] = '\0';
    if (!sLocalUpdates || !sReady || sOpen || (mode != 4 && mode != 80)) {
        return;
    }
    Update_Status(&u);
    if (u.state == UPD_AVAILABLE && !sUpdLater) {
        upd_fill(out, size, PORT_TEXT_UPDATE_AVAILABLE, "发现新版本 {version}，按 F1 查看。", u.latest, 0);
    } else if (u.state == UPD_DOWNLOADING || u.state == UPD_VERIFYING) {
        upd_fill(out, size, PORT_TEXT_UPDATE_DOWNLOADING, "正在下载更新 {version}：{percent}%", u.latest, upd_percent(u));
    } else if (u.state == UPD_READY) {
        upd_fill(out, size, PORT_TEXT_UPDATE_READY, "更新 {version} 已就绪，请在 F1 菜单中选择立即重启。", u.latest, 0);
    }
}

// The top of the settings window: what there is to update, and the buttons.
static void update_panel(void) {
    if (!sLocalUpdates) { return; }
    UpdateStatus u;
    const char *ver;
    int last = Update_LastResult(&ver);
    const ImVec4 gold(1.0f, 0.85f, 0.3f, 1.0f), red(1.0f, 0.55f, 0.35f, 1.0f), green(0.45f, 0.85f, 0.5f, 1.0f);

    Update_Status(&u);
    if (last > 0 && u.state < UPD_AVAILABLE) {
        ImGui::TextColored(green, "已更新至 %s。", ver);
        ImGui::Separator();
    }
    if (u.state < UPD_AVAILABLE) {
        return;
    }
    // the line that says where it stands
    if (u.state == UPD_AVAILABLE) {
        ImGui::TextColored(gold, "发现新版本 %s（当前为 %s）。", u.latest, u.current);
    } else if (u.state == UPD_DOWNLOADING) {
        ImGui::TextColored(gold, "正在下载 %s：%d%%（%.1f / %.1f MB），可继续游玩。", u.latest, upd_percent(u), (double)u.got / 1e6,
                           (double)u.total / 1e6);
        ImGui::ProgressBar((float)upd_percent(u) / 100.0f, ImVec2(-1.0f, 0.0f), "");
    } else if (u.state == UPD_VERIFYING) {
        ImGui::TextColored(gold, "正在验证 %s 的下载签名…", u.latest);
        ImGui::ProgressBar(1.0f, ImVec2(-1.0f, 0.0f), "");
    } else if (u.state == UPD_READY) {
        ImGui::TextColored(green, "更新 %s 已下载并通过验证。", u.latest);
    } else if (u.state == UPD_INSTALLING || u.state == UPD_INSTALLED) {
        ImGui::TextColored(gold, "正在安装 %s…", u.latest);
    } else if (u.state == UPD_FAILED) {
        ImGui::PushStyleColor(ImGuiCol_Text, red);
        ImGui::TextWrapped("未能安装更新 %s：%s", u.latest, u.why);
        ImGui::PopStyleColor();
    }
    // the buttons
    if (u.state == UPD_AVAILABLE && u.canInstall) {
        if (ImGui::Button("立即更新")) {
            Update_Download();
        }
        ImGui::SetItemTooltip("后台下载新版本并验证签名，期间可继续游玩（联机需等待安装完成）。\n下载完成后选择“立即重启”安装。存档、设置、游戏数据、模组和材质包均会保留。");
        ImGui::SameLine();
        if (!sUpdLater) {
            if (ImGui::Button("稍后")) {
                sUpdLater = true;
            }
            ImGui::SetItemTooltip("本次运行期间不再在菜单上显示提醒。");
            ImGui::SameLine();
        }
    } else if (u.state == UPD_READY) {
        bool busy = upd_online();
        if (busy) {
            ImGui::BeginDisabled();
        }
        if (ImGui::Button("立即重启")) {
            upd_restart();
        }
        if (busy) {
            ImGui::EndDisabled();
        }
        ImGui::SetItemTooltip(busy ? "请先结束联机会话。"
                                   : "将更新安装到游戏目录并启动新版本，若失败则恢复原文件。\n存档与设置均会保留。");
        ImGui::SameLine();
    } else if (u.state == UPD_FAILED && u.canInstall) {
        if (ImGui::Button("重试")) {
            Update_Download();
        }
        ImGui::SameLine();
    }
    if (ImGui::Button(sUpdNotes ? "收起更新内容" : "更新内容")) {
        sUpdNotes = !sUpdNotes;
    }
    ImGui::SameLine();
    if (ImGui::Button("发布页面")) {
        SDL_OpenURL(u.page);
    }
    ImGui::SetItemTooltip("在浏览器中打开发布页面。手动更新时，用新文件覆盖旧文件。");
    if (!u.canInstall && u.cannot[0] != '\0') {
        ImGui::PushStyleColor(ImGuiCol_Text, ImGui::GetStyleColorVec4(ImGuiCol_TextDisabled));
        ImGui::TextWrapped("%s", u.cannot);
        ImGui::PopStyleColor();
    }
    if (Port_OnlineBlocked() != NULL && u.state != UPD_INSTALLED) {
        ImGui::PushStyleColor(ImGuiCol_Text, ImGui::GetStyleColorVec4(ImGuiCol_TextDisabled));
        ImGui::TextWrapped("%s", UiZh(Port_OnlineBlocked()));
        ImGui::PopStyleColor();
    }
    if (sUpdWhy[0] != '\0') {
        ImGui::PushStyleColor(ImGuiCol_Text, red);
        ImGui::TextWrapped("%s", sUpdWhy);
        ImGui::PopStyleColor();
    }
    if (sUpdNotes) {
        const char *notes = Update_Notes();
        ImGui::BeginChild("notes", ImVec2(0.0f, U(180.0f)), ImGuiChildFlags_Borders);
        ImGui::TextWrapped("%s", notes[0] != '\0' ? notes : "（此版本没有更新说明。）");
        ImGui::EndChild();
    }
    ImGui::Separator();
}

static void misc_tab(void) {
    {
        bool chk = sLocalUpdates && sUpdCheck != 0;
        ImGui::BeginDisabled(!sLocalUpdates);
        if (ImGui::Checkbox("检查更新", &chk)) {
            sUpdCheck = chk;
            Port_SettingSave("update_check", sUpdCheck);
            Port_SettingsWrite();
        }
        ImGui::EndDisabled();
        ImGui::SetItemTooltip(sLocalUpdates ? "每次启动时检查一次我们服务器发布的新版本与更新公告。"
                                           : "此本地汉化版暂时关闭自动更新。请合并并保留本地修改后手动更新。");
        ImGui::SameLine();
        ImGui::TextDisabled("（当前版本：%s）", Update_Version()); // (PR #107: the version that is running)
        ImGui::SetItemTooltip("当前运行的 Tenkaichi3Decomp 版本（“dev”为本地构建，不接收更新）。");
    }
    // the start of the game (PR #50): read by FirstRun_Main, so they count from the next start
    static int sSkipLogos = -1, sSkipIntro = -1, sSkipCopy = -1;
    if (sSkipLogos < 0) {
        sSkipLogos = Port_Setting("skip_logos", 0) != 0;
        sSkipIntro = Port_Setting("skip_intro", 0) != 0;
        sSkipCopy = Port_Setting("skip_copyright", 0) != 0;
    }
    bool logos = sSkipLogos != 0, intro = sSkipIntro != 0, copy = sSkipCopy != 0;
    ImGui::Spacing();
    if (ImGui::Checkbox("跳过厂商标志", &logos)) {
        sSkipLogos = logos;
        Port_SettingSave("skip_logos", sSkipLogos);
        Port_SettingsWrite();
    }
    ImGui::SetItemTooltip("跳过发行商和开发商标志，下次启动生效。");
    if (ImGui::Checkbox("跳过开场动画", &intro)) {
        sSkipIntro = intro;
        Port_SettingSave("skip_intro", sSkipIntro);
        Port_SettingsWrite();
    }
    ImGui::SetItemTooltip("跳过开场动画，下次启动生效。");
    if (ImGui::Checkbox("跳过版权页面", &copy)) {
        sSkipCopy = copy;
        Port_SettingSave("skip_copyright", sSkipCopy);
        Port_SettingsWrite();
    }
    ImGui::SetItemTooltip("跳过每次进入标题画面前显示 5 秒的版权文字。");
    bool hidePointer = Port_Setting("hide_pointer", 1) != 0;
    if (ImGui::Checkbox("游戏中隐藏鼠标", &hidePointer)) {
        Port_SettingSave("hide_pointer", hidePointer);
        Port_SettingsWrite();
    }
    ImGui::SetItemTooltip("在游戏画面中隐藏鼠标；打开设置、联机、退出确认或输入聊天时显示。");
    bool quickSave = Port_Setting("save_quick", 1) != 0;
    if (ImGui::Checkbox("快速存取", &quickSave)) {
        Port_SettingSave("save_quick", quickSave);
        Port_SettingsWrite();
    }
    ImGui::SetItemTooltip("跳过记忆卡确认与等待页面，保存时在角落显示记忆卡图标，启动时自动读取存档。\n在选项中读取时仍会先询问，确认后立即读取。记忆卡缺失、容量不足或保存失败时\n仍会显示提示。联机时始终使用游戏原有页面。关闭后恢复游戏原有存取流程。");
}

// F1 > Online: the settings of online play (Tenkaichi Budokai Online's screens are the way in: the game's main menu), and
// under Advanced the old Dragon Net Battle window, which the screens have replaced (it is kept for testing and for
// whoever still wants it: the same connections, in a plain window).
// (Since 0.1.39 spectators are a lobby's members in its spectators' places, whom its owner lets in or removes: the
// row "Let others watch your matches", for the rooms of two, went with them.)
static void online_tab(void) {
    bool desyncEnds = Port_Setting("net_desync_end", 0) != 0;
    if (ImGui::Checkbox("发生不同步时结束联机对战", &desyncEnds)) {
        Port_SettingSave("net_desync_end", desyncEnds);
        Port_SettingsWrite();
    }
    ImGui::SetItemTooltip("双方会比较计算结果。关闭时，不同步会显示提示，但比赛继续\n"
                          "（双方画面可能不同）；开启时，发生不同步就结束比赛。");
    bool chat = PortChat_Enabled() != 0;
    if (ImGui::Checkbox("联机聊天", &chat)) {
        PortChat_EnabledSet(chat);
    }
    ImGui::SetItemTooltip("与联机对手文字聊天。Tab 打开输入，Enter 发送，Esc 取消。输入时键盘不控制游戏，手柄仍可操作。关闭后不收发聊天。");
    if (chat) {
        if (sChatSize < 0) {
            sChatSize = Port_Setting("chat_size", 1);
            if (sChatSize < 0 || sChatSize > 2) sChatSize = 1;
        }
        static const char *const kChatSizes[] = {"紧凑", "普通", "较大"};
        int size = sChatSize;
        if (ImGui::Combo("聊天窗口大小", &size, kChatSizes, 3)) {
            sChatSize = size;
            Port_SettingSave("chat_size", sChatSize);
            Port_SettingsWrite();
        }
        ImGui::SetItemTooltip("紧凑：输入时 4 行、平时 2 行；普通：6 / 4 行；较大：8 / 6 行，适合大屏幕。");
    }
    ImGui::Spacing();
    if (getenv("BT3_UI_ADVANCED") != NULL) { // (testing, with BT3_UI_OPEN=7: the section opened, for a picture of it)
        ImGui::SetNextItemOpen(true, ImGuiCond_Once);
    }
    if (ImGui::CollapsingHeader("高级选项")) {
        ImGui::TextWrapped("龙网对战是本移植版早期的联机窗口。主菜单中的联机模式已包含它的全部功能：通过房间码或地址加入大厅，以及快速匹配。");
        ImGui::BeginDisabled(Port_NetActive() != 0);
        if (ImGui::Button("打开龙网对战")) {
            gPortNetMenuRequest = 1; // (opened in place of this window at the next frame: frame_build)
            set_open(false);
        }
        ImGui::EndDisabled();
        bool listed = Port_Setting("net_dnb_menu", 0) != 0;
        if (ImGui::Checkbox("在主菜单显示龙网对战", &listed)) {
            Port_SettingSave("net_dnb_menu", listed ? 1 : 0);
            Port_SettingsWrite();
        }
        ImGui::SetItemTooltip("下次打开主菜单时，在联机模式旁显示龙网对战入口。");
    }
}

static const char kFreeNotice[] = "本游戏完全免费，如果你是买来的，请立即退款！";

static void about_tab(void) {
    ImGui::TextWrapped("%s", kFreeNotice);
    ImGui::Spacing();
    ImGui::Separator();
    ImGui::Spacing();
    ImGui::TextUnformatted("原作者：z3xox");
    ImGui::TextUnformatted("项目地址：");
    ImGui::TextLinkOpenURL("https://github.com/z3xox/Tenkaichi3Decomp");
    ImGui::TextUnformatted("汉化与其它修改：珍妮-玛-爵旺");
    ImGui::TextUnformatted("QQ联机群：485869029");
    ImGui::Spacing();
    ImGui::TextWrapped("感谢 有操作的水 小白 皇叔 的赞助与测试!");
    ImGui::Text("版本号 %s", Update_Version());
}

// The title picture's bottom line, positioned within its letterboxed rectangle.
static void title_notice_draw(void) {
    const char *text = "按F1打开设置菜单  本游戏完全免费，如果你是买来的，请立即退款！";
    ImFont *font = sTitleFont ? sTitleFont : ImGui::GetFont();
    float size = (float)gUiPresentH * 0.033f;
    ImVec2 extent = font->CalcTextSizeA(size, FLT_MAX, 0.0f, text);
    float maxWidth = (float)gUiPresentW * 0.90f;
    if (extent.x > maxWidth) {
        size *= maxWidth / extent.x;
        extent = font->CalcTextSizeA(size, FLT_MAX, 0.0f, text);
    }
    float x = (float)gUiPresentX + ((float)gUiPresentW - extent.x) * 0.5f;
    float y = (float)gUiPresentY + (float)gUiPresentH * 0.94f - extent.y * 0.5f;
    ImDrawList *dl = ImGui::GetBackgroundDrawList();
    dl->AddText(font, size, ImVec2(x + 1.0f, y + 1.0f), IM_COL32(0, 0, 0, 180), text);
    dl->AddText(font, size, ImVec2(x, y), IM_COL32(255, 255, 255, 255), text);
}

static void ui_tab(PortVideo &v) {
    if (sLanguageCount > 0) {
        bool overridden = getenv("BT3_MENU_LANG") != NULL && getenv("BT3_MENU_LANG")[0] != '\0';
        ImGui::BeginDisabled(overridden || Port_NetActive());
        if (ImGui::BeginCombo("游戏语言", sLanguages[sLanguageChoice].name)) {
            for (int i = 0; i < sLanguageCount; i++) {
                if (ImGui::Selectable(sLanguages[i].name, i == sLanguageChoice) && i != sLanguageChoice) language_choose(i);
                if (i == sLanguageChoice) ImGui::SetItemDefaultFocus();
            }
            ImGui::EndCombo();
        }
        ImGui::EndDisabled();
        ImGui::SetItemTooltip("根据已安装的翻译选择游戏语言。");
        bool alwaysPrompt = Port_Setting("language_prompt_always", 0) != 0;
        if (ImGui::Checkbox("启动时显示语言选择", &alwaysPrompt)) {
            Port_SettingSave("language_prompt_always", alwaysPrompt);
            Port_SettingsWrite();
        }
        ImGui::SetItemTooltip("有多种语言时，每次正常启动都显示语言列表。");
        if (sLanguageRestartPending) {
            ImGui::TextColored(ImVec4(1.0f, 0.86f, 0.35f, 1.0f), "语言已保存，下次启动生效。");
        }
        ImGui::Separator();
    }
    if (ImGui::BeginCombo("菜单字体", MenuText_FontName(v.menuFont))) {
        for (int i = 0; i < MenuText_FontCount(); i++) {
            if (!MenuText_FontAvailable(i, MENU_TEXT_MENU)) { continue; }
            ImGui::PushID(i);
            if (ImGui::Selectable(MenuText_FontName(i), v.menuFont == i)) { v.menuFont = i; }
            if (v.menuFont == i) { ImGui::SetItemDefaultFocus(); }
            ImGui::PopID();
        }
        ImGui::EndCombo();
    }
    ImGui::SetItemTooltip("原版使用游戏图片，其他字体立即替换已匹配的菜单文字。战斗播报使用下方独立设置。");
    if (ImGui::BeginCombo("战斗字体", MenuText_FontName(v.battleFont))) {
        for (int i = 0; i < MenuText_FontCount(); i++) {
            if (!MenuText_FontAvailable(i, MENU_TEXT_BATTLE)) { continue; }
            ImGui::PushID(i);
            if (ImGui::Selectable(MenuText_FontName(i), v.battleFont == i)) { v.battleFont = i; }
            if (v.battleFont == i) { ImGui::SetItemDefaultFocus(); }
            ImGui::PopID();
        }
        ImGui::EndCombo();
    }
    ImGui::SetItemTooltip("选择原版战斗播报与 HUD 文字，或 fonts.tsv 中列出的战斗字体。");
    if (ImGui::BeginCombo("对话 / 界面字体", MenuText_FontName(v.textFont))) {
        for (int i = 0; i < MenuText_FontCount(); i++) {
            if (!MenuText_FontAvailable(i, MENU_TEXT_DIALOGUE)) { continue; }
            ImGui::PushID(i);
            if (ImGui::Selectable(MenuText_FontName(i), v.textFont == i)) { v.textFont = i; }
            if (v.textFont == i) { ImGui::SetItemDefaultFocus(); }
            ImGui::PopID();
        }
        ImGui::EndCombo();
    }
    ImGui::SetItemTooltip("替换对话、字幕及普通界面的共用字体。原版保留游戏字形；位置、颜色、阴影和图标保持不变。");
    static const char *const kHud[] = {"屏幕两侧", "两侧长血条", "居中（原版 4:3）"};
    ImGui::Combo("战斗界面样式", &v.hudLayout, kHud, 3);
    ImGui::SetItemTooltip("设置宽屏时血条的位置。长血条从两侧延伸到计时器；居中为原版 4:3 布局。");
    {
        bool m43 = Port_Menus43() != 0;
        if (ImGui::Checkbox("菜单使用 4:3 比例", &m43)) {
            Port_Menus43Set(m43);
            Port_SettingSave("menus_43", m43);
            Port_SettingsWrite();
        }
        ImGui::SetItemTooltip("宽屏时菜单保留原版 4:3 比例并填充两侧，战斗仍使用宽屏。");
    }
    {
        static const char *const kBars[] = {"黑色", "边框", "角色面板"};
        int b = sBars < 0 ? 0 : sBars;
        if (ImGui::Combo("两侧填充", &b, kBars, 3)) {
            sBars = b;
            Port_SettingSave("side_bars", sBars);
            Port_SettingsWrite();
        }
        ImGui::SetItemTooltip("设置窄画面两侧的填充。角色面板会显示战斗角色的姓名与形态；可在游戏目录的 bars 文件夹放入 trim.png 和 fill.png 自定义。");
    }
    if (sBars == 2) { // the fighter panels' faces
        font_picker("姓名字体", sPanelFont[0], "面板上的角色姓名字体。可在 fonts/fonts.tsv 添加字体；默认使用列表中的第一个。");
        font_picker("形态字体", sPanelFont[1], "头像下方的形态字体，默认使用列表中的第一个。");
    }
}

extern "C" int gPortMusicFollows; // snd_adx.c: 1 = looping music is sped up or slowed down with the game

static void audio_tab(PortVideo &v) {
    ImGui::SliderInt("音乐", &v.music, 0, 200, "%d%%", ImGuiSliderFlags_AlwaysClamp);
    ImGui::SliderInt("音效", &v.effects, 0, 200, "%d%%", ImGuiSliderFlags_AlwaysClamp);
    ImGui::SetItemTooltip("打击、气弹和菜单音效；下一次播放时生效。");
    ImGui::SliderInt("语音", &v.voices, 0, 200, "%d%%", ImGuiSliderFlags_AlwaysClamp);
    ImGui::SetItemTooltip("战斗中的角色语音及战斗外的对白。");
    ImGui::SliderInt("场景声音", &v.stage, 0, 200, "%d%%", ImGuiSliderFlags_AlwaysClamp);
    ImGui::SetItemTooltip("场景的风声、水声等环境声音及效果。");
    {
        bool follows = gPortMusicFollows > 0;
        ImGui::Spacing();
        if (ImGui::Checkbox("音乐跟随游戏速度", &follows)) {
            gPortMusicFollows = follows;
            Port_SettingSave("music_follows_speed", follows);
            Port_SettingsWrite(); // (in the file at once: it was lost at the end unless another setting was written after it)
        }
        ImGui::SetItemTooltip("开启后，音乐的播放速度和音调跟随游戏速度；对白始终跟随游戏速度。");
    }
}

// Cheats. "Unlock everything" is the game's own leftover debug function (Save_UnlockAll, which nothing in the game
// calls): the request is set here and carried out on the game's side at the next vertical blank (headless.c).
extern "C" {
extern volatile int gPortUnlockAll, gPortUnlockDone;
}

extern "C" int Port_GameSpeed(void);          // plat_stub.c: the player's own game speed, percent; never used online
extern "C" void Port_GameSpeedSet(int percent);
extern "C" void Port_AudioRefresh(void);

static void cheats_tab(void) {
    {
        int speed = Port_GameSpeed();
        if (ImGui::SliderInt("游戏速度", &speed, 50, 200, "%d%%", ImGuiSliderFlags_AlwaysClamp)) {
            Port_GameSpeedSet(speed);
            Port_AudioRefresh();
        }
        if (ImGui::IsItemDeactivatedAfterEdit()) {
            Port_SettingsWrite(); // (when the slider is let go: the speed was lost at the end unless another setting was written)
        }
        ImGui::SetItemTooltip("本地游戏速度，声音保持音调。原版为 100%%，竞技常用 114%%。联机使用房主或匹配队列的速度。");
        ImGui::SameLine();
        if (ImGui::Button("重置")) {
            Port_GameSpeedSet(100);
            Port_AudioRefresh();
            Port_SettingsWrite();
        }
        ImGui::Separator();
        ImGui::Spacing();
    }
    ImGui::TextWrapped("使用游戏原有调试功能，解锁全部角色、场景、音乐和道具，并将金钱设为最大值。");
    ImGui::Spacing();
    ImGui::TextWrapped("同时会清空记录列表，下一次存档后永久生效。请在存档加载完成后使用。");
    ImGui::Spacing();
    if (ImGui::Button("解锁全部…")) {
        ImGui::OpenPopup("要解锁全部内容吗？");
    }
    if (gPortUnlockDone) {
        ImGui::SameLine();
        ImGui::TextUnformatted("已完成。");
    }
    if (ImGui::BeginPopupModal("要解锁全部内容吗？", NULL, ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::TextUnformatted("记录列表将被清空。游戏保存后无法撤销。");
        ImGui::Spacing();
        if (ImGui::Button("解锁", ImVec2(U(140.0f), 0.0f))) {
            gPortUnlockAll = 1;
            ImGui::CloseCurrentPopup();
        }
        ImGui::SameLine();
        if (ImGui::Button("取消", ImVec2(U(140.0f), 0.0f))) {
            ImGui::CloseCurrentPopup();
        }
        ImGui::EndPopup();
    }
}

// The Controls tab's part for the sticks: each stick of the player's controller as it is now (the dot), its deadzone
// (the shaded middle: a circle, or the game's own square), what the game is given for it (the ring, and in numbers),
// the triggers, and the settings for these and for vibration. For seeing a stick that drifts and choosing a deadzone
// that covers it.
static void sticks_panel(int player) {
    static const char *const kStick[2] = {"左摇杆", "右摇杆"}, *const kTrigger[2] = {"左扳机", "右扳机"};
    static const char *const kDir[5] = {"", "up", "down", "left", "right"};
    const float R = U(42.0f), box = 2.0f * R + U(8.0f);
    const ImU32 colZone = ImGui::GetColorU32(ImGuiCol_Text, 0.22f);
    const ImU32 colRaw = ImGui::GetColorU32(ImGuiCol_Text), colGame = ImGui::GetColorU32(ImVec4(1.0f, 0.75f, 0.2f, 1.0f));
    int *dead = PortInput_Deadzone(player), *vib = PortInput_Vibration(player);
    PortStickView view;
    char label[64];

    PortInput_StickView(player, &view);
    if (!ImGui::BeginTable("sticks", 2)) {
        return;
    }
    float top = 0.0f;
    for (int s = 0; s < 2; s++) {
        ImGui::TableNextColumn();
        if (s == 0) {
            top = ImGui::GetCursorScreenPos().y;
        } else { // (the second cell would start lower by the text offset of the first one's last line)
            ImGui::SetCursorScreenPos(ImVec2(ImGui::GetCursorScreenPos().x, top));
        }
        ImDrawList *dl = ImGui::GetWindowDrawList();
        ImVec2 at = ImGui::GetCursorScreenPos(), c(at.x + box * 0.5f, at.y + box * 0.5f);
        ImGui::Dummy(ImVec2(box, box));
        dl->AddCircleFilled(c, R, ImGui::GetColorU32(ImGuiCol_FrameBg), 48);
        if (dead[s] < 0) { // the game's own: each axis by itself, 50 of 127.5
            float h = R * 50.0f / 127.5f;
            dl->AddRectFilled(ImVec2(c.x - h, c.y - h), ImVec2(c.x + h, c.y + h), colZone);
        } else if (dead[s] > 0) {
            dl->AddCircleFilled(c, R * (float)dead[s] / 100.0f, colZone, 48);
        }
        dl->AddLine(ImVec2(c.x - R, c.y), ImVec2(c.x + R, c.y), ImGui::GetColorU32(ImGuiCol_Border));
        dl->AddLine(ImVec2(c.x, c.y - R), ImVec2(c.x, c.y + R), ImGui::GetColorU32(ImGuiCol_Border));
        dl->AddCircle(c, R, ImGui::GetColorU32(ImGuiCol_Border), 48);
        if (view.connected) {
            dl->AddCircle(ImVec2(c.x + view.game[s][0] * R, c.y + view.game[s][1] * R), 5.5f, colGame, 16, 1.5f);
            dl->AddCircleFilled(ImVec2(c.x + view.raw[s][0] * R, c.y + view.raw[s][1] * R), 3.0f, colRaw, 12);
        }
        ImGui::SameLine();
        ImGui::SetCursorScreenPos(ImVec2(ImGui::GetCursorScreenPos().x, top));
        ImGui::BeginGroup();
        ImGui::AlignTextToFramePadding(); // (in both cells: the second one's lines start that much lower anyway)
        if (view.connected) {
            ImGui::Text(view.dir[s] != 0 ? "%s: %s" : "%s", kStick[s], kDir[view.dir[s]]);
            ImGui::Text("摇杆  %+.2f %+.2f", view.raw[s][0], view.raw[s][1]);
            ImGui::TextColored(ImGui::ColorConvertU32ToFloat4(colGame), "游戏  %+.2f %+.2f", view.game[s][0], view.game[s][1]);
        } else {
            ImGui::TextUnformatted(kStick[s]);
            ImGui::TextDisabled("未连接手柄");
            ImGui::TextDisabled(" ");
        }
        ImGui::SetNextItemWidth(U(100.0f));
        snprintf(label, sizeof(label), "死区##%d", s);
        ImGui::SliderInt(label, &dead[s], -1, PORT_DEADZONE_MAX, dead[s] < 0 ? "原版" : "%d%%", ImGuiSliderFlags_AlwaysClamp);
        if (ImGui::IsItemDeactivatedAfterEdit()) {
            PortInput_Save();
        }
        ImGui::SetItemTooltip("摇杆死区（中间阴影）。原版使用各轴约 39%% 的方形死区；0%% 至 90%% 为圆形死区。白点为实际摇杆，圆环为传给游戏的值。请覆盖松开摇杆后的漂移范围。");
        ImGui::EndGroup();
    }
    for (int s = 0; s < 2; s++) {
        ImGui::TableNextColumn();
        snprintf(label, sizeof(label), "%d%%%s", (int)(view.trigger[s] * 100.0f + 0.5f), view.triggerHeld[s] ? " pressed" : "");
        ImGui::ProgressBar(view.trigger[s], ImVec2(U(144.0f), 0.0f), label);
        ImGui::SetItemTooltip("扳机超过 %d%% 时视为按下。游戏只区分按下和松开，不读取中间压力值。",
                              (PORT_TRIGGER_AT * 100 + 16383) / 32767);
        ImGui::SameLine(0.0f, ImGui::GetStyle().ItemInnerSpacing.x);
        ImGui::TextUnformatted(kTrigger[s]);
    }
    ImGui::EndTable();
    bool on = vib[0] != 0;
    if (ImGui::Checkbox("震动", &on)) {
        vib[0] = on;
        PortInput_Save();
    }
    ImGui::SetItemTooltip("此玩家手柄的游戏震动（打击、对波、聚气等）。游戏内选项的震动也需开启；录像及电脑控制角色不会震动。");
    ImGui::BeginDisabled(!on);
    ImGui::SameLine();
    ImGui::SetNextItemWidth(U(160.0f));
    ImGui::SliderInt("强度", &vib[1], 0, 100, "%d%%", ImGuiSliderFlags_AlwaysClamp);
    if (ImGui::IsItemDeactivatedAfterEdit()) {
        PortInput_Save();
    }
    ImGui::SameLine();
    if (ImGui::Button("测试")) {
        PortInput_VibrationTest(player);
    }
    ImGui::SetItemTooltip("以当前强度测试双马达震动，持续半秒。");
    ImGui::EndDisabled();
    if (view.connected && !view.canVibrate) {
        ImGui::SameLine();
        ImGui::TextDisabled("（此手柄不支持震动）");
    }
}

// Wii mapping page: Dolphin-style groups, with the same expression used for input
// and live tests. Physical controller input is never used for navigation here.
static void wii_row(int player, int split, int action, const float *values, const char *name = NULL) {
    ImGui::TableNextRow(); ImGui::TableNextColumn();
    ImGui::AlignTextToFramePadding();
    ImGui::TextUnformatted(name ? name : PortWii_ActionLabel(split, action));
    ImGui::TableNextColumn();
    PortWii_BindingButton(player, split, action, values[action]);
}
static bool wii_rows(const char *id) {
    if (!ImGui::BeginTable(id, 2, ImGuiTableFlags_SizingStretchProp)) { return false; }
    ImGui::TableSetupColumn("action", ImGuiTableColumnFlags_WidthFixed, U(74));
    ImGui::TableSetupColumn("binding", ImGuiTableColumnFlags_WidthStretch);
    return true;
}
static void wii_stick(int player, int stick, const float *values) {
    float x = values[stick ? 23 : 19] - values[stick ? 22 : 18];
    float y = values[stick ? 21 : 17] - values[stick ? 20 : 16];
    float size = U(90), radius = U(39);
    ImVec2 at = ImGui::GetCursorScreenPos();
    at.x += (ImGui::GetContentRegionAvail().x - size) * 0.5f;
    ImVec2 center(at.x + size / 2, at.y + size / 2);
    ImDrawList *dl = ImGui::GetWindowDrawList();
    dl->AddCircleFilled(center, radius, ImGui::GetColorU32(ImGuiCol_FrameBg), 32);
    dl->AddCircle(center, radius, ImGui::GetColorU32(ImGuiCol_Border), 32);
    dl->AddLine(ImVec2(center.x - radius, center.y), ImVec2(center.x + radius, center.y), ImGui::GetColorU32(ImGuiCol_Border));
    dl->AddLine(ImVec2(center.x, center.y - radius), ImVec2(center.x, center.y + radius), ImGui::GetColorU32(ImGuiCol_Border));
    PortStickView view; PortInput_StickView(player, &view);
    dl->AddCircleFilled(ImVec2(center.x + view.raw[stick][0] * radius, center.y + view.raw[stick][1] * radius), 3,
                       ImGui::GetColorU32(ImGuiCol_Text), 12);
    dl->AddCircleFilled(ImVec2(center.x + x * radius, center.y + y * radius), 5,
                       ImGui::GetColorU32(ImVec4(0.35f, 0.95f, 0.55f, 1)), 12);
    ImGui::Dummy(ImVec2(size, size));
    ImGui::SetItemTooltip("白点：实际摇杆；绿点：共用表达式的输出（也包括键盘与鼠标）。");
}
static void wii_deadzone(int player, int stick) {
    int *dead = PortInput_Deadzone(player);
    ImGui::PushID(stick);
    ImGui::SetNextItemWidth(-U(60));
    ImGui::SliderInt("死区", &dead[stick], -1, PORT_DEADZONE_MAX, dead[stick] < 0 ? "原版" : "%d%%", ImGuiSliderFlags_AlwaysClamp);
    if (ImGui::IsItemDeactivatedAfterEdit()) { PortInput_Save(); }
    ImGui::SetItemTooltip("原版为各轴约 39%% 的方形死区；0%% 至 90%% 为圆形死区。沿用官方摇杆处理算法。");
    ImGui::PopID();
}
static void wii_panel(int player, int split) {
    float values[PORT_WII_ACTIONS];
    PortWii_PreviewBindings(player, split, values);
    ImGui::TextDisabled("左键检测 · 中键清除 · 右键逻辑设置 · 绿灯为触发（>50%%） · 此页仅用键鼠操作菜单");
    int columns = ImGui::GetContentRegionAvail().x >= U(900) ? 4 : 2;
    ImGui::PushStyleVar(ImGuiStyleVar_FramePadding, ImVec2(U(6), U(2)));
    ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing, ImVec2(U(8), U(4)));
    if (ImGui::BeginTable("wii_groups", columns, ImGuiTableFlags_SizingStretchSame)) {
        for (int group = 0; group < 4; group++) {
            ImGui::TableNextColumn(); ImGui::PushID(group);
            ImGui::BeginChild("group", ImVec2(0, 0), ImGuiChildFlags_Borders | ImGuiChildFlags_AutoResizeY,
                              ImGuiWindowFlags_NoScrollbar | ImGuiWindowFlags_NoScrollWithMouse);
            if (group == 0) {
                ImGui::SeparatorText("按键");
                if (wii_rows("buttons")) {
                    const int actions[] = {6, 4, 5, 7, 13, 14, 15};
                    for (int a : actions) { wii_row(player, split, a, values); }
                    if (split) {
                        wii_row(player, split, 26, values);
                        wii_row(player, split, 24, values);
                        wii_row(player, split, 25, values);
                    }
                    ImGui::EndTable();
                }
                ImGui::TextWrapped("菜单：攻击键确认，飞行键返回。暴血仍需双击。");
            } else if (group == 1 || group == 2) {
                int stick = group - 1;
                ImGui::SeparatorText(stick ? "角色 / 视角" : "移动摇杆");
                wii_stick(player, stick, values);
                if (wii_rows("stick")) {
                    const char *directions[] = {"上", "下", "左", "右"};
                    for (int i = 0; i < 4; i++) { wii_row(player, split, 16 + stick * 4 + i, values, stick ?
                        (i == 0 ? "换人" : i == 1 ? "变身" : i == 2 ? "左视角" : "右视角") : directions[i]); }
                    ImGui::EndTable();
                }
                wii_deadzone(player, stick);
                if (!stick) {
                    ImGui::SeparatorText("方向键");
                    if (wii_rows("dpad")) {
                        const char *names[] = {"上", "下", "左", "右"};
                        for (int a = 0; a < 4; a++) { wii_row(player, split, a, values, names[a]); }
                        ImGui::EndTable();
                    }
                } else if (!split) { ImGui::TextWrapped("左右同时切换角色；双击左右暴血。勾选控制分离可分别设置。"); }
            } else {
                ImGui::SeparatorText("升降 / 扳机");
                PortStickView view; PortInput_StickView(player, &view);
                ImGui::ProgressBar(view.trigger[0], ImVec2(-1, 0), "左扳机");
                ImGui::ProgressBar(view.trigger[1], ImVec2(-1, 0), "右扳机");
                if (wii_rows("triggers")) {
                    const int actions[] = {10, 11, 8, 9};
                    for (int a : actions) { wii_row(player, split, a, values); }
                    ImGui::EndTable();
                }
                ImGui::SeparatorText("震动");
                int *vib = PortInput_Vibration(player);
                bool enabled = vib[0] != 0;
                if (ImGui::Checkbox("启用", &enabled)) { vib[0] = enabled; PortInput_Save(); }
                ImGui::BeginDisabled(!enabled);
                ImGui::SetNextItemWidth(-U(60));
                ImGui::SliderInt("强度", &vib[1], 0, 100, "%d%%", ImGuiSliderFlags_AlwaysClamp);
                if (ImGui::IsItemDeactivatedAfterEdit()) { PortInput_Save(); }
                if (ImGui::Button("测试震动")) { PortInput_VibrationTest(player); }
                ImGui::EndDisabled();
            }
            ImGui::EndChild(); ImGui::PopID();
        }
        ImGui::EndTable();
    }
    ImGui::PopStyleVar(2);
    if (ImGui::CollapsingHeader("程序快捷键")) {
        char label[128];
        snprintf(label, sizeof(label), "%s##overlay_key", sCapKind == 1 && sCapAction == PORT_ACTIONS ? "请按键…" :
                 SDL_GetScancodeName((SDL_Scancode)*PortInput_OverlayKey()));
        if (ImGui::Button(label)) { capture(1, player, PORT_ACTIONS); }
        ImGui::SameLine(); ImGui::TextUnformatted("打开设置窗口");
        snprintf(label, sizeof(label), "%s##overlay_pad", sCapKind == 2 && sCapAction == PORT_ACTIONS ? "请按手柄键…" :
                 *PortInput_OverlayPad() < 0 ? "START + SELECT" : pad_source_name(*PortInput_OverlayPad()));
        if (ImGui::Button(label)) { capture(2, player, PORT_ACTIONS); }
        ImGui::SameLine(); ImGui::TextUnformatted("手柄快捷键");
        snprintf(label, sizeof(label), "%s##chat_key", sCapKind == 1 && sCapAction == PORT_ACTIONS + 1 ? "请按键…" :
                 SDL_GetScancodeName((SDL_Scancode)*PortInput_ChatKey()));
        if (ImGui::Button(label)) { capture(1, player, PORT_ACTIONS + 1); }
        ImGui::SameLine(); ImGui::TextUnformatted("打开联机聊天");
    }
}

static void controls_tab(void) {
    int &player = sControlPlayer;
    int previousPlayer = player;
    char label[96];
    int count = 0;

    ImGui::RadioButton("玩家 1", &player, 0);
    ImGui::SameLine();
    ImGui::RadioButton("玩家 2", &player, 1);
    if (player != previousPlayer) { PortWii_Cancel(); }
    ImGui::SameLine(0.0f, 24.0f);
    int *mode = PortInput_ControlMode(player);
    if (ImGui::Button(*mode ? "控制模式：Wii" : "控制模式：PS2")) {
        *mode = !*mode;
        WiiProfiles::Cancel();
        PortWii_Cancel();
        sCapKind = 0;
        gPortInputCapture = 0;
        PortInput_Save();
    }
    ImGui::SetItemTooltip("Wii 默认：右摇杆上换人、下变身，左右切视角 / 角色，双击左右暴血。菜单用左摇杆移动。\nRB / LB 升降，RT / LT 高速升降，按住右摇杆聚气。菜单 X 确认、A 返回。\nPS2 与 Wii 的键盘配置独立保存；勾选控制分离可独立绑定各功能。");
    bool wii = *mode != 0;
    int *split = PortInput_ControlSplit(player);
    if (wii) {
        ImGui::SameLine();
        bool separated = *split != 0;
        if (ImGui::Checkbox("控制分离", &separated)) {
            *split = separated;
            PortWii_Cancel();
            PortInput_Save();
        }
        ImGui::SetItemTooltip("分别设置视角、角色选择和暴血；暴血依旧需要双击。\n新拆出的角色选择与暴血默认为未设置，请自行绑定。");
        WiiProfiles::Draw(player, sUiScale);
    }
    bool separate = wii && *split;
    int *slot = PortInput_PadSlot(player), *keys = PortInput_Keys(player), *pads = PortInput_PadButtons(player);
    SDL_JoystickID *ids = SDL_GetGamepads(&count);
    if (*slot < 0) {
        snprintf(label, sizeof(label), "无");
    } else if (*slot < count) {
        snprintf(label, sizeof(label), "%d: %s", *slot + 1, SDL_GetGamepadNameForID(ids[*slot]));
    } else {
        snprintf(label, sizeof(label), "手柄 %d（未连接）", *slot + 1);
    }
    ImGui::SetNextItemWidth(U(300.0f));
    if (ImGui::BeginCombo("手柄", label)) {
        if (ImGui::Selectable("无", *slot < 0)) { *slot = -1; PortInput_Save(); }
        for (int i = 0; i < (count > 4 ? count : 4); i++) {
            if (i < count) {
                snprintf(label, sizeof(label), "%d: %s", i + 1, SDL_GetGamepadNameForID(ids[i]));
            } else {
                snprintf(label, sizeof(label), "手柄 %d（未连接）", i + 1);
            }
            if (ImGui::Selectable(label, *slot == i)) { *slot = i; PortInput_Save(); }
        }
        ImGui::EndCombo();
    }
    SDL_free(ids);
    ImGui::SameLine();
    if (ImGui::Button("恢复默认设置")) {
        PortInput_ResetDefaults(player);
        PortInput_Save();
    }
    if (wii) { wii_panel(player, separate); return; }
    if (ImGui::CollapsingHeader("摇杆、扳机与震动", ImGuiTreeNodeFlags_DefaultOpen)) {
        sticks_panel(player);
    }
    ImGui::TextDisabled(wii ? "左键检测；中键清除；右键设置逻辑表达式。Esc 取消检测。" :
                             "点击绑定后按下新按键。Esc 取消，Delete 清除；");
    if (!wii) {
        ImGui::TextDisabled("手柄检测等待 5 秒后自动取消。");
    }
    // (never lower than a few rows: in a small window the tab scrolls as a whole instead)
    if (ImGui::BeginTable("bindings", 3, ImGuiTableFlags_RowBg | ImGuiTableFlags_ScrollY | ImGuiTableFlags_BordersInnerV,
                          ImVec2(0.0f, ImGui::GetContentRegionAvail().y > U(140.0f) ? ImGui::GetContentRegionAvail().y : U(140.0f)))) {
        ImGui::TableSetupScrollFreeze(0, 1);
        ImGui::TableSetupColumn("动作");
        ImGui::TableSetupColumn("键盘");
        if (!wii || separate) {
            ImGui::TableSetupColumn("手柄");
        }
        ImGui::TableHeadersRow();
        {   // what opens and closes this window (not a player's: one for the program)
            const int a = PORT_ACTIONS;
            bool waitKey = sCapKind == 1 && sCapAction == a, waitPad = sCapKind == 2 && sCapAction == a;
            int key = *PortInput_OverlayKey(), pad = *PortInput_OverlayPad();
            ImGui::TableNextRow();
            ImGui::TableNextColumn();
            ImGui::AlignTextToFramePadding();
            ImGui::TextUnformatted("打开设置窗口");
            ImGui::TableNextColumn();
            snprintf(label, sizeof(label), "%s##k%d", waitKey ? "请按键…" : key > 0 ? SDL_GetScancodeName((SDL_Scancode)key) : "-", a);
            if (ImGui::Button(label, ImVec2(-FLT_MIN, 0.0f))) {
                capture(1, player, a);
            }
            if (!wii || separate) {
                ImGui::TableNextColumn();
                snprintf(label, sizeof(label), "%s##p%d", waitPad ? "请按手柄键…" : pad >= 0 ? pad_source_name(pad) : "START + SELECT", a);
                if (ImGui::Button(label, ImVec2(-FLT_MIN, 0.0f))) {
                    capture(2, player, a);
                }
            }
        }
        {   // what opens the online chat (not a player's: one for the program)
            const int a = PORT_ACTIONS + 1;
            bool waitKey = sCapKind == 1 && sCapAction == a;
            int key = *PortInput_ChatKey();
            ImGui::TableNextRow();
            ImGui::TableNextColumn();
            ImGui::AlignTextToFramePadding();
            ImGui::TextUnformatted("打开联机聊天");
            ImGui::TableNextColumn();
            snprintf(label, sizeof(label), "%s##k%d", waitKey ? "请按键…" : key > 0 ? SDL_GetScancodeName((SDL_Scancode)key) : "Tab", a);
            if (ImGui::Button(label, ImVec2(-FLT_MIN, 0.0f))) {
                capture(1, player, a);
            }
            if (!wii || separate) {
                ImGui::TableNextColumn();
                ImGui::TextDisabled("-");
            }
        }
        for (int a = 0; a < (separate ? PORT_WII_ACTIONS : PORT_ACTIONS); a++) {
            bool waitKey = sCapKind == 1 && sCapPlayer == player && sCapAction == a;
            bool waitPad = sCapKind == 2 && sCapPlayer == player && sCapAction == a;
            ImGui::TableNextRow();
            ImGui::TableNextColumn();
            ImGui::AlignTextToFramePadding();
            ImGui::TextUnformatted(wii ? PortWii_ActionLabel(separate, a) : PortInput_ActionLabel(player, a));
            ImGui::TableNextColumn();
            snprintf(label, sizeof(label), "%s##k%d", waitKey ? "请按键…" : keys[a] > 0 ? SDL_GetScancodeName((SDL_Scancode)keys[a]) : "-", a);
            if (ImGui::Button(label, ImVec2(-FLT_MIN, 0.0f))) {
                capture(1, player, a);
            }
            if (!wii) {
                ImGui::TableNextColumn();
                if (a < PORT_PAD_BUTTONS) {
                    snprintf(label, sizeof(label), "%s##p%d", waitPad ? "请按手柄键…" : pad_source_name(pads[a]), a);
                    if (ImGui::Button(label, ImVec2(-FLT_MIN, 0.0f))) {
                        capture(2, player, a);
                    }
                } else {
                    ImGui::AlignTextToFramePadding();
                    ImGui::TextDisabled(a < 20 ? "左摇杆" : "右摇杆");
                }
            }
        }
        ImGui::EndTable();
    }
}

static void build(void) {
    PortVideo v, was;
    ImGuiIO &io = ImGui::GetIO();
    bool open = true;
    bool openLobby = false;

    GsGpu_GetSettings(&v);
    was = v;
    if (sCapKind == 2 && SDL_GetTicks() > sCapUntil) { // nothing was pressed: the binding stays
        sCapKind = 0;
        gPortInputCapture = 0;
    }
    if (pad_pressed(ImGuiKey_GamepadFaceRight)) { // Circle / B: out of the window
        open = false;
    }
    if (sForceTab < 0 && (pad_pressed(ImGuiKey_GamepadL1) || pad_pressed(ImGuiKey_GamepadR1))) {
        sForceTab = (sTab + (ImGui::IsKeyPressed(ImGuiKey_GamepadL1, false) ? 8 : 1)) % 9;
        sPadTab = true;
    }
    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.5f), ImGuiCond_Appearing, ImVec2(0.5f, 0.5f));
    // (760 high where the picture has the room: the Controls tab's sticks and its list of bindings together)
    bool wide = (sTab == 4 || sForceTab == 4) && *PortInput_ControlMode(sControlPlayer);
    static bool wasWide;
    {
        float sw = U(wide ? 1120.0f : 720.0f);
        float sh = U(wide ? 900.0f : io.DisplaySize.y >= U(800.0f) ? 760.0f : 600.0f);
        ImGui::SetNextWindowSize(ImVec2(std::min(sw, io.DisplaySize.x * 0.96f),
                                       std::min(sh, io.DisplaySize.y * 0.94f)),
                                 wide != wasWide ? ImGuiCond_Always : ImGuiCond_Appearing);
    }
    wasWide = wide;
    if (ImGui::Begin("设置", &open, ImGuiWindowFlags_NoCollapse)) {
        PortLobbyView lv;
        bool inLobby = Port_LobbyView(&lv) && lv.inMatch;
        if (inLobby) { // a lobby's match: the ways back (the owner: for everyone) and out
            ImGui::AlignTextToFramePadding();
            ImGui::TextColored(ImVec4(1.0f, 0.85f, 0.3f, 1.0f), "大厅%s%s", lv.code[0] != '\0' ? " " : "", lv.code);
            if (lv.owner) {
                ImGui::SameLine();
                if (ImGui::Button("返回大厅")) {
                    Port_LobbyDo(LOBBY_BACK, 0, 0);
                    open = false;
                }
                ImGui::SetItemTooltip("结束所有玩家的比赛并返回大厅，可在那里修改规则。");
            }
            ImGui::SameLine();
            if (ImGui::Button(lv.owner ? "关闭大厅" : "退出大厅")) {
                Port_LobbyDo(LOBBY_LEAVE, 0, 0);
                open = false;
            }
            ImGui::SetItemTooltip(lv.owner ? "为所有玩家结束比赛并关闭大厅。" : "返回主菜单。玩家退出会结束比赛；观战者退出不影响其他人。");
            ImGui::Separator();
        }
        if (Port_NetSpectating()) { // watching a match: whose view, and the way out
            ImGui::AlignTextToFramePadding();
            ImGui::TextColored(ImVec4(1.0f, 0.85f, 0.3f, 1.0f), "正在观战：%s 对 %s", Port_NetName(0), Port_NetName(1));
            ImGui::SameLine();
            if (ImGui::Button("切换视角")) {
                spec_view_next();
            }
            ImGui::SetItemTooltip("在 1P 视角、2P 视角和双方分屏间切换。观战时也可按 V 或 R1。");
            if (!inLobby) { // (in a lobby: "退出大厅", above)
                ImGui::SameLine();
                if (ImGui::Button("结束观战")) {
                    Port_NetSpecLeave();
                    open = false;
                }
            }
            ImGui::TextDisabled("视角：%s", spec_view_name(Port_NetSpecView()));
            ImGui::Separator();
        }
        update_panel();
        // the tabs in a region of their own, above a last line that is always there
        ImGui::BeginChild("body", ImVec2(0.0f, -ImGui::GetFrameHeightWithSpacing() - ImGui::GetStyle().ItemSpacing.y), ImGuiChildFlags_NavFlattened);
        if (ImGui::BeginTabBar("tabs")) {
            if (tab("画面", 0)) { video_tab(v); ImGui::EndTabItem(); }
            if (tab("特效", 1)) { effects_tab(v); ImGui::EndTabItem(); }
            if (tab("声音", 2)) { audio_tab(v); ImGui::EndTabItem(); }
            if (tab("界面", 3)) { ui_tab(v); ImGui::EndTabItem(); }
            if (tab("控制", 4)) {
                bool cs = Port_ClashSquare() != 0;
                if (ImGui::Checkbox("对波 / 对冲：攻击键计为方向输入", &cs)) {
                    Port_ClashSquareSet(cs);
                }
                ImGui::SetItemTooltip("对波或对冲时，游戏按新按下的方向计数。开启后，每次按攻击键也计为一次方向输入。");
                if (cs) {
                    static const int kQuarters[] = {4, 6, 7, 8, 9};
                    static const char *const kWorth[] = {"1", "1.5", "1.75", "2", "2.25"};
                    int at = 4;
                    for (int i = 0; i < 5; i++) {
                        if (kQuarters[i] == Port_ClashSquareX()) {
                            at = i;
                        }
                    }
                    ImGui::SameLine();
                    ImGui::SetNextItemWidth(U(80.0f));
                    if (ImGui::Combo("每次按下", &at, kWorth, 5)) {
                        Port_ClashSquareXSet(kQuarters[at]);
                    }
                    ImGui::SetItemTooltip("每次攻击键的计数权重。1 等于一次方向键输入，每帧最多计一次。");
                }
                ImGui::Separator();
                controls_tab();
                ImGui::EndTabItem();
            }
            if (tab("辅助", 5)) { cheats_tab(); ImGui::EndTabItem(); }
            if (tab("其他", 6)) { misc_tab(); ImGui::EndTabItem(); }
            if (tab("联机", 7)) { online_tab(); ImGui::EndTabItem(); }
            ImGui::BeginDisabled(Port_NetActive() != 0 || Lobby_Active() != 0);
            if (ImGui::TabItemButton("大厅")) { openLobby = true; }
            ImGui::EndDisabled();
            if (tab("关于", 8)) { about_tab(); ImGui::EndTabItem(); }
            ImGui::EndTabBar();
        }
        ImGui::EndChild();
        if (sPadTab) { // (a tab chosen with the shoulder buttons)
            sPadTab = false;
            sTab = sForceTab;
            sForceTab = -1;
        } else if (ImGui::GetFrameCount() > 3) {
            sForceTab = -1;
        }
        ImGui::Separator();
        if (ImGui::Button("退出游戏")) {
            Ui_QuitAsk();
        }
        if ((io.BackendFlags & ImGuiBackendFlags_HasGamepad) != 0) {
            ImGui::SameLine();
            ImGui::TextDisabled(sTab == 4 ? "控制设置页：使用键鼠操作菜单，手柄用于绑定与输入测试" : "方向键移动；PS2：A 确认 / B 返回；Wii：X 确认 / A 返回；LB / RB 切换标签");
        }
        PortWii_DrawEditor();
    }
    ImGui::End();
    if (memcmp(&v, &was, sizeof(v)) != 0) {
        GsGpu_SetSettings(&v);
    }
    if (!open) {
        set_open(false);
    } else if (openLobby) {
        OnlineLobby::Open();
        net_open();
    }
}

static bool sBuilt; // this frame has something to draw: the window, or the line over the picture

void Ui_DrawAgain(SDL_GPUCommandBuffer *cmd, SDL_GPUTexture *target) {
    ImDrawData *dd = sReady && sBuilt ? ImGui::GetDrawData() : NULL; // (sBuilt: Ui_Draw made a picture this frame)
    SDL_GPUColorTargetInfo ti;
    SDL_GPURenderPass *pass;

    if (dd == NULL || dd->CmdListsCount == 0 || dd->DisplaySize.x <= 0.0f || dd->DisplaySize.y <= 0.0f) {
        return;
    }
    ImGui_ImplSDLGPU3_PrepareDrawData(dd, cmd);
    SDL_zero(ti);
    ti.texture = target;
    ti.load_op = SDL_GPU_LOADOP_LOAD;
    ti.store_op = SDL_GPU_STOREOP_STORE;
    pass = SDL_BeginGPURenderPass(cmd, &ti, 1, NULL);
    ImGui_ImplSDLGPU3_RenderDrawData(dd, cmd, pass);
    SDL_EndGPURenderPass(pass);
}

static char sNotice[256];
static Uint64 sNoticeUntil;
static volatile int sNoticeNew;

static void set_notice(const char *text, Uint64 ms) { // (from this thread: shown at once, for `ms`)
    SDL_strlcpy(sNotice, text, sizeof(sNotice));
    sNoticeUntil = SDL_GetTicks() + ms;
}

extern "C" void Port_UiNotice(const char *text) {
    SDL_strlcpy(sNotice, text != NULL ? UiZh(text) : "", sizeof(sNotice));
    sNoticeNew = 1;
}

// A line in the middle of the screen, the picture behind it dimmed, while the game's thread waits inside a blank
// (the start of an online match, gs/net.c): drawn by the frames it shows meanwhile (Gs_HoldFrame). `ms` > 0: the
// wait is over; the line stays that long more, over the game's own pictures and without the dimming. NULL: gone.
static char sBanner[256];
static Uint64 sBannerUntil; // 0: while the game waits
extern "C" void Port_UiBanner(const char *text, int ms) {
    if (text != NULL) {
        SDL_strlcpy(sBanner, text, sizeof(sBanner));
    }
    if (text == NULL && ms <= 0) {
        sBanner[0] = '\0';
    }
    sBannerUntil = ms > 0 ? SDL_GetTicks() + (Uint64)ms : 0;
}

// The save icon (quick saving, src/sys/mcflow_a.c): a small memory card in the bottom right corner of the picture
// while the game saves, at least a second, then it fades. Set from the game's thread: 1 saving, 0 saved, -1 the
// game's own window took over (an error: the icon goes at once).
static volatile int sSaving;
static Uint64 sSaveFrom, sSaveEnd; // (0: not shown; the end, 0 while it saves)
extern "C" void Port_UiSaving(int state) {
    sSaving = state;
}

static bool save_icon_on(Uint64 now) {
    int state = sSaving;
    if (state > 0 && (sSaveFrom == 0 || sSaveEnd != 0)) {
        sSaveFrom = now;
        sSaveEnd = 0;
    }
    if (sSaveFrom != 0 && sSaveEnd == 0 && (state <= 0 || now - sSaveFrom > 15000)) { // (or a flow left half-way)
        sSaveEnd = state < 0 || now > sSaveFrom + 1000 ? now : sSaveFrom + 1000;
        if (state == 0) {
            PortA11y_Say(PortA11y_Label("Saved"), 0);
        }
    }
    if (sSaveEnd != 0 && now >= sSaveEnd + 400) {
        sSaveFrom = 0;
    }
    return sSaveFrom != 0;
}

static void save_icon_draw(Uint64 now) {
    ImDrawList *dl = ImGui::GetForegroundDrawList();
    float h = (float)gUiPresentH * 0.055f, w = h * 0.78f;
    float x1 = (float)(gUiPresentX + gUiPresentW) - h * 0.6f, y1 = (float)(gUiPresentY + gUiPresentH) - h * 0.6f;
    float x0 = x1 - w, y0 = y1 - h;
    float a = sSaveEnd != 0 && now > sSaveEnd ? 1.0f - (float)(now - sSaveEnd) / 400.0f // fading
                                               : 0.7f + 0.3f * cosf((float)(now - sSaveFrom) * 0.006f); // saving: it pulses
    a = a < 0.0f ? 0.0f : a;
    auto col = [a](int r, int g, int b, int alpha) { return IM_COL32(r, g, b, (int)((float)alpha * a)); };
    ImVec2 card[5] = {ImVec2(x0, y0), ImVec2(x1 - w * 0.28f, y0), ImVec2(x1, y0 + w * 0.28f), ImVec2(x1, y1), ImVec2(x0, y1)};
    dl->AddConvexPolyFilled(card, 5, col(20, 24, 40, 210));
    dl->AddPolyline(card, 5, col(255, 255, 255, 235), ImDrawFlags_Closed, h * 0.06f > 1.5f ? h * 0.06f : 1.5f);
    for (int i = 0; i < 3; i++) { // the contacts
        float cx = x0 + w * (0.17f + 0.19f * (float)i);
        dl->AddRectFilled(ImVec2(cx, y0 + h * 0.1f), ImVec2(cx + w * 0.1f, y0 + h * 0.3f), col(255, 255, 255, 220));
    }
    dl->AddRectFilled(ImVec2(x0 + w * 0.18f, y0 + h * 0.48f), ImVec2(x1 - w * 0.18f, y1 - h * 0.14f), col(245, 140, 35, 235), h * 0.05f);
}

// Watching a match (gs/net.c, a spectator): a line at the top, whose match and whose view, and how to change it.
static const char *spec_view_name(int view) {
    static char text[48];
    if (view == 2) {
        return "双方（分屏）";
    }
    SDL_snprintf(text, sizeof(text), "%s", Port_NetName(view)[0] != '\0' ? Port_NetName(view) : view == 0 ? "玩家 1" : "玩家 2");
    return text;
}

static void spec_view_next(void) {
    Port_NetSpecViewSet((Port_NetSpecView() + 1) % 3);
}

// For the players: who watches their match (small, in the top right corner).
static void watchers_line(void) {
    ImGuiIO &io = ImGui::GetIO();
    char text[200];
    int n = Port_NetWatchers();
    size_t at = (size_t)SDL_snprintf(text, sizeof(text), "%d 人观战：", n);
    for (int i = 0; i < n && at < sizeof(text); i++) {
        at += (size_t)SDL_snprintf(text + at, sizeof(text) - at, "%s%s", i > 0 ? ", " : "", Port_NetWatcher(i));
    }
    ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x - U(6.0f), U(6.0f)), ImGuiCond_Always, ImVec2(1.0f, 0.0f));
    ImGui::SetNextWindowBgAlpha(0.35f);
    if (ImGui::Begin("##watchers", NULL, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoInputs |
                                             ImGuiWindowFlags_NoFocusOnAppearing | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoSavedSettings)) {
        ImGui::SetWindowFontScale(0.85f);
        ImGui::TextDisabled("%s", text);
        ImGui::SetWindowFontScale(1.0f);
    }
    ImGui::End();
}

// The meter: frames shown and the game's speed, and in an online match the connection. A setting (Video tab).
static bool meter_on(void) {
    if (sMeter < 0) {
        sMeter = getenv("BT3_METER") != NULL ? atoi(getenv("BT3_METER")) != 0 : Port_Setting("meter", 0) != 0;
    }
    return sMeter != 0;
}
static float sFps, sSpeed; // frames shown per second; the game's vertical blanks per second as a share of 60

static void meter_count(void) { // once per frame shown
    static Uint64 t0;
    static unsigned frames, blanks0;
    Uint64 now = SDL_GetTicks();
    frames++;
    if (t0 == 0) {
        t0 = now;
        blanks0 = gPortLiveBlanks;
    } else if (now - t0 >= 500) {
        sFps = (float)frames * 1000.0f / (float)(now - t0);
        sSpeed = (float)(gPortLiveBlanks - blanks0) * 1000.0f / (float)(now - t0) / 60.0f * 100.0f;
        frames = 0;
        blanks0 = gPortLiveBlanks;
        t0 = now;
    }
}

static void meter_draw(void) {
    int n[10];
    ImGuiIO &io = ImGui::GetIO();
    ImVec2 pos(U((float)Port_Setting("meter_x", 8)), U((float)Port_Setting("meter_y", 8)));
    pos.x = std::clamp(pos.x, 0.0f, std::max(0.0f, io.DisplaySize.x - U(120)));
    pos.y = std::clamp(pos.y, 0.0f, std::max(0.0f, io.DisplaySize.y - U(40)));
    ImGui::SetNextWindowPos(pos, ImGuiCond_Once);
    ImGui::SetNextWindowBgAlpha(0.6f);
    if (ImGui::Begin("##meter", NULL, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize |
                                          ImGuiWindowFlags_NoFocusOnAppearing | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoSavedSettings)) {
        sMeterHover = ImGui::IsWindowHovered();
        if (sMeterHover && ImGui::IsMouseClicked(ImGuiMouseButton_Left)) sMeterDrag = true;
        if (sMeterDrag && !ImGui::IsMouseDown(ImGuiMouseButton_Left)) {
            ImVec2 at = ImGui::GetWindowPos();
            Port_SettingSave("meter_x", (int)(at.x / sUiScale));
            Port_SettingSave("meter_y", (int)(at.y / sUiScale));
            Port_SettingsWrite();
            sMeterDrag = false;
        }
        // a fight shows 30 frames a second and the menus 60, as on the console; the speed is what should stay at 100%
        ImGui::Text("%.0f 帧/秒   速度 %.0f%%", sFps, sSpeed);
        if (Port_NetStats(n)) {
            if (n[0] >= 0) {
                ImGui::Text("延迟 %d 毫秒%s", n[0], Port_LobbyRelayed() ? "（中继）" : "");
            } else {
                ImGui::TextUnformatted("延迟 …");
            }
            if (n[5] > 0) {
                ImGui::Text("回滚 %d 次/秒，%.1f 帧", n[1], (float)n[2] / 10.0f);
            } else {
                ImGui::TextUnformatted("回滚已关闭");
            }
            ImGui::Text("等待 %d 毫秒/秒（%d 次）", n[4], n[3]);
            if (n[8] == 1) { // gs/net.c wait_end: input packets came, without the frame this copy needed
                ImGui::TextColored(ImVec4(1.0f, 0.8f, 0.3f, 1.0f), "  对方游戏运行落后");
            } else if (n[8] == 2) { // nothing came for most of the wait
                ImGui::TextColored(ImVec4(1.0f, 0.8f, 0.3f, 1.0f), "  未收到对方的数据");
            }
            ImGui::Text("输入延迟 %d%s，最多回滚 %d 帧", n[6], n[7] ? "（自动）" : "", n[5]);
            if (n[9] != 0) { // the desync check found the two games apart (the match goes on)
                ImGui::TextColored(ImVec4(1.0f, 0.4f, 0.4f, 1.0f), "从第 %d 帧起不同步", n[9]);
            }
        }
    }
    ImGui::End();
}

// The name of an added stage or song as text, in the rectangle the menu gives (the strip images' place): cream
// letters with a dark outline, as tall as the rectangle allows, centred for a stage and from the left for a song.
static void name_text(ImDrawList *dl, const char *text, float x, float y, float w, float h, bool centre) {
    ImFont *font = ImGui::GetFont();
    float size = h * (centre ? 0.42f : 0.72f);
    ImVec2 ext = font->CalcTextSizeA(size, 10000.0f, 0.0f, text);
    if (ext.x > w * 0.96f && ext.x > 0.0f) { // a long name: smaller, to fit
        size *= w * 0.96f / ext.x;
        ext = font->CalcTextSizeA(size, 10000.0f, 0.0f, text);
    }
    float tx = centre ? x + (w - ext.x) * 0.5f : x + h * 0.15f, ty = y + (h - ext.y) * 0.5f, o = size * 0.07f + 1.0f;
    for (int k = 0; k < 8; k++) {
        static const float dx[8] = {-1, 0, 1, -1, 1, -1, 0, 1}, dy[8] = {-1, -1, -1, 0, 0, 1, 1, 1};
        dl->AddText(font, size, ImVec2(tx + dx[k] * o, ty + dy[k] * o), IM_COL32(40, 20, 0, 255), text);
    }
    dl->AddText(font, size, ImVec2(tx, ty), IM_COL32(255, 236, 170, 255), text);
}

/* Names in the game's own lettering (namefont.c): a name with no picture in a strip is put together from the letters
   of the disc's name pictures, once, and kept as a texture while it is the one shown (a few are kept, for going up
   and down a list). */
struct FontName {
    SDL_GPUTexture *tex; // NULL: this name cannot be drawn that way (a character the disc's names do not have)
    int style, w, h, choice, resolution;
    char text[64];
    bool used;
};
static FontName sFontNames[12];
static unsigned sFontNext;

static const FontName *font_name(int style, const char *text) {
    int choice = MenuText_GetFont();
    if (choice == 0) {
        for (int i = 1; i < MenuText_FontCount(); i++) {
            if (MenuText_FontAvailable(i, MENU_TEXT_MENU)) { choice = i; break; }
        }
    }
    int resolution = choice ? 4 : 1; // (a font's strip: 4 times the disc's, for a window larger than the game's picture)
    if (text == NULL || text[0] == '\0' || (choice == 0 && !NameFont_Ready())) { // (not ready: asked again next frame)
        return NULL;
    }
    for (FontName &n : sFontNames) {
        if (n.used && n.style == style && n.choice == choice && n.resolution == resolution && strncmp(n.text, text, sizeof(n.text) - 1) == 0) {
            return n.tex != NULL ? &n : NULL;
        }
    }
    FontName &n = sFontNames[sFontNext++ % (sizeof(sFontNames) / sizeof(sFontNames[0]))];
    if (n.used && n.tex != NULL) {
        if (sGL) {
            GsGl_StripTextureFree((unsigned)(intptr_t)n.tex);
        } else {
            SDL_ReleaseGPUTexture(sDevice, n.tex);
        }
    }
    n.tex = NULL;
    n.w = n.h = 0;
    n.used = true;
    n.style = style;
    n.choice = choice; n.resolution = resolution;
    SDL_strlcpy(n.text, text, sizeof(n.text));
    unsigned char *pix;
    if (choice) {
        pix = style == NF_STAGE ? MenuText_RenderStage(n.text, resolution, &n.w, &n.h) :
                                  MenuText_RenderSong(n.text, style == NF_SONG_LIT, resolution, &n.w, &n.h);
    } else {
        pix = NameFont_Compose(style, n.text, &n.w, &n.h);
    }
    if (pix != NULL) {
        n.tex = make_strip(pix, (size_t)n.w * n.h * 4, (uint32_t)n.w, (uint32_t)n.h, 1); // (frees pix)
    }
    if (choice) { n.w /= resolution; n.h /= resolution; }
    return n.tex != NULL ? &n : NULL;
}

/* Draws such a name over the place of the disc's name picture: (x, y) is the corner of that picture's row in the
   window, kx and ky are window pixels per pixel of the row (512 wide). A name longer than the row is made smaller
   to fit, about the row's middle line; a stage name stays in the middle, a song name keeps its left edge. */
static void font_draw(ImDrawList *dl, const FontName *n, float x, float y, float kx, float ky, bool centre) {
    float k = n->w > 512 ? 512.0f / (float)n->w : 1.0f;
    float w = (float)n->w * kx * k, h = (float)n->h * ky * k;
    float x0 = centre ? x + (512.0f * kx - w) * 0.5f : x;
    float y0 = y + ((float)n->h * ky - h) * 0.5f;
    dl->AddImage(ImTextureRef((ImTextureID)(intptr_t)n->tex), ImVec2(x0, y0), ImVec2(x0 + w, y0 + h));
}

// The online chat, in the lower left corner. Put away, it shows the newest lines for a few seconds each in a dark
// rounded card, fading out, and takes no input. While a line is typed it shows the last ones, input field and
// allows selecting/copying text with mouse.
enum { CHAT_SHOWN_MS = 8000, CHAT_FADE_MS = 2000 };

static bool chat_recent(void) {
    PortChatLine l;
    unsigned n = PortChat_Count();
    return n > 0 && PortChat_Line(n - 1, &l) && SDL_GetTicks() - l.atMs < CHAT_SHOWN_MS;
}

static void chat_draw(void) {
    ImGuiIO &io = ImGui::GetIO();
    if (sChatSize < 0) {
        sChatSize = Port_Setting("chat_size", 1);
        if (sChatSize < 0 || sChatSize > 2) sChatSize = 1;
    }
    int rowsTyping = 6, rowsPassive = 4; // Normal: as the chat always was
    float wFactor = 0.42f, minW = 320.0f, maxW = 100000.0f;
    if (sChatSize == 0) { // Compact
        rowsTyping = 4;
        rowsPassive = 2;
        wFactor = 0.28f;
        minW = 240.0f;
        maxW = 380.0f;
    } else if (sChatSize == 2) { // Large
        rowsTyping = 8;
        rowsPassive = 6;
        wFactor = 0.52f;
        minW = 400.0f;
    }
    float w = io.DisplaySize.x * wFactor;
    if (w < U(minW)) w = U(minW);
    if (w > U(maxW)) w = U(maxW);
    unsigned n = PortChat_Count(), rows = sChat ? rowsTyping : rowsPassive, first = n > rows ? n - rows : 0;
    Uint64 now = SDL_GetTicks();
    ImGuiWindowFlags flags = ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoNav |
                             ImGuiWindowFlags_NoSavedSettings | ImGuiWindowFlags_NoFocusOnAppearing;
    if (!sChat) {
        flags |= ImGuiWindowFlags_NoInputs;
    }

    // In the lower left corner (growing upwards) until it is dragged; then where it was left (off the screen: back).
    static ImVec2 sChatPos;
    static bool sChatMoved;
    if (sChatMoved && (sChatPos.x < 0.0f || sChatPos.y < 0.0f || sChatPos.x > io.DisplaySize.x - 50.0f ||
                       sChatPos.y > io.DisplaySize.y - 50.0f)) {
        sChatMoved = false;
    }
    if (!sChatMoved) {
        ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.02f, io.DisplaySize.y * 0.86f), ImGuiCond_Always, ImVec2(0.0f, 1.0f));
    } else if (!sChat) {
        ImGui::SetNextWindowPos(sChatPos, ImGuiCond_Always);
    }

    float bgAlpha = 0.85f;
    if (!sChat) {
        float newestAlpha = 1.0f;
        PortChatLine lastLine;
        if (n > 0 && PortChat_Line(n - 1, &lastLine)) {
            Uint64 age = now - lastLine.atMs;
            if (age >= CHAT_SHOWN_MS) {
                return;
            }
            if (age > CHAT_SHOWN_MS - CHAT_FADE_MS) {
                newestAlpha = (float)(CHAT_SHOWN_MS - age) / (float)CHAT_FADE_MS;
            }
        }
        bgAlpha = 0.65f * newestAlpha;
    }
    ImGui::SetNextWindowBgAlpha(bgAlpha);

    ImGui::PushStyleVar(ImGuiStyleVar_WindowRounding, U(8.0f));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowPadding, ImVec2(U(8.0f), U(6.0f)));
    ImGui::PushStyleVar(ImGuiStyleVar_WindowBorderSize, sChat ? 1.0f : 0.0f);
    ImGui::PushStyleVar(ImGuiStyleVar_ItemSpacing, ImVec2(U(4.0f), U(2.0f)));
    ImGui::PushStyleColor(ImGuiCol_Border, ImVec4(1.0f, 0.75f, 0.2f, 0.5f));

    if (sChat && sChatFocus) {
        ImGui::SetNextWindowFocus();
    }
    if (ImGui::Begin("##chat", NULL, flags)) {
        if (sChat && ImGui::IsWindowHovered() && ImGui::IsMouseDragging(ImGuiMouseButton_Left)) {
            sChatMoved = true;
        }
        if (sChat && sChatMoved) {
            sChatPos = ImGui::GetWindowPos();
        }
        const char *names[2] = {Port_NetName(Port_NetMe()), Port_NetName(!Port_NetMe())};
        if (sChat) {
            ImGui::TextColored(ImVec4(1.0f, 0.82f, 0.28f, 1.0f), "聊天（Tab）");
            ImGui::SameLine();
            ImGui::TextDisabled("::");
            if (ImGui::IsItemHovered()) {
                ImGui::SetTooltip("拖动任意位置移动聊天窗口，点击一行复制文字。");
            }
            ImGui::SameLine(w - 70.0f);
            bool mute = PortChat_Muted() != 0;
            if (ImGui::Checkbox("静音", &mute)) {
                PortChat_MutedSet(mute);
                sChatFocus = true;
            }
            ImGui::Separator();
        }

        for (unsigned i = first; i < n; i++) {
            PortChatLine l;
            float alpha = 1.0f;
            if (!PortChat_Line(i, &l)) {
                continue;
            }
            if (!sChat) {
                Uint64 age = now - l.atMs;
                if (age >= CHAT_SHOWN_MS) {
                    continue;
                }
                if (age > CHAT_SHOWN_MS - CHAT_FADE_MS) {
                    alpha = (float)(CHAT_SHOWN_MS - age) / (float)CHAT_FADE_MS;
                }
            }
            const char *sender = l.sender[0] != '\0' ? l.sender : (names[l.mine ? 0 : 1][0] != '\0' ? names[l.mine ? 0 : 1] : (l.mine ? "你" : "对手"));
            ImGui::PushID((int)i);
            ImVec4 nameCol = l.mine ? ImVec4(0.35f, 0.85f, 1.0f, alpha) : ImVec4(1.0f, 0.82f, 0.28f, alpha);
            ImGui::TextColored(nameCol, "%s:", sender);
            ImGui::SameLine(0.0f, U(4.0f));

            ImVec2 at = ImGui::GetCursorScreenPos();
            if (!sChat) {
                ImGui::GetWindowDrawList()->AddText(NULL, 0.0f, ImVec2(at.x + 1.0f, at.y + 1.0f), IM_COL32(0, 0, 0, (int)(230.0f * alpha)), l.text, NULL, w - (at.x - ImGui::GetWindowPos().x));
            }
            ImGui::PushTextWrapPos(w);
            ImGui::TextColored(ImVec4(1.0f, 1.0f, 1.0f, alpha), "%s", l.text);
            ImGui::PopTextWrapPos();
            if (sChat) { // a click copies the line (a room code or an address is passed on this way); a drag does not
                static unsigned sCopiedIdx;
                static Uint64 sCopiedMs;
                bool copied = sCopiedIdx == i + 1 && now - sCopiedMs < 1500;
                if (ImGui::IsItemHovered()) {
                    ImGui::SetTooltip(copied ? "已复制" : "点击复制");
                    if (ImGui::IsMouseReleased(ImGuiMouseButton_Left) && io.MouseDragMaxDistanceSqr[ImGuiMouseButton_Left] < 16.0f) {
                        SDL_SetClipboardText(l.text);
                        sCopiedIdx = i + 1;
                        sCopiedMs = now;
                        sChatFocus = true;
                    }
                }
            }
            ImGui::PopID();
        }

        if (sChat) {
            if (sChatFocus) {
                ImGui::SetKeyboardFocusHere();
                sChatFocus = false;
            }
            ImGui::SetNextItemWidth(w);
            if (ImGui::InputText("##chatline", sChatBuf, sizeof(sChatBuf), ImGuiInputTextFlags_EnterReturnsTrue)) {
                const char *p = sChatBuf;
                while (*p == ' ') {
                    p++;
                }
                if (*p == '\0') {
                    chat_close();
                } else if (PortChat_Say(sChatBuf)) {
                    sChatBuf[0] = '\0';
                    chat_close();
                } else { // (said within a second of the line before: kept, to be sent again)
                    sChatSoon = true;
                    sChatFocus = true;
                }
            }
            ImGui::TextDisabled(sChatSoon ? "每秒限一条：Enter 发送" : "Enter 发送   Esc/Tab 关闭   Ctrl+V 粘贴");
        }
    }
    ImGui::End();
    ImGui::PopStyleColor();
    ImGui::PopStyleVar(4);
}

// Builds this frame's picture of the overlay (the settings or the online window, the line over the picture).
// false: there is nothing to draw. The same for both back ends; each then draws ImGui's data its own way.
static bool frame_build(void) {
    PortWii_MouseFrame();
    PortInput_TboClipboard();
    { // a keypad of Tenkaichi Budokai Online takes text: the system's text input is on for it (letters as typed)
        static SDL_Window *on = NULL;
        SDL_Window *want = gPortTboTyping && !sOpen && !sQuit && !sChat ? SDL_GetKeyboardFocus() : NULL;
        if (want != on) {
            if (on != NULL) { SDL_StopTextInput(on); }
            if (want != NULL) { SDL_StartTextInput(want); }
            on = want;
        }
    }
    if (sQuit && !PortQuit_Active() && !PortQuit_Failed()) {
        sQuit = false;
        input_owner();
        PortA11y_Say(PortA11y_Label("Back to the game"), 1);
    }
    if (sReady && gPortNetWindowClose) { // back from an online session: the window it was started from closes
        gPortNetWindowClose = 0;
        gPortNetMenuRequest = 0;
        set_open(false);
    } else if (sReady && gPortNetMenuRequest) { // Dragon Net Battle was chosen in the game's main menu
        gPortNetMenuRequest = 0;
        net_open();
    }
    { // BT3_SPEC_PAUSE_AT=<seconds>: testing, a spectator's own pause menu (the game's) opens that long into its match
        static Uint64 since;
        static bool done;
        if (!done && getenv("BT3_SPEC_PAUSE_AT") != NULL && sReady && Port_NetSpectating() && !sOpen) {
            if (since == 0) {
                since = SDL_GetTicks();
            } else if (SDL_GetTicks() - since > (Uint64)atoi(getenv("BT3_SPEC_PAUSE_AT")) * 1000) {
                done = true;
                gPortSpecMenuAsk = 1;
            }
        }
    }
    if (sReady) {
        int lobby = OnlineLobby::Tick(sOpen && sNet && sServerTab);
        if (lobby == 1) { set_open(false); }
        else if (lobby == 2) { net_open(); }
    }
    update_tick();
    char updLine[256];
    update_line(updLine, sizeof(updLine)); // (the update's line over the main menu and the online screens)
    bool notice = sNotice[0] != '\0' && SDL_GetTicks() < sNoticeUntil;
    if (sNoticeNew) { // (set from the game's side: the time starts when it is first drawn)
        sNoticeNew = 0;
        sNoticeUntil = SDL_GetTicks() + 6000;
        notice = sNotice[0] != '\0';
    }
    // the name of a stage added from outside the disc, over the stage select (a strip of pre-rendered names)
    bool nameOn = gUiNameReady != 0 && gUiNameIdx >= 0 && gUiNameIdx < PortStages_Count();
    bool songOn = gUiSongReady != 0 && gUiSongIdx >= 0 && gUiSongIdx < PortSongs_Count(); // (the same for an added song)
    bool overlay = nameOn || songOn;
    bool meter = sReady && meter_on();
    // the players' names under the gauges of an online fight
    bool names = sReady && Port_NetActive() && BtlChar_FindByObjId(0) != NULL && (Port_NetName(0)[0] != '\0' || Port_NetName(1)[0] != '\0');
    bool bars = sReady && bars_on();
    bool online = sReady && Port_NetActive() && PortChat_Enabled() && !Port_NetSpectating(); // (a spectator has no one to talk to)
    if (sChat && !online) { // (the match ended while a line was typed)
        chat_close();
    }
    bool chat = online && (sChat || chat_recent());
    if (sBanner[0] != '\0' && sBannerUntil != 0 && SDL_GetTicks() >= sBannerUntil) {
        sBanner[0] = '\0';
    }
    bool banner = sReady && sBanner[0] != '\0';
    Uint64 now = SDL_GetTicks();
    bool saving = save_icon_on(now) && sReady && gUiPresentW > 0 && gUiPresentH > 0;
    bool watched = sReady && Port_NetWatchers() > 0 && !sOpen;  // a player's: who watches the match
    meter_count();
    sBuilt = false;
    bool upd = updLine[0] != '\0';
    bool titleNotice = sReady && !sOpen && !sQuit && Port_TitleNoticeVisible() && gUiPresentW > 0 && gUiPresentH > 0;
    if (!sReady || (!sOpen && !sQuit && !notice && !overlay && !meter && !names && !bars && !chat && !banner && !saving && !watched && !upd && !titleNotice)) {
        return false;
    }
    if (sPadHold && sCapKind != 2) { // a binding was taken: the controller works the window again once nothing is held
        int count = 0;
        SDL_JoystickID *ids = SDL_GetGamepads(&count);
        bool held = false;
        for (int i = 0; i < count; i++) {
            SDL_Gamepad *g = SDL_GetGamepadFromID(ids[i]);
            for (int b = 0; g != NULL && b < SDL_GAMEPAD_BUTTON_COUNT; b++) {
                held = held || SDL_GetGamepadButton(g, (SDL_GamepadButton)b);
            }
        }
        SDL_free(ids);
        sPadHold = held;
    }
    // (the button that becomes the binding would also press the row it is bound in; while a chat line is typed the
    // controller is the game's)
    gamepad_navigation();
    sBuilt = true;
    if (sGL) {
        ImGui_ImplOpenGL3_NewFrame();
    } else {
        ImGui_ImplSDLGPU3_NewFrame();
    }
    ImGui_ImplSDL3_NewFrame();
    ui_scale_apply(); // (the window's size is known from here)
    fonts_apply(); // (a face chosen for the fight panels, between two frames)
    ImGui::NewFrame();
    if (titleNotice) { title_notice_draw(); }
    // The mouse pointer is hidden over the game's picture and shown with a window of this file that takes the mouse:
    // the settings, the online windows, the question before the game closes, a chat line being typed (setting
    // hide_pointer, on unless 0). The SDL back end hides it for this cursor at the next frame.
    if (!sOpen && !sQuit && !sChat && !sMeterHover && !sMeterDrag && Port_Setting("hide_pointer", 1) != 0) {
        ImGui::SetMouseCursor(ImGuiMouseCursor_None);
    }
    if (bars) {
        bars_draw();
    }
    if (sOpen) {
        if (sNet) {
            build_net();
        } else {
            build();
        }
    }
    if (sQuit && PortQuit_Failed()) {
        build_quit();
    }
    if (meter) {
        meter_draw();
    }
    if (chat) {
        chat_draw();
    }
    if (names && GsDraw_HudShown() && gUiPresentW > 0 && gUiPresentH > 0) { // (with the HUD: not over an intro)
        // Under each side's health bar (the game's 512 x 448 page: the bars end at about y 50). The left place is
        // side 0's, or this player's own side when the HUD's sides are swapped.
        ImDrawList *dl = ImGui::GetBackgroundDrawList();
        float sx = (float)gUiPresentW / 512.0f, sy = (float)gUiPresentH / 448.0f;
        float size = 15.0f * sy;
        ImFont *font = ImGui::GetFont();
        for (int place = 0; place < 2; place++) {
            const char *text = Port_NetName(place ^ Port_HudSwap());
            if (text[0] == '\0') {
                continue;
            }
            ImVec2 ts = font->CalcTextSizeA(size, FLT_MAX, 0.0f, text);
            // 106 of the HUD's own pixels in from its outer edge: clear of the panel of a team's waiting fighters,
            // which reaches to about 100 (the name sat on it at 62: reported). The HUD is narrowed in a wide
            // picture and sits at the edges or about the middle (gs_draw.c), and the name goes with it.
            float narrow = Port_IsWide() ? 1333.333f / (float)Port_AspectMilli() : 1.0f;
            float in = Port_HudLayout() == 2 ? 256.0f + (106.0f - 256.0f) * narrow : 106.0f * narrow;
            float x = place == 0 ? (float)gUiPresentX + in * sx : (float)gUiPresentX + (512.0f - in) * sx - ts.x;
            float y = (float)gUiPresentY + 56.0f * sy;
            for (int ox = -1; ox <= 1; ox++) {
                for (int oy = -1; oy <= 1; oy++) {
                    if (ox != 0 || oy != 0) {
                        dl->AddText(font, size, ImVec2(x + (float)ox * 1.5f, y + (float)oy * 1.5f), IM_COL32(0, 0, 0, 220), text);
                    }
                }
            }
            dl->AddText(font, size, ImVec2(x, y), IM_COL32(255, 255, 255, 255), text);
        }
    }
    if (banner) { // the start of an online match (Port_UiBanner): in the middle, large, outlined
        ImGuiIO &io = ImGui::GetIO();
        ImDrawList *dl = ImGui::GetForegroundDrawList();
        ImFont *font = ImGui::GetFont();
        float size = ImGui::GetFontSize() * (io.DisplaySize.y >= 900.0f ? 2.0f : 1.6f);
        float wrap = io.DisplaySize.x * 0.8f;
        ImVec2 extent = font->CalcTextSizeA(size, FLT_MAX, wrap, sBanner);
        float x = (io.DisplaySize.x - extent.x) * 0.5f, y = (io.DisplaySize.y - extent.y) * 0.5f;
        if (sBannerUntil == 0) { // still waiting: the picture dimmed
            dl->AddRectFilled(ImVec2(0.0f, 0.0f), io.DisplaySize, IM_COL32(0, 0, 0, 150));
        }
        dl->AddRectFilled(ImVec2(x - size, y - size * 0.6f), ImVec2(x + extent.x + size, y + extent.y + size * 0.6f), IM_COL32(10, 14, 40, 210),
                          size * 0.4f);
        for (int ox = -1; ox <= 1; ox++) {
            for (int oy = -1; oy <= 1; oy++) {
                if (ox != 0 || oy != 0) {
                    dl->AddText(font, size, ImVec2(x + (float)ox * 2.0f, y + (float)oy * 2.0f), IM_COL32(0, 0, 0, 230), sBanner, NULL, wrap);
                }
            }
        }
        dl->AddText(font, size, ImVec2(x, y), IM_COL32(255, 236, 120, 255), sBanner, NULL, wrap);
    }
    if (saving) {
        save_icon_draw(now);
    }
    if (watched) {
        watchers_line();
    }
    if (upd) { // the update's line (update_line): at the top, over the main menu and the online screens
        ImGuiIO &io = ImGui::GetIO();
        ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.035f), ImGuiCond_Always, ImVec2(0.5f, 0.5f));
        ImGui::SetNextWindowBgAlpha(0.80f);
        if (ImGui::Begin("##update", NULL, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoInputs |
                                               ImGuiWindowFlags_NoFocusOnAppearing | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoSavedSettings)) {
            ImGui::TextColored(ImVec4(1.0f, 0.85f, 0.3f, 1.0f), "%s", updLine);
        }
        ImGui::End();
    }
    if (notice) { // a line over the picture for a few seconds (the end of an online match)
        ImGuiIO &io = ImGui::GetIO();
        ImGui::SetNextWindowPos(ImVec2(io.DisplaySize.x * 0.5f, io.DisplaySize.y * 0.12f), ImGuiCond_Always, ImVec2(0.5f, 0.5f));
        ImGui::SetNextWindowBgAlpha(0.85f);
        if (ImGui::Begin("##notice", NULL, ImGuiWindowFlags_NoDecoration | ImGuiWindowFlags_AlwaysAutoResize | ImGuiWindowFlags_NoInputs |
                                               ImGuiWindowFlags_NoFocusOnAppearing | ImGuiWindowFlags_NoNav | ImGuiWindowFlags_NoSavedSettings)) {
            ImGui::TextUnformatted(sNotice);
        }
        ImGui::End();
    }
    if (overlay && gUiPresentW > 0 && gUiPresentH > 0) {
        /* Each name's rectangle is in the game's 512x448 pixels: map it through the picture's rectangle in the
           window (the letterbox gs_gpu.c just blitted into). */
        float sx = (float)gUiPresentW / 512.0f;
        float sy = (float)gUiPresentH / 448.0f;
        // Stage/song names belong to the game picture, behind settings and other windows,
        // including added names rendered while Menu font is Original.
        ImDrawList *dl = ImGui::GetBackgroundDrawList();

        if (nameOn) {
            const FontName *fn = font_name(NF_STAGE, PortStages_Name(gUiNameIdx));
            float x = (float)gUiPresentX + (float)gUiNameX * sx, y = (float)gUiPresentY + (float)gUiNameY * sy;
            if (fn != NULL) {
                float kx = (float)gUiNameW * sx / 384.0f, ky = (float)gUiNameH * sy / 48.0f;
                font_draw(dl, fn, x - 64.0f * kx, y + (1.5f - 14.0f) * ky, kx, ky, true);
            } else {
                name_text(dl, PortStages_Name(gUiNameIdx), x, y, (float)gUiNameW * sx, (float)gUiNameH * sy, true);
            }
        }
        if (songOn) {
            const FontName *fn = font_name(gUiSongLit ? NF_SONG_LIT : NF_SONG, PortSongs_Name(gUiSongIdx));
            float x = (float)gUiPresentX + (float)gUiSongX * sx, y = (float)gUiPresentY + (float)gUiSongY * sy;
            if (fn != NULL) {
                font_draw(dl, fn, x, y, (float)gUiSongW * sx / 512.0f, (float)gUiSongH * sy / 32.0f, false);
            } else {
                name_text(dl, PortSongs_Name(gUiSongIdx), x, y, (float)gUiSongW * sx, (float)gUiSongH * sy, false);
            }
        }
    }
    ImGui::Render();
    return true;
}

void Ui_Draw(SDL_GPUCommandBuffer *cmd, SDL_GPUTexture *target) {
    if (!sGL && frame_build()) {
        Ui_DrawAgain(cmd, target);
    }
}

// The OpenGL back end's turn: over the presented picture, just before the buffers are swapped.
void Ui_DrawGL(void) {
    if (sGL && frame_build()) {
        ImGui_ImplOpenGL3_RenderDrawData(ImGui::GetDrawData());
    }
}
