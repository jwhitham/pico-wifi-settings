#ifndef FLASH_H
#define FLASH_H

#ifndef UNIT_TEST
#error "THIS IS A MOCK HEADER FOR UNIT TESTING ONLY"
#endif

#define XIP_BASE 0x12300000
#define PICO_FLASH_SIZE_BYTES 0x48000
#define FLASH_SECTOR_SIZE 0x2000
#define FLASH_PAGE_SIZE 0x200
#include <stddef.h>
#include <stdint.h>
#include <stdbool.h>
void flash_range_erase(uint32_t flash_offs, size_t count);
void flash_range_program(uint32_t flash_offs, const uint8_t *data, size_t count);

struct wifi_settings_flash_range_t;
bool wifi_settings_flash_range_verify(
            const struct wifi_settings_flash_range_t* fr,
            const char* data);

#endif
