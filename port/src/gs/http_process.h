/* curl fallback only. SDL owns argument quoting and pipes. On Windows the
   background flag suppresses a console, but SDL reports exit code zero for
   background processes; retain a query handle so download errors stay errors. */
#ifndef BT3_HTTP_PROCESS_H
#define BT3_HTTP_PROCESS_H
#include <SDL3/SDL.h>
#ifdef _WIN32
#include <windows.h>

static void SDLCALL http_process_close(void *unused, void *value) {
    (void)unused;
    CloseHandle((HANDLE)value);
}
#endif

static SDL_Process *HttpProcess_Create(const char *const *args, bool pipe) {
#ifdef _WIN32
    SDL_PropertiesID props = SDL_CreateProperties();
    SDL_Process *p;
    HANDLE handle;
    if (!props) return NULL;
    SDL_SetPointerProperty(props, SDL_PROP_PROCESS_CREATE_ARGS_POINTER, (void *)args);
    SDL_SetBooleanProperty(props, SDL_PROP_PROCESS_CREATE_BACKGROUND_BOOLEAN, true);
    if (pipe) {
        SDL_SetNumberProperty(props, SDL_PROP_PROCESS_CREATE_STDIN_NUMBER, SDL_PROCESS_STDIO_APP);
        SDL_SetNumberProperty(props, SDL_PROP_PROCESS_CREATE_STDOUT_NUMBER, SDL_PROCESS_STDIO_APP);
    }
    p = SDL_CreateProcessWithProperties(props);
    SDL_DestroyProperties(props);
    if (!p) return NULL;
    handle = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE,
        (DWORD)SDL_GetNumberProperty(SDL_GetProcessProperties(p), SDL_PROP_PROCESS_PID_NUMBER, 0));
    if (!handle || !SDL_SetPointerPropertyWithCleanup(SDL_GetProcessProperties(p), "BT3.http.exit_handle",
                                                    handle, http_process_close, NULL)) {
        /* SetPointerPropertyWithCleanup also closes the handle on failure. */
        SDL_KillProcess(p, true);
        SDL_WaitProcess(p, true, NULL);
        SDL_DestroyProcess(p);
        return NULL;
    }
    return p;
#else
    return SDL_CreateProcess(args, pipe);
#endif
}

/* Call after the existing ReadProcess/WaitProcess and before DestroyProcess. */
static void HttpProcess_ExitCode(SDL_Process *p, int *code) {
#ifdef _WIN32
    DWORD value;
    HANDLE handle = (HANDLE)SDL_GetPointerProperty(SDL_GetProcessProperties(p), "BT3.http.exit_handle", NULL);
    *code = handle && GetExitCodeProcess(handle, &value) && value != STILL_ACTIVE ? (int)value : -1;
#else
    (void)p; (void)code;
#endif
}
#endif
