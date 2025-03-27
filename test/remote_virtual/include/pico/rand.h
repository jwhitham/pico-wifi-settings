#ifndef PICO_RAND_H
#define PICO_RAND_H

#ifndef REMOTE_VIRTUAL
#error "THIS IS A MOCK HEADER FOR REMOTE VIRTUAL PLATFORM ONLY"
#endif

typedef struct rng_128 {
    uint64_t r[2];
} rng_128_t;

void get_rand_128(rng_128_t *rand128);

#endif
