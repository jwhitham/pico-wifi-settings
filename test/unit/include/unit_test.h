#ifndef UNIT_TEST_H
#define UNIT_TEST_H

#ifndef UNIT_TEST
#error "THIS HEADER IS FOR UNIT TESTING ONLY"
#endif

#define ASSERT(truth) \
    if (!(truth)) { fprintf(stderr, "Test failed at %s:%u -> %s\n", \
        __FILE__, __LINE__, #truth); exit(1); }

#define NUM_ELEMENTS(array) (sizeof(array) / sizeof(array[0]))

#endif
