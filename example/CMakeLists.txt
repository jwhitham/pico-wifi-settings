#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Example for pico-wifi-settings.
# Build steps for Pico W:
#   mkdir build
#   cd build
#   cmake -DPICO_BOARD=pico_w -DPICO_SDK_PATH=<path to Pico SDK> ..
#   make
#
cmake_minimum_required(VERSION 3.12)


# Pull in SDK (must be before project)
include(pico_sdk_import.cmake)

project(wifi_settings_example C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Initialize the SDK
pico_sdk_init()

# Import pico-wifi-settings
add_subdirectory(.. build-wifi-settings)

# Build example with async_context tasks running in the background
# You can use pico_cyw43_arch_lwip_poll instead of
# pico_cyw43_arch_lwip_threadsafe_background to use polling, if you prefer.
add_executable(example
        example.c
    )
target_include_directories(example PRIVATE
        ${CMAKE_CURRENT_LIST_DIR}
    )
target_compile_options(wifi_settings INTERFACE
        -Wall -Wextra -Werror
        -Wno-array-parameter
        -Wno-unused-parameter
    )
target_link_libraries(example
        pico_cyw43_arch_lwip_threadsafe_background
        wifi_settings 
        pico_stdlib
    )

pico_enable_stdio_usb(example 1)
pico_enable_stdio_uart(example 0)

pico_add_extra_outputs(example)
