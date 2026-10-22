// =============================================================================
// File: tools/sec_gpu_interposer.mm
// Purpose: Host-Side GPU Renderer & Vendor Interposition for Android QEMU
//          Intercepts host OpenGL / SwiftShader / gfxstream translation calls
//          to report Qualcomm Snapdragon 8 Gen 3 Adreno 750 hardware signatures.
// =============================================================================

#import <Foundation/Foundation.h>
#import <mach-o/dyld.h>
#import <dlfcn.h>
#import <pthread.h>
#import <unistd.h>
#import <string>

#define LOG_PATH "/tmp/sec_gpu_interposer.log"

static const char* const SPOOF_VENDOR   = "Qualcomm";
static const char* const SPOOF_RENDERER = "Adreno (TM) 750";
static const char* const SPOOF_VERSION  = "OpenGL ES 3.2 V@0757.0 (GIT@e3qxeea)";
static const char* const SPOOF_SHADING  = "OpenGL ES GLSL ES 3.20";

// Real function pointers
typedef const char* (*glGetString_fn)(unsigned int name);
typedef const char* (*glGetStringi_fn)(unsigned int name, unsigned int index);
static glGetString_fn real_glGetString = NULL;
static glGetStringi_fn real_glGetStringi = NULL;

static void log_msg(const char* fmt, ...) {
    FILE* f = fopen(LOG_PATH, "a");
    if (!f) return;
    va_list args;
    va_start(args, fmt);
    vfprintf(f, fmt, args);
    va_end(args);
    fclose(f);
}

static void init_real_functions() {
    if (!real_glGetString) {
        real_glGetString = (glGetString_fn)dlsym(RTLD_NEXT, "glGetString");
    }
    if (!real_glGetStringi) {
        real_glGetStringi = (glGetStringi_fn)dlsym(RTLD_NEXT, "glGetStringi");
    }
}

// -----------------------------------------------------------------------------
// Interposed OpenGL String Handlers
// -----------------------------------------------------------------------------
extern "C" const char* sec_glGetString(unsigned int name) {
    if (name == 0x1F00) { // GL_VENDOR
        return SPOOF_VENDOR;
    }
    if (name == 0x1F01) { // GL_RENDERER
        return SPOOF_RENDERER;
    }
    if (name == 0x1F02) { // GL_VERSION
        return SPOOF_VERSION;
    }
    if (name == 0x8B8C) { // GL_SHADING_LANGUAGE_VERSION
        return SPOOF_SHADING;
    }
    init_real_functions();
    if (real_glGetString) {
        return real_glGetString(name);
    }
    return "";
}

extern "C" const char* sec_glGetStringi(unsigned int name, unsigned int index) {
    init_real_functions();
    if (real_glGetStringi) {
        return real_glGetStringi(name, index);
    }
    return "";
}

extern "C" void sec_android_getOpenglesHardwareStrings(char** vendor, char** renderer, char** version) {
    if (vendor)   *vendor   = strdup(SPOOF_VENDOR);
    if (renderer) *renderer = strdup(SPOOF_RENDERER);
    if (version)  *version  = strdup(SPOOF_VERSION);
    log_msg("[SEC_GPU] Intercepted android_getOpenglesHardwareStrings -> %s / %s\n", SPOOF_VENDOR, SPOOF_RENDERER);
}

// Forward declarations for target symbols
extern "C" const char* glGetString(unsigned int name);
extern "C" const char* glGetStringi(unsigned int name, unsigned int index);
extern "C" void android_getOpenglesHardwareStrings(char** vendor, char** renderer, char** version) __attribute__((weak_import));

// -----------------------------------------------------------------------------
// Dyld Interposing Table (Native macOS Dynamic Linker Hooking)
// -----------------------------------------------------------------------------
#define DYLD_INTERPOSE(_replacement, _replacee) \
__attribute__((used)) static const struct { const void* replacement; const void* replacee; } _interpose_##_replacee \
__attribute__((section("__DATA,__interpose"))) = { (const void*)(unsigned long)&_replacement, (const void*)(unsigned long)&_replacee };

DYLD_INTERPOSE(sec_glGetString, glGetString);
DYLD_INTERPOSE(sec_glGetStringi, glGetStringi);
DYLD_INTERPOSE(sec_android_getOpenglesHardwareStrings, android_getOpenglesHardwareStrings);

// Explicit symbol exports for direct lookup or dlsym()
extern "C" __attribute__((visibility("default"))) const char* glGetString(unsigned int name) {
    return sec_glGetString(name);
}
extern "C" __attribute__((visibility("default"))) const char* glGetStringi(unsigned int name, unsigned int index) {
    return sec_glGetStringi(name, index);
}
extern "C" __attribute__((visibility("default"))) void android_getOpenglesHardwareStrings(char** vendor, char** renderer, char** version) {
    sec_android_getOpenglesHardwareStrings(vendor, renderer, version);
}

// -----------------------------------------------------------------------------
// libgfxstream_backend In-Memory Patching & Watchdog
// -----------------------------------------------------------------------------
static const uintptr_t OFFSET_GLDISPATCH_GLGETSTRING  = 0xb59e48;
static const uintptr_t OFFSET_GLDISPATCH_GLGETSTRINGI = 0xb5a8a8;

// std::string slots in GLEScontext:
// Slot 1: GLES 1 / 2
static const uintptr_t OFFSET_GLES1_VENDOR   = 0xb5a000 + 0xec8;
static const uintptr_t OFFSET_GLES1_RENDERER = 0xb5a000 + 0xee0;
static const uintptr_t OFFSET_GLES1_VERSION  = 0xb5a000 + 0xef8;
// Slot 2: GLES 3.1
static const uintptr_t OFFSET_GLES31_VENDOR   = 0xb5a000 + 0xf10;
static const uintptr_t OFFSET_GLES31_RENDERER = 0xb5a000 + 0xf28;
static const uintptr_t OFFSET_GLES31_VERSION  = 0xb5a000 + 0xf40;
// Slot 3: GLES 3.0
static const uintptr_t OFFSET_GLES30_VENDOR   = 0xb5a000 + 0xf58;
static const uintptr_t OFFSET_GLES30_RENDERER = 0xb5a000 + 0xf70;
static const uintptr_t OFFSET_GLES30_VERSION  = 0xb5a000 + 0xf88;

static volatile uintptr_t s_gfxstream_base = 0;

static void patch_gfxstream_memory() {
    uintptr_t base = s_gfxstream_base;
    if (!base) return;

    // 1. Dispatch table function pointers
    void** p_dispatch_getstring = (void**)(base + OFFSET_GLDISPATCH_GLGETSTRING);
    void** p_dispatch_getstringi = (void**)(base + OFFSET_GLDISPATCH_GLGETSTRINGI);
    if (*p_dispatch_getstring != (void*)&sec_glGetString) {
        *p_dispatch_getstring = (void*)&sec_glGetString;
    }
    if (*p_dispatch_getstringi != (void*)&sec_glGetStringi) {
        *p_dispatch_getstringi = (void*)&sec_glGetStringi;
    }

    // 2. Overwrite the std::string objects
    uintptr_t vendor_slots[] = {
        base + OFFSET_GLES1_VENDOR,
        base + OFFSET_GLES31_VENDOR,
        base + OFFSET_GLES30_VENDOR
    };
    uintptr_t renderer_slots[] = {
        base + OFFSET_GLES1_RENDERER,
        base + OFFSET_GLES31_RENDERER,
        base + OFFSET_GLES30_RENDERER
    };
    uintptr_t version_slots[] = {
        base + OFFSET_GLES1_VERSION,
        base + OFFSET_GLES31_VERSION,
        base + OFFSET_GLES30_VERSION
    };

    for (int i = 0; i < 3; i++) {
        std::string* v = (std::string*)vendor_slots[i];
        std::string* r = (std::string*)renderer_slots[i];
        std::string* ver = (std::string*)version_slots[i];

        // Check if emulator wrote default/wrapped strings
        if (r->find("Translator") != std::string::npos ||
            r->find("Google") != std::string::npos ||
            r->find("SwiftShader") != std::string::npos ||
            r->empty()) {
            *v   = SPOOF_VENDOR;
            *r   = SPOOF_RENDERER;
            *ver = SPOOF_VERSION;
            log_msg("[SEC_GPU] Sanitized slot %d: Vendor=%s, Renderer=%s, Version=%s\n",
                    i, v->c_str(), r->c_str(), ver->c_str());
        }
    }
}

static void* gpu_watchdog_thread(void* arg) {
    log_msg("[SEC_GPU] Watchdog thread started.\n");
    int count = 0;
    while (1) {
        if (s_gfxstream_base) {
            patch_gfxstream_memory();
        }
        // Poll every 30ms for the first 30 seconds (1000 iterations), then 500ms thereafter
        if (count < 1000) {
            usleep(30000);
            count++;
        } else {
            usleep(500000);
        }
    }
    return NULL;
}

static void on_image_added(const struct mach_header* mh, intptr_t vmaddr_slide) {
    uint32_t count = _dyld_image_count();
    for (uint32_t i = 0; i < count; i++) {
        const char* name = _dyld_get_image_name(i);
        if (name && strstr(name, "libgfxstream_backend.dylib")) {
            if (!s_gfxstream_base) {
                intptr_t slide = _dyld_get_image_vmaddr_slide(i);
                s_gfxstream_base = (uintptr_t)slide;
                log_msg("[SEC_GPU] Detected libgfxstream_backend.dylib at slide 0x%lx\n", (unsigned long)s_gfxstream_base);
                patch_gfxstream_memory();
            }
            break;
        }
    }
}

__attribute__((constructor))
static void sec_gpu_interposer_init() {
    log_msg("[SEC_GPU] Initializing Host-Side GPU Interposer...\n");
    init_real_functions();

    // Check if libgfxstream_backend is already loaded
    uint32_t count = _dyld_image_count();
    for (uint32_t i = 0; i < count; i++) {
        const char* name = _dyld_get_image_name(i);
        if (name && strstr(name, "libgfxstream_backend.dylib")) {
            intptr_t slide = _dyld_get_image_vmaddr_slide(i);
            s_gfxstream_base = (uintptr_t)slide;
            log_msg("[SEC_GPU] Found libgfxstream_backend.dylib at slide 0x%lx\n", (unsigned long)s_gfxstream_base);
            patch_gfxstream_memory();
            break;
        }
    }

    // Register callback for dynamically loaded images
    _dyld_register_func_for_add_image(on_image_added);

    // Launch background watchdog thread
    pthread_t th;
    pthread_create(&th, NULL, gpu_watchdog_thread, NULL);
    pthread_detach(th);
    log_msg("[SEC_GPU] Host-Side GPU Interposer initialized successfully.\n");
}
