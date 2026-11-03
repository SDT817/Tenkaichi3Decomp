// Included inside OnlineLobby's private namespace: uses the existing HTTP worker
// and INI helpers. Directory requests never carry room or battle credentials.
std::string directoryUrl = "http://127.0.0.1:8788", directoryKey, directoryError, directoryAdminName;
Value directoryState;
Job *directoryJob = nullptr;
Uint64 directoryNext = 0;
bool directoryLoaded = false, directoryEnabled = true, directoryAuthenticated = false;
bool roomSettingsReload = true;
std::string issuedAdminKey, directoryQueuedOp, directoryQueuedFields, directoryInfo;

std::string directoryFile(const char *name) {
    std::string path = configFile();
    return path.substr(0, path.find_last_of("/\\")+1) + name;
}
bool directoryWrite(const char *name, const std::string& text) {
    std::string path = directoryFile(name), temp = path+".tmp";
    SDL_IOStream *f = SDL_IOFromFile(temp.c_str(), "wb");
    if (!f) return false;
    bool ok = SDL_WriteIO(f, text.data(), text.size()) == text.size();
    ok = SDL_CloseIO(f) && ok;
    return ok && SDL_RenamePath(temp.c_str(), path.c_str());
}
void directoryLoad() {
    if (directoryLoaded) return;
    directoryLoaded = true;
    for (const char *file : {"bt3_server_directory.ini", "bt3_directory_admin.ini"}) {
        size_t n = 0; void *raw = SDL_LoadFile(directoryFile(file).c_str(), &n);
        if (raw && n < 4096) {
            auto ini = DolphinProfile::Load(std::string((char *)raw, n));
            if (std::string(file) == "bt3_server_directory.ini") {
                if (urlValid(ini["Directory"]["URL"])) directoryUrl = ini["Directory"]["URL"];
                directoryEnabled = ini["Directory"]["Enabled"] != "0";
            } else if (ini["Admin"]["URL"] == directoryUrl && ini["Admin"]["Key"].size() == 64)
                directoryKey = ini["Admin"]["Key"];
        }
        SDL_free(raw);
    }
}
bool directoryBusy() {
    return !directoryQueuedOp.empty() || (directoryJob && directoryJob->op != "list");
}
bool directorySend(const std::string& op, const std::string& fields = "") {
    if (!urlValid(directoryUrl)) return false;
    if (directoryJob) {
        if (directoryJob->op != "list" || !directoryQueuedOp.empty() || op == "list") return false;
        directoryQueuedOp = op; directoryQueuedFields = fields; return true;
    }
    Job *j = new Job;
    SDL_SetAtomicInt(&j->done, 0);
    j->url = directoryUrl+"/directory/v1/request"; j->op = op;
    j->access = op == "list" ? "" : directoryKey;
    j->body = "{\"op\":"+Quote(op)+fields+"}";
    SDL_Thread *t = SDL_CreateThread(request, "bt3-directory-http", j);
    if (!t) { delete j; directoryError = "无法启动目录请求。"; return false; }
    directoryJob = j; SDL_DetachThread(t);
    return true;
}
bool directoryRename(const Favorite& f, const char *name) {
    if (f.directory.empty() || f.url != directoryUrl || directoryKey.empty()) return false;
    return directorySend("rename",",\"id\":"+Quote(f.directory)+",\"url\":"+Quote(f.url)+",\"name\":"+Quote(name));
}
void directoryMerge(const Value& answer) {
    if (!token.empty()) return;
    std::string previous = favorites[selected].url;
    std::vector<std::string> ids;
    for (const auto& s : answer["servers"].array) if (s["enabled"].yes()) ids.push_back(s["id"].str());
    favorites.erase(std::remove_if(favorites.begin(), favorites.end(), [&](const Favorite& f) {
        return !f.personal && std::find(ids.begin(), ids.end(), f.directory) == ids.end();
    }), favorites.end());
    for (const auto& s : answer["servers"].array) {
        std::string u = s["url"].str(), n = s["name"].str(), id = s["id"].str();
        if (!s["enabled"].yes() || !urlValid(u) || !plain(n,64) || !plain(id,32)) continue;
        auto it = std::find_if(favorites.begin(), favorites.end(), [&](const Favorite& f) { return f.url == u || (!f.directory.empty() && f.directory == id); });
        if (it == favorites.end() && favorites.size() < 80) favorites.push_back({n,u,"","",id,false});
        else if (it != favorites.end()) {
            if (it->url != u) { it->access.clear(); it->room.clear(); } // never send an old key to a replaced endpoint
            if (!it->personal) it->name = n;
            it->url = u; it->directory = id;
        }
    }
    if (favorites.empty()) favorites.push_back({"本机演示大厅","http://127.0.0.1:8787","",""});
    selected = 0;
    for (size_t i=0; i<favorites.size(); ++i) if (favorites[i].url == previous) selected = (int)i;
    if (favorites[selected].url != previous) { rooms.clear(); serverName.clear(); nextPoll = 0; }
    save();
}
void directoryTick(bool visible) {
    directoryLoad();
    if (directoryJob && SDL_GetAtomicInt(&directoryJob->done) && !job) {
        Job *j = directoryJob; directoryJob = nullptr;
        if (j->url != directoryUrl+"/directory/v1/request") { delete j; directoryNext = 0; return; }
        Value answer;
        if (!j->success || !OnlineJson::Parse(j->reply, answer) || !answer["ok"].yes()) {
            directoryInfo.clear();
            directoryError = j->success ? answer["error"].str("目录数据无效。") : "目录暂时无法连接，仍可使用已保存的服务器。";
            if (j->op == "whoami") directoryAuthenticated = false;
        } else {
            directoryError.clear();
            if (j->op == "whoami") {
                directoryAuthenticated = true; directoryState = answer;
                roomSettingsReload = true;
                directoryAdminName = answer["admin"]["name"].str();
                directoryWrite("bt3_directory_admin.ini", "[Admin]\nURL = "+directoryUrl+"\nKey = "+directoryKey+"\n");
            } else if (j->op == "list") {
                if (answer["api"].integer() == 1 && answer["servers"].array.size() <= 64) directoryMerge(answer);
                else directoryError = "服务器目录版本或条目数量不受支持。";
            } else {
                if (j->op == "add_admin") issuedAdminKey = answer["key"].str();
                if (j->op == "rename" || j->op == "publish") {
                    if (j->op == "rename") {
                        Value sent;
                        if (OnlineJson::Parse(j->body,sent))
                            for (auto& f : favorites) if (f.directory == sent["id"].str() && f.url == sent["url"].str()) f.personal = false;
                    }
                    directoryMerge(answer); directoryInfo = "服务器名称与目录设置已保存。";
                }
                if (j->op == "save_room" || j->op == "rename_room" || j->op == "add_room") {
                    directoryInfo = "房间设置已保存，服务重启后保留。"; roomSettingsReload = true; nextPoll = 0;
                }
                directorySend("whoami");
            }
        }
        directoryNext = SDL_GetTicks() + (directoryError.empty() ? 30000 : 5000);
        delete j;
    }
    if (!directoryJob && !directoryQueuedOp.empty()) {
        std::string op = directoryQueuedOp, fields = directoryQueuedFields;
        directoryQueuedOp.clear(); directoryQueuedFields.clear(); directorySend(op, fields);
    } else if (visible && directoryEnabled && !directoryJob && SDL_GetTicks() >= directoryNext) directorySend("list");
}
void directoryRooms() {
    const auto& settings = directoryState["room_settings"];
    const auto& list = settings["rooms"].array;
    if (list.empty()) {
        ImGui::TextDisabled("房间规则管理需要配套的新版服务端。");
        return;
    }
    const auto& server = favorites[selected];
    if (server.url != directoryUrl || server.directory != settings["server"].str()) {
        ImGui::TextDisabled("请选择此目录管理的服务器，再设置房间规则。");
        return;
    }
    static std::string id;
    static int battle = 0, time = 4, speed = 100;
    static char roomName[96] = {}, newRoomName[96] = {};
    auto it = std::find_if(list.begin(), list.end(), [&](const Value& r) { return r["id"].str() == id; });
    if (it == list.end()) { it = list.begin(); roomSettingsReload = true; }
    if (roomSettingsReload) {
        id = (*it)["id"].str(); const auto& rules = (*it)["rules"];
        SDL_strlcpy(roomName, (*it)["name"].str().c_str(), sizeof(roomName));
        battle = rules["battle"].integer(); time = rules["time"].integer(4); speed = rules["speed"].integer(100);
        roomSettingsReload = false;
    }
    ImGui::Separator(); ImGui::TextUnformatted("房间管理");
    if (ImGui::BeginCombo("房间", (*it)["name"].str().c_str())) {
        for (const auto& r : list) if (ImGui::Selectable(r["name"].str().c_str(), r["id"].str() == id)) {
            id = r["id"].str(); roomSettingsReload = true;
        }
        ImGui::EndCombo();
    }
    static const char *battles[] = {"单人", "组队", "10 DP", "15 DP", "20 DP"};
    static const char *times[] = {"60 秒", "90 秒", "180 秒", "240 秒", "不限时"};
    ImGui::Combo("游戏模式", &battle, battles, 5);
    ImGui::Combo("时限", &time, times, 5);
    ImGui::SliderInt("游戏速度", &speed, 100, 150, "%d%%");
    if (ImGui::Button("恢复 100%")) speed = 100;
    ImGui::SameLine();
    if (ImGui::Button("重新读取规则")) { roomSettingsReload = true; directorySend("whoami"); }
    ImGui::BeginDisabled((*it)["phase"].str() != "idle" || roomSettingsReload);
    ImGui::InputText("房间名称", roomName, sizeof(roomName));
    if (ImGui::Button("保存房间名称"))
        directorySend("rename_room",",\"server\":"+Quote(server.directory)+",\"room\":"+Quote(id)+",\"name\":"+Quote(roomName));
    if (ImGui::Button("保存房间规则"))
        directorySend("save_room",",\"server\":"+Quote(server.directory)+",\"room\":"+Quote(id)+
            ",\"rules\":{\"battle\":"+std::to_string(battle)+",\"time\":"+std::to_string(time)+",\"speed\":"+std::to_string(speed)+"}");
    ImGui::EndDisabled();
    ImGui::TextDisabled("按房间保存，服务重启后保留；连接或对战期间不能修改。");
    ImGui::InputText("新房间名称", newRoomName, sizeof(newRoomName));
    ImGui::BeginDisabled(list.size() >= 32 || !plain(newRoomName, 64));
    if (ImGui::Button("新增房间"))
        directorySend("add_room",",\"server\":"+Quote(server.directory)+",\"name\":"+Quote(newRoomName));
    ImGui::EndDisabled();
    ImGui::TextDisabled("新房间默认 100% 速度；添加后可在上方选择并设置规则。");
}
void directoryDraw() {
    directoryLoad();
    static char url[224] = {}, key[65] = {}, id[33] = "friends-01", name[96] = {}, endpoint[224] = {};
    static char adminId[33] = {}, adminName[96] = {};
    static bool locked = false;
    ImGui::BeginDisabled(!token.empty() || busy() || directoryBusy() || connecting || launched);
    if (ImGui::Button("刷新服务器目录")) { directoryNext = 0; }
    ImGui::SameLine();
    if (ImGui::Button("目录设置")) { SDL_strlcpy(url,directoryUrl.c_str(),sizeof(url)); ImGui::OpenPopup("服务器目录设置"); }
    ImGui::SameLine();
    if (ImGui::Button("管理员")) { SDL_strlcpy(key,directoryKey.c_str(),sizeof(key)); ImGui::OpenPopup("目录管理员"); if (!directoryKey.empty()) directorySend("whoami"); }
    ImGui::EndDisabled();
    if (!directoryError.empty()) ImGui::TextWrapped("%s",directoryError.c_str());
    if (ImGui::BeginPopupModal("服务器目录设置",nullptr,ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::InputText("目录地址",url,sizeof(url));
        ImGui::Checkbox("自动同步目录",&directoryEnabled);
        if (ImGui::Button("保存")) {
            std::string u = url; while (!u.empty() && u.back() == '/') u.pop_back();
            if (urlValid(u) && !directoryBusy()) {
                if (u != directoryUrl) { directoryAuthenticated = false; directoryKey.clear(); }
                directoryUrl = u; directoryNext = 0;
                directoryWrite("bt3_server_directory.ini","[Directory]\nURL = "+u+"\nEnabled = "+(directoryEnabled ? "1" : "0")+"\n");
                ImGui::CloseCurrentPopup();
            } else directoryError = "请输入有效目录地址，并等待当前请求结束。";
        }
        ImGui::SameLine(); if (ImGui::Button("取消")) ImGui::CloseCurrentPopup();
        ImGui::EndPopup();
    }
    if (ImGui::BeginPopupModal("目录管理员",nullptr,ImGuiWindowFlags_AlwaysAutoResize)) {
        ImGui::Text("目录：%s",directoryUrl.c_str());
        ImGui::InputText("管理员密钥",key,sizeof(key),ImGuiInputTextFlags_Password);
        ImGui::BeginDisabled(directoryBusy());
        if (ImGui::Button("登录")) { directoryKey = key; directorySend("whoami"); }
        ImGui::SameLine();
        if (ImGui::Button("退出管理")) {
            directoryAuthenticated = false; directoryKey.clear(); key[0] = 0; issuedAdminKey.clear();
            directoryWrite("bt3_directory_admin.ini","[Admin]\n");
        }
        if (directoryAuthenticated) {
            ImGui::Text("当前管理员：%s",directoryAdminName.c_str());
            directoryRooms();
            ImGui::Separator();
            if (ImGui::Button("填入当前服务器")) {
                const auto& f = favorites[selected];
                SDL_strlcpy(name,f.name.c_str(),sizeof(name)); SDL_strlcpy(endpoint,f.url.c_str(),sizeof(endpoint));
                if (!f.directory.empty()) SDL_strlcpy(id,f.directory.c_str(),sizeof(id));
                locked = !f.access.empty();
            }
            ImGui::InputText("服务器标识",id,sizeof(id)); ImGui::InputText("显示名称",name,sizeof(name));
            ImGui::InputText("服务器地址",endpoint,sizeof(endpoint)); ImGui::Checkbox("需要房间访问口令",&locked);
            if (ImGui::Button("发布／更新服务器"))
                directorySend("publish",",\"id\":"+Quote(id)+",\"name\":"+Quote(name)+",\"url\":"+Quote(endpoint)+",\"locked\":"+(locked ? "true" : "false"));
            for (const auto& s : directoryState["servers"].array) {
                ImGui::PushID(s["id"].str().c_str());
                ImGui::Text("%s · %s",s["name"].str().c_str(),s["enabled"].yes() ? "已发布" : "已下架");
                ImGui::SameLine(); if (ImGui::Button("下架")) directorySend("unpublish",",\"id\":"+Quote(s["id"].str()));
                ImGui::SameLine(); if (ImGui::Button("删除")) directorySend("remove",",\"id\":"+Quote(s["id"].str()));
                ImGui::PopID();
            }
            ImGui::Separator();
            ImGui::InputText("新管理员标识",adminId,sizeof(adminId)); ImGui::InputText("新管理员名称",adminName,sizeof(adminName));
            if (ImGui::Button("添加管理员")) directorySend("add_admin",",\"id\":"+Quote(adminId)+",\"name\":"+Quote(adminName));
            if (!issuedAdminKey.empty()) {
                ImGui::TextUnformatted("新凭据只在本次显示，请交给指定管理员。");
                if (ImGui::Button("复制新管理员密钥")) SDL_SetClipboardText(issuedAdminKey.c_str());
            }
            for (const auto& a : directoryState["admins"].array) {
                ImGui::PushID(a["id"].str().c_str());
                ImGui::Text("%s · %s",a["name"].str().c_str(),a["active"].integer() ? "有效" : "已撤销");
                ImGui::SameLine(); if (ImGui::Button("撤销")) directorySend("revoke_admin",",\"id\":"+Quote(a["id"].str()));
                ImGui::PopID();
            }
        }
        ImGui::EndDisabled();
        if (!directoryError.empty()) ImGui::TextWrapped("%s",directoryError.c_str());
        if (!directoryInfo.empty()) ImGui::TextWrapped("%s",directoryInfo.c_str());
        if (ImGui::Button("关闭")) { ImGui::CloseCurrentPopup(); directoryNext = 0; }
        ImGui::EndPopup();
    }
}
