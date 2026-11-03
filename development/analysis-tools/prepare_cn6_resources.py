"""Migrate accepted CN5 GlyphFix2 assets to official v13 labels without changing styles."""
from pathlib import Path
import hashlib, json, shutil
from merge_cn6_source import ROOT, OUT, NEW, write_json

BASE = ROOT/'cn5-glyph-fix2-resources'
RES = ROOT/'cn6-resources'
VERIFY = ROOT/'cn6-verification'
GAME = Path(r'D:\Tenkaichi3Decomp')

def fnv(data):
    h=14695981039346656037
    for b in data:h=((h^b)*1099511628211)&0xffffffffffffffff
    return f'{h:016x}'

def main():
    assert not RES.exists(), 'Keep previous resource snapshots'
    shutil.copytree(BASE, RES)
    VERIFY.mkdir(exist_ok=True)
    official=(GAME/'gamedata/game-text/labels.tsv').read_text('utf-8').splitlines()
    assert official[0].startswith('# BT3 menu text v13:') and official[0].endswith('label_id quick')
    lookup={}
    for line in official[1:]:
        if not line or line.startswith('#'):continue
        row=line.split('\t');assert len(row)==32
        key=tuple(row[:3]);assert key not in lookup or lookup[key]==row[-1]
        lookup[key]=row[-1]
    baseline=(BASE/'game-text/labels.tsv').read_text('utf-8').splitlines()
    lines=[official[0]]; rows=[]
    for line in baseline[1:]:
        if not line or line.startswith('#'):continue
        row=line.split('\t');assert len(row)==31
        key=tuple(row[:3]);quick=lookup.get(key)
        source='official generated v13 table'
        if quick is None:
            assert row[-1].startswith('sim-dragon-pause-'),row[-1]
            texture=2 if row[-1].startswith('sim-dragon-pause-selected') else 1
            raw=ROOT/f'cn4-analysis/sim-menu/us474-1-23-{texture}.rgba'
            rgba=raw.read_bytes();pixels=int(row[1])*int(row[2])
            assert len(rgba)==pixels*4 and fnv(rgba)==row[0],row[-1]
            quick=fnv(b''.join(rgba[(k*pixels//64)*4:(k*pixels//64)*4+4] for k in range(64)))
            source=str(raw.relative_to(ROOT))
        lines.append(line+'\t'+quick)
        assert lines[-1].split('\t')[:-1]==row
        rows.append({'id':row[-1],'hash':row[0],'quick':quick,'quick_source':source})
    assert len(rows)==511
    (RES/'game-text/labels.tsv').write_text('\n'.join(lines)+'\n','utf-8')
    fonts=(GAME/'fonts/fonts.tsv').read_text('utf-8-sig')
    assert 'bt3cn-rounded-bold.ttf' not in fonts
    fonts=fonts.rstrip('\r\n')+'\n'+'bt3cn-rounded-bold.ttf\t寒蝉圆黑体·粗体（本地适配）\t3\n'
    (RES/'fonts/fonts.tsv').write_text(fonts,'utf-8')
    changed=[];same=[]
    for p in sorted(BASE.rglob('*')):
        if not p.is_file():continue
        name=p.relative_to(BASE).as_posix()
        (same if p.read_bytes()==(RES/name).read_bytes() else changed).append(name)
    assert changed==['fonts/fonts.tsv','game-text/labels.tsv'],changed
    write_json(VERIFY/'resource-migration.json',{'base':'CN5 GlyphFix2 user accepted',
        'labels_version':13,'label_rows':len(rows),'all_31_original_columns_unchanged':True,
        'official_quick_rows':sum(r['quick_source']=='official generated v13 table' for r in rows),
        'additional_quick_rows':sum(r['quick_source']!='official generated v13 table' for r in rows),
        'changed_files':changed,'unchanged_files':same,'rows':rows,
        'all_glyph_fixes_art_and_catalogs_byte_identical':True,'game_launched':False})
    # Actual new renderer/parser, with the prior standalone test drivers.
    for stem in ['render_cn5_font','check_cn5_lookup']:
        text=(ROOT/'tools'/f'{stem}.c').read_text('utf-8')
        text=text.replace('Tenkaichi3Decomp-WiiLocal-r6-CN5','Tenkaichi3Decomp-WiiLocal-r7-CN6')
        (ROOT/'tools'/f'{stem.replace("cn5","cn6")}.c').write_text(text,'utf-8')
    text=(ROOT/'tools/verify_cn5_glyph_fix2_resources.py').read_text('utf-8')
    text=text.replace("RES=ROOT/'cn5-glyph-fix2-resources';OUT=ROOT/'cn5-glyph-fix2-verification'",
                      "RES=ROOT/'cn6-resources';OUT=ROOT/'cn6-verification'")
    text=text.replace('tools/render_cn5_font.exe','tools/render_cn6_font.exe')
    text=text.replace("'cn5-glyph-fix2-resources/fonts/'","'cn6-resources/fonts/'")
    text=text.replace('cn5-glyph-fix2-verification/extra-','cn6-verification/extra-')
    (ROOT/'tools/verify_cn6_resources.py').write_text(text,'utf-8')
    report=json.loads((OUT/'three-way-merge.json').read_text('utf-8'))
    report.update(unresolved_conflicts=False, conflict_resolutions={
        'port/src/gs/ui.cpp':['Keep the official slider-release Port_SettingsWrite call and existing Chinese tooltip.']})
    write_json(OUT/'three-way-merge.json',report)
    print('Preserved all accepted resource bytes except two metadata tables; migrated 511 labels to v13.')

if __name__=='__main__':main()
