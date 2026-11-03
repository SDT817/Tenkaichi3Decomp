r"""Build a signed private release; never reads player/admin settings or ISO data.

Run on the administrator's BUILD PC, not the public server. Keep the signing
key here. Copy only the output updates directory to C:\BT3Lobby\updates.
The last publication step on the server is replacing latest.json.
"""
import argparse
import base64
import hashlib
import importlib.util
import json
from pathlib import Path
import re
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location('update_key', ROOT/'port/tools/update_key.py')
key = importlib.util.module_from_spec(spec)
spec.loader.exec_module(key)
FILES = ['Tenkaichi3Decomp.exe','Tenkaichi3Decomp.exe.mem','Tenkaichi3Decomp.dat',
         '启动游戏.exe','BT3Connect.exe','SDL3.dll','Lobby-CN8-Build.json']
ASSET = 'Tenkaichi3Decomp-windows-x64.zip'
MANIFEST = 'bt3_files.json'


def managed_files(game):
    """Release-owned files only; never enumerate saves, settings or gamedata."""
    names = list(FILES)
    if (game/'a11y_es.txt').is_file():
        names.append('a11y_es.txt')
    for folder in ('fonts', 'licenses', 'translations', 'tbo/ui'):
        for path in sorted((game/folder).rglob('*')):
            if path.is_file() and path.relative_to(game).as_posix() != 'fonts/fonts.tsv':
                if path.is_symlink():
                    raise ValueError('Release files cannot be symbolic links')
                names.append(path.relative_to(game).as_posix())
    return names


def publish(game, output, version, notes, key_file, endpoint='https://114.132.102.42:2626'):
    if not re.fullmatch(r'[0-9]+(?:\.[0-9]+){1,3}',version):
        raise ValueError('Use a numeric private edition version, e.g. 0.14')
    seed=base64.b64decode(key_file.read_text('ascii').strip(),validate=True)
    if len(seed)!=32 or key.public_key(seed)!=key.header_key():
        raise ValueError('Signing key does not match the compiled public key')
    output.mkdir(parents=True,exist_ok=True)
    tag='v'+version
    folder=output/tag
    folder.mkdir(exist_ok=True)
    archive=folder/ASSET
    if archive.exists():
        raise FileExistsError('A published version is immutable; use a new version number')
    # A curated runtime-only release: personal files and game assets cannot
    # accidentally enter a public update, including administrator credentials.
    missing=[name for name in FILES if not (game/name).is_file()]
    if missing:
        raise FileNotFoundError(', '.join(missing))
    build=json.loads((game/'Lobby-CN8-Build.json').read_text('utf-8-sig'))
    if build.get('private_version')!=version:
        raise ValueError('The built private_version must match the publication number; rebuild before publishing a new version')
    names = managed_files(game)
    integrity = {'format': 1, 'version': version, 'files': [
        {'path': name, 'size': (game/name).stat().st_size,
         'sha256': hashlib.sha256((game/name).read_bytes()).hexdigest()} for name in names]}
    raw_manifest = (json.dumps(integrity, ensure_ascii=False, indent=2)+'\n').encode('utf-8')
    (game/MANIFEST).write_bytes(raw_manifest)
    (game/(MANIFEST+'.sig')).write_text(key.sign(seed, raw_manifest).hex()+'\n', 'ascii')
    with zipfile.ZipFile(archive,'w',zipfile.ZIP_DEFLATED,compresslevel=6) as z:
        for name in [*names, MANIFEST, MANIFEST+'.sig']:
            z.write(game/name,'Tenkaichi3Decomp/'+name)
    raw=archive.read_bytes()
    signature=key.sign(seed,raw)
    assert key.verify(key.public_key(seed),raw,signature)
    (folder/(ASSET+'.sig')).write_text(signature.hex()+'\n','ascii')
    assets=[]
    for file in (archive,folder/(ASSET+'.sig')):
        assets.append({'name':file.name,'size':file.stat().st_size,
                       'digest':'sha256:'+hashlib.sha256(file.read_bytes()).hexdigest(),
                       'browser_download_url':endpoint+'/updates/'+tag+'/'+file.name})
    manifest={'tag_name':tag,'name':'Private edition '+version,'body':notes,
              'html_url':endpoint+'/updates/notes.txt','assets':assets}
    (output/'notes.txt').write_text(notes+'\n','utf-8')
    temporary=output/'latest.json.new'
    temporary.write_text(json.dumps(manifest,ensure_ascii=False,indent=2)+'\n','utf-8')
    temporary.replace(output/'latest.json')
    return manifest


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--game',type=Path,required=True)
    parser.add_argument('--out',type=Path,required=True)
    parser.add_argument('--version',required=True)
    parser.add_argument('--notes',type=Path,required=True)
    parser.add_argument('--key-file',type=Path,required=True)
    args=parser.parse_args()
    manifest=publish(args.game.resolve(),args.out.resolve(),args.version,args.notes.read_text('utf-8-sig'),args.key_file.resolve())
    print('Signed private release '+manifest['tag_name']+' prepared. Copy version files first, latest.json LAST.')
    print('The private signing key was not included in the release.')
