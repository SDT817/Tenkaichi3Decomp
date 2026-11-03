import ctypes as c
from ctypes import wintypes as w
from pathlib import Path
import os
import subprocess
import time
from PIL import ImageGrab
root = Path(__file__).resolve().parents[2]
run = root / 'port/build/qa-local/Tenkaichi3Decomp'
settings = run / 'r3-click-settings.txt'
# Read connected pads to select the virtual test pad appended by the game.
sdl = c.CDLL(str(run / 'SDL3.dll'))
sdl.SDL_Init.argtypes = [c.c_uint32]; sdl.SDL_Init.restype = c.c_bool
sdl.SDL_GetGamepads.argtypes = [c.POINTER(c.c_int)]; sdl.SDL_GetGamepads.restype = c.POINTER(c.c_uint32)
sdl.SDL_free.argtypes = [c.c_void_p]
sdl.SDL_Init(0x2000); count = c.c_int(); ids = sdl.SDL_GetGamepads(c.byref(count)); sdl.SDL_free(ids); sdl.SDL_Quit()
settings.write_text(f'fullscreen=0\nscale=1\ncontrol_mode_p1=1\ncontrol_split_p1=1\npadslot_p1={count.value}\n')
expression_file = Path(str(settings) + '.wii.ini')
expression_file.write_text('# Wii unified expressions v2\n0.1.7=100:\n')
env = {k: v for k, v in os.environ.items() if not k.startswith('BT3_')}
env.update(BT3_UPDATE_CHECK='0', BT3_GS='gpu', BT3_DATA=r'E:\PS2 yizhi\Tenkaichi3Decomp\gamedata', BT3_VERIFY='0',
           BT3_SETTINGS=str(settings), BT3_WINDOW='1280x900', BT3_UI_OPEN='4', BT3_NOSOUND='1',
           BT3_STICK_TEST='32767,0,0,0,0,0')
u = c.windll.user32
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
u.GetClientRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
u.GetWindowRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
u.ClientToScreen.argtypes = [w.HWND, c.POINTER(w.POINT)]
u.EnumWindows.argtypes = [c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM), w.LPARAM]
def find(pid):
    result = []
    @c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def visit(hwnd, _):
        process = w.DWORD(); u.GetWindowThreadProcessId(hwnd, c.byref(process))
        if process.value == pid and u.IsWindowVisible(hwnd): result.append(hwnd)
        return True
    u.EnumWindows(visit, 0)
    return result[0] if result else None
def click(hwnd, x, y, right=False):
    point = w.POINT(x, y); u.ClientToScreen(hwnd, c.byref(point)); u.SetCursorPos(point.x, point.y)
    pos = (y << 16) | x
    u.PostMessageW(hwnd, 0x200, 0, pos)
    u.PostMessageW(hwnd, 0x204 if right else 0x201, 2 if right else 1, pos)
    time.sleep(0.12)
    u.PostMessageW(hwnd, 0x205 if right else 0x202, 0, pos)
    time.sleep(0.3)
def shot(hwnd, name):
    rect = w.RECT(); u.GetClientRect(hwnd, c.byref(rect))
    point = w.POINT(0, 0); u.ClientToScreen(hwnd, c.byref(point))
    img = ImageGrab.grab((point.x, point.y, point.x + rect.right, point.y + rect.bottom))
    img.save(root / ('port/build/' + name + '.png')); return img
def key(hwnd, vk, down=None):
    scan = u.MapVirtualKeyW(vk, 0)
    if down is not False: u.PostMessageW(hwnd, 0x100, vk, 1 | (scan << 16))
    time.sleep(0.15)
    if down is not True: u.PostMessageW(hwnd, 0x101, vk, 1 | (scan << 16) | 0xc0000000)
    time.sleep(0.15)
previous = u.GetForegroundWindow(); cursor = w.POINT(); u.GetCursorPos(c.byref(cursor))
with (run / 'r3-ui-click.log').open('wb') as log:
    p = subprocess.Popen([str(run / 'Tenkaichi3Decomp.exe')], cwd=run, env=env, stdout=log, stderr=log)
    try:
        for _ in range(100):
            hwnd = find(p.pid)
            if hwnd: break
            assert p.poll() is None
            time.sleep(0.1)
        assert hwnd
        u.SetForegroundWindow(hwnd); time.sleep(2)
        rect = w.RECT(); u.GetClientRect(hwnd, c.byref(rect))
        x0 = (rect.right - 1120) // 2; y0 = 12
        px = (rect.right - 680) // 2; py = (rect.bottom - 740) // 2
        print('client', rect.right, rect.bottom, 'settings', x0, y0, 'popup', px, py, flush=True)
        u.SetCursorPos(0, 0); time.sleep(0.4); shot(hwnd, 'r3-ui-groups')
        click(hwnd, x0 + 185, y0 + 377, right=True)
        shot(hwnd, 'r3-ui-expression-empty')
        click(hwnd, px + 596, py + 246)  # Detect Z, below the initially visible A-H.
        key(hwnd, ord('Z')); time.sleep(0.3)
        u.SetCursorPos(0, 0); shot(hwnd, 'r3-ui-detected-z')
        click(hwnd, px + 596, py + 208)  # Insert Z.
        # Exact user report; keep the existing popup open while typing.
        click(hwnd, px + 110, py + 500)
        key(hwnd, 0x11, down=True); key(hwnd, ord('A')); key(hwnd, 0x11, down=False)
        for char in 'W &!': u.PostMessageW(hwnd, 0x102, ord(char), 1)
        time.sleep(0.3)
        u.SetCursorPos(0, 0); shot(hwnd, 'r3-ui-cursor-before')
        click(hwnd, px + 596, py + 208)
        u.SetCursorPos(0, 0); shot(hwnd, 'r3-ui-cursor-after')
        click(hwnd, px + 275, py + 688)
        saved = expression_file.read_text()
        assert '0.1.7=100:W &!Z\n' in saved, [line for line in saved.splitlines() if line.startswith('0.1.7=')]
        click(hwnd, px + 110, py + 500)
        key(hwnd, 0x11, down=True); key(hwnd, ord('A')); key(hwnd, 0x11, down=False)
        u.PostMessageW(hwnd, 0x102, ord('Z'), 1); time.sleep(0.3)
        click(hwnd, px + 220, py + 87)   # Device combo.
        click(hwnd, px + 160, py + 149)  # Controller option in the open device combo.
        click(hwnd, px + 120, py + 220)  # Select the visible Left X+ controller input.
        click(hwnd, px + 596, py + 324)  # AND.
        u.SetCursorPos(0, 0); shot(hwnd, 'r3-ui-expression-mixed')
        click(hwnd, px + 275, py + 688)  # Apply.
        saved = expression_file.read_text()
        assert '0.1.7=100:Z & `Controller:Left X+`' in saved, saved[:1000]
        click(hwnd, px + 65, py + 688)   # OK.
        key(hwnd, ord('Z'), down=True)
        u.SetCursorPos(0, 0); time.sleep(0.3); active = shot(hwnd, 'r3-ui-ki-active')
        key(hwnd, ord('Z'), down=False)
        time.sleep(0.3); inactive = shot(hwnd, 'r3-ui-ki-inactive')
        box = (x0 + 118, y0 + 362, x0 + 261, y0 + 384)
        green = lambda img: sum(1 for r, g, b in img.convert('RGB').crop(box).getdata() if g > 100 and r < 90 and b < 130)
        assert green(active) > 300 and green(inactive) < 100, (green(active), green(inactive))
        assert p.poll() is None
        print('PASS: game-window shared inputs, persistence, live highlight and typed W &! + Select Z = W &!Z', flush=True)
    finally:
        p.terminate(); p.wait(timeout=10)
        u.SetCursorPos(cursor.x, cursor.y)
        if previous: u.SetForegroundWindow(previous)
