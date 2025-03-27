#ifndef PICO_FLASH_H
#define PICO_FLASH_H

#ifndef UNIT_TEST
#error "THIS IS A MOCK HEADER FOR UNIT TESTING ONLY"
#endif

#include <stdint.h>

int flash_safe_execute(void (*func)(void *), void *param, uint32_t enter_exit_timeout_ms);

#endif
