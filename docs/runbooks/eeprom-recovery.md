# EEPROM Recovery Exception

This is an **exception path**, not a normal boot medium or a planned hands-on
session. Enter it only after the remote five-minute deadline and one HDMI
inspection indicate a bootloader or USB-boot failure. Preserve the validated
SSD and all evidence unchanged.

1. On a separate workstation, use Raspberry Pi Imager's Raspberry Pi 5
   bootloader utility with USB boot selected. Write it to one clearly
   identified temporary microSD card.
2. Remove Pi power, disconnect the USB SSD, insert only the recovery card,
   attach HDMI, and power on.
3. Wait for the documented success screen or LED pattern. Remove power and
   the temporary microSD immediately after success.
4. If a Raspberry Pi OS diagnostic card is required, run
   `sudo rpi-eeprom-config`, record `BOOT_ORDER`, and require its hexadecimal
   sequence to contain digit `4` for USB-MSD. Power off and remove the card
   before normal testing.
5. On the x86 host, confirm the bridge remains stable as USB mass storage. If
   failure occurs only with UAS, replace the bridge or enclosure first. A
   kernel quirk requires a separate hardware-compatibility feature and review.
6. Reconnect the unchanged USB SSD and retry the five-minute discovery once.
7. Record the recovery date, displayed result, power supply, EEPROM version,
   `BOOT_ORDER`, bridge model, and whether USB boot resumed.

Do not add a UART step. Do not repeatedly rewrite the SSD or EEPROM. If no
success indication appears or USB-MSD digit `4` cannot be confirmed, stop and
investigate power, cable, enclosure compatibility, and board condition.

Return to [remote validation](remote-validation.md) only after removing the
recovery media.
