// Static derivation of the _nax gather-GEMM kernel name string.
//
// This host (M4 Pro, Apple GPU generation 16) can never enter the _nax
// dispatch path, so the emitted kernel name cannot be captured at runtime.
// Instead this program reproduces the naming logic byte-for-byte:
//   * concatenate<>  is copied verbatim from
//       Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/utils.h:47-69
//   * the kname block is copied verbatim from
//       Vendor/mlx-swift/Source/Cmlx/mlx/mlx/backend/metal/quantized.cpp:1477-1510
// and drives it with the value table that the runtime would produce for the
// two Laguna routed shapes at BN=64 (current default) and BN=128 (candidate).
//
// Build:  c++ -std=c++17 -O0 research/r105a_kname_derive.cpp -o /tmp/r105a_kname

#include <cstdio>
#include <string>
#include <type_traits>

// --- verbatim from mlx/backend/metal/utils.h ---------------------------------
template <typename T>
constexpr bool is_numeric_except_char = std::is_arithmetic_v<T> &&
    !std::is_same_v<T, char> && !std::is_same_v<T, signed char> &&
    !std::is_same_v<T, unsigned char> && !std::is_same_v<T, wchar_t>;

template <typename T>
void concatenate(std::string& acc, T first) {
  if constexpr (is_numeric_except_char<T>) {
    acc += std::to_string(first);
  } else {
    acc += first;
  }
}

template <typename T, typename... Args>
void concatenate(std::string& acc, T first, Args... args) {
  if constexpr (is_numeric_except_char<T>) {
    acc += std::to_string(first);
  } else {
    acc += first;
  }
  concatenate(acc, args...);
}
// -----------------------------------------------------------------------------

struct Vals {
  std::string label;
  std::string mode;
  std::string type_string;
  bool static_expert_shape;
  bool expert_aligned;
  bool transpose;
  int group_size;
  int bits;
  int bm, bn, bk, wm, wn;
  int K, N;
  int egroups;
  bool expert_widest;
  bool expert_wideld;
  int expert_pairwise_scale_layout;
};

static std::string derive(const Vals& v) {
  const std::string& mode = v.mode;
  const std::string& type_string = v.type_string;
  const bool static_expert_shape = v.static_expert_shape;
  const bool expert_aligned = v.expert_aligned;
  const bool transpose = v.transpose;
  const int group_size = v.group_size;
  const int bits = v.bits;
  const int bm = v.bm, bn = v.bn, bk = v.bk, wm = v.wm, wn = v.wn;
  const int K = v.K, N = v.N;
  const int egroups = v.egroups;
  const bool expert_widest = v.expert_widest;
  const bool expert_wideld = v.expert_wideld;
  const int expert_pairwise_scale_layout = v.expert_pairwise_scale_layout;

  // --- verbatim from mlx/backend/metal/quantized.cpp:1477-1510 ---------------
  std::string kname;
  kname.reserve(64);
  concatenate(
      kname,
      mode +
          (static_expert_shape
               ? "_gather_qmm_rhs_expert_static_nax_nt_"
               : (expert_aligned
                      ? "_gather_qmm_rhs_expert_nax_nt_"
               : (transpose ? "_gather_qmm_rhs_nax_nt_"
                            : "_gather_qmm_rhs_nax_nn_"))),
      type_string,
      "_gs_",
      group_size,
      "_b_",
      bits,
      "_bm_",
      bm,
      "_bn_",
      bn,
      "_bk_",
      bk,
      "_wm_",
      wm,
      "_wn_",
      wn,
      static_expert_shape
          ? ("_k_" + std::to_string(K) + "_n_" + std::to_string(N))
          : "",
      expert_aligned
          ? ("_eg_" + std::to_string(egroups) + (expert_widest ? "_ws_1" : "_ws_0") +
             (expert_wideld ? "_wl_1" : "_wl_0") +
             "_ps_" + std::to_string(expert_pairwise_scale_layout))
          : "");
  // ---------------------------------------------------------------------------
  return kname;
}

int main() {
  Vals base{};
  base.mode = "nvfp4";
  base.type_string = "bfloat16_t";
  base.static_expert_shape = true;
  base.expert_aligned = true;
  base.transpose = true;
  base.group_size = 16;
  base.bits = 4;
  base.bm = 64;
  base.bk = 64;
  base.wm = 4;
  base.wn = 1;
  base.egroups = 256;
  base.expert_widest = true;
  base.expert_wideld = true; // darkbloom_stage_wide_load_ok() is true at bn=64 and bn=128

  const int bns[2] = {64, 128};
  for (int i = 0; i < 2; ++i) {
    Vals gu = base;
    gu.label = "gate/up";
    gu.K = 2048;
    gu.N = 1024;
    gu.expert_pairwise_scale_layout = 1;
    gu.bn = bns[i];
    printf("%-8s bn=%-3d %s\n", gu.label.c_str(), gu.bn, derive(gu).c_str());

    Vals dn = base;
    dn.label = "down";
    dn.K = 512;
    dn.N = 2048;
    dn.expert_pairwise_scale_layout = 2;
    dn.bn = bns[i];
    printf("%-8s bn=%-3d %s\n", dn.label.c_str(), dn.bn, derive(dn).c_str());
  }
  return 0;
}
