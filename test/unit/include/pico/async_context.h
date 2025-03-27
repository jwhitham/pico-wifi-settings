#ifndef PICO_ASYNC_CONTEXT_H
#define PICO_ASYNC_CONTEXT_H

#ifndef UNIT_TEST
#error "THIS IS A MOCK HEADER FOR UNIT TESTING ONLY"
#endif

#include "pico/time.h"

typedef struct async_context_t {
    int nothing;
} async_context_t;

typedef struct async_work_on_timeout {
    absolute_time_t next_time;
    void (*do_work)(async_context_t *context, struct async_work_on_timeout *timeout);
} async_at_time_worker_t;

bool async_context_add_at_time_worker(async_context_t *context,
        async_at_time_worker_t *worker);
bool async_context_remove_at_time_worker(async_context_t *context,
        async_at_time_worker_t *worker);



#endif
