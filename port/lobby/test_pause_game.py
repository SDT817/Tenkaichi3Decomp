"""Compile actual pause dispatch/draw functions; check both peers and re-execution."""
from pathlib import Path
import json
import os
import re
import subprocess
import sys
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT.parent/'Chinese-local-analysis-20261022/online-lobby10-v016-20261101/verification'
sys.path.insert(0,str(ROOT/'local'))
import build_windows as build

def function(name,signature):
    text=(ROOT/name).read_text('utf-8');start=text.index(signature)
    brace=text.index('{',start);depth=1;end=brace+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

code=r'''
#include <cassert>
#include <cstring>
#include <cstdint>
#define PORT
typedef int s32;
enum { BATTLE_FLAG_PAUSE=0x100, BATTLE_FLAG_PAUSE_MENU=0x200 };
struct Work { unsigned flags; } work;
struct Pad { unsigned gamePressed; } gPad[2];
struct BtlPause { int padCount,pad; } pauseWork;
struct BtlSeqWaitCtx { int (*poll)(); };
namespace OnlineLobby { bool launched, matchPause; }
static int online,me,mode=6,menuAction,menuFrames,draws,sound,voice,aborted,ended;
static int gPortSeSilent,gPauseMenuWhich;
enum {BTL_RESULT_ABORT=1};
Work *Battle_GetWork(){return &work;}
BtlPause *BtlPause_GetWork(){return &pauseWork;}
int Port_NetActive(){return online;}
int Port_NetMe(){return me;}
int Battle_GetMode(){return mode;}
int BattleReplay_IsActive(){return 0;}
int BattleReplay_IsLoaded(){return 0;}
int BtlPause_GetPad(){return pauseWork.pad;}
int BtlPause_GetMenuPad(){return pauseWork.pad;}
int BtlScript_IsEventRunning(){return 0;}
int PadWatch_GetMissing(int*){return 0;}
void BtlScript_AbortEvents(){}
void BattleResult_Set(int,int){aborted=1;}
int BattleResult_IsAborted(){return aborted;}
int BtlSeq_CheckBattleEnd(){return ended;}
void Adx_PauseSeVoice(){voice=1;}
void Snd_SetPause(int,int on){sound=on;}
void PauseMenu_Reset(){menuFrames=0;}
int PauseMenu_Update(int owner,int which){
 assert(owner==pauseWork.pad && which==0);++menuFrames;
 if(menuAction){work.flags&=~BATTLE_FLAG_PAUSE;voice=0;return 0;}return 1;
}
void BtlMenu_DrawAll(){++draws;}
#define BTL_PAUSE_START 0x1000
'''
code+=function('port/src/gs/online_lobby.cpp','extern "C" int Port_OnlinePauseAllowed(void)')+'\n'
code+=function('src/battle/hud_e_d.c','s32 BtlPause_CheckOpen(void)')+'\n'
code+=function('src/battle/btl_seq.c','s32 BtlSeqFight_Update(BtlSeqWaitCtx *ctx)')+'\n'
code+=function('src/battle/hud_0.c','void PauseMenu_Draw(void)')+'\n'
code+=r'''
static void reset(int enabled,int local,int net=1){
 memset(&work,0,sizeof(work));memset(gPad,0,sizeof(gPad));pauseWork={2,0};
 OnlineLobby::launched=net;OnlineLobby::matchPause=enabled;online=net;me=local;
 menuAction=menuFrames=draws=sound=voice=aborted=ended=gPortSeSilent=gPauseMenuWhich=0;
}
int main(){
 BtlSeqWaitCtx ctx={BtlPause_CheckOpen};
 for(int enabled=0;enabled<2;enabled++)for(int owner=0;owner<2;owner++)for(int local=0;local<3;local++){
   reset(enabled,local);gPad[owner].gamePressed=BTL_PAUSE_START;
   assert(BtlSeqFight_Update(&ctx)==3);assert(pauseWork.pad==owner);
   assert((work.flags&BATTLE_FLAG_PAUSE_MENU)!=0);
   assert(bool(work.flags&BATTLE_FLAG_PAUSE)==bool(enabled));
   assert(sound==enabled && voice==enabled);
   PauseMenu_Draw();assert(draws==(enabled||owner==local));
   gPad[owner].gamePressed=0;
   int simulationTicks=0;
   for(int t=0;t<60;t++){
     // The original frame loop continues to sample input and dispatch the menu.
     if(!(work.flags&BATTLE_FLAG_PAUSE))++simulationTicks;
     assert(BtlSeqFight_Update(&ctx)==3);
   }
   assert(simulationTicks==(enabled?0:60));
   menuAction=1;assert(BtlSeqFight_Update(&ctx)==3);
   assert(!(work.flags&(BATTLE_FLAG_PAUSE|BATTLE_FLAG_PAUSE_MENU)));assert(!sound&&!voice);
 }
 // Predicted START can be removed by restoring game state and re-executing.
 for(int owner=0;owner<2;owner++){
   reset(1,0);Work saved=work;BtlPause savedPause=pauseWork;
   gPad[owner].gamePressed=BTL_PAUSE_START;BtlSeqFight_Update(&ctx);
   assert(work.flags&BATTLE_FLAG_PAUSE);
   work=saved;pauseWork=savedPause;menuFrames=0;memset(gPad,0,sizeof(gPad));
   BtlSeqFight_Update(&ctx);assert(work.flags==0&&menuFrames==0);
   // Both peer identities get the same game state for confirmed START.
   unsigned flags[2];int owners[2];
   for(int local=0;local<2;local++){
     reset(1,local);gPad[owner].gamePressed=BTL_PAUSE_START;BtlSeqFight_Update(&ctx);
     flags[local]=work.flags;owners[local]=pauseWork.pad;
   }
   assert(flags[0]==flags[1]&&owners[0]==owners[1]);
 }
 reset(0,0,0);gPad[1].gamePressed=BTL_PAUSE_START;BtlSeqFight_Update(&ctx);
 assert(work.flags&BATTLE_FLAG_PAUSE);PauseMenu_Draw();assert(draws==1);
 // This option stops applying after the private session; public behavior stays original.
 reset(1,0);OnlineLobby::launched=false;gPad[1].gamePressed=BTL_PAUSE_START;
 BtlSeqFight_Update(&ctx);assert(!(work.flags&BATTLE_FLAG_PAUSE));PauseMenu_Draw();assert(!draws);
 return 0;
}
'''
(OUT/'pause-game-probe.cpp').write_text(code,'utf-8')
run=build.undefined.run(['g++','-m32','-O2','-std=c++17',os.path.relpath(OUT/'pause-game-probe.cpp',ROOT),
    '-o',os.path.relpath(OUT/'pause-game-probe.exe',ROOT)],cwd=ROOT,capture_output=True,text=True)
assert run.returncode==0,run.stderr
run=subprocess.run([str(OUT/'pause-game-probe.exe')],capture_output=True)
assert run.returncode==0,(run.stdout+run.stderr).decode('utf-8','replace')
old=ROOT.parent/'Tenkaichi3Decomp-WiiLocal-r17-Lobby013'
protected=['port/src/gs/net.c','port/src/gs/state.c',
           'port/src/gs/net_relay.c','src/battle/btl_input.c','src/battle/hud_e_d.c','src/battle/battle.c']
assert all((ROOT/n).read_bytes()==(old/n).read_bytes() for n in protected)
# The game's pause work and menu selection must still be captured in .mem.
ranges=[tuple(int(v,16) for v in line.split()) for line in (ROOT/'port/build/bt3.exe.mem').read_text().splitlines()]
mapping=(ROOT/'port/build/bt3.exe.map').read_text('utf-8',errors='replace')
symbols={}
for symbol in ['gBtlPause','gPauseMenuWhich','gBtlMenu']:
    match=re.search(r'^\s+0x([0-9a-fA-F]+)\s+'+symbol+r'\s*$',mapping,re.M)
    assert match,symbol
    address=int(match[1],16)
    assert any(start>1 and start<=address<start+length for start,length in ranges),symbol
    symbols[symbol]=hex(address)
report={'actual_pause_dispatch_draw_and_START_functions':True,
        'both_owners_both_clients_and_spectator_render':True,
        'yes_freezes_and_resumes_no_keeps_official_behavior':True,
        'reexecution_after_restored_state_is_deterministic':True,
        'rollback_network_input_and_main_loop_sources_unchanged':protected,
        'pause_and_menu_globals_in_original_snapshot_ranges':symbols,
        'full_remote_gameplay_and_real_rollback_not_run':True}
(OUT/'pause-game-tests.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
print(json.dumps(report,indent=2))
