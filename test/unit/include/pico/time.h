#ifndef PICO_TIME_H
#define PICO_TIME_H

#ifndef UNIT_TEST
#error "THIS IS A MOCK HEADER FOR UNIT TESTING ONLY"
#endif

#include <stdbool.h>
#include <stdint.h>

typedef struct absolute_time_t {
    uint32_t value;
} absolute_time_t;

absolute_time_t make_timeout_time_ms(const uint32_t ms);
absolute_time_t delayed_by_ms(const absolute_time_t t, const uint32_t ms);
bool time_reached(const absolute_time_t t);

#endif
