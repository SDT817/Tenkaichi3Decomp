from pathlib import Path
import argparse
import json
import os
import re
import subprocess
import time
import zipfile

ROOT = Path(__file__).resolve().parents[2]
parser = argparse.ArgumentParser()
parser.add_argument("--name", default="verify-netplay-20261018")
parser.add_argument("--rollback", default="0")
parser.add_argument("--latency", default="0")
parser.add_argument("--reverse", action="store_true")
parser.add_argument("--seconds", type=int, default=55)
parser.add_argument("--target", type=int, default=12000)
parser.add_argument("--archive")
args = parser.parse_args()
QA = (ROOT / "port/build") / args.name
ARCHIVE = Path(args.archive) if args.archive else ROOT / "dist/Tenkaichi3Decomp-WiiControls-Netplay-windows-x64.zip"

def packet(buttons=0, mode=0, rx=128, ry=128, lx=128, ly=128, extra=0):
    return bytes([(~buttons) & 255, ((~buttons) >> 8) & 255, rx, ry, lx, ly] + [extra] + [0] * 10 + [mode])

def make_table():
    data = bytearray()
    for tick in range(50000):
        buttons = [0, 0]
        if tick % 90 < 4:
            buttons = [0x4000, 0x8000]  # PS2 A / Wii X confirm
        # Exercise both modes throughout the fight, with no Start/back inputs.
        phase = tick % 1200
        ry = 128
        if 300 <= phase < 450:
            buttons[0] |= 0x100  # PS2 LT charge
            buttons[1] |= 0x4    # Wii R3 charge
        if 480 <= phase < 500 or 510 <= phase < 550:
            buttons[0] |= 0x800  # PS2 double RB fast ascent
        if 480 <= phase < 550:
            buttons[1] |= 0x200  # Wii RT fast ascent
        if 600 <= phase < 620 or 630 <= phase < 670:
            buttons[0] |= 0x400  # PS2 double LB fast descent
        if 600 <= phase < 670:
            buttons[1] |= 0x100  # Wii LT fast descent
        if 780 <= phase < 784:
            buttons[0] |= 0x4
            ry = 255  # Wii transformation input, alongside PS2 R3
        if 850 <= phase < 865:
            buttons[0] |= 0x6
            ry = 0  # Wii tag input, alongside PS2 L3 + R3
        # Ordinary attacks keep the same face buttons in both modes.
        if 920 <= phase < 1000 and tick % 16 < 4:
            buttons[0] |= 0x8000
            buttons[1] |= 0x8000
        ps2 = packet(buttons[0])
        wii = packet(buttons[1], mode=0x58, ry=ry, rx=0 if 100 <= phase < 105 or 110 <= phase < 115 else 128,
                     extra=4 if 350 <= phase < 354 or 358 <= phase < 362 else 1 if 750 <= phase < 755 else 2 if 770 <= phase < 775 else 0)
        data.extend(wii if args.reverse else ps2)
        data.extend(ps2 if args.reverse else wii)
    (QA / "mixed-input.bin").write_bytes(data)

def main():
    QA.mkdir(parents=True, exist_ok=False)
    make_table()
    processes = []
    logs = []
    try:
        roles = [(0, "host-Wii", 1), (1, "join-PS2", 0)] if args.reverse else [(0, "host-PS2", 0), (1, "join-Wii", 1)]
        for role, label, mode in roles:
            run = QA / label
            with zipfile.ZipFile(ARCHIVE) as z:
                z.extractall(run)
            run = run / "Tenkaichi3Decomp"
            (run / "qa-settings.txt").write_text(f"control_mode_p1={mode}\ncontrol_mode_p2={1-mode}\n", encoding="ascii")
            env = {k: v for k, v in os.environ.items() if not k.startswith("BT3_")}
            env.update(BT3_GS="none", BT3_UNCAPPED="1", BT3_NOSOUND="1", BT3_NOMOVIE="1",
                       BT3_DATA=r"E:\PS2 yizhi\Tenkaichi3Decomp\gamedata",
                       BT3_NET_SESSION="1", BT3_NET_DELAY="2", BT3_NET_ROLLBACK=args.rollback,
                       BT3_NET_LATENCY=args.latency,
                       BT3_NET_NAME=label, BT3_NET_SEED="12345", BT3_NET_RULES="0x640400",
                       BT3_NET_SCRIPT=str(QA / "mixed-input.bin"), BT3_PAD_TABLE=str(run / "received-input.bin"),
                       BT3_TRACE="120", BT3_TRACE_SEQ="1", BT3_GS_VERBOSE="1",
                       BT3_SETTINGS=str(run / "qa-settings.txt"), BT3_UPDATE_CHECK="0")
            env["BT3_NET_JOIN" if role else "BT3_NET_HOST"] = "127.0.0.1:26839" if role else "26839"
            log = (run / "netplay.log").open("wb")
            logs.append(log)
            process = subprocess.Popen([str(run / "Tenkaichi3Decomp.exe")], cwd=run, env=env,
                                       stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW)
            processes.append((label, run, process))
            print(label, "PID", process.pid, flush=True)
        start = time.monotonic()
        last = 0
        while time.monotonic() - start < args.seconds:
            if any(p.poll() is not None for _, _, p in processes):
                break
            if time.monotonic() - last > 8:
                last = time.monotonic()
                for label, run, p in processes:
                    lines = (run / "bt3_log.txt" if (run / "bt3_log.txt").exists() else run / "netplay.log").read_text(errors="replace").splitlines()
                    notable = [l for l in lines if "net:" in l or "net: blank" in l or l.startswith("trace:") or "sequence" in l]
                    print(label, " | ".join(notable[-3:]), flush=True)
                # Enough confirmed game state comparisons for an initial smoke test.
                text = (processes[0][1] / "bt3_log.txt" if (processes[0][1] / "bt3_log.txt").exists() else processes[0][1] / "netplay.log").read_text(errors="replace")
                blanks = [int(n) for n in re.findall(r"net: blank (\d+)", text)]
                if blanks and max(blanks) >= args.target:
                    break
            time.sleep(0.15)
    finally:
        statuses = {}
        for label, run, p in processes:
            statuses[label] = p.poll()
            if p.poll() is None:
                p.terminate()
                p.wait(timeout=10)
        for log in logs:
            log.close()
        results = {}
        for label, run, p in processes:
            text = (run / "bt3_log.txt" if (run / "bt3_log.txt").exists() else run / "netplay.log").read_text(errors="replace")
            data = (run / "received-input.bin").read_bytes() if (run / "received-input.bin").exists() else b""
            tag_counts = {}
            for i in range(len(data) // 36):
                tags = f"{data[i*36+17]:02x}/{data[i*36+35]:02x}"
                tag_counts[tags] = tag_counts.get(tags, 0) + 1
            results[label] = {"unexpected_exit_code": statuses.get(label), "pad_frames": len(data)//36,
                              "mode_tag_counts": tag_counts,
                              "character_select": "both at the character select" in text,
                              "desync": "two games differ" in text or "desync" in text.lower(),
                              "fight_reached": "seq: state 3" in text,
                              "last_log": text.splitlines()[-12:]}
        (QA / "result.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
        print(json.dumps(results, indent=2))

if __name__ == "__main__":
    main()
