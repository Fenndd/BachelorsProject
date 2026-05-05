#include "absolute_pose_benchmark.hpp"

#include <algorithm>
#include <chrono>
#include <cmath>
#include <limits>
#include <vector>

#include "absolute_pose_problem_generator.hpp"
#include "absolute_pose_validator.hpp"

namespace benchmark::geometric_pose::absolute_pose {
namespace {

double median_runtime(std::vector<double> runtimes) {
    if (runtimes.empty()) {
        return 0.0;
    }

    std::sort(runtimes.begin(), runtimes.end());
    const std::size_t middle = runtimes.size() / 2;
    if (runtimes.size() % 2 == 1) {
        return runtimes[middle];
    }
    return 0.5 * (runtimes[middle - 1] + runtimes[middle]);
}

}  // namespace

bool correctness_policy_passed(
    const AbsolutePoseBenchmarkMetrics& metrics,
    const BenchmarkOptions& options
) {
    if (metrics.num_cases == 0) {
        return false;
    }

    const bool success_rate_ok =
        metrics.success_rate >= options.min_success_rate;
    const bool mean_error_ok =
        metrics.mean_best_reprojection_error <= options.reprojection_error_threshold;

    bool result = success_rate_ok && mean_error_ok;

    if (options.require_all_cases_valid) {
        result = result && (metrics.valid_cases == metrics.num_cases);
    }

    if (options.use_max_reprojection_error_as_hard_gate) {
        result = result &&
            metrics.max_best_reprojection_error <= options.reprojection_error_threshold;
    }

    return result;
}

AbsolutePoseBenchmarkMetrics run_absolute_pose_benchmark(
    const AbsolutePoseSolverAdapter& adapter,
    const BenchmarkOptions& options
) {
    const std::vector<AbsolutePoseCase> test_cases = generate_absolute_pose_cases(options);

    AbsolutePoseBenchmarkMetrics metrics;
    metrics.solver_name = adapter.name();
    metrics.num_cases = test_cases.size();

    double finite_error_sum = 0.0;
    std::size_t finite_error_count = 0;
    metrics.max_best_reprojection_error = 0.0;

    for (const AbsolutePoseCase& test_case : test_cases) {
        const AbsolutePoseResult result = adapter.solve(test_case);
        metrics.total_solutions += result.poses.size();

        const double best_error = best_reprojection_error(test_case, result);
        if (std::isfinite(best_error)) {
            finite_error_sum += best_error;
            ++finite_error_count;
            metrics.max_best_reprojection_error = std::max(metrics.max_best_reprojection_error, best_error);
        } else {
            metrics.max_best_reprojection_error = std::numeric_limits<double>::infinity();
        }

        if (best_error <= options.reprojection_error_threshold) {
            ++metrics.valid_cases;
        }
    }

    if (metrics.num_cases > 0) {
        metrics.success_rate =
            static_cast<double>(metrics.valid_cases) / static_cast<double>(metrics.num_cases);
    }
    if (finite_error_count > 0) {
        metrics.mean_best_reprojection_error =
            finite_error_sum / static_cast<double>(finite_error_count);
    } else if (metrics.num_cases > 0) {
        metrics.mean_best_reprojection_error = std::numeric_limits<double>::infinity();
    }

    // Use shared correctness policy instead of hardcoded 100% valid-cases check.
    metrics.correctness_passed = correctness_policy_passed(metrics, options);

    for (std::size_t warmup_index = 0; warmup_index < options.warmup_iterations; ++warmup_index) {
        std::size_t warmup_solution_count = 0;
        for (const AbsolutePoseCase& test_case : test_cases) {
            warmup_solution_count += adapter.solve(test_case).poses.size();
        }
        volatile std::size_t sink = warmup_solution_count;
        (void)sink;
    }

    std::vector<double> timed_runtimes;
    timed_runtimes.reserve(options.timed_iterations);

    for (std::size_t timed_index = 0; timed_index < options.timed_iterations; ++timed_index) {
        std::size_t timed_solution_count = 0;
        const auto start_time = std::chrono::steady_clock::now();
        for (const AbsolutePoseCase& test_case : test_cases) {
            timed_solution_count += adapter.solve(test_case).poses.size();
        }
        const auto end_time = std::chrono::steady_clock::now();
        volatile std::size_t sink = timed_solution_count;
        (void)sink;

        const auto elapsed =
            std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - start_time);
        timed_runtimes.push_back(static_cast<double>(elapsed.count()));
    }

    metrics.runtime_ns_total_median = median_runtime(timed_runtimes);
    if (metrics.num_cases > 0) {
        metrics.runtime_ns_per_case_median =
            metrics.runtime_ns_total_median / static_cast<double>(metrics.num_cases);
    }

    return metrics;
}

}  // namespace benchmark::geometric_pose::absolute_pose