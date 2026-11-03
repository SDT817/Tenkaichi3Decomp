/* Local analysis only: reuse the official port's texture decoder unchanged.
 * The Python adapter supplies a normal texture-file header and linear CLUT.
 * Compile with section garbage collection so no game runtime is linked. */
#include "../../Tenkaichi3Decomp-WiiLocal-r5/port/src/gs/menu_labels.c"

int main(int argc, char **argv) {
    MlCtx ctx = {0};
    MlTex tex = {0};
    MlBuf data;
    FILE *f;
    long size;
    uint8_t *bytes;
    int result;
    if (argc != 3 && argc != 4) return 2;
    f = fopen(argv[1], "rb");
    if (!f) return 3;
    fseek(f, 0, SEEK_END);
    size = ftell(f);
    rewind(f);
    if (size <= 0 || size > 1024 * 1024) return 4;
    bytes = malloc((size_t)size);
    if (!bytes || fread(bytes, 1, (size_t)size, f) != (size_t)size) return 5;
    fclose(f);
    data.p = bytes;
    data.n = (size_t)size;
    result = ml_texture(&ctx, data, 0, &tex);
    if (result != 1) {
        fprintf(stderr, "decoder result %d: %s\n", result, ctx.why);
        return 6;
    }
    f = fopen(argv[2], "wb");
    if (!f) return 7;
    if (fwrite(tex.rgba, 4, (size_t)tex.w * tex.h, f) != (size_t)tex.w * tex.h) return 8;
    fclose(f);
    if (argc == 4) {
        f = fopen(argv[3], "wb");
        if (!f) return 9;
        if (fwrite(ctx.map, 4, (size_t)tex.w * tex.h, f) != (size_t)tex.w * tex.h) return 10;
        fclose(f);
    }
    printf("%d %d\n", tex.w, tex.h);
    ml_free(&ctx);
    free(bytes);
    return 0;
}
