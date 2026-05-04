#pragma once

#include <cstddef>
#include <string>

namespace benchmark::geometric_pose::absolute_pose {

struct AbsolutePoseBenchmarkMetrics {
    std::string solver_name;
    std::size_t num_cases = 0;
    std::size_t total_solutions = 0;
    std::size_t valid_cases = 0;
    double success_rate = 0.0;
    double mean_best_reprojection_error = 0.0;
    double max_best_reprojection_error = 0.0;
    double runtime_ns_total_median = 0.0;
    double runtime_ns_per_case_median = 0.0;
    bool correctness_passed = false;
};

}  // namespace benchmark::geometric_pose::absolute_pose
