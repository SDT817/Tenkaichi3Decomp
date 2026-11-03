"""Exercise the deployed font registry, saved ids and title rasterizer, CPU only."""
from pathlib import Path
import json
import os
import subprocess

from merge_cn8_hd184_inplace import ROOT, OUT, NEW, GAME, FIX
from record_cn8_history import load_zip, write


def main():
    prefix=(ROOT/'tools/check_cn7_labels.c').read_text('utf-8').split('int main(')[0]
    relative=os.path.relpath(NEW,FIX).replace('\\','/')+'/'
    prefix=prefix.replace('../../Tenkaichi3Decomp-WiiLocal-r8-CN7/',relative)
    # The production prompt enumerator also runs catalog extraction/migration.
    # Keep this CPU font test read-only and provide the already-chosen state.
    prefix=prefix.replace('#include "'+relative+'port/src/gs/menu_translation.c"',
        '#define MenuTranslation_BootPending unused_prompt_enumerator\n#include "'+relative+
        'port/src/gs/menu_translation.c"\n#undef MenuTranslation_BootPending\nint MenuTranslation_BootPending(void);')
    prefix=prefix.replace('int UiText_EuropeanOnStartup(const char *d, char *w, size_t n) { abort(); }',
                          'int UiText_EuropeanOnStartup(const char *d, char *w, size_t n) { return 0; }')
    prefix=prefix.replace('int Port_Setting(const char *n, int d) { abort(); }',r'''
int Port_Setting(const char *n, int d) {
    char line[1200];FILE *f=fopen("bt3_settings.txt","rb");assert(f);
    while(fgets(line,sizeof(line),f)) {
        char *end=strchr(line,'=');
        if(end&&(size_t)(end-line)==strlen(n)&&!memcmp(line,n,strlen(n))) {
            int value=atoi(end+1);fclose(f);return value;
        }
    }
    fclose(f);return d;
}''')
    prefix+='\nint Port_NetSession(void) { return 0; }\nint MenuTranslation_BootPending(void) { return 0; }\n'
    code=prefix+r'''
#undef assert
#define assert(c) do { if(!(c)) { fprintf(stderr,"check failed at %d: %s\n",__LINE__,#c); exit(1); } } while(0)
int main(int argc,char **argv) {
    SetErrorMode(SEM_FAILCRITICALERRORS|SEM_NOGPFAULTERRORBOX);
    int before=argc>1&&!strcmp(argv[1],"before");
    assert(argc==3);
    assert(!_putenv_s("BT3_FONTS",argv[2]));
    assert(!_putenv_s("BT3_MENU_FONT","gamedata/game-text"));
    assert(!_putenv_s("BT3_DATA","gamedata"));
    assert(!_putenv_s("BT3_MENU_LANG","zh-CN"));
    /* Load the exact deployed catalog without its migration/copy side effects.
       All font-directory discovery, parsing, id resolution and rasterizing below
       use the production code, not manually opened faces or forced choices. */
    assert(tr_read("gamedata/game-text/translations/labels/zh-CN.json","zh-CN"));
    strcpy(sLocale,"zh-CN");__atomic_store_n(&sReady,1,__ATOMIC_RELEASE);
    int menuId=Port_Setting("menu_font_id",0),textId=Port_Setting("text_font_id",0);
    assert(menuId==831785631&&textId==831785631);
    MenuText_SetFontId(menuId);MenuText_SetSharedFontId(textId);
    if(before) {
        assert(MenuText_FontChoice(menuId)==0&&!MenuText_GetFont()&&!MenuText_GetSharedFont());
        puts("{\"original_manifest_reproduces_missing_font\":true,\"menu_falls_back_to_original\":true,\"game_launched\":false}");
        return 0;
    }
    int choice=MenuText_FontChoice(menuId);
    assert(choice>0&&MenuText_GetFont()==choice&&MenuText_GetSharedFont()==choice);
    assert(!strcmp(sFonts[choice-1].file,"bt3cn-rounded-bold.ttf"));
    assert(MenuText_FontAvailable(choice,MENU_TEXT_MENU));
    assert(MenuText_FontAvailable(choice,MENU_TEXT_DIALOGUE));
    assert(MenuText_FontIdToSave()==menuId);
    assert(MenuText_FontId(MenuText_GetSharedFont())==textId);
    assert(sCount==585);
    int title=0,mainRows=0;uint64_t titleBytes=0,mainBytes=0;
    for(int i=0;i<sCount;i++) {
        int isTitle=!strcmp(sLabels[i].text,"\xe9\x87\x8d\xe6\x96\xb0\xe6\xb8\xb8\xe6\x88\x8f")||
                    !strcmp(sLabels[i].text,"\xe7\xbb\xa7\xe7\xbb\xad\xe6\xb8\xb8\xe6\x88\x8f");
        if(!isTitle&&!sLabels[i].warmMain)continue;
        Row row;int owned;assert(row_get(i,3,&row,&owned)&&!owned&&row.px&&row.w>0&&row.h>0);
        int ink=0;for(size_t p=3;p<(size_t)row.w*row.h*4;p+=4)ink|=row.px[p];assert(ink);
        if(isTitle){title++;titleBytes+=(uint64_t)row.w*row.h*4;}
        if(sLabels[i].warmMain){mainRows++;mainBytes+=(uint64_t)row.w*row.h*4;}
    }
    assert(title==4&&mainRows==25);
    rows_clear();for(int i=0;i<25;i++)MenuText_WarmGlyphs(3);
    int cached=0;for(int i=0;i<ROW_CACHE_MAX;i++)cached+=sRows[i].scale!=0;assert(cached==25);
    printf("{\"passed\":true,\"actual_deployed_registry_and_saved_ids\":true,\"font_id\":%d,"
           "\"menu_and_dialogue_font_opened\":true,\"label_pieces\":%d,\"title_labels_rasterized\":%d,"
           "\"main_menu_rows_rasterized\":%d,\"raster_scale\":3,\"title_bytes\":%llu,\"main_bytes\":%llu,"
           "\"main_rows_prewarmed\":%d,\"game_launched\":false,\"GPU_used\":false}\n",
           menuId,sCount,title,mainRows,(unsigned long long)titleBytes,(unsigned long long)mainBytes,cached);
    return 0;
}
'''
    p=FIX/'deployed-font-check.c';p.write_text(code,'utf-8')
    exe=p.with_suffix('.exe')
    env=dict(os.environ,PATH=r'E:\BT3-Wii-tools\mingw64\bin;'+os.environ['PATH'])
    run=subprocess.run([r'E:\BT3-Wii-tools\mingw64\bin\gcc.exe','-O2','-std=gnu99',
        '-ffunction-sections','-fdata-sections',str(p.relative_to(ROOT)),
        '-Wl,--gc-sections','-pthread','-lm','-o',str(exe.relative_to(ROOT))],
        cwd=ROOT,env=env,capture_output=True,encoding='utf-8',errors='replace')
    (FIX/'deployed-font-check-build.log').write_text(run.stdout+run.stderr,'utf-8')
    if run.returncode:print((run.stdout+run.stderr)[-5000:])
    run.check_returncode()
    before=FIX/'before-fonts';before.mkdir(exist_ok=True)
    (before/'fonts.tsv').write_bytes(load_zip(FIX/'original-game-config.zip')['fonts/fonts.tsv'])
    report={}
    for name,directory in [('before',os.path.relpath(before,GAME)),('after','fonts')]:
        run=subprocess.run([str(exe),name,directory],cwd=GAME,env=env,
            capture_output=True,encoding='utf-8',errors='replace',timeout=30)
        (FIX/('deployed-font-'+name+'.log')).write_text(run.stdout+run.stderr,'utf-8')
        if run.returncode:print(run.stdout+run.stderr)
        run.check_returncode();report[name]=json.loads(run.stdout)
    write(FIX/'deployed-font-verification.json',report)
    (FIX/'verify_cn8_deployed_hd184.py').write_bytes(Path(__file__).read_bytes())
    print(json.dumps(report,ensure_ascii=False,indent=2))


if __name__=='__main__':main()
