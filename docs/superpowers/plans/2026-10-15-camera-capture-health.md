# Camera capture health and bounded recovery

Scope: the requested remaining-work item 1, firmware and Yocto validation.
Work in the existing checkout; preserve earlier changes. No QEMU build.

Design:
- Use steady-clock liveness: first usable frame within 10 seconds, subsequent
  frames within 5 seconds. Only actual delivered frames establish `running`.
- Publish stable error codes for no first frame and capture stall. Do not infer
  a broken cable from a timeout alone. Clear stale availability/rates on failure.
- Poll in the main lifecycle loop, outside libcamera callbacks. Serialize recovery
  with managed runtime start/stop/settings changes and the existing protection gate.
- Retry a stopped failed graph at 5-second intervals, at most 3 times. Reset the
  budget after 60 seconds of healthy capture or an explicit start/settings change.
  Keep management HTTP available after exhaustion. Manual retry must actually
  restart a self-stopped graph and remain subject to security checks.
- Show the capture problem and retry state in the existing camera status panel.
- Add a reusable, read-only, SSH-pinned runtime capture acceptance command. Require
  stable build/board/boot/PID, positive CFE and ISP progress, and no capture timeout;
  transfer counts only from privileged logs. This does not prove UI/AI acceptance.

Implementation/validation:
1. Add behavior tests for liveness boundaries, bounded retry/reset/stop, manual
   recovery and protection refusal, UI error/retry guidance, probe failures.
2. Implement firmware/API/UI changes and run targeted native/web/host checks.
3. Package exactly these changes as local Yocto patches for firmware and web.
4. Build only the requested Raspberry Pi Hailo image, verify packaged artifacts,
   document build checks separately from later physical deployment acceptance.

Result: implementation and layer packaging complete; runtime 70, HTTP 15, web 770
(with final affected 100), host probe 7 and packaging 25 tests passed. Image
20261015T185424Z-e664cb9647e7 completed; 398 WIC files and 21 changed sources
verified. Independent review issue resolved. The new image is installed;
396 readable device files and 70 independent target runtime tests passed.
Three controlled reboots passed with actual capture progress and zero errors;
the user confirmed final video/Hailo inference/detections. Hardware acceptance
is PASS, recorded separately in
`rpi-cam-hailo/docs/security/camera-capture-health-deployment-validation-2026-10-15.md`.
