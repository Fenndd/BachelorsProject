#pragma once

#include "absolute_pose_adapter.hpp"
#include "absolute_pose_metrics.hpp"
#include "absolute_pose_types.hpp"

namespace benchmark::geometric_pose::absolute_pose {

AbsolutePoseBenchmarkMetrics run_absolute_pose_benchmark(
    const AbsolutePoseSolverAdapter& adapter,
    const BenchmarkOptions& options
);

}  // namespace benchmark::geometric_pose::absolute_pose
