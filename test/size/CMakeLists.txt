#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Test program for pico-wifi-settings integration.
#

cmake_minimum_required(VERSION 3.12)

include(../../example/pico_sdk_import.cmake)

project(test C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

if (PICO_SDK_VERSION_STRING VERSION_LESS "2.1.0")
    message(FATAL_ERROR "Raspberry Pi Pico SDK version 2.1.0 (or later) required. Your version is ${PICO_SDK_VERSION_STRING}")
endif()

pico_sdk_init()

add_executable(test test.c)
target_include_directories(test PRIVATE ${CMAKE_CURRENT_LIST_DIR})
target_link_libraries(test PRIVATE
        pico_stdlib
    )
target_compile_options(test PRIVATE
    -Wall -Wextra -Werror
    -Wno-unused-parameter -Os
)

if (TEST_MODE STREQUAL "basic")
    target_link_libraries(test PRIVATE
        pico_cyw43_arch_lwip_threadsafe_background
    )
    target_compile_definitions(test PRIVATE
        TEST_MODE_BASIC_WIFI
        TEST_MODE_SOME_WIFI
    )
elseif (TEST_MODE STREQUAL "wifi_settings")
    add_subdirectory(../.. build-wifi-settings)
    target_link_libraries(test PRIVATE
        pico_cyw43_arch_lwip_threadsafe_background
        wifi_settings
    )
    target_compile_definitions(test PRIVATE
        TEST_MODE_WIFI_SETTINGS
        TEST_MODE_SOME_WIFI
    )
elseif (TEST_MODE STREQUAL "basic_with_mbedtls")
    target_link_libraries(test PRIVATE
        pico_cyw43_arch_lwip_threadsafe_background
        pico_mbedtls
    )
    target_compile_definitions(test PRIVATE
        TEST_MODE_BASIC_WIFI
        TEST_MODE_SOME_WIFI
        TEST_MODE_SHA256
        TEST_MODE_AES256
    )
elseif (TEST_MODE STREQUAL "no_wifi")
else()
    message(FATAL_ERROR "TEST_MODE invalid, got " ${TEST_MODE})
endif()

pico_enable_stdio_usb(test 1)
pico_enable_stdio_uart(test 0)
pico_add_extra_outputs(test)
