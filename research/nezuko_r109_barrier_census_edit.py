#!/usr/bin/env python3
"""Add an intra-encoder barrier census to the already-patched GPUPROF hook.

LOCAL RESEARCH ONLY. `research/nezuko_armg_split_profile.sh` runs this after
`git apply research/nezuko-pr158-gpuprof-hook.patch` and reverts Vendor/ before
any timing run.

Why a second edit instead of one patch: the GPUPROF hook records command
buffers, which is the wrong granularity for the barrier law. An intra-encoder
dependency edge shows up as `CommandEncoder::maybeInsertBarrier()` firing
`memoryBarrier(BarrierScopeBuffers)`, which serialises the encoder at that
point. `N-INDS-DEPENDENCY-BARRIER` prices one such edge at ~2.55 us/layer, so
the count and the identity of the kernel *behind* each barrier are the direct
mechanism evidence for a decoupling change.

`current_pso_` is set by `set_compute_pipeline_state` immediately before the
dispatch, and `maybeInsertBarrier()` runs at the head of that dispatch, so at
barrier time `current_pso_` names the downstream (blocked) kernel.

Run this census at SPLIT=0 only. At SPLIT=1 every dispatch gets its own command
buffer, `commit()` resets `needs_barrier_` to false, and the census reads zero
by construction.
"""
import sys

PATH = "Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/device.cpp"

METHOD_ANCHOR = """  void register_pso(const void* pso, const std::string& name) {"""
METHOD_ADD = """  // Names the kernel stalled behind an intra-encoder memory barrier. See
  // research/nezuko_r109_barrier_census_edit.py.
  void note_barrier(const void* pso) {
    if (!enabled_) {
      return;
    }
    std::lock_guard<std::mutex> lock(mtx_);
    auto it = pso_names_.find(pso);
    fprintf(
        stderr,
        "GPUBARRIER %s\\n",
        it == pso_names_.end() ? "<unnamed>" : it->second.c_str());
  }

"""

SITE_ANCHOR = """void CommandEncoder::maybeInsertBarrier() {
  if (needs_barrier_) {
    get_command_encoder()->memoryBarrier(MTL::BarrierScopeBuffers);"""
SITE_NEW = """void CommandEncoder::maybeInsertBarrier() {
  if (needs_barrier_) {
    GpuDispatchProfiler::instance().note_barrier(current_pso_);
    get_command_encoder()->memoryBarrier(MTL::BarrierScopeBuffers);"""


def main() -> int:
    with open(PATH) as fh:
        src = fh.read()
    if "GPUBARRIER" in src:
        print("barrier census already present")
        return 0
    if "GpuDispatchProfiler" not in src:
        print("FATAL: GPUPROF hook not applied first", file=sys.stderr)
        return 2
    for anchor in (METHOD_ANCHOR, SITE_ANCHOR):
        if src.count(anchor) != 1:
            print(f"FATAL: anchor not unique ({src.count(anchor)}): "
                  f"{anchor[:60]!r}", file=sys.stderr)
            return 3
    src = src.replace(METHOD_ANCHOR, METHOD_ADD + METHOD_ANCHOR)
    src = src.replace(SITE_ANCHOR, SITE_NEW)
    with open(PATH, "w") as fh:
        fh.write(src)
    print("barrier census inserted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
