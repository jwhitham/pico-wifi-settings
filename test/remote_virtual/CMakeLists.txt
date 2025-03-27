#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# Run remote service on the build system, no Pico required.
#
cmake_minimum_required(VERSION 3.12)

project(remote_virtual)

set(CMAKE_C_STANDARD 11)

add_compile_definitions(
        REMOTE_VIRTUAL
        MBEDTLS_AES_C
        MBEDTLS_CIPHER_MODE_CBC
        LWIP_CALLBACK_API
        ENABLE_REMOTE_UPDATE
        ENABLE_REMOTE_MEMORY_ACCESS
    )
include_directories(
        ${CMAKE_CURRENT_LIST_DIR}/include
        ${CMAKE_CURRENT_LIST_DIR}/../../include
    )

add_executable(remote_virtual
        ${CMAKE_CURRENT_LIST_DIR}/remote_virtual.c
        ${CMAKE_CURRENT_LIST_DIR}/fake_mbedtls.c
        ${CMAKE_CURRENT_LIST_DIR}/fake_lwip.c
        ${CMAKE_CURRENT_LIST_DIR}/fake_handlers.c
        ${CMAKE_CURRENT_LIST_DIR}/../../src/wifi_settings_remote.c
    )
target_link_libraries(remote_virtual crypto)
