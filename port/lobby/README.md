# 私服大厅 r15 / 官方 0.1.39.1

在 r14 CN8 的官方 0.1.39.1 基线上移植 r13 私服大厅，采用官方协议 6。
保留 CN8 汉化/菜单预热、Wii 逻辑按键与独立配置、I immediate。
大厅 API 2、目录 API 1，固定中继使用现有标准 TURN；服务器不运行游戏。

## 房间与管理员

进房自动准备，两人到齐且全屏/分屏模式一致后，任一玩家可点击开始。
延迟显示玩家与所选服务器之间的 UDP 往返时间。
管理员可新增、改名房间，以及保存模式、时限和速度。新房默认 100%，最多 32 房。
SQLite 的 room_names 表保存名称覆盖和新房定义，room_rules 保留规则覆盖。
启动时合并原配置与数据库定义，不覆盖管理员保存的名称或规则。
改名和改规则要求空闲状态并刷新 epoch，旧开始请求会被拒绝。
新增、改名与开始使用数据库事务；普通玩家或撤销的管理员不能修改。

收藏、目录配置和管理员凭据分别在 bt3_online_servers.ini、bt3_server_directory.ini、
bt3_directory_admin.ini 中；Wii 和普通选项仍使用各自原来的文件。

## 升级部署

已有 IP2626 服务在服务器运行 deploy/Upgrade-Online1391.ps1。
脚本按清单校验、备份应用/配置/数据库，更新房间/目录服务及健康检查工具。
保留 2626、TLS 身份、TURN、管理员、数据库与规则；不重新注册任务或开放端口。
配套客户端使用 Apply-Online1391.ps1，双方和服务端都需升级，旧协议 5 不兼容。
仅 CheckOnly 可在本机验证包，不要在玩家电脑实际运行服务器升级。

## 源码边界

net.c 只有 Port_NetView 的原生双视角显示选择与 r14 不同，其余字节完全相同。
net_match.c/h 三方合并旧私服 transport 快照与新版官方匹配；每个匹配任务持有独立
URL/凭据/socket/代次，强制中继分配失败时拒绝直连降级。
私服 Tick 等待 Port_DataFingerprintNeed 完成后才配置 transport 并启动，避免官方异步
等待时丢失私服凭据。官方 UDP 握手、协议 6、回滚、输入包与数据指纹逻辑保持上游实现。
net_relay.c、net_lobby.c、net_sign.c、state.c、游戏/渲染/输入/汉化实现与 r14 一致。
ui.cpp 只接入私服页和生命周期，官方 Host/Join/Quick 页继续保留。
private_gateway 仅把健康检查的协议版本更新为 6；TLS/IP/签名/有效期检查不变。

## 本机验证

- test_lobby2、test_directory、test_room_settings、test_ping：权限、并发、epoch、重启持久化。
- build_probes.py + test_private_native.py：真实 Caddy/TLS、WinHTTP、原生 ImGui，两个独立
  客户端全屏/分屏多局，目录同步、规则应用、改名/新增、刷新顶点一致及指纹等待。
  此项会话启动/结束钩子为模拟；不会启动游戏。
- test_relay.py 和 test_pion.py：标准 TURN 授权、双向 UDP、ChannelBind、续期与错误凭据。
- build_wire_probe.py + test_wire.py：真实 net.c 的 StartCode/Poll/协议 6 握手，经本机 Pion
  强制中继后双方实际收到并校验数据指纹。指纹内容是固定测试值，战斗入口若调用则 abort。
- private_gateway 的 Go 测试包括 TLS 身份、代理限制和协议 5/6/7 健康检查。
- tools/verify_lobby15_update.py：程序文件夹中实际执行客户端更新、嵌套备份和个人配置保留。

未自动启动游戏或修改远程服务器；远程实战需双方升级后验证。
源码端点、三条逐字节重放验证的补丁和编译/测试证据保存在输出目录 records。
本地独立版本，不提交 GitHub。
