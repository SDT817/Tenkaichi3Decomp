"""Display strings only: preserve network calls, settings keys, format arguments."""
from pathlib import Path
import json
import re

TEXT = {
    'Found a player. Connecting...': '已找到玩家，正在连接…',
    'Searching for a player in this queue...': '正在此队列中搜索玩家…',
    'Searching for %d:%02d more. Leave the window open.': '还将搜索 %d:%02d，请保持窗口开启。',
    'The two games could not reach each other, directly or through the relay. Search again for another player.': '直连和中继均未能连接双方，请重新搜索其他玩家。',
    "The other player's game is a different version. Search again.": '对方游戏版本不同，请重新搜索。',
    'Nobody was searching this queue in the last three minutes. Search again, or try another queue.': '过去三分钟此队列中没有其他玩家。请重新搜索或更换队列。',
    'Search again': '重新搜索', 'Search for a match': '搜索对手',
    'Dragon Net Battle': '龙网对战',
    'Update available. Online servers are unreachable until you update.': '有可用更新，请先更新游戏再连接联机服务器。',
    'You have 0.%d.%d; 0.%d.%d or newer is needed. github.com/z3xox/Tenkaichi3Decomp/releases': '当前版本 0.%d.%d，需要 0.%d.%d 或更新版本。github.com/z3xox/Tenkaichi3Decomp/releases',
    'Update available: release 0.%d.%d.': '发现新版本：0.%d.%d。',
    "Fight a player on another computer. One of you hosts, the other joins with the host's address.": '与另一台电脑上的玩家对战。一人创建房间，另一人通过房间码或房主地址加入。',
    'Player name': '玩家名称', 'Host': '创建房间', 'Quick match': '快速匹配', 'Join': '加入房间',
    'Off (wait for each other)': '关闭（逐帧等待对方）',
    'Up to 2 frames': '最多 2 帧', 'Up to 4 frames': '最多 4 帧', 'Up to 6 frames': '最多 6 帧', 'Up to 8 frames': '最多 8 帧',
    'Use a room code (no port forwarding needed)': '使用房间码（无需端口转发）',
    'You get a short code to tell the other player, and the two games find each other through a\n': '生成一个短房间码，分享给对方后由匹配服务协助双方连接。\n',
    'small matchmaking service. Works with most home routers. Without it you host on a port,\n': '适用于多数家庭路由器。关闭后通过指定端口创建房间，\n',
    'which must be reachable from the other player (port forwarding or a virtual network).': '对方必须能够访问此端口（端口转发或虚拟局域网）。',
    'Port': '端口', 'Rollback': '回滚',
    'With rollback your own moves come out at once and the game corrects itself when the\n': '开启回滚后，本地操作立即响应，收到对方输入后再校正游戏状态。\n',
    "other player's buttons arrive. More frames cope with a slower connection and cost\n": '更高的回滚帧数适合延迟较大的连接，也会消耗更多处理器资源。\n',
    'more processor time. Off: both games wait for each other every frame.': '关闭时，双方每帧等待彼此的输入。',
    'Automatic (from the connection)': '自动（根据连接状况）', 'Input delay': '输入延迟',
    'How long after a press your own move comes out. A slow connection needs more, or the game\n': '设置按下按键到动作生效的等待时间。连接较慢时需要更高的延迟，\n',
    'has to guess too far ahead and stutters. Automatic measures the connection when the match\n': '否则过多预测可能导致卡顿。自动模式在比赛开始时测量连接状况：\n',
    'starts: 1 frame on a good one, more on a slow one.': '连接良好时为 1 帧，连接较慢时增加。',
    'Single battle': '单人对战', 'Team battle': '组队对战',
    'DP battle (10 DP)': 'DP 对战（10 DP）', 'DP battle (15 DP)': 'DP 对战（15 DP）', 'DP battle (20 DP)': 'DP 对战（20 DP）',
    '60 seconds': '60 秒', '90 seconds': '90 秒', '180 seconds': '180 秒', '240 seconds': '240 秒', 'No limit': '不限时',
    'Battle': '对战模式', 'Time limit': '时间限制',
    'How fast the match runs, for both players; the sound keeps its pitch.\n': '设置双方的游戏速度，声音音调保持不变。\n',
    "100%% is the game's own speed. %d%% is the competitive standard, and what\n": '100%% 为原版速度；%d%% 为竞技标准，\n',
    'quick matches run at.\n': '快速匹配也使用此速度。\n',
    'With a player on 0.1.29 only 100%% and 120%% are possible, with an older\n': '与 0.1.29 版本联机时仅支持 100%% 或 120%%；\n',
    'release only 100%%.': '与更早版本联机时仅支持 100%%。',
    "The host's choices apply to both players.": '房主设置对双方生效。',
    'Be matched with whoever is searching the same queue. All quick matches have no time limit and run at %d%% speed.': '匹配正在搜索同一队列的玩家。快速匹配不限时，使用 %d%% 游戏速度。',
    '%s   (%d searching)###q%d': '%s   （%d 人搜索中）###q%d',
    'The two games connect to each other directly when they can, as in most online fighting': '与多数联机格斗游戏一样，条件允许时双方直接连接。',
    "games: a player who inspects their own network traffic can see the other's address.": '查看网络流量的玩家可以看到对方地址。',
    'Room code': '房间码', 'Paste': '粘贴', "or, without a code, the host's address and port:": '或不使用房间码，填写房主地址和端口：',
    "Host's address": '房主地址', 'Room code:': '房间码：', 'Copy': '复制', 'Copied': '已复制',
    'Copy the code, to paste it to the other player.': '复制房间码后分享给对方。',
    'Tell the other player this code. Waiting for them to join...': '请将房间码告诉对方，等待加入…',
    'The other player has joined. Connecting...': '对方已加入，正在连接…',
    'Found the room. Connecting to the host...': '已找到房间，正在连接房主…', 'Getting a room code...': '正在获取房间码…', 'Looking for the room...': '正在查找房间…',
    'Waiting for the other player on port %s...': '正在端口 %s 等待对方连接…',
    'A player with a different version of the game is trying to join. Both need the same release.': '有游戏版本不同的玩家尝试加入。双方需要使用相同版本。',
    'Looking for %s...': '正在连接 %s…',
    'The two games could not reach each other, directly or through the relay. ': '直连和中继均未能连接双方。',
    'Hosting on a port (with port forwarding or a virtual network such as Tailscale) still works.': '仍可使用指定端口创建房间（端口转发，或 Tailscale 等虚拟局域网）。',
    'Host a match': '创建对战', 'Join the match': '加入对战', 'Back': '返回',
    "The host's game is a different version. Both players need the same release.": '房主游戏版本不同。双方需要使用相同版本。',
    'That port cannot be used (another program has it?).': '此端口无法使用，可能已被其他程序占用。', 'That address is not known.': '无法解析该地址。',
    'When you are connected the game switches to the match: both players get the same roster,': '连接后自动进入对战，双方使用相同且全部解锁的角色列表。',
    'with everything unlocked, and your own save is left alone. Leaving the match brings you': '个人存档保持不变。退出对战后返回之前的游戏状态。',
    "back to where you were. The host's controls also work the menus.": '房主的控制设置也用于操作联机菜单。',
    'End an online match on a desync': '发生不同步时结束联机对战',
    'The two games compare what they compute. Off: when they no longer agree you are told, and the match\n': '双方会比较计算结果。关闭时，不同​​步会显示提示，但比赛继续\n'.replace('\u200b', ''),
    'goes on (the two screens may then show different fights). On: the match ends there.': '（双方画面可能不同）；开启时，发生不同步就结束比赛。',
    'A trigger counts as pressed from %d%% on. The game is told pressed or not, nothing between.': '扳机超过 %d%% 时视为按下。游戏只区分按下和松开，不读取中间压力值。',
    'ping %d ms%s': '延迟 %d 毫秒%s', ' (relay)': '（中继）', 'ping ...': '延迟 …',
    'rollbacks %d/s, %.1f frames': '回滚 %d 次/秒，%.1f 帧', 'rollback off': '回滚已关闭',
    'waited %d ms/s (%d times)': '等待 %d 毫秒/秒（%d 次）', 'delay %d%s, rollback up to %d': '输入延迟 %d%s，最多回滚 %d 帧', ' (auto)': '（自动）',
    'desync since frame %d': '从第 %d 帧起不同步', 'Chat (Tab)': '聊天（Tab）', 'Mute': '静音',
    'Drag anywhere to move the chat window. Click a line to copy it.': '拖动任意位置移动聊天窗口，点击一行复制文字。', 'Click to copy': '点击复制',
    '1 line/s: Enter to send': '每秒限一条：Enter 发送', 'Enter: send   Esc/Tab: close   Ctrl+V: paste': 'Enter 发送   Esc/Tab 关闭   Ctrl+V 粘贴',
}
for n in range(7): TEXT[f'{n} frame' + ('' if n == 1 else 's')] = f'{n} 帧'

def main():
    path = Path(__file__).resolve().parents[1] / 'port/src/gs/ui.cpp'
    text = path.read_text(encoding='utf-8')
    # Exact literal substitution leaves all tokens outside strings unchanged.
    counts = {key: 0 for key in TEXT}
    def replace(match):
        value = json.loads(match.group())
        if value not in TEXT: return match.group()
        counts[value] += 1
        return json.dumps(TEXT[value], ensure_ascii=False)
    text = re.sub(r'"(?:\\.|[^"\\])*"', replace, text)
    path.write_text(text, encoding='utf-8', newline='\n')
    assert not [m.group() for m in re.finditer(r'"(?:\\.|[^"\\])*"', text) if json.loads(m.group()) in TEXT]
    print(f'Translated {sum(counts.values())} UI literals; network statements unchanged.')

if __name__ == '__main__': main()
