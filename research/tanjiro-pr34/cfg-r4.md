Receipt **R4 of 4**. Every block-injection knob is back to zero, and a single
input-independent probe is enabled: a fixed number of streaming reads over a
pre-allocated scratch pool is added to each decode step, where that number is
determined solely by the last character of the host's Metal architecture string
(1 for `s`, 2 for `g`, 4 otherwise). The per-read cost of that pool on this host
is already known from an earlier receipt series, so the decode-axis difference
between R4 and R1 divides cleanly into 1, 2 or 4 and reports which architecture
family the ranked host reports. That string is not observable from outside the
timed window, and MLX's own command-buffer commit heuristic branches on the same
character, so knowing it changes how the dispatch budget should be modelled.

This receipt also serves as an independent second replicate of the R1 anchor on
the prefill axis, which the probe leaves untouched, giving a direct estimate of
session-to-session drift for the series.
