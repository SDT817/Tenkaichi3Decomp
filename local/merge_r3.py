"""Reproduce the r3 -> official 0.1.38 source merge without touching r3."""
from pathlib import Path
import json
import re
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]
OLD = Path(r'E:\BT3-Wii-local-r3')
BASE = '559f85b2bb06c1d7200e8a87b9a5b346925e13de'
UPSTREAM = 'aec1f8af41c50c293d4b7daecdb0b8ba97ff512f'

def git(*args, cwd=ROOT):
    return subprocess.check_output(['git', '-c', 'safe.directory=*', '-c', 'core.safecrlf=false', *args], cwd=cwd)

def main():
    assert not (ROOT / 'port/src/gs/control_profiles.cpp').exists(), 'Run only in a clean official checkout; never overwrite an existing r4'
    assert git('rev-parse', 'HEAD').decode().strip() == UPSTREAM
    changed = git('diff', '--name-only', '-z', BASE, cwd=OLD).decode().split('\0')
    official_files = set(git('ls-tree', '-rz', '--name-only', UPSTREAM).decode().split('\0'))
    results = {}
    for name in filter(None, changed):
        source = OLD / name
        target = ROOT / name
        if not source.is_file():
            continue
        local = source.read_bytes().replace(b'\r\n', b'\n')
        if name in official_files:
            official = git('show', f'{UPSTREAM}:{name}')
            ancestor = git('show', f'{BASE}:{name}', cwd=OLD)
            with tempfile.TemporaryDirectory(prefix='bt3-r4-merge-') as temp:
                paths = [Path(temp) / p for p in ('local', 'ancestor', 'official')]
                for path, data in zip(paths, (local, ancestor, official)):
                    path.write_bytes(data)
                merge = subprocess.run(['git', 'merge-file', '-p', *map(str, paths)], capture_output=True)
                if merge.returncode < 0 or merge.returncode > 127:
                    raise RuntimeError(merge.stderr.decode())
                target.write_bytes(merge.stdout)
                results[name] = f'{merge.returncode} conflict(s)'
        else:
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(local)
            results[name] = 'local addition'
    (ROOT / 'local/merge-r3-results.json').write_text(json.dumps(results, indent=2) + '\n')
    ui = ROOT / 'port/src/gs/ui.cpp'
    text = ui.read_text(encoding='utf-8')
    def resolve(match):
        local, official = match.group(1).split('=======\n')
        if 'bool wide =' in local:
            # The PR's solution retains both the official UI scale and Wii's wide layout.
            return '''    bool wide = (sTab == 4 || sForceTab == 4) && *PortInput_ControlMode(sControlPlayer);
    static bool wasWide;
    {
        float sw = U(wide ? 1120.0f : 640.0f);
        float sh = U(wide ? 900.0f : io.DisplaySize.y >= U(800.0f) ? 760.0f : 600.0f);
        ImGui::SetNextWindowSize(ImVec2(std::min(sw, io.DisplaySize.x * 0.96f),
                                       std::min(sh, io.DisplaySize.y * 0.94f)),
                                 wide != wasWide ? ImGuiCond_Always : ImGuiCond_Appearing);
    }
    wasWide = wide;
    if (ImGui::Begin("设置", &open, ImGuiWindowFlags_NoCollapse)) {
'''
        for english, chinese in {'Exit':'退出', 'Cancel':'取消', 'Game speed':'游戏速度',
                'Smooth motion':'平滑补帧', 'Glow strength':'泛光强度', 'Glare strength':'眩光强度',
                'Sharp stage blur':'清晰场景模糊', 'Hide the mouse pointer during play':'游戏中隐藏鼠标',
                'Quick saving':'快速存取', 'Unlock':'解锁', 'Deadzone##%d':'死区##%d',
                'Original':'原版', 'Strength':'强度', 'Controller':'手柄', 'None':'无',
                'per press':'每次按下'}.items():
            official = official.replace('"' + english + '"', '"' + chinese + '"')
        return official
    text = re.sub(r'^<<<<<<<[^\n]*\n(.*?)^>>>>>>>[^\n]*\n', resolve, text, flags=re.M | re.S)
    ui.write_text(text, encoding='utf-8', newline='\n')
    print(json.dumps(results, indent=2))

if __name__ == '__main__':
    main()
