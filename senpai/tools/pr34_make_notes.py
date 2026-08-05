#!/usr/bin/env python3
"""Compose the five per-level r2 submission notes from the shared body.

Each official note must be at least 5 KiB, so every level reuses the common
rationale and appends only its own configuration, role and pre-registered
prediction.
"""
import pathlib

HERE = pathlib.Path(__file__).resolve().parents[2] / "research" / "tanjiro-pr34"

PRED = {
    0: ("0 (definitional anchor)", "0 (definitional anchor)", "0 (definitional anchor)"),
    400: ("0.82", "0 (below knee 461)", "0 (below knee 1198)"),
    800: ("1.74", "0.89", "0 (below knee 1198)"),
    1600: ("3.58", "2.98", "0.91"),
    2400: ("5.42", "5.06", "2.73"),
}

ROLE = {
    0: (
        "Zero-injection anchor. This is the reference `T(0)` that every other level "
        "in the series is differenced against, and it is also a fourth free replicate "
        "of the promoted frontier in an official session. It must reproduce the "
        "frontier timing to within the 0.4% window noise; if it does not, the whole "
        "series is void and we will report that instead of a fit."
    ),
    400: (
        "First loaded level, and the sole discriminator for `H_sat`. Only `H_sat` "
        "predicts a non-zero reading here, and it predicts 0.82 ms, which is 34 "
        "standard deviations of the 0.024 ms differencing noise. A zero reading at "
        "this level falsifies `H_sat` outright and tells us the shipped step is not "
        "already dispatch-bound."
    ),
    800: (
        "The three-way discriminator, and the single most informative level in the "
        "series. `H_sat` predicts 1.74 ms, `H_gpu` predicts 0.89 ms, and `H_cpu` "
        "predicts exactly zero. Those three predictions are separated by 36 and 37 "
        "standard deviations of the differencing noise, so this one reading assigns "
        "the machine to a branch on its own."
    ),
    1600: (
        "Lower slope point. It is above the knee under all three hypotheses, so it is "
        "the lower anchor of the linear segment from which `c` is fitted. It is also "
        "the level that separates `H_cpu` from a still larger slack: `H_cpu` predicts "
        "0.91 ms here, and a zero reading would push the knee past 1600 and imply "
        "even more spare dispatch capacity than we expect."
    ),
    2400: (
        "Upper slope point. Paired with the 1600 level it yields the slope "
        "`c = (dT(2400) - dT(1600)) / 800` with a standard error of about 0.030 us. "
        "It also bounds the knee from above: under every hypothesis this level is "
        "well past saturation, so a zero reading here would falsify the law itself "
        "rather than any one branch of it."
    ),
}

TEMPLATE = """
## This receipt

| setting | value |
| --- | --- |
| injected empty dispatches per single-token decode step | **{n}** |
| threadgroups per injected dispatch | 8 (256 threads each) |
| injected dispatches per multi-token prefill forward | 0 |
| spread across the 40 layer boundaries | yes |
| shipped real dispatches per decode step | ~406 (unchanged) |
| absolute dispatches per step | ~{total} |

This is set by editing two default integer literals and nothing else:
`DARKBLOOM_INJECT_DECODE_EMPTY` = {n} and `DARKBLOOM_INJECT_EMPTY_TG` = 8.

### Role of this level in the series

{role}

### Pre-registered prediction for this level

| hypothesis | predicted dT at {n} injected dispatches, ms |
| --- | --- |
| `H_sat` | {h_sat} |
| `H_gpu` | {h_gpu} |
| `H_cpu` | {h_cpu} |

These numbers were committed before this receipt was submitted, so whichever
reading comes back, the branch it selects was named in advance.
"""


def main() -> None:
    common = (HERE / "note-r2-common.md").read_text()
    for n, (h_sat, h_gpu, h_cpu) in PRED.items():
        body = common + TEMPLATE.format(
            n=n, total=406 + n, role=ROLE[n], h_sat=h_sat, h_gpu=h_gpu, h_cpu=h_cpu
        )
        path = HERE / f"note-r2-n{n}.md"
        path.write_text(body)
        size = len(body.encode())
        assert size >= 5120, f"{path.name} is {size} B, below the 5 KiB official minimum"
        print(f"{path.name} {size} bytes ok")


if __name__ == "__main__":
    main()
