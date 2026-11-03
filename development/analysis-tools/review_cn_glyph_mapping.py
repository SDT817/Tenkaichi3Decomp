"""Cross-check manual glyph reading against OCR and independent known sentences."""
from pathlib import Path
from collections import Counter, defaultdict
import json, unicodedata
from PIL import Image, ImageDraw, ImageFont

ROOT=Path(__file__).resolve().parents[1]
OUT=ROOT/'cn3-glyph-mapping'

def norm(s): return unicodedata.normalize('NFKC',s)
def dump(p,v): p.write_text(json.dumps(v,ensure_ascii=False,indent=2)+'\n','utf-8')

def main():
    draft=json.loads((OUT/'manual-grids.json').read_text('utf-8'))['grids']
    mapping={}
    images={}
    for k,lines in sorted(draft.items()):
        cells=json.loads((OUT/f'inputs/grid-5-{k}.json').read_text('utf-8'))
        assert len(''.join(lines))==len(cells),k
        im=Image.open(OUT/f'inputs/grid-5-{k}.png').convert('RGB')
        for cell,char in zip(cells,''.join(lines)):
            code=cell['code'];x,y=cell['cell']
            mapping[code]=char
            images[code]=im.crop((x*130,y*130,(x+1)*130,(y+1)*130))
    known=json.loads((ROOT/'cn3-body-font-options/records/sample-glyph-identities.json').read_text('utf-8'))['encoded_to_Unicode']
    overrides=json.loads((OUT/'manual-overrides.json').read_text('utf-8')) if (OUT/'manual-overrides.json').exists() else {}
    mapping.update(known)
    mapping.update(overrides)
    ocr=defaultdict(dict)
    for line in (OUT/'ocr-grids.jsonl').read_text('utf-8').splitlines():
        record=json.loads(line);path=Path(record['path'])
        cells={tuple(c['cell']):c['code'] for c in json.loads(path.with_suffix('.json').read_text('utf-8'))}
        for ln in record['lines']:
            for word in ln['words']:
                pos=(int((word['x']+word['w']/2)//130),int((word['y']+word['h']/2)//130))
                code=cells.get(pos)
                if code and len(word['text'])==1: ocr[code][path.stem.split('-')[1]]=word['text']
    duplicates=defaultdict(list)
    for code,char in mapping.items(): duplicates[norm(char)].append(code)
    duplicates={char:codes for char,codes in duplicates.items() if len(codes)>1}
    suspects=[]
    for code,char in mapping.items():
        if code not in images or code in known or code in overrides: continue
        votes={norm(s) for s in ocr[code].values()}
        if norm(char) in duplicates or (len(votes)==1 and len(ocr[code])==2 and norm(char) not in votes):
            suspects.append(code)
    font=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',18)
    display=ImageFont.truetype(r'C:\Windows\Fonts\msyh.ttc',30)
    for start in range(0,len(suspects),96):
        part=suspects[start:start+96]
        sheet=Image.new('RGB',(8*200,12*150),'#ededed');d=ImageDraw.Draw(sheet)
        for i,code in enumerate(part):
            x=(i%8)*200;y=(i//8)*150
            sheet.paste(images[code].resize((100,100)),(x,y+25))
            d.text((x+2,y),code,font=font,fill='black')
            d.text((x+107,y+27),mapping[code],font=display,fill='#003a7b')
            d.text((x+107,y+70),'/'.join(ocr[code].values()),font=font,fill='#a00000')
        sheet.save(OUT/f'audit-{start:04d}.png')
    dump(OUT/'manual-map.json',mapping)
    dump(OUT/'audit.json',{'count':len(mapping),'known_sentence_mappings':len(known),'duplicates':duplicates,
                         'suspects':suspects,'ocr':dict(ocr)})
    print('Mapped',len(mapping),'duplicate identities',len(duplicates),'to audit',len(suspects))

if __name__=='__main__':main()
