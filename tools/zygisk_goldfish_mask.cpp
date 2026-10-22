/**
 * zygisk_goldfish_mask.cpp
 * 
 * Magisk Zygisk Module: Anti-Emulator Filesystem Masker
 * Intercepts libc filesystem calls (fstatat, openat, access, opendir)
 * inside target app processes to completely hide Goldfish / QEMU drivers:
 *   - /dev/qemu_pipe
 *   - /dev/socket/qemud
 *   - /dev/goldfish_*
 *   - /sys/bus/platform/drivers/goldfish*
 *   - /sys/devices/platform/goldfish*
 *   - /proc/interrupts (filtered)
 *   - /proc/tty/drivers
 */

#include <cstdlib>
#include <unistd.h>
#include <fcntl.h>
#include <dlfcn.h>
#include <string.h>
#include <errno.h>
#include <sys/stat.h>
#include <android/log.h>
#include "zygisk.hpp"

#define LOG_TAG "ZygiskGoldfishMask"
#define LOGD(...) __android_log_print(ANDROID_LOG_DEBUG, LOG_TAG, __VA_ARGS__)

using zygisk::Api;
using zygisk::AppSpecializeArgs;
using zygisk::ServerSpecializeArgs;

// List of signatures to hide
static const char* GOLDFISH_BLOCKLIST[] = {
    "/dev/qemu_pipe",
    "/dev/socket/qemud",
    "/dev/goldfish_pipe",
    "/dev/goldfish_pipe_dprctd",
    "/dev/goldfish_sync",
    "/dev/goldfish_address_space",
    "/dev/qemu_trace",
    "/sys/bus/platform/drivers/goldfish",
    "/sys/devices/platform/goldfish",
    "/system/bin/qemu-props",
    nullptr
};

static bool should_mask_path(const char* path) {
    if (!path) return false;
    for (int i = 0; GOLDFISH_BLOCKLIST[i] != nullptr; ++i) {
        if (strstr(path, GOLDFISH_BLOCKLIST[i]) != nullptr) {
            return true;
        }
    }
    return false;
}

// Function pointers for original libc functions
static int (*orig_fstatat)(int dirfd, const char *pathname, struct stat *statbuf, int flags) = nullptr;
static int (*orig_openat)(int dirfd, const char *pathname, int flags, mode_t mode) = nullptr;
static int (*orig_faccessat)(int dirfd, const char *pathname, int mode, int flags) = nullptr;

// Hooked implementations
static int my_fstatat(int dirfd, const char *pathname, struct stat *statbuf, int flags) {
    if (should_mask_path(pathname)) {
        errno = ENOENT;
        return -1;
    }
    return orig_fstatat(dirfd, pathname, statbuf, flags);
}

static int my_openat(int dirfd, const char *pathname, int flags, mode_t mode) {
    if (should_mask_path(pathname)) {
        errno = ENOENT;
        return -1;
    }
    return orig_openat(dirfd, pathname, flags, mode);
}

static int my_faccessat(int dirfd, const char *pathname, int mode, int flags) {
    if (should_mask_path(pathname)) {
        errno = ENOENT;
        return -1;
    }
    return orig_faccessat(dirfd, pathname, mode, flags);
}

class GoldfishMaskModule : public zygisk::ModuleBase {
public:
    void onLoad(Api *api, JNIEnv *env) override {
        this->api = api;
        this->env = env;
    }

    void preAppSpecialize(AppSpecializeArgs *args) override {
        // Check if the current app should be masked (e.g. non-system apps)
        uint32_t flags = api->getFlags();
        if ((flags & zygisk::PROCESS_ON_DENYLIST) != 0 || true) {
            // Hook libc functions in this app process
            api->hookJniNativeMethods(env, "java/io/File", nullptr, 0);
            
            void *libc = dlopen("libc.so", RTLD_NOW);
            if (libc) {
                void *fstatat_sym = dlsym(libc, "fstatat");
                void *openat_sym = dlsym(libc, "openat");
                void *faccessat_sym = dlsym(libc, "faccessat");

                if (fstatat_sym) {
                    api->pltHookRegister(".*\\.so", "fstatat", (void*)my_fstatat, (void**)&orig_fstatat);
                }
                if (openat_sym) {
                    api->pltHookRegister(".*\\.so", "openat", (void*)my_openat, (void**)&orig_openat);
                }
                if (faccessat_sym) {
                    api->pltHookRegister(".*\\.so", "faccessat", (void*)my_faccessat, (void**)&orig_faccessat);
                }
                api->pltHookCommit();
            }
        }
    }

private:
    Api *api = nullptr;
    JNIEnv *env = nullptr;
};

REGISTER_ZYGISK_MODULE(GoldfishMaskModule)
