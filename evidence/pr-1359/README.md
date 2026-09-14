# DisplayPort detach evidence for PR #1359

Supporting material for [NVIDIA/open-gpu-kernel-modules#1359](https://github.com/NVIDIA/open-gpu-kernel-modules/pull/1359).
The driver source on this branch is the PR submission; diagnostic patches are
stored separately below. All hardware captures were collected on 2026-09-13.

## Sources and artifacts

| Variant | Exact source |
| --- | --- |
| 610.57.04 | `e4a5faa2567f28c8eabe0ebb6422b6d0abcf37eb` |
| 615.71.09 | `61dcc93722ecb418bb5f2e00923f05b4b8051dd1` |
| PR #1359 | `bd5d6119ca1ed030ad26d06d1b3e980873ff0336` |
| Before, instrumented | 615.71.09 + patch 0001 |
| After, instrumented | 615.71.09 + patches 0001 and 0002, in that order |

- [0001-dp-recovery-diagnostics.patch](patches/0001-dp-recovery-diagnostics.patch):
  the original instrumentation used in both detailed captures. Logs existing
  flush, training, FEC and DSC results; adds no AUX transactions. Includes the
  read-only `nvidia_modeset.dp_recovery_diag` build marker.
- [0002-allow-disconnected-dp-detach.patch](patches/0002-allow-disconnected-dp-detach.patch):
  the hardware-tested fix, including `DPFIX` logging and the read-only
  `nvidia_modeset.dp_disconnected_detach_fix` marker. Its pre/post modeset code
  matches the PR after excluding a comment and the diagnostic log statement.
- [stock-debug.log](logs/stock-debug.log): the original saved excerpt from the
  unmodified 615 driver. Initial 120 Hz works; power cycling causes flush failures;
  60 Hz recovers. This saved file was already an excerpt, not a complete journal.
- [before-kernel.log](logs/before-kernel.log): complete saved diagnostic-build
  journal, originally named `patched-kernel.log`. Here “patched” meant patch 0001
  only; the disconnected-detach fix was absent.
- [after-kernel.log](logs/after-kernel.log): complete saved fixed-build journal,
  originally named `fixed-debug-kernel-2.log`.
- [test-detach.py](test-detach.py): portable control-flow harness extracting the
  actual `dpPreModeset()` and `dpPostModeset()` functions from the pinned commits.
- [sanitize-log.py](sanitize-log.py): the transformation applied to the captures.
- [SHA256SUMS](SHA256SUMS): hashes of the patches, published logs and scripts.

## Run the control-flow checks

Requires Git, Python 3 and a C++11 compiler (`g++` by default). No GPU is required.
Run these commands from the indicated repository root:

```sh
git clone --branch pr-1359-evidence https://github.com/martinstark/open-gpu-kernel-modules.git
cd open-gpu-kernel-modules
git fetch https://github.com/NVIDIA/open-gpu-kernel-modules.git tag 610.57.04 tag 615.71.09
python3 evidence/pr-1359/test-detach.py
```

When following a commit-pinned PR link, check out that evidence commit after
cloning to use the same scripts, patches and captures as the linked revision.
The harness always reads the three exact source commits above, regardless of
the current branch. It does not fetch sources or write into the checkout.
Use `--cxx clang++` to select another compiler, or `--repo /path/to/repository`
to read the commits from another clone. Compiled test files use a temporary
directory and are removed on completion.

Expected output:

```text
610: expected detach behavior and applicable guards verified
615: expected detach behavior and applicable guards verified
pr1359: expected detach behavior and applicable guards verified
These tests exercise source control flow, not GPU/firmware behavior.
```

The stock 615 case passes by reproducing its skipped detach. The other two cases
must complete detach. Checks cover connected detach, an unselected attachment
target, disconnected attachment rejection, rejection of a mixed request before
any partial detach, connector/discovery guards, forced-connected and dynamic-mux
exceptions, empty requests and all 16 detach head masks. Group attachment remains
set until the post-modeset callback, after the hardware-update boundary.

The callbacks are bookkeeping doubles. The harness does not exercise the full
DP library, AUX access, hardware updates, firmware, FEC negotiation or races.

## Recreate the instrumented driver sources

From the evidence repository root, create two disposable sibling worktrees:

```sh
git worktree add --detach ../dp1359-before 61dcc93722ecb418bb5f2e00923f05b4b8051dd1
git worktree add --detach ../dp1359-after 61dcc93722ecb418bb5f2e00923f05b4b8051dd1
git -C ../dp1359-before apply "$PWD/evidence/pr-1359/patches/0001-dp-recovery-diagnostics.patch"
git -C ../dp1359-after apply "$PWD/evidence/pr-1359/patches/0001-dp-recovery-diagnostics.patch"
git -C ../dp1359-after apply "$PWD/evidence/pr-1359/patches/0002-allow-disconnected-dp-detach.patch"
python3 evidence/pr-1359/test-detach.py --fixed-source ../dp1359-after
```

The last command must also report `fixed-source` passing. Patch 0002 is the
original instrumented fix; apply it to the 615 baseline with patch 0001, not on
top of the PR commit, which already contains the functional change.

Build each worktree with matching kernel headers, GCC, Make, binutils and pahole.
For the recorded kernel, run from each prepared worktree root:

```sh
make -j8 modules SYSSRC=/lib/modules/7.2.4-arch1-2/build
```

If the headers are unpacked elsewhere, substitute their `build` directory for
`SYSSRC`; `PAHOLE=/path/to/pahole` selects a locally unpacked pahole binary.
The original Arch build used unpacked headers and pahole, `make -j8 modules`,
and package versions `nvidia-open 615.71.09-1.1` (before) and `615.71.09-1.2`
(after). Both used NVIDIA userspace `615.71.09` and kernel `7.2.4-arch1-2`.
Install through the distribution's module packaging process, update the
initramfs if it contains NVIDIA modules, and reboot into the matching kernel.
The source patches reproduce the tested change; the commands do not promise
byte-identical packages across toolchains.

## Hardware reproduction and log capture

Recorded setup: RTX 5090, Dell U2725QE directly connected over DisplayPort,
Arch Linux, Sway/Wayland, kernel `7.2.4-arch1-2`, NVIDIA `615.71.09`.
60 Hz used 3840×2160, four lanes at 5.4 Gbit/s, DSC/FEC off.
120 Hz used 3840×2160, four lanes at 8.1 Gbit/s, DSC/FEC on.

Before testing, verify the loaded build and enable existing NVKMS logging:

```sh
cat /sys/module/nvidia_modeset/parameters/dp_recovery_diag
# The following parameter exists only in the fixed instrumented build:
cat /sys/module/nvidia_modeset/parameters/dp_disconnected_detach_fix
sudo sh -c 'echo 1 > /sys/module/nvidia_modeset/parameters/debug'
```

Each applicable marker should report `Y`.

1. Fresh boot at 60 Hz. Power the monitor off for approximately 10 seconds,
   then turn it on. The failing driver can recover the picture with stale state.
2. Select 120 Hz on the same connector. In the before capture, the monitor
   immediately reports no signal.
3. Power-cycle again at 120 Hz. In the before capture it remains dark; moving
   the cable to a different GPU connector recovers it.
4. For a direct 120 Hz test, start with working 120 Hz and power-cycle without
   moving the cable. The unmodified driver failed this scenario; the fixed
   capture shows recovery on the original connector.

Use the compositor's output configuration to select refresh rates. Record
physical actions and cable moves separately; software mode requests alone do
not establish that a power cycle happened or that a picture appeared.

Save the journal and turn off debug logging after the test:

```sh
journalctl -k -b --no-pager -o short-monotonic > capture-kernel.log
sudo sh -c 'echo 0 > /sys/module/nvidia_modeset/parameters/debug'
python3 /path/to/evidence/pr-1359/sanitize-log.py capture-kernel.log capture-public.log
```

## Reading the captures

Timestamps are seconds since boot. The before/after journals come from separate
boots and connector assignments; their timestamps and SOR numbers are not
expected to match each other.

| Before: display `0x800`, SOR 1 unless noted | Observation |
| --- | --- |
| 264.325 | Power-off at 60 Hz; device becomes zombie. No detach begin/end follows. |
| 271.752 | Rediscovery finds head 2 still attached; flush phase 1 returns `0x40`. |
| 272.171 | 60 Hz returns through the redundant-training path. |
| 280.483–280.522 | Ordinary mode change detaches head 3. |
| 280.536 | Head 2 remains attached; 120 Hz flush fails before training and sink DSC enable. |
| 294–302 | Another power cycle leaves heads 2 and 3 listed as attached. |
| 328.559–329.101 | Cable move: display `0x200`, SOR 2; 120 Hz training and DSC succeed. |

| After: display `0x200`, SOR 0 throughout the cycle | Observation |
| --- | --- |
| 362.039–362.130 | Initial 120 Hz attach succeeds. |
| 367.254 | Power-off marks the device zombie. |
| 367.274 | `DPFIX allowing disconnected detach headMask=0x8`. |
| 367.274–367.299 | Detach begin/end both execute. |
| 376.320 | Rediscovery reports `groupsEmpty=1`. |
| 376.786 | Reattach lists only the new head 3 group, `attached=0`, `dsc=1`. |
| 376.833–376.853 | First training attempt, FEC configuration and sink DSC enable succeed. |

`0x40` is `NV_ERR_INVALID_STATE`. The saved after journal has no phase-1 flush
failure, `status=0x40`, failed attach-training result or Xid. AUX, panel-wake and
lost-device errors remain during power-off/rediscovery, followed by recovery.
These errors have been retained in the published captures.

## Validation scope

- The instrumented fixed build completed the full kernel-module build, MODPOST
  and BTF generation and was installed on the test machine. Both build markers
  and the matching kernel/userspace versions were verified locally.
- The user reported successful power cycles at 60 Hz and 120 Hz. The detailed
  after capture directly verifies **one complete 120 Hz power cycle**, including
  execution of the new branch and recovery on the same connector. It does not
  contain a separately logged 60 Hz power cycle.
- The exact PR's changed translation unit compiled, and the extracted-function
  checks passed. No full diagnostic-free module build or hardware retest is
  recorded in these artifacts.
- MST, UHBR, laptop panels, other GPUs and repeated-cycle reliability were not
  hardware-validated. Mixed attach/detach requests at HPD-low retain the existing
  whole-request rejection.

The firmware-side reason for rejecting flush is not visible in this host source
tree. The trace establishes stale host bookkeeping, the returned error and its
position before training; the fixed capture connects restored detach cleanup to
successful recovery on this setup.

## Sanitization and integrity

Published logs retain every line of their saved input, including warnings,
errors, boot messages and the original monotonic timestamps. The sanitizer
replaces hostnames, UUIDs, filesystem volume IDs, MAC addresses, USB serial
numbers, home-directory usernames and zombie pointer values with placeholders.
It does not filter events or change display IDs, SORs, heads, training results,
DSC/FEC fields or status codes. It is scoped to these captures, not a general
secret scanner for arbitrary journals.

Verify published artifact hashes from this directory:

```sh
sha256sum -c SHA256SUMS
```

AI tools assisted with investigation, patch development, the harness and this
write-up. Hardware observations were supplied by the person operating the test
machine; publishing these artifacts does not represent another hardware test.
