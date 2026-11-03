// Display-only translations for messages returned by the unchanged net code.
#pragma once
#include <cstring>

static const char *UiZh(const char *text) {
    static const char *const messages[][2] = {
        {"Modified game data: this build supports the original USA disc. Glitches are expected.", "检测到修改过的游戏数据：本程序基于原版美版镜像，修改数据可能导致异常。"},
        {"This computer's clock is wrong: set its date and time, then try again.", "本机时钟不正确，请校准日期和时间后重试。"},
        {"The matchmaking service does not take lobbies yet. A lobby by address (a port) still works.", "匹配服务尚不支持大厅，仍可通过地址和端口加入。"},
        {"The selected server's TURN relay could not be allocated.", "无法分配所选服务器的战斗中继，请稍后重试。"},
        {"Too many wrong codes from this address, or too many joining that lobby at once; try again soon.", "房间码错误次数过多，或同时加入大厅的人数过多，请稍后重试。"},
        {"The lobby's room code has run out (the matchmaking service no longer knows it). Members by address can still come.", "大厅的房间码已过期，其他玩家仍可通过地址加入。"},
        {"This computer's address could not be found (no network?).", "无法获取本机地址，请检查网络连接。"},
        {"The matchmaking service could not be reached (is the network up?).", "无法连接匹配服务，请检查网络连接。"},
        {"Update available. Online servers are unreachable until you update.", "有可用更新，请先更新游戏再连接联机服务器。"},
        {"Quick match needs an official release of the game.", "快速匹配需要官方发布版本。"},
        {"Room codes need an official release of the game. Playing by address still works.", "房间码需要官方发布版本，仍可通过 IP 地址联机。"},
        {"Too many searches from this address; try again in a few minutes.", "此地址搜索过于频繁，请几分钟后重试。"},
        {"The matchmaking service does not know quick match yet.", "匹配服务尚不支持快速匹配。"},
        {"The matchmaking service gave no answer.", "匹配服务没有返回结果。"},
        {"Too many rooms from this address; try again in a few minutes.", "此地址创建房间过多，请几分钟后重试。"},
        {"The matchmaking service gave no room.", "匹配服务未能创建房间。"},
        {"Nobody joined: the room code has run out. Host again for a new one.", "无人加入，房间码已过期。请重新创建房间。"},
        {"The host's game is a different version: both players need the same release.", "房主游戏版本不同，双方需要使用相同版本。"},
        {"Someone has already joined that room.", "已有其他玩家加入该房间。"},
        {"No room with that code (codes last ten minutes).", "未找到该房间码，房间码有效期为十分钟。"},
        {"Too many wrong codes from this address; try again in an hour.", "此地址输入错误房间码过多，请一小时后重试。"},
        {"The matchmaking could not be started.", "无法启动匹配。"},
        {"Your game data and the other player's are not the same (a modified disc image or mods on one side): an online match needs the same on both.",
         "双方游戏数据不同，可能使用了不同的修改镜像或模组。联机需要双方数据相同。"},
    };
    for (const auto& message : messages) { if (!strcmp(text, message[0])) { return message[1]; } }
    return text;
}
