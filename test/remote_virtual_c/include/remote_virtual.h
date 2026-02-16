#ifndef REMOTE_VIRTUAL_H
#define REMOTE_VIRTUAL_H

#ifndef REMOTE_VIRTUAL
#error "THIS HEADER IS FOR REMOTE VIRTUAL TESTING ONLY"
#endif

#include <stdio.h>
#include <stdlib.h>

#define ASSERT(truth) \
    if (!(truth)) { fprintf(stderr, "Assert failed at %s:%u -> %s\n", \
        __FILE__, __LINE__, #truth); exit(1); }

void register_handlers(void);

#endif
