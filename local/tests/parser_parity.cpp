// Compare the imported evaluator with the supplied, unmodified Dolphin parser.
#include <cstdio>
#include <cstdlib>
#include <map>
#include <random>
#include "../../port/third_party/dolphin/InputCommon/ControlReference/ExpressionParser.cpp"
#include "../../port/build/local-tests/original.cpp"
using namespace ciface::Core;
class TestInput : public Device::Input {
    double value;
public:
    explicit TestInput(double v) : value(v) {}
    double GetState() const override { return value; }
};
class TestDevice : public Device {
    TestInput a{0.3}, b{0.7}, c{1.0}, zero{-0.2};
public:
    Device::Input *FindInput(const std::string& name) override {
        return name == "A" ? &a : name == "B" ? &b : name == "C" ? &c : name == "Zero" ? &zero : nullptr;
    }
};
class TestDevices : public DeviceContainer {
    std::shared_ptr<Device> device = std::make_shared<TestDevice>();
public:
    std::shared_ptr<Device> FindDevice(const DeviceQualifier&) const override { return device; }
};
std::mt19937 random_source(10912);
std::string expression(int depth) {
    if (!depth || random_source() % 3 == 0) {
        static const char *atoms[] = {"A", "B", "C", "Zero", "Missing", "`Keyboard:A`", "!B", "!Zero"};
        return atoms[random_source() % 8];
    }
    static const char *ops[] = {" | ", " & ", " + "};
    return "(" + expression(depth - 1) + ops[random_source() % 3] + expression(depth - 1) + ")";
}
int main() {
    TestDevices devices;
    DeviceQualifier default_device; default_device.FromString("Keyboard");
    ciface::ExpressionParser::ControlFinder adapted_finder(devices, default_device, true);
    ciface::OriginalParser::ControlFinder original_finder(devices, default_device, true);
    for (int i = 0; i < 2000; i++) {
        std::string text = i == 0 ? "A | B & C" : i == 1 ? "" : expression(4);
        auto a = ciface::ExpressionParser::ParseExpression(text);
        auto b = ciface::OriginalParser::ParseExpression(text);
        if ((int)a.first != (int)b.first || (bool)a.second != (bool)b.second) return 1;
        if (!a.second) continue;
        a.second->UpdateReferences(adapted_finder); b.second->UpdateReferences(original_finder);
        if (a.second->GetValue() != b.second->GetValue() || a.second->CountNumControls() != b.second->CountNumControls()) {
            fprintf(stderr, "Parity failed: %s\n", text.c_str()); return 1;
        }
    }
    puts("PASS: 2000 expressions identical to the original Dolphin 10912 parser and evaluator");
}
