#include "VectorContainerLifetimeFixtures.h"

#include "mlx/array.h"

extern "C" mlx_array mlx_benchmark_array_new_lazy(void) {
  return mlx_array{new mlx::core::array(
      mlx::core::Shape{}, mlx::core::int32, nullptr, {})};
}
