#ifndef PORT_CONTROL_BINDINGS_H
#define PORT_CONTROL_BINDINGS_H
#include <SDL3/SDL.h>
#define PORT_WII_ACTIONS 27
#define PORT_WII_EXPR_SIZE 16384
#ifdef __cplusplus
extern "C" {
#endif
void PortWii_Init(int player, const int *keys, const int *pads);
void PortWii_Reset(int player, int split, const int *keys, const int *pads);
void PortWii_Save(void);
int PortWii_Set(int player, int split, int action, const char *text, int range);
int PortWii_Validate(const char *text, int range);
// Reuse Dolphin's lexer to compact expressions or restore readable spacing.
int PortWii_Format(const char *text, int readable, char *out, int size);
// 1: translated; 0: invalid expression; -1: unsupported device or input.
int PortWii_TranslateDolphin(const char *text, const char *device, char *out, int size, char *error, int error_size);
void PortWii_Get(int player, int split, int action, char *text, int size, int *range);
void PortWii_Read(int player, int split, SDL_Gamepad *pad, const bool *keys, const unsigned char *sticks,
                  int (*blocked_key)(int), float *values);
int PortWii_KeysHeld(int player, int split, const bool *keys);
int PortWii_InputCount(int device);
const char *PortWii_InputName(int device, int index);
float PortWii_Preview(int player, const char *text, int range);
void PortWii_PreviewBindings(int player, int split, float *values);
void PortWii_MouseEvent(const SDL_Event *ev);
void PortWii_MouseFrame(void);
const char *PortWii_ActionLabel(int split, int action);
void PortWii_BindingButton(int player, int split, int action, float value);
void PortWii_DrawEditor(void);
int PortWii_Event(const SDL_Event *ev);
void PortWii_Cancel(void);
#ifdef __cplusplus
}
#endif
#endif
