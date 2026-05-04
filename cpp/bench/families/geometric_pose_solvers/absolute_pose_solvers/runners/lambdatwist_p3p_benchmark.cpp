#include <iomanip>
#include <iostream>

#include "absolute_pose_benchmark.hpp"
#include "lambdatwist_p3p_adapter.hpp"

int main() {
    using benchmark::geometric_pose::absolute_pose::AbsolutePoseBenchmarkMetrics;
    using benchmark::geometric_pose::absolute_pose::BenchmarkOptions;
    using benchmark::geometric_pose::absolute_pose::run_absolute_pose_benchmark;
    using benchmark::geometric_pose::absolute_pose::adapters::LambdaTwistP3PAdapter;

    const LambdaTwistP3PAdapter adapter;
    BenchmarkOptions options;

    const AbsolutePoseBenchmarkMetrics metrics =
        run_absolute_pose_benchmark(adapter, options);

    std::cout << std::boolalpha << std::setprecision(12);
    std::cout << "solver_name: " << metrics.solver_name << '\n';
    std::cout << "num_cases: " << metrics.num_cases << '\n';
    std::cout << "total_solutions: " << metrics.total_solutions << '\n';
    std::cout << "valid_cases: " << metrics.valid_cases << '\n';
    std::cout << "success_rate: " << metrics.success_rate << '\n';
    std::cout << "mean_best_reprojection_error: " << metrics.mean_best_reprojection_error << '\n';
    std::cout << "max_best_reprojection_error: " << metrics.max_best_reprojection_error << '\n';
    std::cout << "runtime_ns_total_median: " << metrics.runtime_ns_total_median << '\n';
    std::cout << "runtime_ns_per_case_median: " << metrics.runtime_ns_per_case_median << '\n';
    std::cout << "correctness_passed: " << metrics.correctness_passed << '\n';

    return metrics.correctness_passed ? 0 : 1;
}
