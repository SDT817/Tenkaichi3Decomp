#pragma once
#include <string>
namespace OnlinePing {
void Start(const std::string& host, int port, const std::string& key);
void Stop();
bool Idle();
}
