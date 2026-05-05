#pragma once

#include "absolute_pose_adapter.hpp"
#include "absolute_pose_metrics.hpp"
#include "absolute_pose_types.hpp"

namespace benchmark::geometric_pose::absolute_pose {

AbsolutePoseBenchmarkMetrics run_absolute_pose_benchmark(
    const AbsolutePoseSolverAdapter& adapter,
    const BenchmarkOptions& options
);

// Shared correctness acceptance policy for adapter validation and benchmark runs.
//
// Returns true when all of the following hold:
//   - num_cases > 0
//   - success_rate >= options.min_success_rate
//   - mean_best_reprojection_error <= options.reprojection_error_threshold
//
// If options.require_all_cases_valid is true, also requires:
//   - valid_cases == num_cases
//
// If options.use_max_reprojection_error_as_hard_gate is true, also requires:
//   - max_best_reprojection_error <= options.reprojection_error_threshold
bool correctness_policy_passed(
    const AbsolutePoseBenchmarkMetrics& metrics,
    const BenchmarkOptions& options
);

}  // namespace benchmark::geometric_pose::absolute_pose