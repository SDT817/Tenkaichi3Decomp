// Host-side HTTP lobby. All calls below are from ui.cpp's render thread.
#pragma once
namespace OnlineLobby {
// 1: connection launched, close overlay. 2: session ended, reopen lobby.
int Tick(bool visible);
void Draw(const char *name, float scale);
void Open();
void Close();
bool FocusTab();
bool Connecting();
}
