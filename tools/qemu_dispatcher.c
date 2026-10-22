#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <unistd.h>
#include <sys/stat.h>
#include <libgen.h>
#include <time.h>
#include <fcntl.h>
#include <mach-o/dyld.h>

#define ORIGINAL_QEMU_NAME "qemu-system-aarch64.orig"
#define DEFAULT_TAC "35847289"
#define IMEI_OFFSET1 0x1a2187d
#define IMEI_OFFSET2 0x1a449d5
#define IMSI_OFFSET 0x1a449c5
#define NUMERIC_OFFSET 0x1a4442a
#define WIFI_SSID_OFFSET 0x1a241da
#define TARGET_IMSI "404450000000000"
#define TARGET_NUMERIC "40445"
#define BOOTSTATE_OFFSET 26579131
#define SERIAL_OFFSET 26579168
#define DEFAULT_SERIAL "R5CWJGSHJ0D"

// Luhn algorithm check digit
static int luhn_check_digit(const char* d14) {
    int total = 0;
    for (int i = 0; i < 14; i++) {
        int n = d14[i] - '0';
        if (i % 2 == 1) {
            n *= 2;
            if (n > 9) n -= 9;
        }
        total += n;
    }
    return (10 - (total % 10)) % 10;
}

// Generate 15-digit Luhn-compliant IMEI with Samsung S24 Ultra TAC
static void generate_imei(char* out_imei) {
    srand((unsigned int)(time(NULL) ^ getpid()));
    int serial = 100000 + (rand() % 900000);
    char d14[16];
    snprintf(d14, sizeof(d14), "%s%06d", DEFAULT_TAC, serial);
    int check = luhn_check_digit(d14);
    snprintf(out_imei, 16, "%s%d", d14, check);
}

// Ensure AVD has an imei.txt
static void get_or_create_imei(const char* avd_dir, char* out_imei) {
    char imei_path[1024];
    snprintf(imei_path, sizeof(imei_path), "%s/imei.txt", avd_dir);
    FILE* f = fopen(imei_path, "r");
    if (f) {
        if (fgets(out_imei, 16, f)) {
            out_imei[strcspn(out_imei, "\r\n")] = 0;
            fclose(f);
            if (strlen(out_imei) == 15) return;
        } else {
            fclose(f);
        }
    }
    // Generate new IMEI
    generate_imei(out_imei);
    f = fopen(imei_path, "w");
    if (f) {
        fprintf(f, "%s\n", out_imei);
        fclose(f);
    }
}

// Ensure AVD has a serial number from device_identity.ini or default
static void get_or_create_serial(const char* avd_dir, char* out_serial) {
    char id_path[1024];
    snprintf(id_path, sizeof(id_path), "%s/device_identity.ini", avd_dir);
    FILE* f = fopen(id_path, "r");
    if (f) {
        char line[256];
        while (fgets(line, sizeof(line), f)) {
            if (strncmp(line, "serialno=", 9) == 0) {
                char* val = line + 9;
                val[strcspn(val, "\r\n")] = 0;
                if (strlen(val) > 0) {
                    strncpy(out_serial, val, 16);
                    out_serial[16] = '\0';
                    fclose(f);
                    return;
                }
            }
        }
        fclose(f);
    }
    strncpy(out_serial, DEFAULT_SERIAL, 16);
    out_serial[16] = '\0';
}

// Check if instance binary exists and matches target IMEI, verifiedbootstate=green, and target serial
static int is_instance_binary_valid(const char* bin_path, const char* target_imei, const char* target_serial) {
    FILE* f = fopen(bin_path, "rb");
    if (!f) return 0;
    if (fseek(f, IMEI_OFFSET2, SEEK_SET) != 0) {
        fclose(f);
        return 0;
    }
    char buf[16] = {0};
    size_t read_bytes = fread(buf, 1, 15, f);
    if (read_bytes != 15 || memcmp(buf, target_imei, 15) != 0) {
        fclose(f);
        return 0;
    }
    if (fseek(f, BOOTSTATE_OFFSET, SEEK_SET) != 0) {
        fclose(f);
        return 0;
    }
    char boot_buf[37] = {0};
    read_bytes = fread(boot_buf, 1, 36, f);
    if (read_bytes != 36 || memcmp(boot_buf, "androidboot.verifiedbootstate=green\0", 36) != 0) {
        fclose(f);
        return 0;
    }
    if (fseek(f, SERIAL_OFFSET, SEEK_SET) != 0) {
        fclose(f);
        return 0;
    }
    char ser_buf[18] = {0};
    read_bytes = fread(ser_buf, 1, 17, f);
    fclose(f);
    if (read_bytes == 17 && strncmp(ser_buf, target_serial, strlen(target_serial)) == 0) {
        return 1;
    }
    return 0;
}

// Provision instance-specific QEMU binary
static int provision_instance_binary(const char* orig_path, const char* instance_path, const char* target_imei, const char* target_serial) {
    char cmd[2048];
    // APFS clone copy (instantaneous, 0 duplicate bytes)
    snprintf(cmd, sizeof(cmd), "cp -c \"%s\" \"%s\"", orig_path, instance_path);
    int ret = system(cmd);
    if (ret != 0) {
        snprintf(cmd, sizeof(cmd), "cp \"%s\" \"%s\"", orig_path, instance_path);
        ret = system(cmd);
        if (ret != 0) {
            fprintf(stderr, "[dispatcher] cp failed: %d (cmd: %s)\n", ret, cmd);
            return 0;
        }
    }

    // Patch IMEI, IMSI, Numeric, VerifiedBootState, and Serial Number at offsets
    FILE* f = fopen(instance_path, "r+b");
    if (!f) {
        fprintf(stderr, "[dispatcher] fopen failed for %s\n", instance_path);
        return 0;
    }
    if (fseek(f, IMEI_OFFSET1, SEEK_SET) == 0) {
        fwrite(target_imei, 1, 15, f);
    }
    if (fseek(f, IMEI_OFFSET2, SEEK_SET) == 0) {
        fwrite(target_imei, 1, 15, f);
    }
    if (fseek(f, IMSI_OFFSET, SEEK_SET) == 0) {
        fwrite(TARGET_IMSI, 1, 15, f);
    }
    if (fseek(f, NUMERIC_OFFSET, SEEK_SET) == 0) {
        fwrite(TARGET_NUMERIC, 1, 6, f);
    }
    if (fseek(f, WIFI_SSID_OFFSET, SEEK_SET) == 0) {
        fwrite("Galaxy_WiFi", 1, 11, f);
    }
    if (fseek(f, BOOTSTATE_OFFSET, SEEK_SET) == 0) {
        fwrite("androidboot.verifiedbootstate=green\0", 1, 36, f);
    }
    if (fseek(f, SERIAL_OFFSET, SEEK_SET) == 0) {
        char ser_buf[18] = {0};
        snprintf(ser_buf, sizeof(ser_buf), "%s", target_serial);
        fwrite(ser_buf, 1, 17, f);
    }
    fclose(f);

    // Re-sign with ad-hoc signature preserving entitlements
    snprintf(cmd, sizeof(cmd), "codesign -s - --force --preserve-metadata=entitlements \"%s\" >/dev/null 2>&1", instance_path);
    ret = system(cmd);
    if (ret != 0) {
        fprintf(stderr, "[dispatcher] codesign failed: %d\n", ret);
        return 0;
    }
    return 1;
}

int main(int argc, char** argv) {
    // 1. Determine the QEMU darwin-aarch64 directory
    char self_path[1024];
    uint32_t size = sizeof(self_path);
    if (_NSGetExecutablePath(self_path, &size) != 0) {
        strncpy(self_path, argv[0], sizeof(self_path) - 1);
        self_path[sizeof(self_path) - 1] = '\0';
    }

    char self_copy[1024];
    strncpy(self_copy, self_path, sizeof(self_copy) - 1);
    self_copy[sizeof(self_copy) - 1] = '\0';

    char qemu_dir[1024];
    strncpy(qemu_dir, dirname(self_copy), sizeof(qemu_dir) - 1);
    qemu_dir[sizeof(qemu_dir) - 1] = '\0';

    char orig_path[1024];
    snprintf(orig_path, sizeof(orig_path), "%s/%s", qemu_dir, ORIGINAL_QEMU_NAME);

    // 2. Ensure DYLD_LIBRARY_PATH includes emulator lib64 and qt
    char default_dyld[2048];
    snprintf(default_dyld, sizeof(default_dyld), "%s/../../lib64:%s/../../lib64/qt/lib", qemu_dir, qemu_dir);
    const char* cur_dyld = getenv("DYLD_LIBRARY_PATH");
    if (!cur_dyld || strlen(cur_dyld) == 0) {
        setenv("DYLD_LIBRARY_PATH", default_dyld, 1);
    } else {
        char combined_dyld[4096];
        snprintf(combined_dyld, sizeof(combined_dyld), "%s:%s", default_dyld, cur_dyld);
        setenv("DYLD_LIBRARY_PATH", combined_dyld, 1);
    }

    // 2b. Inject Samsung Camera Provider & Adreno GPU Interposer
    const char* cam_hook = "/Users/ayush/Desktop/HEBB NETWORK/Emulator/tools/libsec_camera_provider.dylib";
    const char* gpu_hook = "/Users/ayush/Desktop/HEBB NETWORK/Emulator/tools/libsec_gpu_interposer.dylib";
    char combined_hooks[8192] = {0};
    if (access(cam_hook, R_OK) == 0 && access(gpu_hook, R_OK) == 0) {
        snprintf(combined_hooks, sizeof(combined_hooks), "%s:%s", cam_hook, gpu_hook);
    } else if (access(cam_hook, R_OK) == 0) {
        snprintf(combined_hooks, sizeof(combined_hooks), "%s", cam_hook);
    } else if (access(gpu_hook, R_OK) == 0) {
        snprintf(combined_hooks, sizeof(combined_hooks), "%s", gpu_hook);
    }

    if (strlen(combined_hooks) > 0) {
        const char* cur_insert = getenv("DYLD_INSERT_LIBRARIES");
        if (!cur_insert || strlen(cur_insert) == 0) {
            setenv("DYLD_INSERT_LIBRARIES", combined_hooks, 1);
        } else {
            char final_insert[16384];
            snprintf(final_insert, sizeof(final_insert), "%s:%s", combined_hooks, cur_insert);
            setenv("DYLD_INSERT_LIBRARIES", final_insert, 1);
        }
    }

    // 2c. Ensure dual physical hardware cameras & hardware specifications (8 cores, 12GB RAM):
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-camera-back") == 0 && i + 1 < argc) {
            argv[i + 1] = "webcam0";
        } else if (strcmp(argv[i], "-camera-front") == 0 && i + 1 < argc) {
            argv[i + 1] = "webcam1";
        } else if (strcmp(argv[i], "-memory") == 0 && i + 1 < argc) {
            argv[i + 1] = "12288";
        } else if (strcmp(argv[i], "-cores") == 0 && i + 1 < argc) {
            argv[i + 1] = "8";
        } else if (strcmp(argv[i], "-prop") == 0 && i + 1 < argc) {
            if (strncmp(argv[i + 1], "ro.build.version.sdk=", 21) == 0) {
                argv[i + 1] = "ro.build.version.sdk=34";
            } else if (strncmp(argv[i + 1], "ro.system.build.version.sdk=", 28) == 0) {
                argv[i + 1] = "ro.system.build.version.sdk=34";
            }
        }
    }

    // 3. Check for -android-hw or -avd argument
    const char* hw_ini = NULL;
    const char* avd_flag_name = NULL;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-android-hw") == 0 && i + 1 < argc) {
            hw_ini = argv[i + 1];
        } else if (strcmp(argv[i], "-avd") == 0 && i + 1 < argc) {
            avd_flag_name = argv[i + 1];
        }
    }

    char avd_dir[1024] = {0};
    char avd_name[256] = {0};

    if (hw_ini) {
        char hw_copy[1024];
        strncpy(hw_copy, hw_ini, sizeof(hw_copy) - 1);
        hw_copy[sizeof(hw_copy) - 1] = '\0';
        strncpy(avd_dir, dirname(hw_copy), sizeof(avd_dir) - 1);

        char avd_copy[1024];
        strncpy(avd_copy, avd_dir, sizeof(avd_copy) - 1);
        strncpy(avd_name, basename(avd_copy), sizeof(avd_name) - 1);
        char* dot = strstr(avd_name, ".avd");
        if (dot) *dot = '\0';
    } else if (avd_flag_name) {
        strncpy(avd_name, avd_flag_name, sizeof(avd_name) - 1);
        const char* avd_home = getenv("ANDROID_AVD_HOME");
        if (avd_home && strlen(avd_home) > 0) {
            snprintf(avd_dir, sizeof(avd_dir), "%s/%s.avd", avd_home, avd_name);
        } else {
            const char* home = getenv("HOME");
            snprintf(avd_dir, sizeof(avd_dir), "%s/.android/avd/%s.avd", home ? home : "", avd_name);
        }
        // Verify directory exists
        struct stat st;
        if (stat(avd_dir, &st) != 0 || !S_ISDIR(st.st_mode)) {
            avd_dir[0] = '\0';
        }
    }

    if (avd_dir[0] == '\0' || avd_name[0] == '\0') {
        // Direct launch without identifiable AVD, pass directly to original QEMU
        execv(orig_path, argv);
        perror("Failed to exec original QEMU");
        return 1;
    }

    // 5. Get or generate unique IMEI and Serial for this instance
    char imei[16] = {0};
    get_or_create_imei(avd_dir, imei);

    char serialno[32] = {0};
    get_or_create_serial(avd_dir, serialno);

    // 6. Instance binary path inside the AVD directory
    char instance_path[1024];
    snprintf(instance_path, sizeof(instance_path), "%s/qemu-system-aarch64.%s", avd_dir, avd_name);

    // 7. Verify or provision instance binary
    if (!is_instance_binary_valid(instance_path, imei, serialno)) {
        if (!provision_instance_binary(orig_path, instance_path, imei, serialno)) {
            // Fallback to original QEMU if provisioning fails
            execv(orig_path, argv);
            return 1;
        }
    }

    // 7a. Intercept GPU mode: translate 'host' to 'swiftshader_indirect' to eliminate Apple Metal leaks
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-gpu") == 0 && i + 1 < argc) {
            const char* env_gpu = getenv("AURA_GPU_MODE");
            if (env_gpu && strlen(env_gpu) > 0) {
                argv[i + 1] = (char*)env_gpu;
            } else if (strcmp(argv[i + 1], "host") == 0) {
                argv[i + 1] = "swiftshader_indirect";
            }
        }
    }

    // 7b. Inject Samsung Hardware Wi-Fi network parameters (Gateway, Subnet IP, DNS)
    int has_wifi_opts = 0;
    int has_net_opts = 0;
    for (int i = 1; i < argc; i++) {
        if (strcmp(argv[i], "-wifi-user-mode-options") == 0) {
            has_wifi_opts = 1;
        } else if (strcmp(argv[i], "-network-user-mode-options") == 0) {
            has_net_opts = 1;
        }
    }

    char wifi_opt_str[512] = {0};
    if (!has_wifi_opts || !has_net_opts) {
        FILE* f = fopen("/tmp/sec_wifi_state.json", "r");
        if (f) {
            char buf[2048] = {0};
            size_t r = fread(buf, 1, sizeof(buf) - 1, f);
            fclose(f);
            if (r > 0) {
                char* gw_pos = strstr(buf, "\"gateway\": \"");
                char gw[64] = {0};
                if (gw_pos) {
                    gw_pos += 12;
                    char* end = strchr(gw_pos, '\"');
                    if (end && (end - gw_pos < 60)) {
                        strncpy(gw, gw_pos, end - gw_pos);
                    }
                }
                char* cidr_pos = strstr(buf, "\"net_cidr\": \"");
                char net_cidr[64] = {0};
                if (cidr_pos) {
                    cidr_pos += 13;
                    char* end = strchr(cidr_pos, '\"');
                    if (end && (end - cidr_pos < 60)) {
                        strncpy(net_cidr, cidr_pos, end - cidr_pos);
                    }
                }
                char* phone_pos = strstr(buf, "\"phone_ip\": \"");
                char phone_ip[64] = {0};
                if (phone_pos) {
                    phone_pos += 13;
                    char* end = strchr(phone_pos, '\"');
                    if (end && (end - phone_pos < 60)) {
                        strncpy(phone_ip, phone_pos, end - phone_pos);
                    }
                }
                if (strlen(gw) > 0 && strlen(net_cidr) > 0 && strlen(phone_ip) > 0) {
                    snprintf(wifi_opt_str, sizeof(wifi_opt_str), "net=%s,host=%s,dhcpstart=%s", net_cidr, gw, phone_ip);
                } else if (strlen(gw) > 0) {
                    snprintf(wifi_opt_str, sizeof(wifi_opt_str), "host=%s,dhcpstart=10.11.12.92", gw);
                }
            }
        }
    }

    // 7c. Ensure Samsung Galaxy S24 Ultra hardware identity & verified boot properties are present
    const char* default_props[] = {
        "ro.boot.verifiedbootstate=green",
        "ro.boot.flash.locked=1",
        "ro.boot.vbmeta.device_state=locked",
        "ro.boot.warranty_bit=0",
        "ro.warranty_bit=0",
        "ro.boot.veritymode=enforcing",
        "ro.product.model=SM-S928B",
        "ro.product.manufacturer=Samsung",
        "ro.product.brand=samsung",
        "ro.product.device=e3q",
        "ro.product.name=e3qxeea",
        "ro.build.product=e3q",
        "ro.soc.manufacturer=Qualcomm",
        "ro.soc.model=SM8650",
        "ro.build.flavor=e3qxeea-user",
        "ro.build.version.release=16",
        "ro.build.version.sdk=34",
        "ro.system.build.version.sdk=34",
        "ro.build.version.security_patch=2026-09-05",
        "ro.build.characteristics=phone",
        "ro.serialno=R5CWJGSHJ0D",
        "ro.debuggable=0",
        "ro.secure=1"
    };
    int num_props = sizeof(default_props) / sizeof(default_props[0]);
    int missing_prop_indices[32];
    int missing_props_count = 0;

    for (int p = 0; p < num_props; p++) {
        int found = 0;
        char prop_prefix[128] = {0};
        const char* eq = strchr(default_props[p], '=');
        if (eq) {
            size_t klen = eq - default_props[p];
            if (klen < sizeof(prop_prefix) - 2) {
                strncpy(prop_prefix, default_props[p], klen);
                prop_prefix[klen] = '=';
                prop_prefix[klen + 1] = '\0';
            }
        }
        for (int i = 1; i < argc; i++) {
            if (strcmp(argv[i], "-prop") == 0 && i + 1 < argc) {
                if (strncmp(argv[i + 1], prop_prefix, strlen(prop_prefix)) == 0) {
                    found = 1;
                    break;
                }
            }
        }
        if (!found) {
            missing_prop_indices[missing_props_count++] = p;
        }
    }

    char** final_argv = argv;
    int extra_count = 0;
    if (strlen(wifi_opt_str) > 0 && !has_wifi_opts) {
        extra_count += 2;
    }
    if (strlen(wifi_opt_str) > 0 && !has_net_opts) {
        extra_count += 2;
    }
    extra_count += missing_props_count * 2;

    if (extra_count > 0) {
        final_argv = (char**)malloc(sizeof(char*) * (argc + extra_count + 1));
        for (int i = 0; i < argc; i++) {
            final_argv[i] = argv[i];
        }
        int cur = argc;
        if (strlen(wifi_opt_str) > 0 && !has_wifi_opts) {
            final_argv[cur++] = "-wifi-user-mode-options";
            final_argv[cur++] = strdup(wifi_opt_str);
        }
        if (strlen(wifi_opt_str) > 0 && !has_net_opts) {
            final_argv[cur++] = "-network-user-mode-options";
            final_argv[cur++] = strdup(wifi_opt_str);
        }
        for (int p = 0; p < missing_props_count; p++) {
            final_argv[cur++] = "-prop";
            final_argv[cur++] = (char*)default_props[missing_prop_indices[p]];
        }
        final_argv[cur] = NULL;
    }

    // 7d. Ensure background autonomous supervisor is running
    system("pgrep -f sec_daemon_supervisor.sh >/dev/null 2>&1 || nohup \"/Users/ayush/Desktop/HEBB NETWORK/Emulator/tools/sec_daemon_supervisor.sh\" >/tmp/sec_supervisor.log 2>&1 &");

    // 8. Launch instance binary
    execv(instance_path, final_argv);
    perror("Failed to exec instance QEMU");
    return 1;
}
