#ifndef SYNC_H
#define SYNC_H

#ifndef UNIT_TEST
#error "THIS IS A MOCK HEADER FOR UNIT TESTING ONLY"
#endif

#include <stdint.h>
uint32_t save_and_disable_interrupts();
void restore_interrupts(uint32_t flags);

#endif
