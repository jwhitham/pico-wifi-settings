package(default_visibility = ["//visibility:public"])

# mbedtls library: see note in /MODULE.bazel
cc_library(
    name = "mbedtls_aes_sha256",
    srcs = [
        "library/aes.c",
        "library/sha256.c",
        "library/platform_util.c",
    ],
    hdrs = glob(
        include = [
            "include/**/*.h",
            "library/*.h",
        ],
    ),
    includes = ["include"],
    linkopts = select({
        "@rules_cc//cc/compiler:msvc-cl": ["-DEFAULTLIB:AdvAPI32.Lib"],
        "//conditions:default": [],
    }),
)
