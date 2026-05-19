#include <iomanip>
#include <iostream>
#include <limits>
#include <string>
#include <vector>

#include "absolute_pose_benchmark.hpp"
#include "absolute_pose_problem_generator.hpp"
#include "absolute_pose_validator.hpp"
#include "lambdatwist_p3p_adapter.hpp"

namespace {

using benchmark::geometric_pose::absolute_pose::AbsolutePoseBenchmarkMetrics;
using benchmark::geometric_pose::absolute_pose::AbsolutePoseProblemInstance;
using benchmark::geometric_pose::absolute_pose::AdapterInfo;
using benchmark::geometric_pose::absolute_pose::BenchmarkOptions;
using benchmark::geometric_pose::absolute_pose::Pose;
using benchmark::geometric_pose::absolute_pose::adapters::LambdaTwistP3PAdapter;
using benchmark::geometric_pose::absolute_pose::compute_pose_error;
using benchmark::geometric_pose::absolute_pose::correctness_policy_passed;
using benchmark::geometric_pose::absolute_pose::generate_absolute_pose_problems;
using benchmark::geometric_pose::absolute_pose::is_finite_pose;
using benchmark::geometric_pose::absolute_pose::is_rotation_matrix_reasonable;
using benchmark::geometric_pose::absolute_pose::is_valid_calibrated_pose;

struct ValidationSummary {
    std::string adapter_name;
    std::size_t num_problems = 0;
    std::size_t total_solutions = 0;
    double solutions_per_problem = 0.0;
    std::size_t valid_solutions = 0;
    double valid_solutions_percent = 0.0;
    std::size_t gt_found = 0;
    double gt_found_percent = 0.0;
    bool metadata_check_passed = false;
    bool solver_output_check_passed = true;
    bool finite_output_check_passed = true;
    bool rotation_matrix_check_passed = true;
    bool benchmark_correctness_check_passed = false;
    bool final_status_passed = false;
};

bool validate_metadata(const LambdaTwistP3PAdapter& adapter) {
    const AdapterInfo info = adapter.info();
    return !adapter.name().empty()
           && info.solver_name == "lambdatwist_p3p"
           && info.min_points == 3
           && info.default_case_points == 3
           && info.returns_multiple_solutions;
}

ValidationSummary run_adapter_validation() {
    constexpr double rotation_tolerance = 1e-5;

    BenchmarkOptions options;
    options.num_problems = 1000;
    options.tolerance = 1e-6;
    options.camera_fov = 75.0;
    options.n_point_point = 3;
    options.n_point_line = 0;
    options.timed_iterations = 1;

    const LambdaTwistP3PAdapter adapter;
    const std::vector<AbsolutePoseProblemInstance> problem_instances =
        generate_absolute_pose_problems(options);

    ValidationSummary summary;
    summary.adapter_name = adapter.name();
    summary.num_problems = problem_instances.size();
    summary.metadata_check_passed = validate_metadata(adapter);

    for (const AbsolutePoseProblemInstance& instance : problem_instances) {
        std::vector<Pose> solutions;
        const int solution_count = adapter.solve(instance, &solutions);

        if (solution_count <= 0 || solutions.empty()) {
            summary.solver_output_check_passed = false;
        }
        if (solution_count > 0) {
            summary.total_solutions += static_cast<std::size_t>(solution_count);
        }

        double best_pose_error = std::numeric_limits<double>::max();
        for (const Pose& pose : solutions) {
            if (!is_finite_pose(pose)) {
                summary.finite_output_check_passed = false;
            }
            if (!is_rotation_matrix_reasonable(pose, rotation_tolerance)) {
                summary.rotation_matrix_check_passed = false;
            }
            if (is_valid_calibrated_pose(instance, pose, 1.0, options.tolerance)) {
                ++summary.valid_solutions;
            }
            best_pose_error = std::min(best_pose_error, compute_pose_error(instance, pose, 1.0));
        }

        if (best_pose_error < options.tolerance) {
            ++summary.gt_found;
        }
    }

    if (summary.num_problems > 0) {
        summary.solutions_per_problem =
            static_cast<double>(summary.total_solutions) / static_cast<double>(summary.num_problems);
        summary.gt_found_percent =
            static_cast<double>(summary.gt_found) / static_cast<double>(summary.num_problems) * 100.0;
    }
    if (summary.total_solutions > 0) {
        summary.valid_solutions_percent =
            static_cast<double>(summary.valid_solutions) / static_cast<double>(summary.total_solutions) * 100.0;
    }

    AbsolutePoseBenchmarkMetrics metrics;
    metrics.num_problems = summary.num_problems;
    metrics.valid_solutions = summary.valid_solutions;
    metrics.valid_solutions_percent = summary.valid_solutions_percent;
    metrics.gt_found = summary.gt_found;
    metrics.gt_found_percent = summary.gt_found_percent;
    metrics.runtime_ns_per_problem_median = 1.0;

    summary.benchmark_correctness_check_passed = correctness_policy_passed(metrics);
    summary.final_status_passed =
        summary.metadata_check_passed
        && summary.solver_output_check_passed
        && summary.finite_output_check_passed
        && summary.rotation_matrix_check_passed
        && summary.benchmark_correctness_check_passed;

    return summary;
}

void print_validation_summary(const ValidationSummary& summary) {
    std::cout << std::boolalpha << std::setprecision(12);
    std::cout << "adapter_name: " << summary.adapter_name << '\n';
    std::cout << "num_problems: " << summary.num_problems << '\n';
    std::cout << "total_solutions: " << summary.total_solutions << '\n';
    std::cout << "solutions_per_problem: " << summary.solutions_per_problem << '\n';
    std::cout << "valid_solutions: " << summary.valid_solutions << '\n';
    std::cout << "valid_solutions_percent: " << summary.valid_solutions_percent << '\n';
    std::cout << "gt_found: " << summary.gt_found << '\n';
    std::cout << "gt_found_percent: " << summary.gt_found_percent << '\n';
    std::cout << "metadata_check_passed: " << summary.metadata_check_passed << '\n';
    std::cout << "solver_output_check_passed: " << summary.solver_output_check_passed << '\n';
    std::cout << "finite_output_check_passed: " << summary.finite_output_check_passed << '\n';
    std::cout << "rotation_matrix_check_passed: " << summary.rotation_matrix_check_passed << '\n';
    std::cout << "benchmark_correctness_check_passed: "
              << summary.benchmark_correctness_check_passed << '\n';
    std::cout << "final_status: " << (summary.final_status_passed ? "passed" : "failed") << '\n';
}

}  // namespace

int main() {
    const ValidationSummary summary = run_adapter_validation();
    print_validation_summary(summary);
    return summary.final_status_passed ? 0 : 1;
}
