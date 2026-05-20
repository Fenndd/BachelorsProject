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
    options.camera_fov = 75.0;
    options.n_point_point = 3;
    options.n_point_line = 0;
    options.tolerance = 1e-6;
    options.num_problems = 100000;
    options.timed_iterations = 10;

    const AbsolutePoseBenchmarkMetrics metrics =
        run_absolute_pose_benchmark(adapter, options);

    std::cout << std::boolalpha << std::setprecision(12);
    std::cout << "solver_name: " << metrics.solver_name << '\n';
    std::cout << "num_problems: " << metrics.num_problems << '\n';
    std::cout << "total_solutions: " << metrics.total_solutions << '\n';
    std::cout << "solutions_per_problem: " << metrics.solutions_per_problem << '\n';
    std::cout << "valid_solutions: " << metrics.valid_solutions << '\n';
    std::cout << "valid_solutions_percent: " << metrics.valid_solutions_percent << '\n';
    std::cout << "gt_found: " << metrics.gt_found << '\n';
    std::cout << "gt_found_percent: " << metrics.gt_found_percent << '\n';
    std::cout << "runtime_ns_total_median: " << metrics.runtime_ns_total_median << '\n';
    std::cout << "runtime_ns_per_problem_median: " << metrics.runtime_ns_per_problem_median << '\n';
    std::cout << "tolerance: " << options.tolerance << '\n';
    std::cout << "camera_fov: " << options.camera_fov << '\n';
    std::cout << "n_point_point: " << options.n_point_point << '\n';
    std::cout << "n_point_line: " << options.n_point_line << '\n';
    std::cout << "timed_iterations: " << options.timed_iterations << '\n';
    std::cout << "runtime_unit: ns\n";
    std::cout << "correctness_passed: " << metrics.correctness_passed << '\n';

    return 0;
}
