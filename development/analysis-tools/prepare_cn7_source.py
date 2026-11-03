"""Isolate accepted G source and add only display translation adapters."""
from pathlib import Path
import hashlib,json,shutil

ROOT=Path(__file__).resolve().parents[1]
BASE=ROOT.parent/'Tenkaichi3Decomp-WiiLocal-r7-CN6-Perf4'
OUT=ROOT.parent/'Tenkaichi3Decomp-WiiLocal-r8-CN7'
RECORDS=ROOT/'cn7-records'
SKIP={'.git','build','dist','gamedata','__pycache__'}

def source_files(folder):
    import os
    files={}
    for current,dirs,names in os.walk(folder):
        dirs[:]=sorted(d for d in dirs if d not in SKIP)
        for n in sorted(names):
            p=Path(current)/n
            files[p.relative_to(folder).as_posix()]=p.read_bytes()
    return files

def main():
    assert not OUT.exists(),'Preserve previous source endpoints'
    RECORDS.mkdir(exist_ok=True)
    before=source_files(BASE)
    (RECORDS/'base-G-source-hashes.json').write_text(json.dumps(
        {n:hashlib.sha256(b).hexdigest() for n,b in before.items()},indent=2)+'\n','utf-8')
    for n,b in before.items():
        p=OUT/n;p.parent.mkdir(parents=True,exist_ok=True);p.write_bytes(b)
    shutil.copytree(BASE/'port/build',OUT/'port/build')
    p=OUT/'src/battle/btl_script.c'
    text=p.read_text('utf-8')
    anchor='extern void Font_PrintAt(s32 x, s32 y, void *text);'
    assert text.count(anchor)==1
    text=text.replace(anchor,anchor+'\n#ifdef PORT\nextern const u16 *UiText_TranslateLine(const u32 *table, int line, const u16 *original);\n#endif')
    anchor='        text = BtlScript_GetText(work->textId);'
    assert text.count(anchor)==1
    text=text.replace(anchor,anchor+'\n#ifdef PORT\n        text = (void *)UiText_TranslateLine((const u32 *)work->textFile, work->textId, (const u16 *)text);\n#endif')
    p.write_text(text,'utf-8')
    p=OUT/'port/src/gs/ui_text_translate.c';text=p.read_text('utf-8')
    assert '#define UI_MAX_ROWS 30000' in text
    text=text.replace('#define UI_MAX_ROWS 30000','#define UI_MAX_ROWS 40000')
    start=text.index('const uint16_t *UiText_TranslateSpan(')
    end=text.index('const uint16_t *UiText_TranslateLine(',start)
    text=text[:start]+'''/* A skill can have the same name but a different following condition.
   Prefer an exact two-line catalog entry, then the ordinary one-line span. */
static const uint16_t *ui_span_text(const uint16_t *original, int length, uint64_t h) {
    unsigned slot;
    int i;
    UiWord *w;
    h = ui_hash_char(h, 0);
    slot = (unsigned)h & (UI_WORD_SLOTS - 1);
    while ((w = &sWords[slot])->original) {
        if (w->hash == h) {
            for (i = 0; i < length && w->original[i + 1] == original[i]; i++) { }
            if (i == length && !w->original[length + 1]) {
                return !w->ambiguous ? w->translated : NULL;
            }
        }
        slot = (slot + 1) & (UI_WORD_SLOTS - 1);
    }
    return NULL;
}
const uint16_t *UiText_TranslateSpan(const uint16_t *original) {
    uint64_t h = UINT64_C(1469598103934665603), contextHash;
    int length, contextLength;
    const uint16_t *translated;
    if (!__atomic_load_n(&sReady, __ATOMIC_ACQUIRE) || !original) return original;
    if (*original == 0xfeff) return UiText_TranslateString(original);
    h = ui_hash_char(h, 0xfeff);
    for (length = 0; length < UI_MAX_UNITS - 2; length++) {
        uint16_t c = original[length];
        if (!c || c == '\\n' || c == '\\r') break;
        h = ui_hash_char(h, c);
    }
    if (length == 0 || length == UI_MAX_UNITS - 2) return original;
    if (original[length] == '\\n') {
        contextHash = ui_hash_char(h, '\\n');
        for (contextLength = length + 1; contextLength < UI_MAX_UNITS - 2; contextLength++) {
            uint16_t c = original[contextLength];
            if (!c || c == '\\n' || c == '\\r') break;
            contextHash = ui_hash_char(contextHash, c);
        }
        if (contextLength < UI_MAX_UNITS - 2 &&
            (translated = ui_span_text(original, contextLength, contextHash))) return translated;
    }
    translated = ui_span_text(original, length, h);
    return translated ? translated : original;
}
''' +text[end:]
    p.write_text(text,'utf-8')
    doc=OUT/'local/CN7_CHANGES.md'
    doc.write_text('''# CN7 translation completion

Base: user-accepted G / CN6-Perf4, official v0.1.38.7 (52b675c3ee4ed90f4f0d8e94217867a52638cc15).

The battle story view translates its existing text table and line immediately before measuring and drawing. The original table, script, line id, voice, speaker, trigger and timing remain unchanged. The UI row bound is 40,000 for the existing 21,100 rows plus 50 complete 300-row story tables and two contextual skill entries; the existing 16 MiB file/arena and 256-group bounds remain.

Skill display spans prefer an exact two-line match before their existing one-line fallback. This disambiguates the identically named Z Counter entries using their existing following condition lines. No script parsing or gameplay command is changed.

The new resource edition retains audited glyph identities and accepted menu styles. Newly used private ISO glyphs without a reviewed Unicode identity retain their exact ISO bitmap instead of inventing a character mapping. CLEAR!! and FAILED... remain original, as requested.

Networking/protocol source, controls, settings persistence, saves and accepted G renderer behavior are unchanged. This edition is local only; no commit, push or PR update.
''','utf-8')
    after=source_files(OUT)
    changed=[n for n in before if before[n]!=after[n]]
    assert changed==['port/src/gs/ui_text_translate.c','src/battle/btl_script.c'],changed
    print('Prepared',OUT,'display source changes:',changed)

if __name__=='__main__':main()
