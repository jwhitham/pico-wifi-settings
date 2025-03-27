#ifndef PICO_STDLIB_H
#define PICO_STDLIB_H

#ifndef REMOTE_VIRTUAL
#error "THIS IS A MOCK HEADER FOR REMOTE VIRTUAL PLATFORM ONLY"
#endif

#define PICO_ERROR_NONE 0
#define PICO_ERROR_INVALID_ARG 151
#define PICO_ERROR_INSUFFICIENT_RESOURCES 152
#define PICO_ERROR_RESOURCE_IN_USE 153

typedef unsigned int uint;
void panic(const char* fmt, ...);

#endif
