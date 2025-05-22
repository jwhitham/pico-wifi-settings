#
# Copyright (c) 2025 Jack Whitham
#
# SPDX-License-Identifier: BSD-3-Clause
#
# pico-wifi-settings toplevel CMakeLists.txt
#
# Creates the wifi_settings library, ready to be linked to
# Pico or Pico 2 applications. The Pico SDK is also required,
# along with a suitable PICO_BOARD setting (WiFi driver is needed!)
#
cmake_minimum_required(VERSION 3.12)

if (PICO_SDK_VERSION_STRING VERSION_LESS "2.1.0")
    message(FATAL_ERROR "Raspberry Pi Pico SDK version 2.1.0 (or later) required. Your version is ${PICO_SDK_VERSION_STRING}")
endif()

if (NOT PICO_CYW43_SUPPORTED)
    message(FATAL_ERROR "wifi_settings: WiFi hardware is required: run cmake -DPICO_BOARD=pico_w or -DPICO_BOARD=pico2_w")
endif()

if (NOT TARGET pico_cyw43_arch)
    message(FATAL_ERROR "wifi_settings: WiFi driver pico_cyw43_arch is not present")
endif()

if (NOT TARGET pico_lwip_core)
    message(FATAL_ERROR "wifi_settings: IP layer pico_lwip_core is not present")
endif()

if ((NOT WIFI_SETTINGS_REMOTE) AND NOT (WIFI_SETTINGS_REMOTE STREQUAL "0"))
    set(WIFI_SETTINGS_REMOTE 1)
endif()

if ((NOT TARGET pico_mbedtls) AND (WIFI_SETTINGS_REMOTE GREATER 0))
    message(FATAL_ERROR "wifi_settings: crypto library pico_mbedtls is not present, remote features must be disabled (cmake -DWIFI_SETTINGS_REMOTE=0)")
endif()

message("wifi_settings: library is available.")
set(WIFI_SETTINGS_VERSION_STRING "0.2.2")
set(WIFI_SETTINGS_PROJECT_URL "https://github.com/jwhitham/pico-wifi-settings")


add_library(wifi_settings_headers INTERFACE)
target_include_directories(wifi_settings_headers INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/include
)
target_link_libraries(wifi_settings_headers INTERFACE
    pico_async_context_base
    pico_stdlib
)

add_library(wifi_settings INTERFACE)
target_sources(wifi_settings INTERFACE
    ${CMAKE_CURRENT_LIST_DIR}/src/wifi_settings_connect.c
    ${CMAKE_CURRENT_LIST_DIR}/src/wifi_settings_flash_storage.c
    ${CMAKE_CURRENT_LIST_DIR}/src/wifi_settings_flash_range.c
    ${CMAKE_CURRENT_LIST_DIR}/src/wifi_settings_hostname.c
)
target_link_libraries(wifi_settings INTERFACE
    wifi_settings_headers 
    pico_cyw43_arch
    pico_lwip_core
    pico_sync
)
target_compile_options(wifi_settings INTERFACE
    -Wno-unused-parameter
)
target_compile_definitions(wifi_settings INTERFACE
    WIFI_SETTINGS_VERSION_STRING="${WIFI_SETTINGS_VERSION_STRING}"
    WIFI_SETTINGS_PROJECT_URL="${WIFI_SETTINGS_PROJECT_URL}"
)
if (WIFI_SETTINGS_FILE_ADDRESS)
    message("wifi_settings: use alternate Flash address for wifi-settings file: ${WIFI_SETTINGS_FILE_ADDRESS}")
    target_compile_definitions(wifi_settings INTERFACE
        WIFI_SETTINGS_FILE_ADDRESS=${WIFI_SETTINGS_FILE_ADDRESS}
    )
endif()

if (WIFI_SETTINGS_REMOTE GREATER 0)
    if (WIFI_SETTINGS_REMOTE GREATER 1)
        message("wifi_settings: remote update feature is enabled with memory access functions")
        target_compile_definitions(wifi_settings INTERFACE
            ENABLE_REMOTE_MEMORY_ACCESS
        )
        target_sources(wifi_settings INTERFACE
            ${CMAKE_CURRENT_LIST_DIR}/src/wifi_settings_remote_memory_access_handlers.c
        )
    else()
        message("wifi_settings: remote update feature is enabled without memory access functions")
    endif()
    target_compile_definitions(wifi_settings INTERFACE
        ENABLE_REMOTE_UPDATE
    )
    target_sources(wifi_settings INTERFACE
        ${CMAKE_CURRENT_LIST_DIR}/src/wifi_settings_remote.c
        ${CMAKE_CURRENT_LIST_DIR}/src/wifi_settings_remote_handlers.c
        ${CMAKE_CURRENT_LIST_DIR}/src/wifi_settings_flash_storage_update.c
    )
    target_link_libraries(wifi_settings INTERFACE
        pico_mbedtls
    )
else()
    message("wifi_settings: remote update feature is disabled")
endif()


