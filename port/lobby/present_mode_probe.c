// Execute the real presentation selector with only the SDL device calls mocked.
#define SDL_DECLSPEC
#define SDL_WaitForGPUIdle Probe_Wait
#define SDL_WindowSupportsGPUPresentMode Probe_Supports
#define SDL_SetGPUSwapchainParameters Probe_Set
#include "../src/gs/gs_gpu.c"
#include <assert.h>

static int immediate, mailbox, applied = -1, waits;
const char *Port_GetEnv(const char *name) { return NULL; }
bool Probe_Wait(SDL_GPUDevice *dev) { waits++; return true; }
bool Probe_Supports(SDL_GPUDevice *dev, SDL_Window *window, SDL_GPUPresentMode mode) {
    return mode == SDL_GPU_PRESENTMODE_IMMEDIATE ? immediate : mode == SDL_GPU_PRESENTMODE_MAILBOX ? mailbox : true;
}
bool Probe_Set(SDL_GPUDevice *dev, SDL_Window *window, SDL_GPUSwapchainComposition composition, SDL_GPUPresentMode mode) {
    applied = mode; return true;
}
int main(void) {
    sDev = (SDL_GPUDevice *)1; sWindow = (SDL_Window *)1;
    immediate = mailbox = 1;
    vsync_apply(0); assert(applied == SDL_GPU_PRESENTMODE_IMMEDIATE);
    vsync_apply(1); assert(applied == SDL_GPU_PRESENTMODE_IMMEDIATE);
    vsync_apply(0); assert(applied == SDL_GPU_PRESENTMODE_IMMEDIATE);
    immediate = 0;
    vsync_apply(1); assert(applied == SDL_GPU_PRESENTMODE_MAILBOX);
    vsync_apply(0); assert(applied == SDL_GPU_PRESENTMODE_MAILBOX);
    mailbox = 0;
    vsync_apply(0); assert(applied == SDL_GPU_PRESENTMODE_VSYNC);
    vsync_apply(1); assert(applied == SDL_GPU_PRESENTMODE_VSYNC);
    assert(waits == 7);
    puts("always_immediate_with_vsync_on_and_off=ok unsupported_mode_fallback=ok");
    return 0;
}
