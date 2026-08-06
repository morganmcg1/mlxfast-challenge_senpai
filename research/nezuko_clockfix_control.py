#!/usr/bin/env python3
"""Control run for the PR #158 clock fix: prove the failure detector fires.

`decode_probe.mach_now()` uses CLOCK_UPTIME_RAW so the driver's per-step spans
share an epoch with `MTLCommandBuffer.GPUStartTime`. PR #158 §4.1.d found that
CPython 3.9 on macOS puts `time.perf_counter()` on a process-relative epoch,
which silently produces an empty correlation window instead of an error.

This wrapper deliberately reinstates the broken instrument. Run it under
`/usr/bin/python3` (CPython 3.9) with DARKBLOOM_GPU_PROFILE=1 and --profile:
`decode_probe.analyze_profile` must print WINDOW CORRELATION FAILED. A green
profiled run is only evidence that the clock is right if this control is also
shown to go red.
"""
import os
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import decode_probe  # noqa: E402

print(f"clock control: python {sys.version.split()[0]}, "
      f"mach_now -> time.perf_counter (deliberately broken); "
      f"offset perf_counter - CLOCK_UPTIME_RAW = "
      f"{time.perf_counter() - time.clock_gettime(time.CLOCK_UPTIME_RAW):.6f} s",
      flush=True)
decode_probe.mach_now = time.perf_counter
sys.exit(decode_probe.main())
