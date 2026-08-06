
// Copyright © 2025 Apple Inc.

// Auto generated source for mlx/backend/metal/kernels/utils.h

///////////////////////////////////////////////////////////////////////////////
// Contents from "mlx/backend/metal/kernels/bf16.h"
///////////////////////////////////////////////////////////////////////////////

#line 1 "mlx/backend/metal/kernels/bf16.h"
// Copyright © 2023 Apple Inc.


#include <metal_stdlib>

using namespace metal;

typedef bfloat bfloat16_t;
inline uint16_t bfloat16_to_uint16(const bfloat16_t x) {
  return as_type<uint16_t>(x);
}

inline bfloat16_t uint16_to_bfloat16(const uint16_t x) {
  return as_type<bfloat16_t>(x);
}

///////////////////////////////////////////////////////////////////////////////
// Contents from "mlx/backend/metal/kernels/bf16_math.h"
///////////////////////////////////////////////////////////////////////////////

#line 1 "mlx/backend/metal/kernels/bf16_math.h"
// Copyright © 2023 Apple Inc.


///////////////////////////////////////////////////////////////////////////////
// Metal math for bfloat16
///////////////////////////////////////////////////////////////////////////////

/*

Following the Metal Shading Language Specification (Metal 3.1)

"bfloat is an extended itypeing point type that only allows implicit conversion
 to a type of greater itypeing point rank. While bfloat can be implicitly
 converted to itype, it cannot be implicitly converted to half, and neither
 itype nor half can be implicitly converted to bfloat."

Further, as far as I can tell, the stdlib math/simd functions are not defined
for bfloat and calling with an argument of type bfloat will result in that
argument getting implicitly converted to itype which then returns an output
that is (likely) a itype which cannot be implicitly converted into a bfloat

This leads to situations where
bfloat a = 5.0bf;
bfloat b = metal::abs(a); // this will throw an error since abs return itype
bfloat c = static_cast<bfloat>(metal::abs(a)); // this is fine

For the moment, I will be adding overloaded instantiations of the math
functions to accordingly automatically handle the casting

*/

#define instantiate_metal_math_funcs(itype, otype, ctype, mfast)               \
                                                                               \
  METAL_FUNC otype abs(itype x) {                                              \
    return static_cast<otype>(__metal_fabs(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype acos(itype x) {                                             \
    return static_cast<otype>(__metal_acos(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype acosh(itype x) {                                            \
    return static_cast<otype>(__metal_acosh(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype asin(itype x) {                                             \
    return static_cast<otype>(__metal_asin(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype asinh(itype x) {                                            \
    return static_cast<otype>(__metal_asinh(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype atan(itype y_over_x) {                                      \
    return static_cast<otype>(                                                 \
        __metal_atan(static_cast<ctype>(y_over_x), mfast));                    \
  }                                                                            \
  METAL_FUNC otype atan2(itype y, itype x) {                                   \
    return static_cast<otype>(                                                 \
        __metal_atan2(static_cast<ctype>(y), static_cast<ctype>(x), mfast));   \
  }                                                                            \
  METAL_FUNC otype atanh(itype x) {                                            \
    return static_cast<otype>(__metal_atanh(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype ceil(itype x) {                                             \
    return static_cast<otype>(__metal_ceil(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype cos(itype x) {                                              \
    return static_cast<otype>(__metal_cos(static_cast<ctype>(x), mfast));      \
  }                                                                            \
  METAL_FUNC otype cosh(itype x) {                                             \
    return static_cast<otype>(__metal_cosh(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype cospi(itype x) {                                            \
    return static_cast<otype>(__metal_cospi(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype divide(itype x, itype y) {                                  \
    return static_cast<otype>(                                                 \
        __metal_divide(static_cast<ctype>(x), static_cast<ctype>(y), mfast));  \
  }                                                                            \
  METAL_FUNC otype exp(itype x) {                                              \
    return static_cast<otype>(__metal_exp(static_cast<ctype>(x), mfast));      \
  }                                                                            \
  METAL_FUNC otype exp10(itype x) {                                            \
    return static_cast<otype>(__metal_exp10(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype exp2(itype x) {                                             \
    return static_cast<otype>(__metal_exp2(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype fabs(itype x) {                                             \
    return static_cast<otype>(__metal_fabs(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype fdim(itype x, itype y) {                                    \
    ctype t = static_cast<ctype>(x - y);                                       \
    return static_cast<otype>(select(t, ctype(0), t < ctype(0) || x == y));    \
  }                                                                            \
  METAL_FUNC otype floor(itype x) {                                            \
    return static_cast<otype>(__metal_floor(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype fma(itype x, itype y, itype z) {                            \
    return static_cast<otype>(__metal_fma(                                     \
        static_cast<ctype>(x), static_cast<ctype>(y), static_cast<ctype>(z))); \
  }                                                                            \
  METAL_FUNC otype fmax(itype x, itype y) {                                    \
    return static_cast<otype>(                                                 \
        __metal_fmax(static_cast<ctype>(x), static_cast<ctype>(y), mfast));    \
  }                                                                            \
  METAL_FUNC otype fmax3(itype x, itype y, itype z) {                          \
    return static_cast<otype>(__metal_fmax3(                                   \
        static_cast<ctype>(x),                                                 \
        static_cast<ctype>(y),                                                 \
        static_cast<ctype>(z),                                                 \
        mfast));                                                               \
  }                                                                            \
  METAL_FUNC otype fmedian3(itype x, itype y, itype z) {                       \
    return static_cast<otype>(__metal_fmedian3(                                \
        static_cast<ctype>(x),                                                 \
        static_cast<ctype>(y),                                                 \
        static_cast<ctype>(z),                                                 \
        mfast));                                                               \
  }                                                                            \
  METAL_FUNC otype fmin(itype x, itype y) {                                    \
    return static_cast<otype>(                                                 \
        __metal_fmin(static_cast<ctype>(x), static_cast<ctype>(y), mfast));    \
  }                                                                            \
  METAL_FUNC otype fmin3(itype x, itype y, itype z) {                          \
    return static_cast<otype>(__metal_fmin3(                                   \
        static_cast<ctype>(x),                                                 \
        static_cast<ctype>(y),                                                 \
        static_cast<ctype>(z),                                                 \
        mfast));                                                               \
  }                                                                            \
  METAL_FUNC otype fmod(itype x, itype y) {                                    \
    return static_cast<otype>(                                                 \
        __metal_fmod(static_cast<ctype>(x), static_cast<ctype>(y), mfast));    \
  }                                                                            \
  METAL_FUNC otype fract(itype x) {                                            \
    return static_cast<otype>(__metal_fract(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype frexp(itype x, thread int& exp) {                           \
    return static_cast<otype>(__metal_frexp(static_cast<ctype>(x), &exp));     \
  }                                                                            \
  METAL_FUNC otype ldexp(itype x, int k) {                                     \
    return static_cast<otype>(__metal_ldexp(static_cast<ctype>(x), k, mfast)); \
  }                                                                            \
  METAL_FUNC otype log(itype x) {                                              \
    return static_cast<otype>(__metal_log(static_cast<ctype>(x), mfast));      \
  }                                                                            \
  METAL_FUNC otype log10(itype x) {                                            \
    return static_cast<otype>(__metal_log10(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype log2(itype x) {                                             \
    return static_cast<otype>(__metal_log2(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype max(itype x, itype y) {                                     \
    return static_cast<otype>(                                                 \
        __metal_fmax(static_cast<ctype>(x), static_cast<ctype>(y), mfast));    \
  }                                                                            \
  METAL_FUNC otype max3(itype x, itype y, itype z) {                           \
    return static_cast<otype>(__metal_fmax3(                                   \
        static_cast<ctype>(x),                                                 \
        static_cast<ctype>(y),                                                 \
        static_cast<ctype>(z),                                                 \
        mfast));                                                               \
  }                                                                            \
  METAL_FUNC otype median3(itype x, itype y, itype z) {                        \
    return static_cast<otype>(__metal_fmedian3(                                \
        static_cast<ctype>(x),                                                 \
        static_cast<ctype>(y),                                                 \
        static_cast<ctype>(z),                                                 \
        mfast));                                                               \
  }                                                                            \
  METAL_FUNC otype min(itype x, itype y) {                                     \
    return static_cast<otype>(                                                 \
        __metal_fmin(static_cast<ctype>(x), static_cast<ctype>(y), mfast));    \
  }                                                                            \
  METAL_FUNC otype min3(itype x, itype y, itype z) {                           \
    return static_cast<otype>(__metal_fmin3(                                   \
        static_cast<ctype>(x),                                                 \
        static_cast<ctype>(y),                                                 \
        static_cast<ctype>(z),                                                 \
        mfast));                                                               \
  }                                                                            \
  METAL_FUNC otype nextafter(itype x, itype y) {                               \
    return static_cast<otype>(                                                 \
        __metal_nextafter(static_cast<ctype>(x), static_cast<ctype>(y)));      \
  }                                                                            \
  METAL_FUNC otype pow(itype x, itype y) {                                     \
    return static_cast<otype>(                                                 \
        __metal_pow(static_cast<ctype>(x), static_cast<ctype>(y), mfast));     \
  }                                                                            \
  METAL_FUNC otype powr(itype x, itype y) {                                    \
    return static_cast<otype>(                                                 \
        __metal_powr(static_cast<ctype>(x), static_cast<ctype>(y), mfast));    \
  }                                                                            \
  METAL_FUNC otype rint(itype x) {                                             \
    return static_cast<otype>(__metal_rint(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype round(itype x) {                                            \
    return static_cast<otype>(__metal_round(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype rsqrt(itype x) {                                            \
    return static_cast<otype>(__metal_rsqrt(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype sin(itype x) {                                              \
    return static_cast<otype>(__metal_sin(static_cast<ctype>(x), mfast));      \
  }                                                                            \
  METAL_FUNC otype sinh(itype x) {                                             \
    return static_cast<otype>(__metal_sinh(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype sinpi(itype x) {                                            \
    return static_cast<otype>(__metal_sinpi(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype sqrt(itype x) {                                             \
    return static_cast<otype>(__metal_sqrt(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype tan(itype x) {                                              \
    return static_cast<otype>(__metal_tan(static_cast<ctype>(x), mfast));      \
  }                                                                            \
  METAL_FUNC otype tanh(itype x) {                                             \
    return static_cast<otype>(__metal_tanh(static_cast<ctype>(x), mfast));     \
  }                                                                            \
  METAL_FUNC otype tanpi(itype x) {                                            \
    return static_cast<otype>(__metal_tanpi(static_cast<ctype>(x), mfast));    \
  }                                                                            \
  METAL_FUNC otype trunc(itype x) {                                            \
    return static_cast<otype>(__metal_trunc(static_cast<ctype>(x), mfast));    \
  }

namespace metal {

instantiate_metal_math_funcs(
    bfloat16_t,
    bfloat16_t,
    float,
    __METAL_MAYBE_FAST_MATH__);

namespace fast {

instantiate_metal_math_funcs(
    bfloat16_t,
    bfloat16_t,
    float,
    __METAL_FAST_MATH__);

} // namespace fast

namespace precise {

instantiate_metal_math_funcs(
    bfloat16_t,
    bfloat16_t,
    float,
    __METAL_PRECISE_MATH__);

} // namespace precise

} // namespace metal

///////////////////////////////////////////////////////////////////////////////
// Metal simd for bfloat16
///////////////////////////////////////////////////////////////////////////////

#define instantiate_metal_simd_comm_funcs(                                   \
    itype, otype, ctype, itype_to_ctype, ctype_to_otype)                     \
                                                                             \
  METAL_FUNC otype simd_broadcast(itype data, ushort broadcast_lane_id) {    \
    return ctype_to_otype(                                                   \
        __metal_simd_broadcast(itype_to_ctype(data), broadcast_lane_id));    \
  }                                                                          \
                                                                             \
  METAL_FUNC otype simd_shuffle(itype data, ushort simd_lane_id) {           \
    return ctype_to_otype(                                                   \
        __metal_simd_shuffle(itype_to_ctype(data), simd_lane_id));           \
  }                                                                          \
                                                                             \
  METAL_FUNC otype simd_shuffle_and_fill_down(                               \
      itype data, itype filling_data, ushort delta, ushort modulo) {         \
    return ctype_to_otype(__metal_simd_shuffle_and_fill_down(                \
        itype_to_ctype(data), itype_to_ctype(filling_data), delta, modulo)); \
  }                                                                          \
                                                                             \
  METAL_FUNC otype simd_shuffle_and_fill_down(                               \
      itype data, itype filling_data, ushort delta) {                        \
    return ctype_to_otype(__metal_simd_shuffle_and_fill_down(                \
        itype_to_ctype(data),                                                \
        itype_to_ctype(filling_data),                                        \
        delta,                                                               \
        __metal_get_simdgroup_size(ushort())));                              \
  }                                                                          \
                                                                             \
  METAL_FUNC otype simd_shuffle_and_fill_up(                                 \
      itype data, itype filling_data, ushort delta, ushort modulo) {         \
    return ctype_to_otype(__metal_simd_shuffle_and_fill_up(                  \
        itype_to_ctype(data), itype_to_ctype(filling_data), delta, modulo)); \
  }                                                                          \
                                                                             \
  METAL_FUNC otype simd_shuffle_and_fill_up(                                 \
      itype data, itype filling_data, ushort delta) {                        \
    return ctype_to_otype(__metal_simd_shuffle_and_fill_up(                  \
        itype_to_ctype(data),                                                \
        itype_to_ctype(filling_data),                                        \
        delta,                                                               \
        __metal_get_simdgroup_size(ushort())));                              \
  }                                                                          \
                                                                             \
  METAL_FUNC otype simd_shuffle_down(itype data, ushort delta) {             \
    return ctype_to_otype(                                                   \
        __metal_simd_shuffle_down(itype_to_ctype(data), delta));             \
  }                                                                          \
                                                                             \
  METAL_FUNC otype simd_shuffle_rotate_down(itype data, ushort delta) {      \
    return ctype_to_otype(                                                   \
        __metal_simd_shuffle_rotate_down(itype_to_ctype(data), delta));      \
  }                                                                          \
                                                                             \
  METAL_FUNC otype simd_shuffle_rotate_up(itype data, ushort delta) {        \
    return ctype_to_otype(                                                   \
        __metal_simd_shuffle_rotate_up(itype_to_ctype(data), delta));        \
  }                                                                          \
                                                                             \
  METAL_FUNC otype simd_shuffle_up(itype data, ushort delta) {               \
    return ctype_to_otype(                                                   \
        __metal_simd_shuffle_up(itype_to_ctype(data), delta));               \
  }                                                                          \
                                                                             \
  METAL_FUNC otype simd_shuffle_xor(itype data, ushort mask) {               \
    return ctype_to_otype(                                                   \
        __metal_simd_shuffle_xor(itype_to_ctype(data), mask));               \
  }

#define instantiate_metal_simd_reduction_funcs(itype, otype, ctype)            \
                                                                               \
  METAL_FUNC otype simd_max(itype data) {                                      \
    return static_cast<otype>(__metal_simd_max(static_cast<ctype>(data)));     \
  }                                                                            \
                                                                               \
  METAL_FUNC otype simd_min(itype data) {                                      \
    return static_cast<otype>(__metal_simd_min(static_cast<ctype>(data)));     \
  }                                                                            \
                                                                               \
  METAL_FUNC otype simd_prefix_exclusive_product(itype data) {                 \
    return static_cast<otype>(                                                 \
        __metal_simd_prefix_exclusive_product(static_cast<ctype>(data)));      \
  }                                                                            \
                                                                               \
  METAL_FUNC otype simd_prefix_exclusive_sum(itype data) {                     \
    return static_cast<otype>(                                                 \
        __metal_simd_prefix_exclusive_sum(static_cast<ctype>(data)));          \
  }                                                                            \
                                                                               \
  METAL_FUNC otype simd_prefix_inclusive_product(itype data) {                 \
    return static_cast<otype>(                                                 \
        __metal_simd_prefix_inclusive_product(static_cast<ctype>(data)));      \
  }                                                                            \
                                                                               \
  METAL_FUNC otype simd_prefix_inclusive_sum(itype data) {                     \
    return static_cast<otype>(                                                 \
        __metal_simd_prefix_inclusive_sum(static_cast<ctype>(data)));          \
  }                                                                            \
                                                                               \
  METAL_FUNC otype simd_product(itype data) {                                  \
    return static_cast<otype>(__metal_simd_product(static_cast<ctype>(data))); \
  }                                                                            \
                                                                               \
  METAL_FUNC otype simd_sum(itype data) {                                      \
    return static_cast<otype>(__metal_simd_sum(static_cast<ctype>(data)));     \
  }                                                                            \
                                                                               \
  METAL_FUNC otype simd_xor(itype data) {                                      \
    return static_cast<otype>(__metal_simd_xor(static_cast<ctype>(data)));     \
  }

namespace metal {

instantiate_metal_simd_comm_funcs(
    bfloat16_t,
    bfloat16_t,
    uint16_t,
    bfloat16_to_uint16,
    uint16_to_bfloat16);
instantiate_metal_simd_reduction_funcs(bfloat16_t, bfloat16_t, float);

} // namespace metal

///////////////////////////////////////////////////////////////////////////////
// Contents from "mlx/backend/metal/kernels/complex.h"
///////////////////////////////////////////////////////////////////////////////

#line 1 "mlx/backend/metal/kernels/complex.h"
// Copyright © 2023 Apple Inc.


#include <metal_stdlib>

using namespace metal;

struct complex64_t;

template <typename T>
static constexpr constant bool can_convert_to_complex64 =
    !is_same_v<T, complex64_t> && is_convertible_v<T, float>;

template <typename T>
static constexpr constant bool can_convert_from_complex64 =
    !is_same_v<T, complex64_t> &&
    (is_convertible_v<float, T> || is_convertible_v<bfloat16_t, T>);

struct complex64_t {
  float real;
  float imag;

  // Constructors
  constexpr complex64_t(float real, float imag) : real(real), imag(imag) {};
  constexpr complex64_t() : real(0), imag(0) {};
  constexpr complex64_t() threadgroup : real(0), imag(0) {};

  // Conversions to complex64_t
  template <
      typename T,
      typename = typename enable_if<can_convert_to_complex64<T>>::type>
  constexpr complex64_t(T x) thread : real(x), imag(0) {}

  template <
      typename T,
      typename = typename enable_if<can_convert_to_complex64<T>>::type>
  constexpr complex64_t(T x) threadgroup : real(x), imag(0) {}

  template <
      typename T,
      typename = typename enable_if<can_convert_to_complex64<T>>::type>
  constexpr complex64_t(T x) device : real(x), imag(0) {}

  template <
      typename T,
      typename = typename enable_if<can_convert_to_complex64<T>>::type>
  constexpr complex64_t(T x) constant : real(x), imag(0) {}

  // Conversions from complex64_t
  template <
      typename T,
      typename = typename enable_if<can_convert_from_complex64<T>>::type>
  constexpr operator T() const thread {
    return static_cast<T>(real);
  }

  template <
      typename T,
      typename = typename enable_if<can_convert_from_complex64<T>>::type>
  constexpr operator T() const threadgroup {
    return static_cast<T>(real);
  }

  template <
      typename T,
      typename = typename enable_if<can_convert_from_complex64<T>>::type>
  constexpr operator T() const device {
    return static_cast<T>(real);
  }

  template <
      typename T,
      typename = typename enable_if<can_convert_from_complex64<T>>::type>
  constexpr operator T() const constant {
    return static_cast<T>(real);
  }
};

constexpr complex64_t operator-(complex64_t x) {
  return {-x.real, -x.imag};
}

constexpr bool operator>=(complex64_t a, complex64_t b) {
  return (a.real > b.real) || (a.real == b.real && a.imag >= b.imag);
}

constexpr bool operator>(complex64_t a, complex64_t b) {
  return (a.real > b.real) || (a.real == b.real && a.imag > b.imag);
}

constexpr bool operator<=(complex64_t a, complex64_t b) {
  return operator>=(b, a);
}

constexpr bool operator<(complex64_t a, complex64_t b) {
  return operator>(b, a);
}

constexpr bool operator==(complex64_t a, complex64_t b) {
  return a.real == b.real && a.imag == b.imag;
}

constexpr complex64_t operator+(complex64_t a, complex64_t b) {
  return {a.real + b.real, a.imag + b.imag};
}

constexpr thread complex64_t& operator+=(thread complex64_t& a, complex64_t b) {
  a.real += b.real;
  a.imag += b.imag;
  return a;
}

constexpr threadgroup complex64_t& operator+=(
    threadgroup complex64_t& a,
    complex64_t b) {
  a.real += b.real;
  a.imag += b.imag;
  return a;
}

constexpr device complex64_t& operator+=(device complex64_t& a, complex64_t b) {
  a.real += b.real;
  a.imag += b.imag;
  return a;
}

constexpr complex64_t operator+(float a, complex64_t b) {
  return {a + b.real, b.imag};
}
constexpr complex64_t operator+(complex64_t a, float b) {
  return {a.real + b, a.imag};
}

constexpr complex64_t operator-(complex64_t a, complex64_t b) {
  return {a.real - b.real, a.imag - b.imag};
}
constexpr complex64_t operator-(float a, complex64_t b) {
  return {a - b.real, -b.imag};
}
constexpr complex64_t operator-(complex64_t a, float b) {
  return {a.real - b, a.imag};
}

constexpr complex64_t operator*(complex64_t a, complex64_t b) {
  return {a.real * b.real - a.imag * b.imag, a.real * b.imag + a.imag * b.real};
}

constexpr complex64_t operator/(complex64_t a, complex64_t b) {
  auto denom = b.real * b.real + b.imag * b.imag;
  auto x = a.real * b.real + a.imag * b.imag;
  auto y = a.imag * b.real - a.real * b.imag;
  return {x / denom, y / denom};
}

constexpr complex64_t operator/(float a, complex64_t b) {
  auto denom = b.real * b.real + b.imag * b.imag;
  auto x = a * b.real;
  auto y = -a * b.imag;
  return {x / denom, y / denom};
}

constexpr complex64_t operator%(complex64_t a, complex64_t b) {
  auto real = a.real - (b.real * static_cast<int64_t>(a.real / b.real));
  auto imag = a.imag - (b.imag * static_cast<int64_t>(a.imag / b.imag));
  if (real != 0 && (real < 0 != b.real < 0)) {
    real += b.real;
  }
  if (imag != 0 && (imag < 0 != b.imag < 0)) {
    imag += b.imag;
  }
  return {real, imag};
}

///////////////////////////////////////////////////////////////////////////////
// Contents from "mlx/backend/metal/kernels/defines.h"
///////////////////////////////////////////////////////////////////////////////

#line 1 "mlx/backend/metal/kernels/defines.h"
// Copyright © 2023 Apple Inc.


#if defined __METAL__ || defined MLX_METAL_JIT
#define MTL_CONST constant
#else
#define MTL_CONST
#endif

static MTL_CONST constexpr int MAX_REDUCE_SPECIALIZED_DIMS = 4;
static MTL_CONST constexpr int REDUCE_N_READS = 4;
static MTL_CONST constexpr int REDUCE_N_WRITES = 4;
static MTL_CONST constexpr int SOFTMAX_N_READS = 4;
static MTL_CONST constexpr int RMS_N_READS = 4;
static MTL_CONST constexpr int RMS_LOOPED_LIMIT = 4096;

// Instantiate a templated kernel.
// Extra args are used as template parameters:
// e.g. instantiate_kernel(binary_int, binary, a, b) ->
// [[host_name(binary_int)]] [kernel] binary<a, b>
#define instantiate_kernel(name, func, ...) \
  template [[host_name(                     \
      name)]] [[kernel]] decltype(func<__VA_ARGS__>) func<__VA_ARGS__>;

///////////////////////////////////////////////////////////////////////////////
// Contents from "mlx/backend/metal/kernels/logging.h"
///////////////////////////////////////////////////////////////////////////////

#line 1 "mlx/backend/metal/kernels/logging.h"
// Copyright © 2025 Apple Inc.


#if defined(__METAL_VERSION__) && (__METAL_VERSION__ >= 320)
#include <metal_logging>

namespace mlx {
using os_log = metal::os_log;
} // namespace mlx

#else

namespace mlx {
struct os_log {
  constexpr os_log(constant char*, constant char*) constant {}

  template <typename... Args>
  void log_debug(constant char*, Args...) const {}

  template <typename... Args>
  void log_debug(constant char*, Args...) const constant {}
};
} // namespace mlx

#endif

///////////////////////////////////////////////////////////////////////////////
// Contents from "mlx/backend/metal/kernels/utils.h"
///////////////////////////////////////////////////////////////////////////////

#line 1 "mlx/backend/metal/kernels/utils.h"
// Copyright © 2023-2024 Apple Inc.


#include <metal_math>


typedef half float16_t;

// Work per thread values for different types. The values here are expected to
// match get_work_per_thread in mlx/backend/metal/utils.h
template <typename U>
struct WorkPerThread {
  static_assert(sizeof(U) <= 8, "Type too large");
  static constexpr int constant n = 8 / sizeof(U);
};

///////////////////////////////////////////////////////////////////////////////
// Type limits utils
///////////////////////////////////////////////////////////////////////////////

template <typename U>
struct Limits {
  static const constant U max = metal::numeric_limits<U>::max();
  static const constant U min = metal::numeric_limits<U>::min();
  static const constant U finite_max = metal::numeric_limits<U>::max();
  static const constant U finite_min = metal::numeric_limits<U>::min();
};

#define instantiate_default_limit(type)                                      \
  template <>                                                                \
  struct Limits<type> {                                                      \
    static constexpr constant type max = metal::numeric_limits<type>::max(); \
    static constexpr constant type min = metal::numeric_limits<type>::min(); \
    static constexpr constant type finite_max =                              \
        metal::numeric_limits<type>::max();                                  \
    static constexpr constant type finite_min =                              \
        metal::numeric_limits<type>::min();                                  \
  };

instantiate_default_limit(uint8_t);
instantiate_default_limit(uint16_t);
instantiate_default_limit(uint32_t);
instantiate_default_limit(uint64_t);
instantiate_default_limit(int8_t);
instantiate_default_limit(int16_t);
instantiate_default_limit(int32_t);
instantiate_default_limit(int64_t);

#define instantiate_float_limit(type)             \
  template <>                                     \
  struct Limits<type> {                           \
    static constexpr constant type max =          \
        metal::numeric_limits<type>::infinity();  \
    static constexpr constant type min =          \
        -metal::numeric_limits<type>::infinity(); \
    static constexpr constant type finite_max =   \
        metal::numeric_limits<type>::max();       \
    static constexpr constant type finite_min =   \
        -metal::numeric_limits<type>::max();      \
  };

instantiate_float_limit(half);
instantiate_float_limit(float);
instantiate_float_limit(bfloat16_t);

template <>
struct Limits<bool> {
  static constexpr constant bool max = true;
  static constexpr constant bool min = false;
};

template <>
struct Limits<complex64_t> {
  static constexpr constant complex64_t max = complex64_t(
      metal::numeric_limits<float>::infinity(),
      metal::numeric_limits<float>::infinity());
  static constexpr constant complex64_t min = complex64_t(
      -metal::numeric_limits<float>::infinity(),
      -metal::numeric_limits<float>::infinity());
};

///////////////////////////////////////////////////////////////////////////////
// Indexing utils
///////////////////////////////////////////////////////////////////////////////

#define MLX_MTL_PRAGMA_UNROLL _Pragma("clang loop unroll(full)")

///////////////////////////////////////////////////////////////////////////////
// Single Array with generic dims

template <typename IdxT = int64_t>
METAL_FUNC IdxT elem_to_loc(
    IdxT elem,
    constant const int* shape,
    constant const int64_t* strides,
    int ndim) {
  IdxT loc = 0;
  for (int i = ndim - 1; i >= 0 && elem > 0; --i) {
    loc += (elem % shape[i]) * IdxT(strides[i]);
    elem /= shape[i];
  }
  return loc;
}

// Non templated version to handle arbitrary dims
template <typename IdxT = int64_t>
METAL_FUNC IdxT elem_to_loc(
    uint3 elem,
    constant const int* shape,
    constant const int64_t* strides,
    int ndim) {
  IdxT loc =
      elem.x * IdxT(strides[ndim - 1]) + elem.y * IdxT(strides[ndim - 2]);
  for (int d = ndim - 3; d >= 0; --d) {
    loc += (elem.z % shape[d]) * IdxT(strides[d]);
    elem.z /= shape[d];
  }
  return loc;
}

///////////////////////////////////////////////////////////////////////////////
// Single Array with fixed N dims

template <typename IdxT = int64_t>
METAL_FUNC IdxT elem_to_loc_1(uint elem, constant const int64_t& stride) {
  return elem * IdxT(stride);
}

template <typename IdxT = int64_t>
METAL_FUNC IdxT elem_to_loc_2(uint2 elem, constant const int64_t strides[2]) {
  return elem.x * IdxT(strides[1]) + elem.y * IdxT(strides[0]);
}

template <typename IdxT = int64_t>
METAL_FUNC IdxT elem_to_loc_3(uint3 elem, constant const int64_t strides[3]) {
  return elem.x * IdxT(strides[2]) + elem.y * IdxT(strides[1]) +
      elem.z * IdxT(strides[0]);
}

///////////////////////////////////////////////////////////////////////////////
// Multiple Arrays with generic dims

template <typename IdxT = int64_t>
METAL_FUNC vec<IdxT, 2> elem_to_loc_2_nd(
    uint3 elem,
    constant const int* shape,
    constant const int64_t* a_strides,
    constant const int64_t* b_strides,
    int ndim) {
  vec<IdxT, 2> loc = {
      IdxT(
          elem.x * IdxT(a_strides[ndim - 1]) +
          IdxT(elem.y) * IdxT(a_strides[ndim - 2])),
      IdxT(
          elem.x * IdxT(b_strides[ndim - 1]) +
          elem.y * IdxT(b_strides[ndim - 2]))};
  for (int d = ndim - 3; d >= 0; --d) {
    uint l = elem.z % shape[d];
    loc.x += l * IdxT(a_strides[d]);
    loc.y += l * IdxT(b_strides[d]);
    elem.z /= shape[d];
  }
  return loc;
}

template <typename IdxT = int64_t>
METAL_FUNC vec<IdxT, 3> elem_to_loc_3_nd(
    uint3 elem,
    constant const int* shape,
    constant const int64_t* a_strides,
    constant const int64_t* b_strides,
    constant const int64_t* c_strides,
    int ndim) {
  vec<IdxT, 3> loc = {
      IdxT(elem.x * IdxT(a_strides[ndim - 1])) +
          IdxT(elem.y * IdxT(a_strides[ndim - 2])),
      IdxT(elem.x * IdxT(b_strides[ndim - 1])) +
          IdxT(elem.y * IdxT(b_strides[ndim - 2])),
      IdxT(elem.x * IdxT(c_strides[ndim - 1])) +
          IdxT(elem.y * IdxT(c_strides[ndim - 2]))};
  for (int d = ndim - 3; d >= 0; --d) {
    uint l = elem.z % shape[d];
    loc.x += l * IdxT(a_strides[d]);
    loc.y += l * IdxT(b_strides[d]);
    loc.z += l * IdxT(c_strides[d]);
    elem.z /= shape[d];
  }
  return loc;
}

///////////////////////////////////////////////////////////////////////////////
// Elem to loc in a loop utils
///////////////////////////////////////////////////////////////////////////////

template <int DIM, typename OffsetT = size_t, bool General = true>
struct LoopedElemToLoc {
  int dim;
  LoopedElemToLoc<DIM - 1, OffsetT, General> inner_looper;
  OffsetT offset{0};
  int index{0};

  LoopedElemToLoc(int dim) : dim(dim), inner_looper(dim - 1) {}

  void next(const constant int* shape, const constant int64_t* strides) {
    if (dim == 0) {
      return;
    }
    index++;
    offset += OffsetT(strides[dim - 1]);
    if (index >= shape[dim - 1]) {
      index = 0;
      inner_looper.next(shape, strides);
      offset = inner_looper.offset;
    }
  }

  void next(int n, const constant int* shape, const constant int64_t* strides) {
    if (dim == 0) {
      return;
    }
    index += n;
    offset += n * OffsetT(strides[dim - 1]);

    if (index >= shape[dim - 1]) {
      int extra = index - shape[dim - 1];
      if (extra >= shape[dim - 1]) {
        inner_looper.next(1 + extra / shape[dim - 1], shape, strides);
        extra = extra % shape[dim - 1];
      } else {
        inner_looper.next(shape, strides);
      }
      index = 0;
      offset = inner_looper.offset;
      if (extra > 0) {
        next(extra, shape, strides);
      }
    }
  }

  OffsetT location() {
    return offset;
  }
};

template <typename OffsetT>
struct LoopedElemToLoc<1, OffsetT, true> {
  int dim;
  OffsetT offset{0};
  uint index{0};

  LoopedElemToLoc(int dim) : dim(dim) {}

  void next(const constant int* shape, const constant int64_t* strides) {
    index++;
    if (dim > 1) {
      offset = elem_to_loc<OffsetT>(index, shape, strides, dim);
    } else {
      offset += OffsetT(strides[0]);
    }
  }

  void next(int n, const constant int* shape, const constant int64_t* strides) {
    index += n;
    if (dim > 1) {
      offset = elem_to_loc<OffsetT>(index, shape, strides, dim);
    } else {
      offset = index * OffsetT(strides[0]);
    }
  }

  OffsetT location() {
    return offset;
  }
};

template <typename OffsetT>
struct LoopedElemToLoc<1, OffsetT, false> {
  OffsetT offset{0};

  LoopedElemToLoc(int) {}

  void next(const constant int*, const constant int64_t* strides) {
    offset += OffsetT(strides[0]);
  }

  void next(int n, const constant int*, const constant int64_t* strides) {
    offset += n * OffsetT(strides[0]);
  }

  OffsetT location() {
    return offset;
  }
};

///////////////////////////////////////////////////////////////////////////////
// Calculation utils
///////////////////////////////////////////////////////////////////////////////

/** Compute ceil((float)N/(float)M) */
template <typename T, typename U>
inline T ceildiv(T N, U M) {
  return (N + M - 1) / M;
}

// https://docs.oracle.com/cd/E19957-01/806-3568/ncg_goldberg.html#1202
inline float log1p(float x) {
  float xp1 = 1.0f + x;
  if (xp1 == Limits<float>::max) {
    return Limits<float>::max;
  }
  if (xp1 == 1.0f) {
    return x;
  }

  return x * (metal::log(xp1) / (xp1 - 1.0f));
}

inline bfloat16_t log1p(bfloat16_t x) {
  float xp1 = 1.0f + static_cast<float>(x);
  if (xp1 == Limits<float>::max) {
    return Limits<bfloat16_t>::max;
  }
  if (xp1 == 1.0f) {
    return x;
  }

  return bfloat16_t(x * (metal::log(xp1) / (xp1 - 1.0f)));
}

inline complex64_t log1p(complex64_t in) {
  float x = in.real;
  float y = in.imag;
  float zabs = metal::precise::sqrt(x * x + y * y);
  float theta = metal::atan2(y, x + 1);
  if (zabs < 0.5f) {
    float r = x * (2 + x) + y * y;
    if (r == 0) { // handle underflow
      return {x, theta};
    }
    return {0.5f * log1p(r), theta};
  } else {
    auto z0 = metal::sqrt((x + 1) * (x + 1) + y * y);
    return {metal::log(z0), theta};
  }
}

///////////////////////////////////////////////////////////////////////////////
// SIMD shuffle ops
///////////////////////////////////////////////////////////////////////////////

inline uint64_t simd_shuffle_down(uint64_t data, uint16_t delta) {
  return as_type<uint64_t>(
      metal::simd_shuffle_down(as_type<uint2>(data), delta));
}

inline int64_t simd_shuffle_down(int64_t data, uint16_t delta) {
  return as_type<int64_t>(
      metal::simd_shuffle_down(as_type<uint2>(data), delta));
}

inline bool simd_shuffle_down(bool data, uint16_t delta) {
  return simd_shuffle_down(static_cast<uint32_t>(data), delta);
}

inline complex64_t simd_shuffle_down(complex64_t data, uint16_t delta) {
  return complex64_t(
      simd_shuffle_down(data.real, delta), simd_shuffle_down(data.imag, delta));
}

inline uint64_t simd_shuffle_up(uint64_t data, uint16_t delta) {
  return as_type<uint64_t>(metal::simd_shuffle_up(as_type<uint2>(data), delta));
}

inline int64_t simd_shuffle_up(int64_t data, uint16_t delta) {
  return as_type<int64_t>(metal::simd_shuffle_up(as_type<uint2>(data), delta));
}

inline bool simd_shuffle_up(bool data, uint16_t delta) {
  return simd_shuffle_up(static_cast<uint32_t>(data), delta);
}

inline complex64_t simd_shuffle_up(complex64_t data, uint16_t delta) {
  return complex64_t(
      simd_shuffle_up(data.real, delta), simd_shuffle_up(data.imag, delta));
}

inline uint64_t
simd_shuffle_and_fill_up(uint64_t data, uint64_t filling, uint16_t delta) {
  return as_type<uint64_t>(metal::simd_shuffle_and_fill_up(
      as_type<uint2>(data), as_type<uint2>(filling), delta));
}

inline int64_t
simd_shuffle_and_fill_up(int64_t data, int64_t filling, uint16_t delta) {
  return as_type<int64_t>(metal::simd_shuffle_and_fill_up(
      as_type<uint2>(data), as_type<uint2>(filling), delta));
}

inline bool simd_shuffle_and_fill_up(bool data, bool filling, uint16_t delta) {
  return simd_shuffle_and_fill_up(
      static_cast<uint32_t>(data), static_cast<uint32_t>(filling), delta);
}

inline complex64_t simd_shuffle_and_fill_up(
    complex64_t data,
    complex64_t filling,
    uint16_t delta) {
  return complex64_t(
      simd_shuffle_and_fill_up(data.real, filling.real, delta),
      simd_shuffle_and_fill_up(data.imag, filling.imag, delta));
}

inline uint64_t simd_shuffle(uint64_t data, uint16_t lane) {
  return as_type<uint64_t>(metal::simd_shuffle(as_type<uint2>(data), lane));
}

inline int64_t simd_shuffle(int64_t data, uint16_t lane) {
  return as_type<int64_t>(metal::simd_shuffle(as_type<uint2>(data), lane));
}

inline bool simd_shuffle(bool data, uint16_t lane) {
  return simd_shuffle(static_cast<uint32_t>(data), lane);
}

inline complex64_t simd_shuffle(complex64_t data, uint16_t lane) {
  return complex64_t(
      simd_shuffle(data.real, lane), simd_shuffle(data.imag, lane));
}

// std::conditional is not included with Metal
template <bool condition, typename T, typename U>
struct ConditionalType {
  using type = U;
};

template <typename T, typename U>
struct ConditionalType<true, T, U> {
  using type = T;
};

///////////////////////////////////////////////////////////////////////////////
#define LAGUNA_RESCALE(dst, delta_expr)         \
  do {                                          \
    const float db_delta_ = (delta_expr);       \
    if (as_type<uint>(db_delta_) == 0u) {       \
      dst = float(1.0f);                        \
    } else {                                    \
      dst = metal::fast::exp(db_delta_);        \
    }                                           \
  } while (false)

#define T_LOAD_K(dst, substitute, ptr)                     \
  do {                                                     \
    if (substitute) {                                      \
      dst[0] = tg_k[lane * qk_per_thread + 0];             \
      dst[1] = tg_k[lane * qk_per_thread + 1];             \
      dst[2] = tg_k[lane * qk_per_thread + 2];             \
      dst[3] = tg_k[lane * qk_per_thread + 3];             \
    } else {                                               \
      const vec<bfloat, 4> v_ =                            \
          *reinterpret_cast<const device vec<bfloat, 4>*>( \
              ptr);                                        \
      dst[0] = v_.x;                                       \
      dst[1] = v_.y;                                       \
      dst[2] = v_.z;                                       \
      dst[3] = v_.w;                                       \
    }                                                      \
  } while (false)

#define T_LOAD_V(d0, d1, d2, d3, substitute, ptr)          \
  do {                                                     \
    if (substitute) {                                      \
      d0 = tg_v[lane * v_per_thread + 0];                  \
      d1 = tg_v[lane * v_per_thread + 1];                  \
      d2 = tg_v[lane * v_per_thread + 2];                  \
      d3 = tg_v[lane * v_per_thread + 3];                  \
    } else {                                               \
      const vec<bfloat, 4> v_ =                            \
          *reinterpret_cast<const device vec<bfloat, 4>*>( \
              ptr);                                        \
      d0 = v_.x;                                           \
      d1 = v_.y;                                           \
      d2 = v_.z;                                           \
      d3 = v_.w;                                           \
    }                                                      \
  } while (false)

[[kernel]] void custom_kernel_laguna_sliding_fused_attn_ring_v1_p4(
  const device bfloat16_t* raw_queries [[buffer(0)]],
  const device bfloat16_t* raw_keys [[buffer(1)]],
  const device bfloat16_t* raw_values [[buffer(2)]],
  const device bfloat16_t* query_weight [[buffer(3)]],
  const device bfloat16_t* key_weight [[buffer(4)]],
  const device float* angles [[buffer(5)]],
  const device bfloat16_t* k_cache [[buffer(6)]],
  const device bfloat16_t* v_cache [[buffer(7)]],
  const constant uint32_t* params [[buffer(8)]],
  const constant float* scale_arr [[buffer(9)]],
  device bfloat16_t* attended [[buffer(10)]],
  uint simdgroup_index_in_threadgroup [[simdgroup_index_in_threadgroup]],
  uint thread_index_in_simdgroup [[thread_index_in_simdgroup]],
  uint3 threadgroup_position_in_grid [[threadgroup_position_in_grid]]) {
constexpr uint head_dim = 128;
constexpr uint window = 512;
constexpr uint gqa = 8;
constexpr int BN = 32;
constexpr int BD = 32;
constexpr int BDP = BD + 1;
constexpr int qk_per_thread = 4;
constexpr int v_per_thread = 4;
constexpr uint rotary_pairs = 64;
constexpr int N = 512;

typedef float U;

uint pair_tg = threadgroup_position_in_grid.x;
uint head0 = pair_tg * 2;
uint head1 = head0 + 1;
uint kv_head = head0 / gqa;
uint sg = simdgroup_index_in_threadgroup;
uint lane = thread_index_in_simdgroup;
uint widx = params[0];
float scale = scale_arr[0];

threadgroup bfloat tg_q0[head_dim];
threadgroup bfloat tg_q1[head_dim];
threadgroup bfloat tg_k[head_dim];
threadgroup bfloat tg_v[head_dim];

if (sg < 3) {
    const device bfloat* input =
        sg == 0 ? raw_queries + head0 * head_dim
        : sg == 1 ? raw_queries + head1 * head_dim
                  : raw_keys + kv_head * head_dim;
    const device bfloat* weight =
        sg == 2 ? key_weight : query_weight;
    threadgroup bfloat* outrow =
        sg == 0 ? tg_q0 : sg == 1 ? tg_q1 : tg_k;

    uint base = lane * 4;
    thread bfloat normalized[4];
    float sum = 0.0f;
    for (uint i = 0; i < 4; ++i) {
        float value = float(input[base + i]);
        sum += value * value;
    }
    sum = simd_sum(sum);
    float inverse_rms = metal::precise::rsqrt(sum / 128.0f + 1.0e-6f);
    for (uint i = 0; i < 4; ++i) {
        normalized[i] =
            weight[base + i] *
            bfloat(float(input[base + i]) * inverse_rms);
    }
    thread float paired[4];
    for (uint i = 0; i < 4; ++i) {
        paired[i] = simd_shuffle(float(normalized[i]), lane ^ 16);
    }
    if (lane < 16) {
        for (uint i = 0; i < 4; ++i) {
            uint pair = base + i;
            float first = float(normalized[i]);
            float second = paired[i];
            float cosine = angles[pair];
            float sine = angles[pair + rotary_pairs];
            outrow[pair] = bfloat(first * cosine - second * sine);
            outrow[pair + rotary_pairs] =
                bfloat(first * sine + second * cosine);
        }
    }
} else if (sg == 3) {
    const device bfloat* vin = raw_values + kv_head * head_dim;
    for (uint i = lane; i < head_dim; i += 32) {
        tg_v[i] = vin[i];
    }
}
threadgroup_barrier(mem_flags::mem_threadgroup);

if ((head0 % gqa) == 0 && sg == 0) {
    device bfloat* kc = (device bfloat*)k_cache +
        (size_t)kv_head * (window * head_dim) +
        (size_t)widx * head_dim;
    device bfloat* vc = (device bfloat*)v_cache +
        (size_t)kv_head * (window * head_dim) +
        (size_t)widx * head_dim;
    for (uint i = lane; i < head_dim; i += 32) {
        kc[i] = tg_k[i];
        vc[i] = tg_v[i];
    }
}

threadgroup U outputs[4 * BN * BDP];
threadgroup U max_scores[2 * BN];
threadgroup U sum_exp_scores[2 * BN];

const device bfloat* pair_keys = k_cache +
    (size_t)kv_head * (window * head_dim) +
    (size_t)sg * head_dim + lane * qk_per_thread;
const device bfloat* pair_values = v_cache +
    (size_t)kv_head * (window * head_dim) +
    (size_t)sg * head_dim + lane * v_per_thread;
const int inner_k_stride = BN * int(head_dim);
const int inner_v_stride = BN * int(head_dim);

thread U pair_q0[qk_per_thread];
thread U pair_q1[qk_per_thread];
thread U pair_o0[v_per_thread];
thread U pair_o1[v_per_thread];

for (int j = 0; j < qk_per_thread; ++j) {
    pair_q0[j] =
        static_cast<U>(scale) * tg_q0[lane * qk_per_thread + j];
    pair_q1[j] =
        static_cast<U>(scale) * tg_q1[lane * qk_per_thread + j];
}
for (int j = 0; j < v_per_thread; ++j) {
    pair_o0[j] = 0;
    pair_o1[j] = 0;
}

U pair_max0 = metal::numeric_limits<U>::lowest();
U pair_max1 = metal::numeric_limits<U>::lowest();
U pair_sum0 = 0;
U pair_sum1 = 0;

int i = sg;
for (; i + 3 * BN < N; i += 4 * BN) {
    const device bfloat* pk_a = pair_keys;
    const device bfloat* pk_b = pair_keys + 1 * inner_k_stride;
    const device bfloat* pk_c = pair_keys + 2 * inner_k_stride;
    const device bfloat* pk_d = pair_keys + 3 * inner_k_stride;
    const device bfloat* pv_a = pair_values;
    const device bfloat* pv_b = pair_values + 1 * inner_v_stride;
    const device bfloat* pv_c = pair_values + 2 * inner_v_stride;
    const device bfloat* pv_d = pair_values + 3 * inner_v_stride;
    const bool sub_a = uint(i) == widx;
    const bool sub_b = uint(i + 1 * BN) == widx;
    const bool sub_c = uint(i + 2 * BN) == widx;
    const bool sub_d = uint(i + 3 * BN) == widx;
    U pipe_ka[4];
    U pipe_kb[4];
    U pipe_kc[4];
    U pipe_kd[4];
    bfloat pipe_va0, pipe_va1, pipe_va2, pipe_va3;
    bfloat pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3;
    bfloat pipe_vc0, pipe_vc1, pipe_vc2, pipe_vc3;
    bfloat pipe_vd0, pipe_vd1, pipe_vd2, pipe_vd3;
    T_LOAD_K(pipe_ka, sub_a, pk_a);
    T_LOAD_K(pipe_kb, sub_b, pk_b);
    T_LOAD_K(pipe_kc, sub_c, pk_c);
    T_LOAD_K(pipe_kd, sub_d, pk_d);
    T_LOAD_V(pipe_va0, pipe_va1, pipe_va2, pipe_va3, sub_a, pv_a);
    T_LOAD_V(pipe_vb0, pipe_vb1, pipe_vb2, pipe_vb3, sub_b, pv_b);
    T_LOAD_V(pipe_vc0, pipe_vc1, pipe_vc2, pipe_vc3, sub_c, pv_c);
    T_LOAD_V(pipe_vd0, pipe_vd1, pipe_vd2, pipe_vd3, sub_d, pv_d);

    U a_score0 = 0;
    U a_score1 = 0;
    a_score0 += pair_q0[0] * pipe_ka[0];
    a_score1 += pair_q1[0] * pipe_ka[0];
    a_score0 += pair_q0[1] * pipe_ka[1];
    a_score1 += pair_q1[1] * pipe_ka[1];
    a_score0 += pair_q0[2] * pipe_ka[2];
    a_score1 += pair_q1[2] * pipe_ka[2];
    a_score0 += pair_q0[3] * pipe_ka[3];
    a_score1 += pair_q1[3] * pipe_ka[3];
    a_score0 = simd_sum(a_score0);
    a_score1 = simd_sum(a_score1);

    U a_new_max0 = metal::max(pair_max0, a_score0);
    U a_new_max1 = metal::max(pair_max1, a_score1);
    U a_factor0;
    U a_factor1;
    LAGUNA_RESCALE(a_factor0, pair_max0 - a_new_max0);
    LAGUNA_RESCALE(a_factor1, pair_max1 - a_new_max1);
    U a_exp0 = metal::fast::exp(a_score0 - a_new_max0);
    U a_exp1 = metal::fast::exp(a_score1 - a_new_max1);

    pair_max0 = a_new_max0;
    pair_max1 = a_new_max1;
    pair_sum0 = pair_sum0 * a_factor0 + a_exp0;
    pair_sum1 = pair_sum1 * a_factor1 + a_exp1;

    pair_o0[0] = pair_o0[0] * a_factor0 + a_exp0 * pipe_va0;
    pair_o1[0] = pair_o1[0] * a_factor1 + a_exp1 * pipe_va0;
    pair_o0[1] = pair_o0[1] * a_factor0 + a_exp0 * pipe_va1;
    pair_o1[1] = pair_o1[1] * a_factor1 + a_exp1 * pipe_va1;
    pair_o0[2] = pair_o0[2] * a_factor0 + a_exp0 * pipe_va2;
    pair_o1[2] = pair_o1[2] * a_factor1 + a_exp1 * pipe_va2;
    pair_o0[3] = pair_o0[3] * a_factor0 + a_exp0 * pipe_va3;
    pair_o1[3] = pair_o1[3] * a_factor1 + a_exp1 * pipe_va3;

    U b_score0 = 0;
    U b_score1 = 0;
    b_score0 += pair_q0[0] * pipe_kb[0];
    b_score1 += pair_q1[0] * pipe_kb[0];
    b_score0 += pair_q0[1] * pipe_kb[1];
    b_score1 += pair_q1[1] * pipe_kb[1];
    b_score0 += pair_q0[2] * pipe_kb[2];
    b_score1 += pair_q1[2] * pipe_kb[2];
    b_score0 += pair_q0[3] * pipe_kb[3];
    b_score1 += pair_q1[3] * pipe_kb[3];
    b_score0 = simd_sum(b_score0);
    b_score1 = simd_sum(b_score1);

    U b_new_max0 = metal::max(pair_max0, b_score0);
    U b_new_max1 = metal::max(pair_max1, b_score1);
    U b_factor0;
    U b_factor1;
    LAGUNA_RESCALE(b_factor0, pair_max0 - b_new_max0);
    LAGUNA_RESCALE(b_factor1, pair_max1 - b_new_max1);
    U b_exp0 = metal::fast::exp(b_score0 - b_new_max0);
    U b_exp1 = metal::fast::exp(b_score1 - b_new_max1);

    pair_max0 = b_new_max0;
    pair_max1 = b_new_max1;
    pair_sum0 = pair_sum0 * b_factor0 + b_exp0;
    pair_sum1 = pair_sum1 * b_factor1 + b_exp1;

    pair_o0[0] = pair_o0[0] * b_factor0 + b_exp0 * pipe_vb0;
    pair_o1[0] = pair_o1[0] * b_factor1 + b_exp1 * pipe_vb0;
    pair_o0[1] = pair_o0[1] * b_factor0 + b_exp0 * pipe_vb1;
    pair_o1[1] = pair_o1[1] * b_factor1 + b_exp1 * pipe_vb1;
    pair_o0[2] = pair_o0[2] * b_factor0 + b_exp0 * pipe_vb2;
    pair_o1[2] = pair_o1[2] * b_factor1 + b_exp1 * pipe_vb2;
    pair_o0[3] = pair_o0[3] * b_factor0 + b_exp0 * pipe_vb3;
    pair_o1[3] = pair_o1[3] * b_factor1 + b_exp1 * pipe_vb3;

    U c_score0 = 0;
    U c_score1 = 0;
    c_score0 += pair_q0[0] * pipe_kc[0];
    c_score1 += pair_q1[0] * pipe_kc[0];
    c_score0 += pair_q0[1] * pipe_kc[1];
    c_score1 += pair_q1[1] * pipe_kc[1];
    c_score0 += pair_q0[2] * pipe_kc[2];
    c_score1 += pair_q1[2] * pipe_kc[2];
    c_score0 += pair_q0[3] * pipe_kc[3];
    c_score1 += pair_q1[3] * pipe_kc[3];
    c_score0 = simd_sum(c_score0);
    c_score1 = simd_sum(c_score1);

    U c_new_max0 = metal::max(pair_max0, c_score0);
    U c_new_max1 = metal::max(pair_max1, c_score1);
    U c_factor0;
    U c_factor1;
    LAGUNA_RESCALE(c_factor0, pair_max0 - c_new_max0);
    LAGUNA_RESCALE(c_factor1, pair_max1 - c_new_max1);
    U c_exp0 = metal::fast::exp(c_score0 - c_new_max0);
    U c_exp1 = metal::fast::exp(c_score1 - c_new_max1);

    pair_max0 = c_new_max0;
    pair_max1 = c_new_max1;
    pair_sum0 = pair_sum0 * c_factor0 + c_exp0;
    pair_sum1 = pair_sum1 * c_factor1 + c_exp1;

    pair_o0[0] = pair_o0[0] * c_factor0 + c_exp0 * pipe_vc0;
    pair_o1[0] = pair_o1[0] * c_factor1 + c_exp1 * pipe_vc0;
    pair_o0[1] = pair_o0[1] * c_factor0 + c_exp0 * pipe_vc1;
    pair_o1[1] = pair_o1[1] * c_factor1 + c_exp1 * pipe_vc1;
    pair_o0[2] = pair_o0[2] * c_factor0 + c_exp0 * pipe_vc2;
    pair_o1[2] = pair_o1[2] * c_factor1 + c_exp1 * pipe_vc2;
    pair_o0[3] = pair_o0[3] * c_factor0 + c_exp0 * pipe_vc3;
    pair_o1[3] = pair_o1[3] * c_factor1 + c_exp1 * pipe_vc3;

    U d_score0 = 0;
    U d_score1 = 0;
    d_score0 += pair_q0[0] * pipe_kd[0];
    d_score1 += pair_q1[0] * pipe_kd[0];
    d_score0 += pair_q0[1] * pipe_kd[1];
    d_score1 += pair_q1[1] * pipe_kd[1];
    d_score0 += pair_q0[2] * pipe_kd[2];
    d_score1 += pair_q1[2] * pipe_kd[2];
    d_score0 += pair_q0[3] * pipe_kd[3];
    d_score1 += pair_q1[3] * pipe_kd[3];
    d_score0 = simd_sum(d_score0);
    d_score1 = simd_sum(d_score1);

    U d_new_max0 = metal::max(pair_max0, d_score0);
    U d_new_max1 = metal::max(pair_max1, d_score1);
    U d_factor0;
    U d_factor1;
    LAGUNA_RESCALE(d_factor0, pair_max0 - d_new_max0);
    LAGUNA_RESCALE(d_factor1, pair_max1 - d_new_max1);
    U d_exp0 = metal::fast::exp(d_score0 - d_new_max0);
    U d_exp1 = metal::fast::exp(d_score1 - d_new_max1);

    pair_max0 = d_new_max0;
    pair_max1 = d_new_max1;
    pair_sum0 = pair_sum0 * d_factor0 + d_exp0;
    pair_sum1 = pair_sum1 * d_factor1 + d_exp1;

    pair_o0[0] = pair_o0[0] * d_factor0 + d_exp0 * pipe_vd0;
    pair_o1[0] = pair_o1[0] * d_factor1 + d_exp1 * pipe_vd0;
    pair_o0[1] = pair_o0[1] * d_factor0 + d_exp0 * pipe_vd1;
    pair_o1[1] = pair_o1[1] * d_factor1 + d_exp1 * pipe_vd1;
    pair_o0[2] = pair_o0[2] * d_factor0 + d_exp0 * pipe_vd2;
    pair_o1[2] = pair_o1[2] * d_factor1 + d_exp1 * pipe_vd2;
    pair_o0[3] = pair_o0[3] * d_factor0 + d_exp0 * pipe_vd3;
    pair_o1[3] = pair_o1[3] * d_factor1 + d_exp1 * pipe_vd3;

    pair_keys += 4 * inner_k_stride;
    pair_values += 4 * inner_v_stride;
}

constexpr int pair_planes = 2;
constexpr int pair_plane_size = BN * BDP;
if (lane == 0) {
    max_scores[sg] = pair_max0;
    max_scores[BN + sg] = pair_max1;
    sum_exp_scores[sg] = pair_sum0;
    sum_exp_scores[BN + sg] = pair_sum1;
}
for (int p = 0; p < pair_planes; ++p) {
    outputs[p * pair_plane_size + lane * BDP + sg] = pair_o0[p];
    outputs[
        (pair_planes + p) * pair_plane_size + lane * BDP + sg] =
        pair_o1[p];
}
threadgroup_barrier(mem_flags::mem_threadgroup);

pair_max0 = max_scores[lane];
pair_max1 = max_scores[BN + lane];
U pair_global_max0 = simd_max(pair_max0);
U pair_global_max1 = simd_max(pair_max1);
U pair_global_factor0 = metal::fast::exp(pair_max0 - pair_global_max0);
U pair_global_factor1 = metal::fast::exp(pair_max1 - pair_global_max1);
pair_sum0 = simd_sum(sum_exp_scores[lane] * pair_global_factor0);
pair_sum1 = simd_sum(sum_exp_scores[BN + lane] * pair_global_factor1);

for (int p = 0; p < pair_planes; ++p) {
    U acc0 = simd_sum(
        outputs[p * pair_plane_size + sg * BDP + lane] *
        pair_global_factor0);
    U acc1 = simd_sum(
        outputs[
            (pair_planes + p) * pair_plane_size + sg * BDP + lane] *
        pair_global_factor1);
    pair_o0[p] = pair_sum0 == 0 ? acc0 : (acc0 / pair_sum0);
    pair_o1[p] = pair_sum1 == 0 ? acc1 : (acc1 / pair_sum1);
}

threadgroup_barrier(mem_flags::mem_threadgroup);
for (int p = 0; p < pair_planes; ++p) {
    outputs[p * pair_plane_size + lane * BDP + sg] =
        pair_o0[pair_planes + p];
    outputs[
        (pair_planes + p) * pair_plane_size + lane * BDP + sg] =
        pair_o1[pair_planes + p];
}
threadgroup_barrier(mem_flags::mem_threadgroup);
for (int p = 0; p < pair_planes; ++p) {
    U acc0 = simd_sum(
        outputs[p * pair_plane_size + sg * BDP + lane] *
        pair_global_factor0);
    U acc1 = simd_sum(
        outputs[
            (pair_planes + p) * pair_plane_size + sg * BDP + lane] *
        pair_global_factor1);
    pair_o0[pair_planes + p] =
        pair_sum0 == 0 ? acc0 : (acc0 / pair_sum0);
    pair_o1[pair_planes + p] =
        pair_sum1 == 0 ? acc1 : (acc1 / pair_sum1);
}

if (lane == 0) {
    device bfloat* pair_out0 =
        attended + head0 * head_dim + sg * v_per_thread;
    device bfloat* pair_out1 =
        attended + head1 * head_dim + sg * v_per_thread;
    for (int p = 0; p < v_per_thread; ++p) {
        pair_out0[p] = static_cast<bfloat>(pair_o0[p]);
        pair_out1[p] = static_cast<bfloat>(pair_o1[p]);
    }
}
}
