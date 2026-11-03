"""CN2 catalog repairs; the game's exact-match lookup remains authoritative."""
from collections import Counter, defaultdict
from pathlib import Path
import json
import re

ROOT = Path(__file__).resolve().parents[1]


def supplement(english, chosen, candidates, glyphs):
    groups = defaultdict(list)
    for key, row in english['labels'].items():
        groups[row['original']].append(key)
    repaired = []
    # Identical English role names and sentences must agree for the existing
    # unambiguous fallback. Prefer the character-select wording for names, then
    # the most common translated wording. Never turn numbers into dialogue.
    for original, keys in groups.items():
        options = [chosen[k] for k in keys if chosen[k][0] != 'original']
        if len(set(chosen[k] for k in keys)) < 2 or not options or not re.search('[A-Za-z]', original):
            continue
        canonical = next((chosen[k] for k in keys if k.startswith('pzs3us1/00448/2/43/') and chosen[k][0] != 'original'),
                         Counter(options).most_common(1)[0][0])
        for k in keys:
            chosen[k] = canonical
        repaired.append({'original': original, 'ids': keys, 'kind': canonical[0], 'text': canonical[1]})

    skills = json.loads((ROOT / 'cn2-skill-candidates.json').read_text(encoding='utf-8'))
    overrides = {
        'Rushing Technique': '连击技巧', 'Special Attack': '必杀技',
        'Signature Technique': '固有技巧', 'Combo': '连招',
        'Heavy Finish': '重击终结', 'Rolling Hammer': '旋转重锤',
        'Blaster Wave': '爆破冲击波', 'Rush Ki Wave': '连击气功波',
        'Lift Strike': '上挑攻击', 'Ground Slash': '下劈攻击',
        'Auto-Blaster Wave Counter': '爆破冲击波反击', 'Chargeable': '可蓄力',
        'Unblockable Attack': '无法防御的攻击', 'During Rush': '连击过程中',
        'Auto-Heavy Counter': '重击反击', 'Step-In Heavy': '踏步重击',
        'Step-In Lift Strike': '踏步上挑', 'Step-In Ground Slash': '踏步下劈',
        'Step-In Auto-Heavy Counter': '踏步重击反击',
        'Step-In Kiai Cannon': '踏步气合炮', 'Step-In Auto-Counter': '踏步反击',
        'Sway Heavy': '闪身重击', 'Sway Lift Strike': '闪身上挑',
        'Sway Ground Slash': '闪身下劈', 'Step-In Sway': '踏步闪身',
        'Auto-Ki Blast Cannon Counter': '气功炮反击',
        'Step-In Rolling Hammer': '踏步旋转重锤', 'Step-In Flying Kick': '踏步飞踢',
        'Sway Flying Kick': '闪身飞踢', 'Step-In Ki Wave': '踏步气功波',
        'Sway Kiai Cannon': '闪身气合炮', 'Step in Blaster Wave': '踏步爆破冲击波',
        'Sway Rolling Hammer': '闪身旋转重锤',
        '1 additional attack possible in MAX Power mode': '爆气状态可追加一次追击',
        '2 additional attacks possible in MAX Power mode': '爆气状态可追加两次追击',
        '3 additional attacks possible in MAX Power mode': '爆气状态可追加三次追击',
        'Angry Kamehameha': '愤怒龟派气功', 'Begone!': '消失吧！',
        'Counterattack!': '反击！', 'Devilmite Beam': '恶魔光线',
        'Energy Ballet': '能量乱舞', 'Final Revenger': '最终复仇',
        'Final Spirit Cannon': '最终灵魂炮', "Here's a present!": '送你一份礼物！',
        'Hysteric Saiyan Lady': '愤怒的赛亚女战士',
        "I'm A Top-class Warrior!": '我是上级战士！',
        'Kaio-ken': '界王拳', 'Kaio-ken Attack': '界王拳攻击', 'Kapa': '卡帕',
        'Meteor Smash': '流星重击', "Now I'm Mad!": '我生气了！',
        'Partner: Vegeta (End)': '搭档：贝吉塔（后期）', 'Penetrate!': '贯穿！',
        'Super Galick Gun': '超级加力克炮', 'Super Spirit Bomb': '超元气弹',
        'Transformation Limited only': '仅限特定变身', 'Volcano Explosion': '火山爆发',
        'in the stage with Full Moon': '在有满月的场景中',
    }
    added, rejected = [], []
    skill_rows = {k: {'translations': {}, 'sources': []} for k in overrides}
    skill_rows.update(skills)
    for original, row in skill_rows.items():
        if original in overrides:
            kind, text = 'unicode', overrides[original]
        elif original in groups:
            options = [chosen[k] for k in groups[original] if chosen[k][0] != 'original']
            if options:
                kind, text = Counter(options).most_common(1)[0][0]
            else:
                kind, text = 'iso', Counter(row['translations']).most_common(1)[0][0]
        else:
            kind, text = 'iso', Counter(row['translations']).most_common(1)[0][0]
        text = text.strip().replace('\xa0', ' ')
        missing = {ord(c) for c in text if ord(c) > 127 and ord(c) not in glyphs}
        if kind == 'iso' and (missing or any(0x3040 <= ord(c) <= 0x30ff for c in text)):
            rejected.append({'original': original, 'text': text, 'missing': sorted(missing)})
            continue
        # Script command prefixes and PAD tags are never translated or copied.
        key = f'local/skill-display/{len(added)}'
        english['labels'][key] = {'original': original, 'text': original}
        chosen[key] = (kind, text)
        for existing in groups.get(original, []):
            chosen[existing] = (kind, text)
        added.append({'id': key, 'original': original, 'kind': kind, 'text': text})
    return {'duplicate_English_canonicalized': repaired,
            'skill_display_entries': added, 'unresolved_skill_entries': rejected,
            'script_commands_and_PAD_tags_preserved': True}
