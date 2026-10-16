# Flash Device Pinning Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Bind the prepared local SSD launcher to the approved disk throughout the existing flasher's pre-write checks.

**Architecture:** The ignored local launcher supplies a literal `lsblk -P` fingerprint using a new optional `--expected-fingerprint` argument. The common flasher compares its initial fingerprint with that value; its existing before-write and after-write equality checks preserve the binding. This is a fail-closed check, not a guarantee against disconnecting hardware between the final check and opening the device.

**Tech Stack:** Bash, Python unittest, existing lsblk/bmaptool workflow.

**Spec:** [Approved scope](#approved-scope).

## Approved scope

The user approved preparing the launcher for the completed minimal image. Review found that a replacement during the flasher's setup could become its accepted baseline. Add the smallest compatible host-tool safety check; do not flash a disk in this task.

## Global Constraints

- Keep actual device identifiers and Wi-Fi credentials out of tracked files.
- Do not modify reference firmware, image recipes, image artifacts, or build gates.
- Preserve the existing implementation worktree and unrelated outer `.gitignore` edit.
- Do not commit or change the image's source HEAD during this launcher preparation.
- Tests must never invoke real privileged flashing or write a block device.

## Task 1: Pin the flasher's baseline and connect the local launcher

**Files:**
- Modify: `scripts/flash-ssd.sh`
- Test: `tests/host/test_flash_contract.py`
- Modify (ignored, outside this worktree): `../../flash-rpi5-minimal.local.sh`
- Test (ignored): `.state/test-local-flash-launcher.py`

**Interfaces:**
- Consumes: `require_unchanged_device EXPECTED ACTUAL PHASE` and the existing before/after-write fingerprints.
- Produces: optional `--expected-fingerprint VALUE`; mismatches terminate before `bmaptool copy`, absent option preserves compatibility.

- [x] Add a behavioral regression test that sources the real pre-write section with fake lsblk, uv, and bmaptool functions. The confirmed fingerprint is `SERIAL="USB1"`; a setup-time replacement reports `SERIAL="USB2"` both before and after unmounting. Assert nonzero exit and no simulated write marker. Also test matching, later replacement, and absent-pin cases.
- [x] Run `.venv/bin/python -m unittest discover -s tests/host -p test_flash_contract.py -q`; confirm the setup-time replacement test fails before implementation.
- [x] Parse `--expected-fingerprint`, requiring a nonempty argument. Immediately after capturing `fingerprint_before`, add:

```bash
if [[ -n "$expected_fingerprint" ]]; then
    require_unchanged_device \
        "$expected_fingerprint" "$fingerprint_before" "since confirmation"
fi
```

- [x] Add the exact observed fingerprint only to the ignored launcher and forward it as a quoted argument. Update its isolated argument-forwarding test.
- [x] Run syntax checks, both host flash/block-device test modules, and the isolated launcher suite. Run the real launcher with `--check` only. Confirm no flash PASS marker exists, review the diff for secrets, and obtain follow-up independent review.
- [x] Hand off the terminal command and new confirmation prompt; leave changes uncommitted and explicitly state that the SSD has not been written.

## Verification result

Host flasher tests: 12 passed. Block-device tests: 7 passed. Isolated local launcher tests: 12 passed. Both shell syntax checks, real read-only launcher check, secret-exclusion check, and independent review passed. No block-device write was performed; no flash PASS marker was created. Image recipes and source HEAD are unchanged.
