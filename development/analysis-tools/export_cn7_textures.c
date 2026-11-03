/* Offline inspection: the port's decoder and archive parser, unchanged. */
#include "../../Tenkaichi3Decomp-WiiLocal-r7-CN6-Perf4/port/src/gs/menu_labels.c"

static const char *prefix;
static void visit(MlBuf data, const char *path, int depth) {
    uint32_t count, i;
    if (ml_is_texture_file(data)) {
        if (!ml_get32(data, 0, &count) || count > 64) return;
        for (i = 0; i < count; i++) {
            MlCtx ctx = {0};
            MlTex tex = {0};
            char name[512];
            if (ml_texture(&ctx, data, i, &tex) > 0) {
                FILE *out;
                snprintf(name, sizeof(name), "%s-%s-%u.rgba", prefix, path, i);
                out = fopen(name, "wb");
                if (out) {
                    fwrite(tex.rgba, 4, (size_t)tex.w * tex.h, out);
                    fclose(out);
                    printf("%s\t%d\t%d\t%016llx\n", name, tex.w, tex.h, (unsigned long long)tex.hash);
                }
            }
            ml_free(&ctx);
        }
        return;
    }
    if (depth >= 4 || !(count = ml_table_count(data))) return;
    for (i = 1; i <= count; i++) {
        char child[120];
        snprintf(child, sizeof(child), "%s-%u", path, i);
        visit(ml_part(data, i), child, depth + 1);
    }
}

int main(int argc, char **argv) {
    FILE *f;
    long size;
    uint8_t *bytes;
    MlBuf data;
    uint32_t count, i;
    if (argc != 3 || !(f = fopen(argv[1], "rb"))) return 2;
    fseek(f, 0, SEEK_END); size = ftell(f); rewind(f);
    if (size <= 0 || size > 64L * 1024 * 1024) return 3;
    bytes = malloc((size_t)size);
    if (!bytes || fread(bytes, 1, (size_t)size, f) != (size_t)size) return 4;
    fclose(f);
    data = (MlBuf){bytes, (size_t)size}; prefix = argv[2];
    count = ml_table_count(data);
    if (!count) {
        size_t n = 0;
        uint8_t *member = ml_member(data, 0, &n);
        if (member) visit((MlBuf){member,n}, "0", 0);
        free(member); free(bytes); return 0;
    }
    for (i = 1; i <= count; i++) {
        size_t n = 0;
        uint8_t *member = ml_member(ml_part(data, i), 0, &n);
        char path[32];
        snprintf(path, sizeof(path), "%u", i);
        if (member) visit((MlBuf){member, n}, path, 0);
        free(member);
    }
    free(bytes);
    return 0;
}

int MenuTranslation_Ensure(void) { abort(); }
int MenuTranslation_Load(const char *d, char *w, size_t n) { abort(); }
const char *MenuTranslation_Text(const char *id) { abort(); }
const char *MenuTranslation_Original(const char *id) { abort(); }
const char *MenuTranslation_Group(const char *id) { abort(); }
const char *MenuTranslation_MainOriginal(void) { abort(); }
const char *MenuTranslation_ItemOriginal(void) { abort(); }
const char *const *MenuTranslation_StageNames(void) { abort(); }
const char *const *MenuTranslation_SongNames(void) { abort(); }

