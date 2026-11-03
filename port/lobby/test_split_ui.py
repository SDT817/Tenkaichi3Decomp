"""Compile the actual viewport/HUD selectors and title predicate in isolation."""
from pathlib import Path
import os
import subprocess
import sys
import json
ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT.parent/'Chinese-local-analysis-20261022/online-lobby8-v014-20261030/verification'
sys.path.insert(0,str(ROOT/'local'))
import build_windows as b

def function(name,signature):
    text=(ROOT/name).read_text('utf-8')
    start=text.index(signature)
    brace=text.index('{',start);depth=1;end=brace+1
    while depth:
        depth+=(text[end]=='{')-(text[end]=='}');end+=1
    return text[start:end]

text='''#include <stdlib.h>
#include <assert.h>
namespace OnlineLobby { bool splitView; int primarySide; }
static int active, sMe, spectator;
int Port_NetActive(void){return active;}
int Port_NetMe(void){return sMe;}
int Port_NetSpectating(void){return spectator;}
int Port_OnlineSplitView(void){return OnlineLobby::splitView;}
int Port_Setting(const char *,int def){return def;}
'''
text+=function('port/src/gs/online_lobby.cpp','extern "C" int Port_OnlineSplitSwap(void)')+'\n'
text+=function('port/src/gs/net.c','int Port_HudSwap(void)')+'\n'
text+='''typedef int s32; typedef float f32;
enum {VIEW_LAYOUT_FULL,VIEW_LAYOUT_LEFT,VIEW_LAYOUT_RIGHT};
struct Vec4{float x,y,z,w;};
struct View{float aspect,centerX;int scissorX0,scissorX1,scissorY0,scissorY1;};
void Vec4_Set(Vec4 *v,float x,float y,float z,float w){*v={x,y,z,w};}
void View_SetProjection(View *v,Vec4*,float,float,float,float x,float,float,float,float,float,float){v->centerX=x;}
#define PORT
'''
text+=function('src/battle/btl_cam.c','void View_InitLayout(View *view, s32 layout)')+'\n'
text+='''struct Title{int state,flags;}; Title title,*gTitle;
int mode; int Port_GameMode(void){return mode;}
#define MODE_TITLE 1
#define TITLE_LEAVING 2
'''
text+=function('port/src/a11y_game.c','int Port_TitleNoticeVisible(void)')+'\n'
text+='''int main(){
for(spectator=0;spectator<2;spectator++)for(sMe=0;sMe<2;sMe++)for(int side=0;side<2;side++){
 active=1;OnlineLobby::splitView=true;OnlineLobby::primarySide=side;
 int swap=(spectator?0:sMe)^side;
 assert(Port_HudSwap()==swap);
 View left={},right={};View_InitLayout(&left,VIEW_LAYOUT_LEFT);View_InitLayout(&right,VIEW_LAYOUT_RIGHT);
 assert(left.scissorX0==(swap?257:0)); assert(right.scissorX0==(swap?0:257));
 assert(left.centerX==(swap?2176:1920));assert(right.centerX==(swap?1920:2176));
 View full={};View_InitLayout(&full,VIEW_LAYOUT_FULL);assert(full.scissorX0==0&&full.scissorX1==511);
 OnlineLobby::splitView=false;assert(Port_HudSwap()==(sMe==1));
}
mode=1;gTitle=nullptr;assert(!Port_TitleNoticeVisible());
gTitle=&title;title.state=0;assert(!Port_TitleNoticeVisible());
title.state=1;assert(Port_TitleNoticeVisible());title.state=2;assert(Port_TitleNoticeVisible());
title.flags=2;assert(!Port_TitleNoticeVisible());title.flags=0;mode=4;assert(!Port_TitleNoticeVisible());
return 0;}
'''
(OUT/'split_ui_probe.cpp').write_text(text,'utf-8')
cmd=['g++','-m32','-std=c++17','-O2',os.path.relpath(OUT/'split_ui_probe.cpp',ROOT),'-o',os.path.relpath(OUT/'split_ui_probe.exe',ROOT)]
r=b.undefined.run(cmd,cwd=ROOT,capture_output=True,text=True)
assert r.returncode==0,r.stderr
env=dict(os.environ);env.pop('BT3_HUD_SWAP',None)
r=subprocess.run([str(OUT/'split_ui_probe.exe')],capture_output=True,env=env)
assert r.returncode==0,r.stderr
report={'actual_HUD_and_camera_functions':True,'both_players_both_primary_sides':True,
        'spectator_views':True,'full_screen_layout_preserved':True,
        'title_intro_leaving_demo_predicate':True,'battle_simulation_not_run':True}
(OUT/'split-ui-tests.json').write_text(json.dumps(report,indent=2)+'\n','utf-8')
print(json.dumps(report,indent=2))
