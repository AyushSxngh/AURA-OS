#!/system/bin/sh
# ==============================================================================
# sec_mask_goldfish_drivers.sh
# Masks QEMU and Goldfish kernel drivers, device nodes, and sysfs/proc artifacts
# to evade emulator detection checks used by banking, lending, and security SDKs.
# Compatible with standalone root, init.d, and Magisk (post-fs-data / service.sh).
# ==============================================================================

set +e

LOG_TAG="SEC_GOLDFISH_MASK"
log_info() {
    echo "[$LOG_TAG] $1"
    log -t "$LOG_TAG" "$1" 2>/dev/null || true
}

log_info "Starting Goldfish & QEMU driver filesystem masking..."

# ------------------------------------------------------------------------------
# 1. Clean and Cloak Device Nodes in /dev
# ------------------------------------------------------------------------------
# Ensure legacy QEMU pipes/sockets do not exist
rm -f /dev/qemu_pipe 2>/dev/null
rm -f /dev/socket/qemud 2>/dev/null
rm -f /dev/qemu_trace 2>/dev/null

# Mask active Goldfish character devices
# Restrict permissions (000) so non-root apps receive ENOENT / EACCES
GOLDFISH_NODES="
/dev/goldfish_pipe
/dev/goldfish_pipe_dprctd
/dev/goldfish_sync
/dev/goldfish_address_space
"

for node in $GOLDFISH_NODES; do
    if [ -e "$node" ]; then
        chmod 000 "$node" 2>/dev/null
        chown root:root "$node" 2>/dev/null
        log_info "Cloaked device node: $node (chmod 000)"
    fi
done

# ------------------------------------------------------------------------------
# 2. Cloak Platform Drivers in /sys/bus/platform/drivers/
# ------------------------------------------------------------------------------
# Anti-fraud SDKs probe: /sys/bus/platform/drivers/goldfish_pipe, goldfish-battery, etc.
# Bind-mount an empty directory over each detected goldfish driver directory.
EMPTY_DIR="/data/local/tmp/.empty_mask"
mkdir -p "$EMPTY_DIR" 2>/dev/null
chmod 755 "$EMPTY_DIR" 2>/dev/null

SYS_DRIVERS="/sys/bus/platform/drivers"
if [ -d "$SYS_DRIVERS" ]; then
    for driver in "$SYS_DRIVERS"/goldfish*; do
        if [ -d "$driver" ]; then
            mount -o bind "$EMPTY_DIR" "$driver" 2>/dev/null || true
            log_info "Masked platform driver: $driver"
        fi
    done
fi

# ------------------------------------------------------------------------------
# 3. Cloak Platform Devices in /sys/devices/platform/
# ------------------------------------------------------------------------------
SYS_DEVICES="/sys/devices/platform"
if [ -d "$SYS_DEVICES" ]; then
    for dev in "$SYS_DEVICES"/goldfish* "$SYS_DEVICES"/*.goldfish_* "$SYS_DEVICES"/*goldfish*; do
        if [ -d "$dev" ]; then
            mount -o bind "$EMPTY_DIR" "$dev" 2>/dev/null || true
            log_info "Masked platform device: $dev"
        fi
    done
fi

# ------------------------------------------------------------------------------
# 4. Sanitize /proc/interrupts (Remove Goldfish IRQ lines)
# ------------------------------------------------------------------------------
# Anti-fraud checks grep /proc/interrupts for "goldfish"
if [ -r /proc/interrupts ]; then
    PROC_DIR="/data/local/tmp/.proc_mask"
    mkdir -p "$PROC_DIR" 2>/dev/null
    CLEAN_IRQS="$PROC_DIR/interrupts"
    
    # Filter out goldfish interrupt handlers
    grep -v -i "goldfish" /proc/interrupts > "$CLEAN_IRQS" 2>/dev/null || true
    if [ -s "$CLEAN_IRQS" ]; then
        chmod 444 "$CLEAN_IRQS" 2>/dev/null
        mount -o bind "$CLEAN_IRQS" /proc/interrupts 2>/dev/null || true
        log_info "Sanitized /proc/interrupts (Goldfish IRQs filtered)"
    fi
fi

# ------------------------------------------------------------------------------
# 5. Clean up any remaining traces in /system/bin or /vendor/bin
# ------------------------------------------------------------------------------
# Ensure qemu-props is not directly executable by untrusted apps
if [ -f /system/bin/qemu-props ]; then
    chmod 000 /system/bin/qemu-props 2>/dev/null || true
fi

log_info "Goldfish & QEMU kernel driver masking completed successfully."
