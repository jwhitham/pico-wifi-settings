#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Test program for pico-wifi-settings integration.
#

cmake_minimum_required(VERSION 3.12)

include(pico_sdk_import.cmake)

project(test C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

if (PICO_SDK_VERSION_STRING VERSION_LESS "2.1.0")
    message(FATAL_ERROR "Raspberry Pi Pico SDK version 2.1.0 (or later) required. Your version is ${PICO_SDK_VERSION_STRING}")
endif()

pico_sdk_init()

add_executable(test test.c)
target_include_directories(test PRIVATE ${CMAKE_CURRENT_LIST_DIR})
target_link_libraries(test pico_stdlib)

pico_enable_stdio_usb(test 1)
pico_enable_stdio_uart(test 0)
pico_add_extra_outputs(test)
