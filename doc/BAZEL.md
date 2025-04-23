# Using pico-wifi-settings with Bazel projects

[Bazel](https://bazel.build) 
support has been added to the Pico SDK
[quite recently](https://github.com/raspberrypi/pico-sdk/tree/2.1.1/bazel).

Some things are not fully supported,
but it is already possible to build a WiFi-enabled Pico project
with Bazel and pico-wifi-settings. This page describes the necessary steps,
but because Bazel is still a new feature in the Pico SDK, it begins
with an overview of how Pico W projects are currently built with Bazel.

# Short guide to building Pico W projects with Bazel

Currently ([Pico SDK 2.1.1](https://github.com/raspberrypi/pico-sdk/tree/2.1.1/bazel)),
Bazel options are used for most configuration settings. CMake options such
as `PICO_BOARD` are also Bazel options, and so are some of the settings
that were found inside `CMakeLists.txt`, such as
`pico_enable_stdio_usb`, which becomes the `PICO_STDIO_USB` option. Here
is a general command to build a target named `//:example` for Pico W:
```
    bazel build --platforms=@pico-sdk//bazel/platform:rp2040 \
      --@pico-sdk//bazel/config:PICO_BOARD=pico_w  \
      --@pico-sdk//bazel/config:PICO_STDIO_USB=true \
      //:example
```
The `BUILD.bazel` file contains a description of this target:
```
    cc_binary(
        name = "example",
        srcs = ["example.c"],
        deps = [
            "@pico-sdk//src/rp2_common/pico_cyw43_arch",
            "@pico-sdk//src/rp2_common/pico_stdlib",
            "@pico-sdk//src/rp2_common/pico_lwip:pico_lwip_nosys",
        ],
    )
```
Output binaries appear in `bazel-bin`, which points into Bazel's cache of build artifacts.
The output is normally just an ELF file, but UF2 files can be generated as well
using an aspect:
```
    bazel build ... \
      --aspects @pico-sdk//tools:uf2_aspect.bzl%pico_uf2_aspect \
      --output_groups=+pico_uf2_files \
      ...
```
When LwIP is used, an `lwipopts.h` configuration file has to be provided
to set which LwIP features should be enabled. This must be declared as a Bazel
target in `BUILD.bazel`:
```
    cc_library(
        name = "example_lwipopts",
        hdrs = ["config/lwipopts.h"],
        includes = ["config"],
    )
```
and it must also be provided as a Bazel option:
```
    bazel build ... \
      --@pico-sdk//bazel/config:PICO_LWIP_CONFIG=//:example_lwipopts \
      ...
```
A Pico W project using Bazel also requires a `MODULE.bazel` file in the root of the
workspace which defines dependencies on other Bazel modules, particularly the
Pico SDK. There is an example in [/example/MODULE.bazel](/example/MODULE.bazel)
alongside a sample [BUILD.bazel](/example/BUILD.bazel) file. The example can be built
for Pico W using the command:
```
    cd example
    bazel build --platforms=@pico-sdk//bazel/platform:rp2040 \
      --@pico-sdk//bazel/config:PICO_BOARD=pico_w  \
      --@pico-sdk//bazel/config:PICO_LWIP_CONFIG=//:example_lwipopts \
      --@pico-sdk//bazel/config:PICO_STDIO_USB=true \
      --aspects @pico-sdk//tools:uf2_aspect.bzl%pico_uf2_aspect \
      --output_groups=+pico_uf2_files \
      //:example
```
or Pico 2 W:
```
    cd example
    bazel build --platforms=@pico-sdk//bazel/platform:rp2350 \
      --@pico-sdk//bazel/config:PICO_BOARD=pico2_w  \
      --@pico-sdk//bazel/config:PICO_LWIP_CONFIG=//:example_lwipopts \
      --@pico-sdk//bazel/config:PICO_STDIO_USB=true \
      --aspects @pico-sdk//tools:uf2_aspect.bzl%pico_uf2_aspect \
      --output_groups=+pico_uf2_files \
      //:example
```


# Integrating pico-wifi-settings into a Bazel project

The source code changes [are the same as
for CMake](/doc/INTEGRATION.md), just a few lines of code:
```
    #include "wifi_settings.h"                  // << add this
    int main() {
        stdio_init_all();
        if (wifi_settings_init() != 0) {        // << and add this
            panic(...);
        }
        wifi_settings_connect();                // << and add this
        // and that's it...
    }
```
See the [integration guide](/doc/INTEGRATION.md) for more details about
source code changes.

The Bazel changes are as follows:

## Add pico-wifi-settings to your MODULE.bazel file

Add the following lines to your `MODULE.bazel` file:
```
    bazel_dep(name = "pico-wifi-settings", version = "")

    git_override(
        module_name = "pico-wifi-settings",
        tag = "v0.1.3", # <-- use the version of the most recent release
        remote = "https://github.com/jwhitham/pico-wifi-settings.git",
    )
```
It's good to use a commit ID in order to have a completely reproducible
build, but the `git_override` rule is also able to track tags, which should
never change, and are more human-readable than commit IDs.

## Modify BUILD.bazel to add a dependency to pico-wifi-settings

Your application's build rule (e.g. `cc_binary`) must have
a dependency on `pico-wifi-settings`, e.g.:
```
    cc_binary(
        name = "example",
        srcs = ["example.c"],
        deps = [
            "@pico-wifi-settings//:pico-wifi-settings",
            ... other dependencies ...
        ],
    )
```
Your application will probably require LwIP, so you also need a Bazel target
for a `lwipopts.h` file:
```
    cc_library(
        name = "example_lwipopts",
        hdrs = ["config/lwipopts.h"],
        includes = ["config"],
    )
```

## Controlling remote update features

The `WIFI_SETTINGS_REMOTE` option controls whether [remote update features](/doc/REMOTE.md)
are enabled.  The option is specified like this:
```
    bazel build ... \
      --@pico-wifi-settings//bazel/config:WIFI_SETTINGS_REMOTE=2 \
      ...
```
The supported values are:

 - `WIFI_SETTINGS_REMOTE=0` will disable all remote update features.
 - `WIFI_SETTINGS_REMOTE=1` is the default setting. It allows some
   basic remote update commands (`info`, `update`, `update_reboot`, `reboot`).
 - `WIFI_SETTINGS_REMOTE=2` is the maximum setting. This enables commands
   for remote access to Pico memory (RAM and Flash) including "over the air" (OTA)
   updates.

## Building with pico-wifi-settings and Bazel

Here are some suggested Bazel build commands for projects using pico-wifi-settings.

For Pico W:
```
    bazel build --platforms=@pico-sdk//bazel/platform:rp2040 \
      --@pico-sdk//bazel/config:PICO_BOARD=pico_w  \
      --@pico-sdk//bazel/config:PICO_LWIP_CONFIG=//:example_lwipopts \
      --@pico-sdk//bazel/config:PICO_STDIO_USB=true \
      --@pico-wifi-settings//bazel/config:WIFI_SETTINGS_REMOTE=2 \
      --aspects @pico-sdk//tools:uf2_aspect.bzl%pico_uf2_aspect \
      --output_groups=+pico_uf2_files \
      //:example
```
and Pico 2 W:
```
    bazel build --platforms=@pico-sdk//bazel/platform:rp2350 \
      --@pico-sdk//bazel/config:PICO_BOARD=pico2_w  \
      --@pico-sdk//bazel/config:PICO_LWIP_CONFIG=//:example_lwipopts \
      --@pico-sdk//bazel/config:PICO_STDIO_USB=true \
      --aspects @pico-sdk//tools:uf2_aspect.bzl%pico_uf2_aspect \
      --@pico-wifi-settings//bazel/config:WIFI_SETTINGS_REMOTE=2 \
      --output_groups=+pico_uf2_files \
      //:example
```

# Notes about using Bazel

- Default Bazel options can be placed in a `.bazelrc` file to cut down on typing!
- Multicore is enabled by default, unlike CMake. This affects writing to Flash,
  as described in the [Multicore support section of REMOTE.md](/doc/REMOTE.md#multicore-support).
  You can use `--@pico-sdk//bazel/config:PICO_MULTICORE_ENABLED=false` to disable it.
- For a debug build, use the Bazel option `-c dbg`.

# Limitations and known issues

## mbedtls with Pico SDK and Bazel

If your application used [the remote update feature](REMOTE.md) with CMake, you would
need `mbedtls_config.h`, but as of version 2.1.1, the Pico SDK Bazel files
do not include the mbedtls library as a
dependency and therefore there is no officially established way of using it within
Pico projects.  Pico SDK doesn't have an equivalent of `PICO_LWIP_CONFIG`
for mbedtls and Bazel (e.g. `PICO_MBEDTLS_CONFIG`) and modules that
require mbedtls, such as pico-wifi-settings
or [picotool](https://github.com/raspberrypi/picotool) must reference it directly.

This situation will probably change in the future, but for now, pico-wifi-settings
uses a workaround in which the required features of mbedtls (SHA-256, AES) are
directly imported via a special Bazel target (`@mbedtls_aes_sha256`). With no
future-proof way to use a `mbedtls_config.h` file, default settings are used.
Unfortunately this means that Pico 2's SHA-256 acceleration is not available and
the implementation is purely software. This means a slightly increased boot time
(due to generating a hash for the `update_secret`) and somewhat lower performance when
handling remote updates.

## OTA updates for Bazel projects

The Bazel toolchain natively produces `.elf` files, but `.uf2` can be
enabled with the parameters:
```
    bazel build ... \
      --aspects @pico-sdk//tools:uf2_aspect.bzl%pico_uf2_aspect \
      --output_groups=+pico_uf2_files \
      ...
```
`.uf2` files can be used with `remote_picotool ota`.
