# Remote Raspberry Pi 5 Validation

USB-to-UART is not part of this project. The normal route uses wired Ethernet,
mDNS/DHCP discovery, key-only SSH, persistent journals, and bounded retries.
HDMI stays disconnected unless the five minutes network deadline expires.

The Pi must already be assembled and powered as described by the preceding
[USB SSD runbook](usb-ssd-bringup.md).

## First boot and phase-1 acceptance

Start the clock immediately before applying power:

```bash
BUILD_ID="$(cat .state/active-build-id)"
read -r -p 'Press Enter, then immediately apply power: '
BOOT_WAIT_START="$SECONDS"
RPI_IP="$(./scripts/discover-rpi5.sh --hostname rpi5-minimal --timeout 300)"
ssh-keyscan -T 3 -H "$RPI_IP" > .state/rpi5-initial-known-hosts
ssh -i keys/rpi5_admin -o BatchMode=yes -o StrictHostKeyChecking=yes \
  -o UserKnownHostsFile=.state/rpi5-initial-known-hosts \
  "rpiadmin@$RPI_IP" true
BOOT_WAIT_ELAPSED=$((SECONDS - BOOT_WAIT_START))
test "$BOOT_WAIT_ELAPSED" -le 180
./scripts/test-rpi5.sh --build-id "$BUILD_ID" --host "$RPI_IP"
test -f "artifacts/$BUILD_ID/rpi5-test/PASS"
```

Expected: key-only SSH is ready within 180 seconds. Acceptance verifies
`aarch64`, Raspberry Pi 5 identity, matching build ID, systemd, wired
DHCP/default route, `/dev/sda2` on USB transport, writable root, locked
password/root SSH, and exactly three reboots recovered within 120 seconds each.

If there is no network signal after five minutes, perform one local HDMI and
power inspection. Record the displayed state and power indication before
changing anything. Use the [EEPROM recovery exception](eeprom-recovery.md) only
when that inspection specifically indicates a bootloader or USB-boot problem.

After phase-1 PASS, continue with
[Camera Module 3 Wide validation](camera-validation.md).
