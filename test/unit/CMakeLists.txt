#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Unit test CMakeLists.txt.
# Unit tests run natively on the build system, no Pico required.
#
cmake_minimum_required(VERSION 3.12)

project(test_wifi_settings)
enable_testing()

set(CMAKE_C_STANDARD 11)

add_compile_definitions(
        UNIT_TEST
        PICO_RP2040
    )
include_directories(
        ${CMAKE_CURRENT_LIST_DIR}/include
        ${CMAKE_CURRENT_LIST_DIR}/../../include
    )


add_executable(test_wifi_settings_flash_storage
        ${CMAKE_CURRENT_LIST_DIR}/test_wifi_settings_flash_storage.c
        ${CMAKE_CURRENT_LIST_DIR}/../../src/wifi_settings_flash_storage.c
    )
add_test(test_wifi_settings_flash_storage
        test_wifi_settings_flash_storage
    )
add_executable(test_wifi_settings_flash_storage_update
        ${CMAKE_CURRENT_LIST_DIR}/test_wifi_settings_flash_storage_update.c
        ${CMAKE_CURRENT_LIST_DIR}/../../src/wifi_settings_flash_storage_update.c
    )
add_test(test_wifi_settings_flash_storage_update
        test_wifi_settings_flash_storage_update
    )
add_executable(test_wifi_settings_connect
        ${CMAKE_CURRENT_LIST_DIR}/test_wifi_settings_connect.c
        ${CMAKE_CURRENT_LIST_DIR}/../../src/wifi_settings_connect.c
    )
add_test(test_wifi_settings_connect
        test_wifi_settings_connect
    )
