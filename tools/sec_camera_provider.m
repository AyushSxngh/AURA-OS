// =============================================================================
// File: tools/sec_camera_provider.m
// Purpose: Intercepts QEMU MacCamera and VerMacCamera AVFoundation capture feed
//          and injects SEC DeepFake frames directly into Android's Camera HAL.
//          Features:
//            - Lock-Free Triple Buffering (Version 3) — 100% tear-free
//            - Thread-safe static holdover buffer (zero raw-webcam flicker/leakage)
//            - Precomputed coordinate LUT scaling (<2ms latency)
//            - Exact 32ARGB / BGRA / RGBA / NV12 color channel placement
// =============================================================================

#import <Foundation/Foundation.h>
#import <AVFoundation/AVFoundation.h>
#import <CoreMedia/CoreMedia.h>
#import <CoreVideo/CoreVideo.h>
#import <objc/runtime.h>
#import <sys/mman.h>
#import <sys/stat.h>
#import <fcntl.h>
#import <unistd.h>
#import <time.h>
#import <pthread.h>
#import <Accelerate/Accelerate.h>
#import <os/lock.h>
#import <dlfcn.h>

#define SEC_MAGIC 0x41555241 // 'SEC'
#define SHM_PATH "/tmp/sec_cam_shm"
#define LOG_PATH "/tmp/sec_camera_provider.log"

struct __attribute__((packed)) AuraCamHeader {
    uint32_t magic;                 // 0x41555241 ('SEC')
    uint32_t version;               // 1, 2, or 3
    uint32_t width;                 // width in pixels
    uint32_t height;                // height in pixels
    uint32_t stride;                // bytes per row
    uint32_t format;                // 0 = BGR24, 1 = BGRA32, 2 = RGB24
    uint64_t timestamp_ms;          // epoch ms
    uint32_t data_size;             // byte size of pixel data
    uint32_t frame_seq;             // incrementing frame counter
    volatile uint32_t latest_ready_buf;     // 0, 1, or 2 (version 3)
    volatile uint32_t consumer_reading_buf; // 0, 1, 2, or 0xFFFFFFFF (version 3)
    uint32_t buffer_stride;         // offset between buffers
    uint32_t num_buffers;           // number of buffers (3)
    uint8_t  reserved[8];
};

static void (*orig_MacCamera_captureOutput)(id, SEL, AVCaptureOutput*, CMSampleBufferRef, AVCaptureConnection*) = NULL;
static void (*orig_VerMacCamera_captureOutput)(id, SEL, AVCaptureOutput*, CMSampleBufferRef, AVCaptureConnection*) = NULL;
static int (*orig_MacCamera_startCapturing)(id, SEL, const char*, int, int, const char*) = NULL;
static void (*orig_MacCamera_processCameraFrame)(id, SEL, CMSampleBufferRef, int) = NULL;

static int shm_fd = -1;
static void* shm_ptr = MAP_FAILED;
static size_t shm_size = 0;

// Thread-safe static holdover buffer (no dynamic realloc -> zero heap crashes)
static pthread_mutex_t s_hook_mutex = PTHREAD_MUTEX_INITIALIZER;
static uint8_t s_last_frame[1920 * 1080 * 4];
static size_t s_last_dw = 0;
static size_t s_last_dh = 0;
static size_t s_last_dbpr = 0;
static bool s_has_last_frame = false;
static uint64_t s_last_df_time_ms = 0;

static void hook_log(const char* fmt, ...) {
    FILE* f = fopen(LOG_PATH, "a");
    if (!f) return;
    va_list args;
    va_start(args, fmt);
    vfprintf(f, fmt, args);
    va_end(args);
    fclose(f);
}

static uint64_t get_current_time_ms(void) {
    struct timespec ts;
    clock_gettime(CLOCK_REALTIME, &ts);
    return (uint64_t)ts.tv_sec * 1000 + (uint64_t)ts.tv_nsec / 1000000;
}

static const char* s_candidate_shm_paths[] = {
    "/tmp/sec_cam_shm",
    "/tmp/aura_cam_shm",
    NULL
};

static const uint8_t* get_shared_frame(struct AuraCamHeader** out_hdr, uint32_t* out_buf_idx) {
    if (shm_fd < 0 || shm_ptr == MAP_FAILED) {
        for (int i = 0; s_candidate_shm_paths[i] != NULL; i++) {
            shm_fd = open(s_candidate_shm_paths[i], O_RDWR);
            if (shm_fd < 0) {
                shm_fd = open(s_candidate_shm_paths[i], O_RDONLY);
            }
            if (shm_fd >= 0) break;
        }
        if (shm_fd < 0) return NULL;
        
        struct stat st;
        if (fstat(shm_fd, &st) != 0 || st.st_size < (off_t)sizeof(struct AuraCamHeader)) {
            close(shm_fd);
            shm_fd = -1;
            return NULL;
        }
        shm_size = (size_t)st.st_size;
        shm_ptr = mmap(NULL, shm_size, PROT_READ | PROT_WRITE, MAP_SHARED, shm_fd, 0);
        if (shm_ptr == MAP_FAILED) {
            shm_ptr = mmap(NULL, shm_size, PROT_READ, MAP_SHARED, shm_fd, 0);
            if (shm_ptr == MAP_FAILED) {
                close(shm_fd);
                shm_fd = -1;
                return NULL;
            }
        }
    }
    
    struct AuraCamHeader* hdr = (struct AuraCamHeader*)shm_ptr;
    if (hdr->magic != SEC_MAGIC) {
        return NULL;
    }
    
    uint64_t now = get_current_time_ms();
    // Freshness check: frame must have been updated within last 3000 ms
    if (now > hdr->timestamp_ms && (now - hdr->timestamp_ms) > 3000) {
        return NULL;
    }
    
    *out_hdr = hdr;
    
    // Support version 3 Lock-Free Triple Buffering
    if (hdr->version >= 3 && hdr->buffer_stride > 0) {
        uint32_t num_bufs = hdr->num_buffers > 0 ? hdr->num_buffers : 3;
        uint32_t buf_idx = hdr->latest_ready_buf % num_bufs;
        hdr->consumer_reading_buf = buf_idx; // Announce to producer that consumer is reading this buffer
        if (out_buf_idx) *out_buf_idx = buf_idx;
        return (const uint8_t*)hdr + 64 + (buf_idx * hdr->buffer_stride);
    }
    
    // Support version 2 double-buffered ping-pong
    if (hdr->version == 2 && hdr->buffer_stride > 0) {
        uint32_t buf_idx = hdr->latest_ready_buf % 2;
        if (out_buf_idx) *out_buf_idx = buf_idx;
        return (const uint8_t*)hdr + 64 + (buf_idx * hdr->buffer_stride);
    }
    
    if (out_buf_idx) *out_buf_idx = 0;
    return (const uint8_t*)hdr + sizeof(struct AuraCamHeader);
}

static void release_shared_frame(struct AuraCamHeader* hdr) {
    if (hdr && hdr->version >= 3) {
        hdr->consumer_reading_buf = 0xFFFFFFFF;
    }
}

static void get_selfie_orientation(int* out_flip_x, int* out_flip_y) {
    static int s_flip_x = 0;
    static int s_flip_y = 0;
    static uint64_t s_last_check = 0;
    uint64_t now = get_current_time_ms();
    if (now - s_last_check > 500) {
        s_last_check = now;
        FILE* f = fopen("/tmp/sec_selfie_rotation.txt", "r");
        if (f) {
            char buf[64] = {0};
            if (fscanf(f, "%63s", buf) == 1) {
                if (strcmp(buf, "180") == 0) {
                    s_flip_x = 1;
                    s_flip_y = 1;
                } else if (strcasecmp(buf, "vflip") == 0 || strcasecmp(buf, "flip_v") == 0) {
                    s_flip_x = 0;
                    s_flip_y = 1;
                } else if (strcasecmp(buf, "hflip") == 0 || strcasecmp(buf, "flip_h") == 0) {
                    s_flip_x = 1;
                    s_flip_y = 0;
                } else {
                    // "0" or default: upright
                    s_flip_x = 0;
                    s_flip_y = 0;
                }
            }
            fclose(f);
        } else {
            s_flip_x = 0;
            s_flip_y = 0;
        }
    }
    if (out_flip_x) *out_flip_x = s_flip_x;
    if (out_flip_y) *out_flip_y = s_flip_y;
}

// Convert/scale BGR24 source to 32ARGB (0x00000020): Byte 0=A, Byte 1=R, Byte 2=G, Byte 3=B
static void copy_bgr_to_argb(const uint8_t* src, uint32_t sw, uint32_t sh,
                             uint8_t* dst, size_t dw, size_t dh, size_t dbpr) {
    if (!src || !dst || dw == 0 || dh == 0 || sw == 0 || sh == 0) return;

    int flip_x = 0, flip_y = 0;
    get_selfie_orientation(&flip_x, &flip_y);
    size_t x_map[dw];
    for (size_t x = 0; x < dw; x++) {
        size_t sx = flip_x ? (dw - 1 - x) : x;
        x_map[x] = (sx * sw / dw) * 3;
    }

    size_t src_stride = sw * 3;
    for (size_t y = 0; y < dh; y++) {
        size_t sy_idx = flip_y ? (dh - 1 - y) : y;
        size_t sy = sy_idx * sh / dh;
        const uint8_t* src_row = src + (sy * src_stride);
        uint8_t* dst_row = dst + (y * dbpr);
        for (size_t x = 0; x < dw; x++) {
            const uint8_t* sp = src_row + x_map[x];
            uint8_t* dp = dst_row + (x << 2);
            dp[0] = 255;   // Alpha
            dp[1] = sp[2]; // Red
            dp[2] = sp[1]; // Green
            dp[3] = sp[0]; // Blue
        }
    }
}

// Convert/scale BGR24 source to BGRA32: Byte 0=B, Byte 1=G, Byte 2=R, Byte 3=A
static void copy_bgr_to_bgra(const uint8_t* src, uint32_t sw, uint32_t sh,
                             uint8_t* dst, size_t dw, size_t dh, size_t dbpr) {
    if (!src || !dst || dw == 0 || dh == 0 || sw == 0 || sh == 0) return;

    int flip_x = 0, flip_y = 0;
    get_selfie_orientation(&flip_x, &flip_y);
    size_t x_map[dw];
    for (size_t x = 0; x < dw; x++) {
        size_t sx = flip_x ? (dw - 1 - x) : x;
        x_map[x] = (sx * sw / dw) * 3;
    }

    size_t src_stride = sw * 3;
    for (size_t y = 0; y < dh; y++) {
        size_t sy_idx = flip_y ? (dh - 1 - y) : y;
        size_t sy = sy_idx * sh / dh;
        const uint8_t* src_row = src + (sy * src_stride);
        uint8_t* dst_row = dst + (y * dbpr);
        for (size_t x = 0; x < dw; x++) {
            const uint8_t* sp = src_row + x_map[x];
            uint8_t* dp = dst_row + (x << 2);
            dp[0] = sp[0]; // B
            dp[1] = sp[1]; // G
            dp[2] = sp[2]; // R
            dp[3] = 255;   // A
        }
    }
}

// Convert/scale BGR24 source to RGBA32: Byte 0=R, Byte 1=G, Byte 2=B, Byte 3=A
static void copy_bgr_to_rgba(const uint8_t* src, uint32_t sw, uint32_t sh,
                             uint8_t* dst, size_t dw, size_t dh, size_t dbpr) {
    if (!src || !dst || dw == 0 || dh == 0 || sw == 0 || sh == 0) return;

    int flip_x = 0, flip_y = 0;
    get_selfie_orientation(&flip_x, &flip_y);
    size_t x_map[dw];
    for (size_t x = 0; x < dw; x++) {
        size_t sx = flip_x ? (dw - 1 - x) : x;
        x_map[x] = (sx * sw / dw) * 3;
    }

    size_t src_stride = sw * 3;
    for (size_t y = 0; y < dh; y++) {
        size_t sy_idx = flip_y ? (dh - 1 - y) : y;
        size_t sy = sy_idx * sh / dh;
        const uint8_t* src_row = src + (sy * src_stride);
        uint8_t* dst_row = dst + (y * dbpr);
        for (size_t x = 0; x < dw; x++) {
            const uint8_t* sp = src_row + x_map[x];
            uint8_t* dp = dst_row + (x << 2);
            dp[0] = sp[2]; // R
            dp[1] = sp[1]; // G
            dp[2] = sp[0]; // Blue
            dp[3] = 255;   // A
        }
    }
}

// Convert/scale BGR24 source to NV12 destination (BiPlanar Y + UV)
static void copy_bgr_to_nv12(const uint8_t* src, uint32_t sw, uint32_t sh,
                             uint8_t* dst_y, size_t dy_bpr,
                             uint8_t* dst_uv, size_t duv_bpr,
                             size_t dw, size_t dh) {
    if (!src || !dst_y || !dst_uv || dw == 0 || dh == 0 || sw == 0 || sh == 0) return;

    int flip_x = 0, flip_y = 0;
    get_selfie_orientation(&flip_x, &flip_y);
    size_t x_map[dw];
    for (size_t x = 0; x < dw; x++) {
        size_t sx = flip_x ? (dw - 1 - x) : x;
        x_map[x] = (sx * sw / dw) * 3;
    }

    size_t src_stride = sw * 3;
    for (size_t y = 0; y < dh; y++) {
        size_t sy_idx = flip_y ? (dh - 1 - y) : y;
        size_t sy = sy_idx * sh / dh;
        const uint8_t* src_row = src + (sy * src_stride);
        uint8_t* y_row = dst_y + (y * dy_bpr);
        uint8_t* uv_row = dst_uv + ((y / 2) * duv_bpr);
        
        for (size_t x = 0; x < dw; x++) {
            const uint8_t* sp = src_row + x_map[x];
            int b = sp[0];
            int g = sp[1];
            int r = sp[2];
            
            // Standard BT.601 conversion
            int y_val = ((66 * r + 129 * g + 25 * b + 128) >> 8) + 16;
            y_row[x] = (uint8_t)(y_val < 0 ? 0 : (y_val > 255 ? 255 : y_val));
            
            if ((y % 2 == 0) && (x % 2 == 0)) {
                int u_val = ((-38 * r - 74 * g + 112 * b + 128) >> 8) + 128;
                int v_val = ((112 * r - 94 * g - 18 * b + 128) >> 8) + 128;
                uv_row[x]     = (uint8_t)(u_val < 0 ? 0 : (u_val > 255 ? 255 : u_val));
                uv_row[x + 1] = (uint8_t)(v_val < 0 ? 0 : (v_val > 255 ? 255 : v_val));
            }
        }
    }
}

static void handle_capture_output(id self, SEL _cmd, AVCaptureOutput *output, CMSampleBufferRef sampleBuffer, AVCaptureConnection *connection, void (*orig_fn)(id, SEL, AVCaptureOutput*, CMSampleBufferRef, AVCaptureConnection*)) {
    BOOL is_back = NO;
    NSNumber* is_back_num = objc_getAssociatedObject(self, "is_back_camera");
    if (is_back_num) {
        is_back = [is_back_num boolValue];
    } else if (self && [self isMemberOfClass:objc_getClass("MacCamera")]) {
        if (*(int*)((uint8_t*)(__bridge void*)self + 0x40) == 1) {
            is_back = YES;
        }
    }
    if (is_back) {
        // Back camera (Document scan / OCR / Rear camera):
        // Allow the live host mobile webcam to pass through directly into Android without face-swap injection!
        static int s_back_cnt = 0;
        if (++s_back_cnt % 60 == 1) {
            hook_log("[SEC] 📄 Back Camera (Doc Scan) pass-through frame #%d\n", s_back_cnt);
        }
        if (orig_fn) {
            orig_fn(self, _cmd, output, sampleBuffer, connection);
        }
        return;
    }

    struct AuraCamHeader* hdr = NULL;
    uint32_t active_buf = 0;
    const uint8_t* src_pixels = get_shared_frame(&hdr, &active_buf);
    
    if (sampleBuffer) {
        CVPixelBufferRef pixelBuffer = CMSampleBufferGetImageBuffer(sampleBuffer);
        if (pixelBuffer && CVPixelBufferLockBaseAddress(pixelBuffer, 0) == kCVReturnSuccess) {
            OSType fmt = CVPixelBufferGetPixelFormatType(pixelBuffer);
            size_t dw = CVPixelBufferGetWidth(pixelBuffer);
            size_t dh = CVPixelBufferGetHeight(pixelBuffer);
            size_t dbpr = CVPixelBufferGetBytesPerRow(pixelBuffer);
            uint8_t* dst = (uint8_t*)CVPixelBufferGetBaseAddress(pixelBuffer);
            
            static int frame_count = 0;
            if (++frame_count % 120 == 1 && hdr) {
                hook_log("[SEC] Frame #%d intercepted (%s): fmt=0x%08x dw=%zu dh=%zu v=%d buf=%d age=%llums\n",
                         frame_count, object_getClassName(self),
                         (unsigned int)fmt, dw, dh,
                         hdr->version, active_buf,
                         get_current_time_ms() - hdr->timestamp_ms);
            }

            if (hdr && src_pixels) {
                // We have a fresh DeepFake frame — render it
                if (CVPixelBufferIsPlanar(pixelBuffer)) {
                    uint8_t* dst_y = (uint8_t*)CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 0);
                    uint8_t* dst_uv = (uint8_t*)CVPixelBufferGetBaseAddressOfPlane(pixelBuffer, 1);
                    size_t dy_bpr = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 0);
                    size_t duv_bpr = CVPixelBufferGetBytesPerRowOfPlane(pixelBuffer, 1);
                    if (dst_y && dst_uv) {
                        copy_bgr_to_nv12(src_pixels, hdr->width, hdr->height, dst_y, dy_bpr, dst_uv, duv_bpr, dw, dh);
                    }
                } else if (dst) {
                    if (fmt == 0x00000020 /* kCVPixelFormatType_32ARGB */) {
                        copy_bgr_to_argb(src_pixels, hdr->width, hdr->height, dst, dw, dh, dbpr);
                    } else if (fmt == kCVPixelFormatType_32BGRA || fmt == 0x42475234) {
                        copy_bgr_to_bgra(src_pixels, hdr->width, hdr->height, dst, dw, dh, dbpr);
                    } else if (fmt == kCVPixelFormatType_32RGBA || fmt == 0x72676261) {
                        copy_bgr_to_rgba(src_pixels, hdr->width, hdr->height, dst, dw, dh, dbpr);
                    } else {
                        copy_bgr_to_argb(src_pixels, hdr->width, hdr->height, dst, dw, dh, dbpr);
                    }

                    // Save to static holdover buffer (thread-safe, no realloc)
                    size_t req_size = dh * dbpr;
                    if (req_size <= sizeof(s_last_frame)) {
                        pthread_mutex_lock(&s_hook_mutex);
                        memcpy(s_last_frame, dst, req_size);
                        s_last_dw = dw;
                        s_last_dh = dh;
                        s_last_dbpr = dbpr;
                        s_has_last_frame = true;
                        s_last_df_time_ms = get_current_time_ms();
                        pthread_mutex_unlock(&s_hook_mutex);
                    }
                }
                release_shared_frame(hdr);
            } else {
                // If DeepFake is momentarily between frames, hold the last frame for up to 2 seconds.
                // If DeepFake is stopped/idle, allow live webcam to pass through naturally.
                uint64_t now = get_current_time_ms();
                pthread_mutex_lock(&s_hook_mutex);
                if (s_has_last_frame && (now - s_last_df_time_ms) < 2000) {
                    if (dst && s_last_dw == dw && s_last_dh == dh && s_last_dbpr == dbpr) {
                        memcpy(dst, s_last_frame, dh * dbpr);
                    }
                } else {
                    s_has_last_frame = false;
                }
                pthread_mutex_unlock(&s_hook_mutex);
            }
            
            CVPixelBufferUnlockBaseAddress(pixelBuffer, 0);
        }
    }
    
    if (orig_fn) {
        orig_fn(self, _cmd, output, sampleBuffer, connection);
    }
}


static float get_docscan_zoom(void) {
    static float s_zoom = 1.0f;
    static uint64_t s_last_check = 0;
    uint64_t now = get_current_time_ms();
    if (now - s_last_check > 500) {
        s_last_check = now;
        FILE* f = fopen("/tmp/sec_zoom.txt", "r");
        if (f) {
            float z = 1.0f;
            if (fscanf(f, "%f", &z) == 1 && z >= 0.3f && z <= 3.0f) {
                s_zoom = z;
            }
            fclose(f);
        }
    }
    return s_zoom;
}

static int get_docscan_rotation(void) {
    static int s_rot = 180;
    static uint64_t s_last_check = 0;
    uint64_t now = get_current_time_ms();
    if (now - s_last_check > 500) {
        s_last_check = now;
        FILE* f = fopen("/tmp/sec_rotation.txt", "r");
        if (f) {
            int r = 180;
            if (fscanf(f, "%d", &r) == 1) {
                s_rot = r;
            }
            fclose(f);
        }
    }
    return s_rot;
}

// Full-frame scaler: scales the ENTIRE uncropped source frame to destination without cutting off any borders
static void scale_full_frame(
    const uint8_t* src, size_t sw, size_t sh, size_t sbpr,
    uint8_t* dst, size_t dw, size_t dh, size_t dbpr,
    int rot_deg, float zoom_factor)
{
    if (!src || !dst || sw == 0 || sh == 0 || dw == 0 || dh == 0) return;
    
    if (zoom_factor < 0.3f) zoom_factor = 0.3f;
    if (zoom_factor > 3.0f) zoom_factor = 3.0f;
    
    float inv_z = 1.0f / zoom_factor;
    float center_x = (float)sw * 0.5f;
    float center_y = (float)sh * 0.5f;
    float half_x = (float)sw * 0.5f * inv_z;
    float half_y = (float)sh * 0.5f * inv_z;
    
    float min_x = center_x - half_x;
    float max_x = center_x + half_x;
    float min_y = center_y - half_y;
    float max_y = center_y + half_y;
    
    int r = ((rot_deg % 360) + 360) % 360;
    
    if (r == 0 || r == 180) {
        size_t lut_x[dw];
        for (size_t dx = 0; dx < dw; dx++) {
            float fx = (float)dx / (float)(dw > 1 ? dw - 1 : 1);
            if (r == 180) fx = 1.0f - fx;
            float sxf = min_x + fx * (max_x - min_x);
            if (sxf < 0.0f) sxf = 0.0f;
            if (sxf >= (float)sw) sxf = (float)sw - 1.0f;
            lut_x[dx] = ((size_t)sxf) << 2; // 4 bytes per pixel
        }
        
        for (size_t dy = 0; dy < dh; dy++) {
            float fy = (float)dy / (float)(dh > 1 ? dh - 1 : 1);
            if (r == 180) fy = 1.0f - fy;
            float syf = min_y + fy * (max_y - min_y);
            if (syf < 0.0f) syf = 0.0f;
            if (syf >= (float)sh) syf = (float)sh - 1.0f;
            size_t sy = (size_t)syf;
            
            const uint8_t* src_row = src + (sy * sbpr);
            uint32_t* dst_row = (uint32_t*)(dst + (dy * dbpr));
            
            for (size_t dx = 0; dx < dw; dx++) {
                dst_row[dx] = *(const uint32_t*)(src_row + lut_x[dx]);
            }
        }
    } else { // r == 90 or r == 270
        size_t lut_y[dw];
        for (size_t dx = 0; dx < dw; dx++) {
            float fx = (float)dx / (float)(dw > 1 ? dw - 1 : 1);
            if (r == 90) fx = 1.0f - fx;
            float syf = min_y + fx * (max_y - min_y);
            if (syf < 0.0f) syf = 0.0f;
            if (syf >= (float)sh) syf = (float)sh - 1.0f;
            lut_y[dx] = (size_t)syf;
        }
        
        for (size_t dy = 0; dy < dh; dy++) {
            float fy = (float)dy / (float)(dh > 1 ? dh - 1 : 1);
            if (r == 270) fy = 1.0f - fy;
            float sxf = min_x + fy * (max_x - min_x);
            if (sxf < 0.0f) sxf = 0.0f;
            if (sxf >= (float)sw) sxf = (float)sw - 1.0f;
            size_t sx_offset = ((size_t)sxf) << 2;
            
            uint32_t* dst_row = (uint32_t*)(dst + (dy * dbpr));
            for (size_t dx = 0; dx < dw; dx++) {
                const uint8_t* src_pixel = src + (lut_y[dx] * sbpr) + sx_offset;
                dst_row[dx] = *(const uint32_t*)src_pixel;
            }
        }
    }
}

static void hooked_MacCamera_processCameraFrame(id self, SEL _cmd, CMSampleBufferRef sampleBuffer, int orientation) {
    if (orig_MacCamera_processCameraFrame) {
        orig_MacCamera_processCameraFrame(self, _cmd, sampleBuffer, orientation);
    }
}

static int hooked_MacCamera_startCapturing(id self, SEL _cmd, const char* device_name, int width, int height, const char* direction) {
    BOOL is_back = NO;
    if (direction && (strcasecmp(direction, "back") == 0 || strstr(direction, "back") != NULL)) {
        is_back = YES;
    }
    
    objc_setAssociatedObject(self, "is_back_camera", @(is_back), OBJC_ASSOCIATION_RETAIN_NONATOMIC);
    
    const char* effective_device = device_name;
    if (is_back) {
        FILE* f = fopen("/tmp/sec_docscan_cam.txt", "r");
        if (f) {
            char choice[64] = {0};
            if (fscanf(f, "%63s", choice) == 1) {
                if (strcasecmp(choice, "mac") == 0 || strcasecmp(choice, "macbook") == 0) {
                    effective_device = "6C707041-05AC-0011-0003-000000000001"; // MacBook Air Camera
                } else if (strcasecmp(choice, "iriun") == 0) {
                    effective_device = "5A0B78EA-4C72-485C-B87D-086EC8E5E180"; // Iriun Camera
                }
            }
            fclose(f);
        } else {
            effective_device = "6C707041-05AC-0011-0003-000000000001";
        }
    }
    
    hook_log("[SEC] 📷 MacCamera startCapturing: orig_dev=%s -> effective_dev=%s, %dx%d, direction=%s -> is_back=%d\n",
             device_name ? device_name : "(null)", effective_device, width, height, direction ? direction : "(null)", is_back);
    
    if (orig_MacCamera_startCapturing) {
        return orig_MacCamera_startCapturing(self, _cmd, effective_device, width, height, direction);
    }
    return 0;
}

static void hooked_MacCamera_captureOutput(id self, SEL _cmd, AVCaptureOutput *output, CMSampleBufferRef sampleBuffer, AVCaptureConnection *connection) {
    handle_capture_output(self, _cmd, output, sampleBuffer, connection, orig_MacCamera_captureOutput);
}

static void hooked_VerMacCamera_captureOutput(id self, SEL _cmd, AVCaptureOutput *output, CMSampleBufferRef sampleBuffer, AVCaptureConnection *connection) {
    handle_capture_output(self, _cmd, output, sampleBuffer, connection, orig_VerMacCamera_captureOutput);
}

typedef int (*fn_camera_enumerate_devices)(void* info_array, int max_cameras);
typedef void (*fn_camera_info_copy)(void* dst, const void* src);
typedef void (*fn_camera_info_done)(void* info);

static void ensure_dual_cameras(void) {
    void* sym_init = dlsym(RTLD_DEFAULT, "android_camera_service_init");
    fn_camera_enumerate_devices p_enum = (fn_camera_enumerate_devices)dlsym(RTLD_DEFAULT, "camera_enumerate_devices");
    fn_camera_info_copy p_copy = (fn_camera_info_copy)dlsym(RTLD_DEFAULT, "camera_info_copy");
    fn_camera_info_done p_done = (fn_camera_info_done)dlsym(RTLD_DEFAULT, "camera_info_done");

    if (!sym_init) {
        hook_log("[SEC] ⚠️ android_camera_service_init not found\n");
        return;
    }
    uint8_t* s_cameraService = (uint8_t*)sym_init + 0x24e0a94;
    uint32_t* p_cam_count = (uint32_t*)(s_cameraService + 0x240);
    hook_log("[SEC] 🔍 s_cameraService=%p, current count=%u\n", s_cameraService, *p_cam_count);

    if (*p_cam_count == 1) {
        uint8_t* cam0 = s_cameraService;
        uint8_t* cam1 = s_cameraService + 0x48;

        const char* cam0_chan = *(const char**)(cam0 + 0x18);
        const char* cam0_dir = *(const char**)(cam0 + 0x28);
        hook_log("[SEC] 📷 Cam 0: chan=%s, dir=%s\n", cam0_chan ? cam0_chan : "(null)", cam0_dir ? cam0_dir : "(null)");

        int registered = 0;
        if (p_enum && p_copy && p_done) {
            uint8_t enum_devs[8 * 0x48];
            memset(enum_devs, 0, sizeof(enum_devs));
            int num_found = p_enum(enum_devs, 8);
            hook_log("[SEC] 🔎 Enumerated %d host camera devices\n", num_found);

            int matched_idx = -1;
            for (int i = 0; i < num_found; i++) {
                uint8_t* dev = enum_devs + (i * 0x48);
                const char* disp_name = *(const char**)(dev + 0x08);
                const char* dev_id = *(const char**)(dev + 0x10);
                const char* inp_chan = *(const char**)(dev + 0x18);
                hook_log("[SEC]    Dev[%d]: name='%s', id='%s', chan='%s'\n", i, disp_name ? disp_name : "", dev_id ? dev_id : "", inp_chan ? inp_chan : "");
                if ((inp_chan && strcmp(inp_chan, "webcam1") == 0) || (disp_name && strstr(disp_name, "MacBook") != NULL)) {
                    matched_idx = i;
                }
            }

            if (matched_idx >= 0) {
                uint8_t* dev1 = enum_devs + (matched_idx * 0x48);
                p_copy(cam1, dev1);
                // Set WebCameraDevice ops vtable from cam0
                *(const void**)(cam1 + 0x00) = *(const void**)(cam0 + 0x00);
                // Update channel index to 1
                *(uint32_t*)(cam1 + 0x20) = 1;
                // Set direction to "front"
                if (*(void**)(cam1 + 0x28)) free(*(void**)(cam1 + 0x28));
                *(char**)(cam1 + 0x28) = strdup("front");
                // Set sensor_orientation to 90 degrees (native Android portrait front camera)
                *(uint32_t*)(cam1 + 0x30) = 90;
                *(uint32_t*)(cam1 + 0x44) = 0; // in_use = 0

                *p_cam_count = 2;
                registered = 1;
                hook_log("[SEC] 🎉 Successfully registered Dual Cameras in QEMU! count=2 (Back + Front)\n");
            }

            // Cleanup temporary enumerated devices
            for (int i = 0; i < num_found; i++) {
                p_done(enum_devs + (i * 0x48));
            }
        }

        if (!registered) {
            // Robust fallback if camera_enumerate_devices failed
            memcpy(cam1, cam0, 0x48);
            *(const void**)(cam1 + 0x00) = *(const void**)(cam0 + 0x00);
            *(char**)(cam1 + 0x08) = strdup("MacBook Air Camera");
            *(char**)(cam1 + 0x10) = strdup("6C707041-05AC-0011-0003-000000000001");
            *(char**)(cam1 + 0x18) = strdup("webcam1");
            *(uint32_t*)(cam1 + 0x20) = 1;
            *(uint32_t*)(cam1 + 0x24) = *(uint32_t*)(cam0 + 0x24);
            *(char**)(cam1 + 0x28) = strdup("front");
            *(uint32_t*)(cam1 + 0x30) = 90;
            *(uint32_t*)(cam1 + 0x34) = 0;
            uint32_t dims_cnt = *(uint32_t*)(cam0 + 0x40);
            uint32_t* dims_src = *(uint32_t**)(cam0 + 0x38);
            if (dims_cnt > 0 && dims_src) {
                uint32_t* dims_dst = (uint32_t*)malloc(dims_cnt * 8);
                if (dims_dst) {
                    memcpy(dims_dst, dims_src, dims_cnt * 8);
                    *(uint32_t**)(cam1 + 0x38) = dims_dst;
                }
            }
            *(uint32_t*)(cam1 + 0x44) = 0;
            *p_cam_count = 2;
            hook_log("[SEC] 🎉 Successfully registered Dual Cameras in QEMU (fallback)! count=2 (Back + Front)\n");
        }
    } else {
        hook_log("[SEC] ℹ️ Camera count already %u\n", *p_cam_count);
    }
}

static void* camera_monitor_thread(void* arg) {
    (void)arg;
    hook_log("[SEC] 🧵 Camera monitor thread started in PID %d...\n", getpid());
    void* sym = dlsym(RTLD_DEFAULT, "android_camera_service_init");
    if (!sym) {
        hook_log("[SEC] ⚠️ android_camera_service_init not found in monitor thread\n");
        return NULL;
    }
    uint8_t* s_cameraService = (uint8_t*)sym + 0x24e0a94;
    uint32_t* p_cam_count = (uint32_t*)(s_cameraService + 0x240);

    for (int i = 0; i < 1200; i++) { // 1200 * 25ms = 30 seconds
        usleep(25000); // 25ms
        if (*p_cam_count >= 1) {
            hook_log("[SEC] 🎯 Detected camera service initialized with %u cameras (after %d ms)\n", *p_cam_count, (i + 1) * 25);
            ensure_dual_cameras();
            break;
        }
    }
    return NULL;
}

__attribute__((constructor)) static void init_sec_camera_provider(void) {
    hook_log("[SEC] 🚀 Initializing SEC camera hook in PID %d...\n", getpid());

    pthread_t tid;
    if (pthread_create(&tid, NULL, camera_monitor_thread, NULL) == 0) {
        pthread_detach(tid);
    }

    Class mc = objc_getClass("MacCamera");
    if (mc) {
        SEL sel = @selector(captureOutput:didOutputSampleBuffer:fromConnection:);
        Method m = class_getInstanceMethod(mc, sel);
        if (m) {
            orig_MacCamera_captureOutput = (void*)method_getImplementation(m);
            method_setImplementation(m, (IMP)hooked_MacCamera_captureOutput);
            hook_log("[SEC] ✅ Hooked MacCamera captureOutput\n");
        }

        SEL sel_sc = @selector(startCapturing:width:height:direction:);
        Method m_sc = class_getInstanceMethod(mc, sel_sc);
        if (m_sc) {
            orig_MacCamera_startCapturing = (void*)method_getImplementation(m_sc);
            method_setImplementation(m_sc, (IMP)hooked_MacCamera_startCapturing);
            hook_log("[SEC] ✅ Hooked MacCamera startCapturing:width:height:direction:\n");
        }

        SEL sel_pcf = @selector(processCameraFrame:orientation:);
        Method m_pcf = class_getInstanceMethod(mc, sel_pcf);
        if (m_pcf) {
            orig_MacCamera_processCameraFrame = (void*)method_getImplementation(m_pcf);
            method_setImplementation(m_pcf, (IMP)hooked_MacCamera_processCameraFrame);
            hook_log("[SEC] ✅ Hooked MacCamera processCameraFrame:orientation:\n");
        }
    }

    Class vmc = objc_getClass("VerMacCamera");
    if (vmc) {
        SEL sel = @selector(captureOutput:didOutputSampleBuffer:fromConnection:);
        Method m = class_getInstanceMethod(vmc, sel);
        if (m) {
            orig_VerMacCamera_captureOutput = (void*)method_getImplementation(m);
            method_setImplementation(m, (IMP)hooked_VerMacCamera_captureOutput);
            hook_log("[SEC] ✅ Hooked VerMacCamera captureOutput\n");
        }
    }
}
