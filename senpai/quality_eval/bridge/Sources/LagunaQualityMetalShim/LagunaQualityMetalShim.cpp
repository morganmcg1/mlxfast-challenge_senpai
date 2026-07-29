#include "LagunaQualityMetalShim.h"

#include <string>

namespace mlx {
namespace core {
namespace metal {
void set_metallib_path(const std::string &path);
}
} // namespace core
} // namespace mlx

void laguna_quality_set_metallib_path(const char *path) {
  mlx::core::metal::set_metallib_path(path);
}
