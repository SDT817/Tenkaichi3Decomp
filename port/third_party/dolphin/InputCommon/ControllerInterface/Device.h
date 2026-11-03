// Local SDL adapter for Dolphin's expression parser; no emulator/core dependencies.
#pragma once
#include <memory>
#include <string>

using ControlState = double;
namespace ciface::Core {
class DeviceQualifier {
    std::string name;
public:
    void FromString(const std::string& text) { name = text; }
    std::string ToString() const { return name; }
};
class Device {
public:
    class Input;
    class Output;
    class Control {
    public:
        virtual ~Control() = default;
        virtual Input* ToInput() { return nullptr; }
        virtual Output* ToOutput() { return nullptr; }
    };
    class Input : public Control {
    public:
        Input* ToInput() override { return this; }
        virtual ControlState GetState() const = 0;
    };
    class Output : public Control {
    public:
        Output* ToOutput() override { return this; }
        virtual void SetState(ControlState) = 0;
    };
    virtual ~Device() = default;
    virtual Input* FindInput(const std::string&) = 0;
    Output* FindOutput(const std::string&) { return nullptr; }
};
class DeviceContainer {
public:
    virtual ~DeviceContainer() = default;
    virtual std::shared_ptr<Device> FindDevice(const DeviceQualifier&) const = 0;
};
}
