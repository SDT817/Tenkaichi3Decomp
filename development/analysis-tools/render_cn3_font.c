/* Headless use of the game's actual checked TrueType/menu renderer. */
#include "../../Tenkaichi3Decomp-WiiLocal-r5-CN3/port/src/gs/menu_text.c"

/* These services belong to the running game. A row-only test must never call them. */
int MenuTranslation_BootPending(void) { abort(); }
int MenuTranslation_Load(const char *d, char *w, size_t n) { abort(); }
const char *MenuTranslation_Locale(void) { abort(); }
const char *MenuTranslation_Text(const char *id) { abort(); }
const char *MenuTranslation_Original(const char *id) { abort(); }
int UiText_EuropeanOnStartup(const char *d, char *w, size_t n) { abort(); }
int MenuLabels_Make(const char *d, const char *o, int a, char *w, size_t n) { abort(); }
int MenuLabels_MainItem(const char *d, unsigned char *o[2]) { abort(); }
int MenuLabels_Art(const char *d, int b, char *w, size_t n) { abort(); }
void MenuLabels_ItemPixels(const unsigned char *p, const unsigned char *t, unsigned char *o) { abort(); }
int Port_Setting(const char *n, int d) { abort(); }

static unsigned char *file_bytes(const char *path, size_t *size) {
    FILE *f = fopen(path, "rb");
    unsigned char *data;
    long n;
    if (!f) return NULL;
    fseek(f, 0, SEEK_END); n = ftell(f); rewind(f);
    if (n <= 0) { fclose(f); return NULL; }
    data = malloc((size_t)n);
    if (data == NULL || fread(data, 1, (size_t)n, f) != (size_t)n) { free(data); fclose(f); return NULL; }
    fclose(f); *size = (size_t)n; return data;
}

static int shared_test(int argc, char **argv) {
    size_t size, pixels;
    unsigned char *font, *rgba, *out;
    const char *why;
    int plane, w, h, count, i;
    uint32_t table;
    FILE *f;
    if (argc != 7) return 10;
    why = face_open(&sSharedFont, argv[2]);
    if (why) { fprintf(stderr, "%s\n", why); return 11; }
    font = file_bytes(argv[3], &size);
    rgba = file_bytes(argv[4], &pixels);
    if (!font || !rgba || pixels != 512*512*4 || size < 36) return 12;
    memcpy(&table, font + 20, 4); memcpy(&count, font + 24, 4);
    if (count < 1 || count > 10000 || table > size || (size_t)count*6 > size-table) return 13;
    plane = atoi(argv[5]);
    MenuText_RegisterGlyphs(0x2A08, 0x2A00, font+table, count, font[32]);
    sSharedChoice = 1;
    out = menu_text_glyphs(rgba, 512, 512, 0x2A08, 0x2A00+plane, 4, &w, &h);
    if (!out) return 14;
    f = fopen(argv[6], "wb");
    if (!f || fwrite(out, 4, (size_t)w*h, f) != (size_t)w*h) return 15;
    fclose(f);
    printf("atlas\t%d\t%d\n", w, h);
    for (i=0; i<count; i++) {
        SharedGlyph *g=&sSharedSheets[0].glyphs[i];
        SharedRect *r=&sSharedLayouts[0][plane].rects[i];
        if (r->w) printf("%04X\t%d\t%d\t%d\t%d\t%d\t%d\n", g->code,r->x,r->y,r->w,r->h,r->top,r->bottom);
    }
    free(font); free(rgba); free(out); face_close(&sSharedFont);
    return 0;
}

int main(int argc, char **argv) {
    Face face;
    char line[3000], path[1500];
    FILE *jobs;
    int count = 0;
    const char *why;
    if (argc > 1 && strcmp(argv[1], "--sheet") == 0) return shared_test(argc, argv);
    if (argc != 4) return 2;
    why = face_open(&face, argv[1]);
    if (why != NULL) { fprintf(stderr, "%s\n", why); return 3; }
    fprintf(stderr, "Font cap units: %d, em: %d\n", face.capUnits, face.unitsPerEm);
    jobs = fopen(argv[2], "rb");
    if (!jobs) return 4;
    while (fgets(line, sizeof(line), jobs)) {
        MenuLabel label = {0};
        Row row = {0};
        unsigned long long hash;
        int pos = 0, end = 0;
        char id[80], *text;
        FILE *out;
        if (sscanf(line, "%llx\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%d\t%x\t%x\t%x\t%d\t%x\t%d\t%d\t%d\t%x\t%d\t%x\t%d\t%x\t%x\t%d\t%d\t%d\t%n",
            &hash, &label.width, &label.height, &label.y, &label.rowHeight, &label.cap,
            &label.baseline, &label.center, &label.margin, &label.widthMilli, &label.x, &label.rowWidth,
            &label.artWidth, &label.top, &label.bottom, &label.middleColor, &label.hasMiddle, &label.outline, &label.italic,
            &label.outlineMilli, &label.outerMilli, &label.outerColor, &label.shadow, &label.outlineBottom,
            &label.bevelMilli, &label.bevelLight, &label.bevelDark, &label.depthMilli, &label.midGradient, &label.fontFace, &pos) != 30) return 5;
        text = strchr(line + pos, '\t');
        if (!text) return 6;
        *text++ = 0;
        snprintf(id, sizeof(id), "%s", line + pos);
        text[strcspn(text, "\r\n")] = 0;
        snprintf(label.text, sizeof(label.text), "%s", text);
        label.fontFace = 0;
        if (!menu_text_row(&face, &label, 4, &row) || !row.px) return 7;
        snprintf(path, sizeof(path), "%s/%s.rgba", argv[3], id);
        out = fopen(path, "wb");
        if (!out || fwrite(row.px, 4, (size_t)row.w * row.h, out) != (size_t)row.w * row.h) return 8;
        fclose(out);
        printf("%s\t%d\t%d\t%d\t%d\t%d\t%d\n", id, row.w, row.h, row.x, row.y, label.rowWidth*4, label.rowHeight*4);
        free(row.px);
        count++;
    }
    fclose(jobs);
    face_close(&face);
    return count ? 0 : 9;
}
