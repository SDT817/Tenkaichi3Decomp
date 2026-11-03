/*
 * The player's settings, kept between runs in a small text file of `name=number` lines:
 *
 *     bt3_settings.txt in the current directory, or the path in $BT3_SETTINGS (an empty $BT3_SETTINGS: no file)
 *
 * The settings overlay (port/src/gs/gs_gpu.c) writes it whenever a setting changes. At start an environment
 * variable (BT3_SCALE, BT3_ASPECT, ...) still wins over the file, so a single run can be started differently.
 * Names: scale, aspect_milli, fullscreen, fx_off, glow, music, effects, voices, stage_sounds, hud_layout, game_speed, music_follows_speed, display; the bindings of port/src/gs/gs_input.c
 * (key_p1_cross = an SDL scancode, pad_p1_cross = a controller button, padslot_p1 = which controller,
 * deadzone_p1_ls / deadzone_p1_rs = a stick's deadzone, vibration_p1 and vibration_p1_strength).
 */
#include <pthread.h>
#include <limits.h>
#include <stdint.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>

static struct Setting { char name[24]; int value; } *sSet;
static int sCapacity;
/* The few settings that are text (online name, menu language): `name="text"` in the file, after the numbers. A
   release from before these reads past such a line. */
static struct TextSetting { char name[24]; char value[64]; } *sText;
static int sTextCount, sTextCapacity;
static int sLoadFailed;
static int sDirty;
static int sCount;
static pthread_once_t sOnce = PTHREAD_ONCE_INIT;
static pthread_mutex_t sLock = PTHREAD_MUTEX_INITIALIZER;

static const char *path(void) {
    const char *p = getenv("BT3_SETTINGS");
    return p == NULL ? "bt3_settings.txt" : p[0] == '\0' ? NULL : p;
}

/* Old binding files can contain many more entries than the current UI uses. Grow
   both tables on demand; a numeric table must not stop the trailing text reads. */
static void *reserve(void *items, size_t width, int used, int *capacity) {
    void *p;
    int n;

    if (used < *capacity) return items;
    if (*capacity > INT_MAX / 2) return NULL;
    n = *capacity != 0 ? *capacity * 2 : 32;
    if ((size_t)n > SIZE_MAX / width) return NULL;
    p = realloc(items, (size_t)n * width);
    if (p != NULL) *capacity = n;
    else fprintf(stderr, "bt3: could not allocate settings table\n");
    return p;
}

static void load(void) {
    char line[128], name[24];
    int value;
    FILE *fp = path() != NULL ? fopen(path(), "r") : NULL;

    while (fp != NULL && fgets(line, sizeof(line), fp) != NULL) {
        char text[64];
        if (sscanf(line, " %23[a-z0-9_]=\"%63[^\"\n]", name, text) == 2) {
            struct TextSetting *p = reserve(sText, sizeof(*sText), sTextCount, &sTextCapacity);
            if (p == NULL) { sLoadFailed = 1; break; }
            sText = p;
            strcpy(sText[sTextCount].name, name);
            strcpy(sText[sTextCount++].value, text);
        } else if (sscanf(line, " %23[a-z0-9_]=%d", name, &value) == 2) {
            struct Setting *p = reserve(sSet, sizeof(*sSet), sCount, &sCapacity);
            if (p == NULL) { sLoadFailed = 1; break; }
            sSet = p;
            strcpy(sSet[sCount].name, name);
            sSet[sCount++].value = value;
        }
    }
    if (fp != NULL) {
        fclose(fp);
    }
}

/* The saved value of a setting, or `def` when the file does not have it. */
int Port_Setting(const char *name, int def) {
    int i, v = def;

    pthread_once(&sOnce, load);
    pthread_mutex_lock(&sLock);
    for (i = 0; i < sCount; i++) {
        if (strcmp(sSet[i].name, name) == 0) {
            v = sSet[i].value;
        }
    }
    pthread_mutex_unlock(&sLock);
    return v;
}

/* Stores a setting; Port_SettingsWrite puts the changes into the file. */
void Port_SettingSave(const char *name, int value) {
    int i;

    pthread_once(&sOnce, load);
    pthread_mutex_lock(&sLock);
    for (i = 0; i < sCount && strcmp(sSet[i].name, name) != 0; i++) {
    }
    if (i == sCount) {
        struct Setting *p = reserve(sSet, sizeof(*sSet), sCount, &sCapacity);
        if (p == NULL) { pthread_mutex_unlock(&sLock); return; }
        sSet = p;
        snprintf(sSet[sCount].name, sizeof(sSet[0].name), "%s", name);
        sSet[sCount++].value = 0;
        sDirty = 1;
    }
    if (sSet[i].value != value) {
        sSet[i].value = value;
        sDirty = 1;
    }
    pthread_mutex_unlock(&sLock);
}

/* A saved text setting copied into out (size bytes), or `def` when the file does not have it. */
void Port_SettingText(const char *name, const char *def, char *out, int size) {
    int i;

    pthread_once(&sOnce, load);
    pthread_mutex_lock(&sLock);
    snprintf(out, (size_t)size, "%s", def);
    for (i = 0; i < sTextCount; i++) {
        if (strcmp(sText[i].name, name) == 0) {
            snprintf(out, (size_t)size, "%s", sText[i].value);
        }
    }
    pthread_mutex_unlock(&sLock);
}

/* Stores a text setting (a double quote or a line break in it becomes an apostrophe or a space: the file's form). */
void Port_SettingTextSave(const char *name, const char *value) {
    char clean[64];
    int i;

    snprintf(clean, sizeof(clean), "%s", value);
    for (i = 0; clean[i] != '\0'; i++) {
        clean[i] = clean[i] == '"' ? '\'' : clean[i] == '\n' || clean[i] == '\r' ? ' ' : clean[i];
    }
    pthread_once(&sOnce, load);
    pthread_mutex_lock(&sLock);
    for (i = 0; i < sTextCount && strcmp(sText[i].name, name) != 0; i++) {
    }
    if (i == sTextCount) {
        struct TextSetting *p = reserve(sText, sizeof(*sText), sTextCount, &sTextCapacity);
        if (p == NULL) { pthread_mutex_unlock(&sLock); return; }
        sText = p;
        snprintf(sText[i].name, sizeof(sText[i].name), "%s", name);
        sText[i].value[0] = '\0';
        sTextCount++;
        sDirty = 1;
    }
    if (strcmp(sText[i].value, clean) != 0) {
        strcpy(sText[i].value, clean);
        sDirty = 1;
    }
    pthread_mutex_unlock(&sLock);
}

void Port_SettingsWrite(void) {
    FILE *fp;
    int i;

    pthread_mutex_lock(&sLock);
    fp = sDirty && !sLoadFailed && path() != NULL ? fopen(path(), "w") : NULL;
    if (fp != NULL) {
        for (i = 0; i < sCount; i++) {
            fprintf(fp, "%s=%d\n", sSet[i].name, sSet[i].value);
        }
        for (i = 0; i < sTextCount; i++) {
            fprintf(fp, "%s=\"%s\"\n", sText[i].name, sText[i].value);
        }
        fclose(fp);
    }
    sDirty = 0;
    pthread_mutex_unlock(&sLock);
}
