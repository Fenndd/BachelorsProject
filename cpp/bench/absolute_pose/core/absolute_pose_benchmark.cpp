#include "absolute_pose_benchmark.hpp"

// Closely adapted from PoseLib's benchmark/solver_benchmark.{h,cc}.
// Copyright (c) 2020, Viktor Larsson. BSD 3-Clause License.

#include <algorithm>
#include <chrono>
#include <limits>
#include <vector>

#include "absolute_pose_problem_generator.hpp"
#include "absolute_pose_validator.hpp"

namespace benchmark::geometric_pose::absolute_pose {
namespace {

double poselib_style_median_runtime(std::vector<long long> runtimes) {
    if (runtimes.empty()) {
        return 0.0;
    }

    std::sort(runtimes.begin(), runtimes.end());
    return static_cast<double>(runtimes[runtimes.size() / 2]);
}

}  // namespace

bool correctness_policy_passed(const AbsolutePoseBenchmarkMetrics& metrics) {
    return metrics.num_problems > 0
           && metrics.gt_found_percent >= 99.0
           && metrics.valid_solutions_percent > 0.0
           && metrics.runtime_ns_per_problem_median > 0.0;
}

AbsolutePoseBenchmarkMetrics run_absolute_pose_benchmark(
    const AbsolutePoseSolverAdapter& adapter,
    const BenchmarkOptions& options
) {
    const std::vector<AbsolutePoseProblemInstance> problem_instances =
        generate_absolute_pose_problems(options);

    AbsolutePoseBenchmarkMetrics metrics;
    metrics.solver_name = adapter.name();
    metrics.num_problems = problem_instances.size();

    for (const AbsolutePoseProblemInstance& instance : problem_instances) {
        std::vector<Pose> solutions;
        const int solution_count = adapter.solve(instance, &solutions);

        double pose_error = std::numeric_limits<double>::max();
        if (solution_count > 0) {
            metrics.total_solutions += static_cast<std::size_t>(solution_count);
        }

        for (const Pose& pose : solutions) {
            if (is_valid_calibrated_pose(instance, pose, 1.0, options.tolerance)) {
                ++metrics.valid_solutions;
            }
            pose_error = std::min(pose_error, compute_pose_error(instance, pose, 1.0));
        }

        if (pose_error < options.tolerance) {
            ++metrics.gt_found;
        }
    }

    if (metrics.num_problems > 0) {
        metrics.solutions_per_problem =
            static_cast<double>(metrics.total_solutions) / static_cast<double>(metrics.num_problems);
        metrics.gt_found_percent =
            static_cast<double>(metrics.gt_found) / static_cast<double>(metrics.num_problems) * 100.0;
    }
    if (metrics.total_solutions > 0) {
        metrics.valid_solutions_percent =
            static_cast<double>(metrics.valid_solutions) / static_cast<double>(metrics.total_solutions) * 100.0;
    }

    std::vector<long long> runtimes;
    runtimes.reserve(options.timed_iterations);
    std::vector<Pose> solutions;

    for (std::size_t iter = 0; iter < options.timed_iterations; ++iter) {
        const auto start_time = std::chrono::high_resolution_clock::now();
        for (const AbsolutePoseProblemInstance& instance : problem_instances) {
            solutions.clear();
            adapter.solve(instance, &solutions);
        }
        const auto end_time = std::chrono::high_resolution_clock::now();
        runtimes.push_back(
            std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - start_time).count()
        );
    }

    metrics.runtime_ns_total_median = poselib_style_median_runtime(runtimes);
    if (metrics.num_problems > 0) {
        metrics.runtime_ns_per_problem_median =
            metrics.runtime_ns_total_median / static_cast<double>(metrics.num_problems);
    }
    metrics.correctness_passed = correctness_policy_passed(metrics);

    return metrics;
}

}  // namespace benchmark::geometric_pose::absolute_pose
