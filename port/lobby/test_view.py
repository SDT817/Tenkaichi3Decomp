"""Compile the actual display selector; no game process or network is used."""
import json
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = ROOT.parent/'Chinese-local-analysis-20261022/online-lobby2-preview-20261027/verification'
sys.path.insert(0,str(ROOT/'local'))
import build_windows as build

source=(ROOT/'port/src/gs/net.c').read_text('utf-8')
start=source.index('int Port_NetView(void) {')
end=source.index('\n}\n',start)+3
function=source[start:end]
harness='''#include <stdlib.h>
#include <assert.h>
static int active,split,sMe;
int Port_NetActive(void){return active;}
int Port_OnlineSplitView(void){return split;}
'''+function+'''
int main(int argc,char **argv){
  int forced=argc>1?atoi(argv[1]):-1;
  for(active=0;active<2;++active)for(split=0;split<2;++split)for(sMe=0;sMe<2;++sMe){
    int expected=active && split?-1:forced>=0?forced&1:active?sMe:-1;
    assert(Port_NetView()==expected);
  }
  return 0;
}
'''
(OUT/'view_probe.c').write_text(harness,'utf-8')
result=build.undefined.run(['gcc','-m32','-O2',os.path.relpath(OUT/'view_probe.c',ROOT),'-o',os.path.relpath(OUT/'view_probe.exe',ROOT)],cwd=ROOT,capture_output=True,text=True)
assert result.returncode==0,result.stderr
for forced in (None,0,1,2,3):
    env=dict(os.environ);env.pop('BT3_VIEW',None)
    if forced is not None:env['BT3_VIEW']=str(forced)
    result=subprocess.run([str(OUT/'view_probe.exe')]+([] if forced is None else [str(forced)]),env=env,capture_output=True)
    assert result.returncode==0,result.stderr
(OUT/'view-tests.json').write_text(json.dumps({'actual_Port_NetView_compiled':True,'local_full_split_and_forced_view_cases':40,'game_launched':False},indent=2)+'\n','utf-8')
print('Passed 40 actual display selector cases (no game launch).')
