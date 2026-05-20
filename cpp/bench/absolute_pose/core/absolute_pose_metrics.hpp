#pragma once

#include <cstddef>
#include <string>

namespace benchmark::geometric_pose::absolute_pose {

struct AbsolutePoseBenchmarkMetrics {
    std::string solver_name;
    std::size_t num_problems = 0;
    std::size_t total_solutions = 0;
    double solutions_per_problem = 0.0;
    std::size_t valid_solutions = 0;
    double valid_solutions_percent = 0.0;
    std::size_t gt_found = 0;
    double gt_found_percent = 0.0;
    double runtime_ns_total_median = 0.0;
    double runtime_ns_per_problem_median = 0.0;
    bool correctness_passed = false;
};

}  // namespace benchmark::geometric_pose::absolute_pose
