/* No texture pixels, formatted output or disk writes on the rendering path. */
#include "perf_trace.h"
#include <inttypes.h>
#include <pthread.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <time.h>

#ifndef PERF_TRACE_FRAMES
#define PERF_TRACE_FRAMES 32768
#endif
#ifndef PERF_TRACE_TEXTURES
#define PERF_TRACE_TEXTURES 1
#endif
#ifndef PERF_TRACE_FONTS
#define PERF_TRACE_FONTS 1
#endif

typedef struct Record {
    uint64_t ns, list, values[PERF_TRACE_VALUES];
    unsigned frame;
} Record;
typedef struct Ring {
    Record *records;
    size_t capacity;
    uint64_t count;
} Ring;
static Ring sRings[PERF_TRACE_KINDS] = {
    {NULL, PERF_TRACE_FRAMES, 0}, {NULL, PERF_TRACE_TEXTURES, 0}, {NULL, PERF_TRACE_FONTS, 0}, {NULL, PERF_TRACE_FRAMES, 0}
};
static pthread_once_t sOnce = PTHREAD_ONCE_INIT;
static pthread_mutex_t sLock = PTHREAD_MUTEX_INITIALIZER;
static int sEnabled, sClosing;
static uint64_t sStart, sList;

uint64_t PerfTrace_Now(void) {
    struct timespec ts;
    clock_gettime(CLOCK_MONOTONIC, &ts);
    return (uint64_t)ts.tv_sec * 1000000000ull + (uint64_t)ts.tv_nsec;
}

static void trace_flush(void) {
    static const char *names[] = {"frames", "textures", "fonts", "game"};
    static const char *columns[] = {
        "list_start_ns,total_ns,list_ns,uploads_ns,issue_ns,wait_ns,present_ns,submit_ns,texture_ns,pipeline_ns,image_ns,lookup_ns,vu_ns,xfer_ns,upload_bytes,new_textures,images_made,images_pooled,images_freed,draws,vertices,vu_vertices,refill_ns,live_textures",
        "tex0,texa,generation,source_w,source_h,output_w,output_h,decode_ns,recognize_ns,font_ns,create_queue_ns,total_ns,shared_font_ns,other_font_ns,pack,shared_font,menu_font,battle_art,pack_wait_plus1,output_bytes,source_bits,live_textures,reserved22,reserved23",
        "source_w,source_h,tbp,cbp,scale,font,slot_plus1,plane,cache_status,lock_wait_ns,work_ns,output_bytes,generation,registrations,calibrations,font_changes,evictions,cache_bytes,reserved18,reserved19,reserved20,reserved21,reserved22,reserved23",
        "previous_start_ns,at_chain_ns,work_end_ns,elapsed_ns,slept_ns,before_sync_ns,sync_or_render_ns,work_ns,snapshot_post_ns,menu_mode,blanks,live_blanks,threaded,reserved13,reserved14,reserved15,reserved16,reserved17,reserved18,reserved19,reserved20,reserved21,reserved22,reserved23"
    };
    FILE *info;
    int kind;
    pthread_mutex_lock(&sLock);
    sClosing = 1;
    for (kind = 0; kind < PERF_TRACE_KINDS; kind++) {
        Ring *ring = &sRings[kind];
        uint64_t first = ring->count > ring->capacity ? ring->count - ring->capacity : 0, seq;
        char name[80];
        FILE *file;
        snprintf(name, sizeof(name), "pacing-trace-%s.csv", names[kind]);
        file = fopen(name, "wb");
        if (file == NULL) { continue; }
        fprintf(file, "sequence,time_ns,list,frame,%s\n", columns[kind]);
        for (seq = first; seq < ring->count; seq++) {
            const Record *r = &ring->records[seq % ring->capacity];
            int i;
            fprintf(file, "%" PRIu64 ",%" PRIu64 ",%" PRIu64 ",%u", seq, r->ns, r->list, r->frame);
            for (i = 0; i < PERF_TRACE_VALUES; i++) { fprintf(file, ",%" PRIu64, r->values[i]); }
            fputc('\n', file);
        }
        fclose(file);
    }
    info = fopen("pacing-trace-info.json", "wb");
    if (info != NULL) {
        fprintf(info, "{\"version\":1,\"disk_writes_during_capture\":false,\"cpu_timings_only\":true,\"rings\":[");
        for (kind = 0; kind < PERF_TRACE_KINDS; kind++) {
            Ring *r = &sRings[kind];
            fprintf(info, "%s{\"name\":\"%s\",\"capacity\":%zu,\"total\":%" PRIu64 ",\"overwritten\":%" PRIu64 "}",
                    kind ? "," : "", names[kind], r->capacity, r->count,
                    r->count > r->capacity ? r->count - r->capacity : 0);
        }
        fprintf(info, "]}\n");
        fclose(info);
    }
    pthread_mutex_unlock(&sLock);
}

static void trace_init(void) {
    const char *setting = getenv("BT3_PACING_TRACE");
    int i;
    if (setting == NULL || strcmp(setting, "1") != 0) { return; }
    for (i = 0; i < PERF_TRACE_KINDS; i++) {
        size_t bytes = sRings[i].capacity * sizeof(Record), at;
        volatile unsigned char *touch;
        sRings[i].records = malloc(bytes);
        if (sRings[i].records == NULL) { break; }
        memset(sRings[i].records, 0, bytes);
        touch = (volatile unsigned char *)sRings[i].records;
        for (at = 0; at < bytes; at += 4096) { touch[at] = 0; }
    }
    if (i != PERF_TRACE_KINDS || atexit(trace_flush) != 0) {
        for (i = 0; i < PERF_TRACE_KINDS; i++) { free(sRings[i].records); sRings[i].records = NULL; }
        return;
    }
    sStart = PerfTrace_Now();
    sEnabled = 1;
}

void PerfTrace_Begin(void) {
    pthread_once(&sOnce, trace_init);
    if (!sEnabled) { return; }
    pthread_mutex_lock(&sLock);
    sList++;
    pthread_mutex_unlock(&sLock);
}

int PerfTrace_Enabled(void) { return sEnabled; }

void PerfTrace_Write(int kind, unsigned frame, const uint64_t values[PERF_TRACE_VALUES]) {
    Ring *ring;
    Record *record;
    if (!sEnabled || kind < 0 || kind >= PERF_TRACE_KINDS) { return; }
    pthread_mutex_lock(&sLock);
    if (!sClosing) {
        ring = &sRings[kind];
        record = &ring->records[ring->count++ % ring->capacity];
        record->ns = PerfTrace_Now() - sStart;
        record->list = sList;
        record->frame = frame;
        memcpy(record->values, values, sizeof(record->values));
    }
    pthread_mutex_unlock(&sLock);
}
