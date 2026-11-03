/* Exercise the real settings store across fresh processes, without the game. */
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

int Port_Setting(const char *name, int def);
void Port_SettingSave(const char *name, int value);
void Port_SettingText(const char *name, const char *def, char *out, int size);
void Port_SettingTextSave(const char *name, const char *value);
void Port_SettingsWrite(void);
#define TEST_ENTRIES 5000
#define TEST_TEXTS 64

static void menu_save(void) {
    Port_SettingSave("skip_logos", 1);
    Port_SettingSave("skip_intro", 1);
    Port_SettingSave("menus_43", 1);
    Port_SettingSave("ui_scale", 125);
    Port_SettingTextSave("menu_lang", "zh-CN");
    Port_SettingsWrite();
}

int main(int argc, char **argv) {
    int i;
    char name[24], language[64], expected[64];

    if (argc != 2) return 2;
    if (!strcmp(argv[1], "save")) {
        menu_save();
    } else if (!strcmp(argv[1], "inspect")) {
        Port_SettingText("menu_lang", "missing", language, sizeof(language));
        printf("{\"language_loaded\":%d,\"skip_logos\":%d,\"skip_intro\":%d,"
               "\"menus_43\":%d,\"ui_scale\":%d}\n",
               !strcmp(language, "zh-CN"), Port_Setting("skip_logos", -1),
               Port_Setting("skip_intro", -1), Port_Setting("menus_43", -1),
               Port_Setting("ui_scale", -1));
    } else if (!strcmp(argv[1], "fill")) {
        for (i = 0; i < TEST_ENTRIES; i++) {
            snprintf(name, sizeof(name), "test_slot_%03d", i);
            Port_SettingSave(name, i * 3 + 1);
        }
        for (i = 0; i < TEST_TEXTS; i++) {
            snprintf(name, sizeof(name), "test_text_%03d", i);
            snprintf(expected, sizeof(expected), "text-value-%03d", i);
            Port_SettingTextSave(name, expected);
        }
        menu_save();
    } else if (!strcmp(argv[1], "verify")) {
        for (i = 0; i < TEST_ENTRIES; i++) {
            snprintf(name, sizeof(name), "test_slot_%03d", i);
            if (Port_Setting(name, -1) != i * 3 + 1) {
                fprintf(stderr, "Setting %s did not survive restart\n", name);
                return 1;
            }
        }
        for (i = 0; i < TEST_TEXTS; i++) {
            snprintf(name, sizeof(name), "test_text_%03d", i);
            snprintf(expected, sizeof(expected), "text-value-%03d", i);
            Port_SettingText(name, "missing", language, sizeof(language));
            if (strcmp(language, expected)) return 1;
        }
        Port_SettingText("menu_lang", "missing", language, sizeof(language));
        if (strcmp(language, "zh-CN")) return 1;
        puts("5000 numeric settings, 64 text settings and trailing language survived restart");
    } else return 2;
    return 0;
}
