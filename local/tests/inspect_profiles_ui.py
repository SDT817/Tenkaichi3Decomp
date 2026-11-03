"""Interactive local QA driver: JSON clicks/keys/screenshots on a private test run."""
import ctypes as c
from ctypes import wintypes as w
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from PIL import ImageGrab
c.windll.user32.SetProcessDPIAware()

root = Path(__file__).resolve().parents[2]
run = root / 'port/build/qa-local/Tenkaichi3Decomp'
settings = run / 'r5-ui-settings.txt'
settings.write_text('fullscreen=0\nscale=1\ncontrol_mode_p1=1\ncontrol_split_p1=1\npadslot_p1=-1\n')
env = {k: v for k, v in os.environ.items() if not k.startswith('BT3_')}
env.update(BT3_UPDATE_CHECK='0', BT3_GS='gpu', BT3_DATA=r'E:\PS2 yizhi\Tenkaichi3Decomp\gamedata', BT3_VERIFY='0',
           BT3_SETTINGS=str(settings), BT3_WINDOW='1280x900', BT3_UI_OPEN=os.environ.get('BT3_TEST_UI_TAB', '4'), BT3_NOSOUND='1',
           BT3_MATCH_URL='http://127.0.0.1:9')
u = c.windll.user32
u.PostMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
u.GetClientRect.argtypes = [w.HWND, c.POINTER(w.RECT)]
u.ClientToScreen.argtypes = [w.HWND, c.POINTER(w.POINT)]
u.EnumWindows.argtypes = [c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM), w.LPARAM]
u.EnumChildWindows.argtypes = [w.HWND, c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM), w.LPARAM]
u.SendMessageW.argtypes = [w.HWND, w.UINT, w.WPARAM, w.LPARAM]
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
    time.sleep(0.25)
    u.mouse_event(0x0008 if right else 0x0002, 0, 0, 0, 0)
    time.sleep(0.25)
    u.mouse_event(0x0010 if right else 0x0004, 0, 0, 0, 0)
    time.sleep(0.7)
def key(hwnd, vk, down=None):
    scan = u.MapVirtualKeyW(vk, 0)
    if down is not False: u.PostMessageW(hwnd, 0x100, vk, 1 | (scan << 16))
    time.sleep(0.1)
    if down is not True: u.PostMessageW(hwnd, 0x101, vk, 1 | (scan << 16) | 0xc0000000)
    time.sleep(0.1)
def shot(hwnd, name):
    rect = w.RECT(); u.GetClientRect(hwnd, c.byref(rect))
    point = w.POINT(0, 0); u.ClientToScreen(hwnd, c.byref(point))
    ImageGrab.grab((point.x, point.y, point.x + rect.right, point.y + rect.bottom)).save(root / ('port/build/' + name + '.png'))
def manual_select(pid, path):
    dialogs = []
    @c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def dialog(hwnd, _):
        process = w.DWORD(); u.GetWindowThreadProcessId(hwnd, c.byref(process))
        cls = c.create_unicode_buffer(256); u.GetClassNameW(hwnd, cls, 256)
        if process.value == pid and cls.value == '#32770' and u.IsWindowVisible(hwnd): dialogs.append(hwnd)
        return True
    u.EnumWindows(dialog, 0); assert len(dialogs) == 1, dialogs
    edits = []
    @c.WINFUNCTYPE(w.BOOL, w.HWND, w.LPARAM)
    def child(hwnd, _):
        cls = c.create_unicode_buffer(256); u.GetClassNameW(hwnd, cls, 256)
        if cls.value == 'Edit' and u.IsWindowVisible(hwnd): edits.append(hwnd)
        return True
    u.EnumChildWindows(dialogs[0], child, 0); assert edits
    value = c.create_unicode_buffer(str(Path(path)))
    u.SendMessageW(edits[-1], 0x000c, 0, c.cast(value, c.c_void_p).value)
    u.PostMessageW(dialogs[0], 0x0111, 1, 0)
    time.sleep(1)
previous = u.GetForegroundWindow(); cursor = w.POINT(); u.GetCursorPos(c.byref(cursor))
with (run / 'r5-ui-driver.log').open('wb') as log:
    process = subprocess.Popen([str(run / 'Tenkaichi3Decomp.exe')], cwd=run, env=env, stdout=log, stderr=log)
    try:
        hwnd = None
        for _ in range(100):
            hwnd = find(process.pid)
            if hwnd: break
            assert process.poll() is None
            time.sleep(0.1)
        assert hwnd
        u.SetForegroundWindow(hwnd); time.sleep(2)
        rect = w.RECT(); u.GetClientRect(hwnd, c.byref(rect))
        shot(hwnd, 'r5-ui-groups')
        print(json.dumps({'ready': True, 'hwnd': hwnd, 'client': [rect.right, rect.bottom]}), flush=True)
        commands = open(sys.argv[1], encoding='utf-8') if len(sys.argv) > 1 else sys.stdin
        for line in commands:
            command = json.loads(line)
            if command.get('quit'): break
            u.SetForegroundWindow(hwnd); time.sleep(0.3)
            if 'manual_path' in command: manual_select(process.pid, command['manual_path'])
            if 'click' in command: click(hwnd, *command['click'], right=command.get('right', False))
            if 'key' in command: key(hwnd, command['key'], command.get('down'))
            if 'text_file' in command: command['text'] = (root / command['text_file']).read_text(encoding='utf-8')
            if 'text' in command:
                for char in command['text']: u.PostMessageW(hwnd, 0x102, ord(char), 1)
                time.sleep(0.3)
            if 'shot' in command:
                u.SetCursorPos(0, 0); time.sleep(0.2); shot(hwnd, command['shot'])
            assert process.poll() is None
            print(json.dumps({'done': {k: v for k, v in command.items() if k != 'text'}, 'text_length': len(command.get('text', ''))}, ensure_ascii=True), flush=True)
    finally:
        if process.poll() is None: process.terminate()
        process.wait(timeout=10)
        u.SetCursorPos(cursor.x, cursor.y)
        if previous: u.SetForegroundWindow(previous)
