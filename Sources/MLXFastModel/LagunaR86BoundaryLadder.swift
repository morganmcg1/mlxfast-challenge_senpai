import Foundation
import MLX

// MARK: - R86-B in-situ boundary-price ladder (research-only, never shipped)
//
// Injects `DARKBLOOM_R86_INSERTS` genuine dependent round trips of the live
// hidden row into every single-token decode layer boundary, so the marginal
// price of one kernel boundary can be read off the slope inside the real
// decode step rather than on an otherwise-idle pipe.
//
//   DARKBLOOM_R86_MODE
//     unset  — stock decode path, no injection at all.
//     wide   — chain `h = h * 1` on the live [1,1,2048] bf16 hidden row.
//              Each inserted dispatch is a 4096 B read + 4096 B write that the
//              next inserted dispatch depends on: `c_issue + c_drain`.
//     tiny   — the same chain on a [1] bf16 scratch, folded back into `h` with
//              one broadcast add. Byte-free, so the slope is `c_issue` alone.
//     size   — `tiny` with the scratch width swept by DARKBLOOM_R86_WIDTH,
//              which separates the fixed boundary term from the byte term.
//   DARKBLOOM_R86_INSERTS — inserted ops per decoder layer (default 0).
//   DARKBLOOM_R86_WIDTH   — bf16 element count of the `size` scratch.
//
// `x * 1` and `x + 0` are exact identities in bf16, so every checked token is
// unchanged and the ladder measures pure boundary overhead.

let lagunaR86Mode = ProcessInfo.processInfo.environment["DARKBLOOM_R86_MODE"]

let lagunaR86Inserts =
    Int(ProcessInfo.processInfo.environment["DARKBLOOM_R86_INSERTS"] ?? "") ?? 0

let lagunaR86Width =
    Int(ProcessInfo.processInfo.environment["DARKBLOOM_R86_WIDTH"] ?? "") ?? 1

enum LagunaR86Ladder {
    // A Swift `Float` literal operand would promote the chain to FP32 and
    // change both the dtype and the traffic under test.
    nonisolated(unsafe) static let one = MLXArray([Float(1)]).asType(.bfloat16)
    nonisolated(unsafe) static let scratch = MLXArray.zeros(
        [max(1, lagunaR86Mode == "size" ? lagunaR86Width : 1)], dtype: .bfloat16)
}

@inline(never)
func lagunaR86InjectBoundaries(_ h: MLXArray) -> MLXArray {
    guard let mode = lagunaR86Mode,
        h.dtype == .bfloat16,
        h.dims(1, 1, LagunaConstants.hiddenSize)
    else { return h }
    if mode == "wide" {
        var y = h
        for _ in 0..<lagunaR86Inserts { y = y * LagunaR86Ladder.one }
        return y
    }
    guard mode == "tiny" || mode == "size" else { return h }
    var t = LagunaR86Ladder.scratch
    for _ in 0..<lagunaR86Inserts { t = t * LagunaR86Ladder.one }
    // The fold is emitted at every `k`, including `k == 0`, so its cost lands
    // in the intercept rather than the slope.
    return h + t[0..<1]
}
