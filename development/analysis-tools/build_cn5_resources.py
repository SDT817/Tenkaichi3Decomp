"""Preserve CN4 resources and correct the encoded 负 glyph globally."""
from pathlib import Path
import json,shutil
import build_cn4_resources as build

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT/'cn4-resources'
OUT=ROOT/'cn5-resources'


def main():
    assert not OUT.exists(),'Preserve completed resource builds'
    shutil.copytree(BASE,OUT)
    build.BASE=BASE;build.OUT=OUT;build.GLYPH_FIXES={'E06F':'负'};build.TOURNAMENT={}
    build.main()
    report=json.loads((OUT/'cn4-manifest.json').read_text('utf-8'))
    report.update(edition='r6-CN5',base='CN4',official_version='0.1.38.3',
                  official_commit='13ecf4f3eaf4ba5b285adba33f81f699246598a9')
    report['new_tournament_explanations']=0
    report['inherited_tournament_explanations']=34
    report['new_sim_pause_labels']=0
    report['inherited_sim_pause_labels']=6
    report['inherited_glyph_fixes']=json.loads((BASE/'glyph-corrections.json').read_text('utf-8'))
    report['affected_UI_rows']=sum(chr(0xe06f) in r['text'] for r in json.loads(
        (OUT/'game-text/translations/ui/zh-CN.json').read_text('utf-8'))['labels'].values())
    (OUT/'cn5-manifest.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n','utf-8')
    # The prior catalog/menu layout, art and all translation strings are immutable.
    for p in (BASE/'game-text').rglob('*'):
        if p.is_file():assert p.read_bytes()==(OUT/'game-text'/p.relative_to(BASE/'game-text')).read_bytes(),str(p)
    print('Corrected E06F 页 -> 负; affected text rows:',report['affected_UI_rows'])


if __name__=='__main__':main()
