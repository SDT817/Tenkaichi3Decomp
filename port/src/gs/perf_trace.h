/* Local diagnostic only: bounded RAM records, written once at normal exit. */
#ifndef BT3_PERF_TRACE_H
#define BT3_PERF_TRACE_H
#include <stdint.h>

#define PERF_TRACE_VALUES 24
enum { PERF_TRACE_FRAME, PERF_TRACE_TEXTURE, PERF_TRACE_FONT, PERF_TRACE_GAME, PERF_TRACE_KINDS };
void PerfTrace_Begin(void);
int PerfTrace_Enabled(void);
uint64_t PerfTrace_Now(void);
void PerfTrace_Write(int kind, unsigned frame, const uint64_t values[PERF_TRACE_VALUES]);
#endif
