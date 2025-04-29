#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Setup app for pico-wifi-settings.
# See /doc/SETUP_APP.md for build instructions.
#
cmake_minimum_required(VERSION 3.12)


# Pull in SDK (must be before project)
include(../example/pico_sdk_import.cmake)

project(wifi_settings_setup C CXX ASM)

set(CMAKE_C_STANDARD 11)
set(CMAKE_CXX_STANDARD 17)

# Initialize the SDK
pico_sdk_init()

# Import pico-wifi-settings
add_subdirectory(.. build-wifi-settings)

add_executable(setup
        setup.c
        activity_root.c
        activity_scan_for_a_hotspot.c
        activity_edit_hotspots.c
        activity_force_disconnect_reconnect.c
        activity_set_shared_secret.c
        activity_edit_others.c
        activity_connection_test.c
        activity_ping.c
        activity_dns_test.c
        activity_telnet_test.c
        activity_set_file_location.c
        dns_lookup.c
        edit_key_value.c
        user_interface.c
        file_operations.c
        wifi_slots.c
        file_finder.c
    )
target_include_directories(setup PRIVATE
        ${CMAKE_CURRENT_LIST_DIR}
        ${CMAKE_CURRENT_LIST_DIR}/config
    )
target_link_libraries(setup PRIVATE
        pico_cyw43_arch_lwip_threadsafe_background
        wifi_settings 
        pico_stdlib
        pico_multicore
    )
target_compile_options(setup PRIVATE
    -Wall -Wextra -Werror
    -Wno-unused-parameter
)
if (NOT SETUP_GIT_COMMIT)
    set(SETUP_GIT_COMMIT "??")
endif()
target_compile_definitions(setup PRIVATE
    SETUP_GIT_COMMIT="${SETUP_GIT_COMMIT}"
)

pico_set_program_name(setup "pico-wifi-settings setup")
pico_enable_stdio_usb(setup 1)
pico_enable_stdio_uart(setup 0)

pico_add_extra_outputs(setup)
