#ifndef PICO_ERROR_H
#define PICO_ERROR_H

#ifndef UNIT_TEST
#error "THIS IS A MOCK HEADER FOR UNIT TESTING ONLY"
#endif

#define PICO_OK 0
#define PICO_ERROR_INVALID_STATE -100
#define PICO_ERROR_GENERIC -101
#define PICO_ERROR_INVALID_DATA -102
#define PICO_ERROR_INVALID_ARG -103
#endif
