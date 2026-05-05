#include <algorithm>
#include <cmath>
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
using benchmark::geometric_pose::absolute_pose::AbsolutePoseCase;
using benchmark::geometric_pose::absolute_pose::AbsolutePoseResult;
using benchmark::geometric_pose::absolute_pose::AdapterInfo;
using benchmark::geometric_pose::absolute_pose::BenchmarkOptions;
using benchmark::geometric_pose::absolute_pose::Pose;
using benchmark::geometric_pose::absolute_pose::adapters::LambdaTwistP3PAdapter;
using benchmark::geometric_pose::absolute_pose::best_reprojection_error;
using benchmark::geometric_pose::absolute_pose::correctness_policy_passed;
using benchmark::geometric_pose::absolute_pose::generate_absolute_pose_cases;
using benchmark::geometric_pose::absolute_pose::is_finite_pose;
using benchmark::geometric_pose::absolute_pose::is_rotation_matrix_reasonable;

struct ValidationSummary {
    std::string adapter_name;
    std::size_t num_cases = 0;
    std::size_t passed_cases = 0;
    std::size_t failed_cases = 0;
    double success_rate = 0.0;
    double mean_best_reprojection_error = 0.0;
    double max_best_reprojection_error = 0.0;
    bool metadata_check_passed = false;
    bool solver_success_check_passed = true;
    bool finite_output_check_passed = true;
    bool rotation_matrix_check_passed = true;
    bool reprojection_check_passed = false;
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
    options.num_cases = 1000;
    options.warmup_iterations = 0;
    options.timed_iterations = 0;
    options.reprojection_error_threshold = 1e-6;
    options.random_seed = 42;

    const LambdaTwistP3PAdapter adapter;
    const std::vector<AbsolutePoseCase> test_cases = generate_absolute_pose_cases(options);

    ValidationSummary summary;
    summary.adapter_name = adapter.name();
    summary.num_cases = test_cases.size();
    summary.metadata_check_passed = validate_metadata(adapter);

    double finite_error_sum = 0.0;
    std::size_t finite_error_count = 0;

    for (const AbsolutePoseCase& test_case : test_cases) {
        const AbsolutePoseResult result = adapter.solve(test_case);

        if (!result.success || result.poses.empty()) {
            summary.solver_success_check_passed = false;
        }
        if (!result.success && !result.poses.empty()) {
            summary.solver_success_check_passed = false;
        }

        for (const Pose& pose : result.poses) {
            if (!is_finite_pose(pose)) {
                summary.finite_output_check_passed = false;
            }
            if (!is_rotation_matrix_reasonable(pose, rotation_tolerance)) {
                summary.rotation_matrix_check_passed = false;
            }
        }

        const double best_error = best_reprojection_error(test_case, result);
        if (std::isfinite(best_error)) {
            finite_error_sum += best_error;
            ++finite_error_count;
            summary.max_best_reprojection_error =
                std::max(summary.max_best_reprojection_error, best_error);
        } else {
            summary.max_best_reprojection_error = std::numeric_limits<double>::infinity();
        }

        if (best_error <= options.reprojection_error_threshold) {
            ++summary.passed_cases;
        }
    }

    summary.failed_cases = summary.num_cases - summary.passed_cases;
    if (summary.num_cases > 0) {
        summary.success_rate =
            static_cast<double>(summary.passed_cases) / static_cast<double>(summary.num_cases);
    }
    if (finite_error_count > 0) {
        summary.mean_best_reprojection_error =
            finite_error_sum / static_cast<double>(finite_error_count);
    } else if (summary.num_cases > 0) {
        summary.mean_best_reprojection_error = std::numeric_limits<double>::infinity();
    }

    // Build metrics object and use the shared correctness policy helper.
    AbsolutePoseBenchmarkMetrics metrics;
    metrics.num_cases = summary.num_cases;
    metrics.valid_cases = summary.passed_cases;
    metrics.success_rate = summary.success_rate;
    metrics.mean_best_reprojection_error = summary.mean_best_reprojection_error;
    metrics.max_best_reprojection_error = summary.max_best_reprojection_error;

    summary.reprojection_check_passed = correctness_policy_passed(metrics, options);

    summary.final_status_passed =
        summary.metadata_check_passed
        && summary.solver_success_check_passed
        && summary.finite_output_check_passed
        && summary.rotation_matrix_check_passed
        && summary.reprojection_check_passed;

    return summary;
}

void print_validation_summary(const ValidationSummary& summary) {
    std::cout << std::boolalpha << std::setprecision(12);
    std::cout << "adapter_name: " << summary.adapter_name << '\n';
    std::cout << "num_cases: " << summary.num_cases << '\n';
    std::cout << "passed_cases: " << summary.passed_cases << '\n';
    std::cout << "failed_cases: " << summary.failed_cases << '\n';
    std::cout << "success_rate: " << summary.success_rate << '\n';
    std::cout << "mean_best_reprojection_error: " << summary.mean_best_reprojection_error << '\n';
    std::cout << "max_best_reprojection_error: " << summary.max_best_reprojection_error << '\n';
    std::cout << "metadata_check_passed: " << summary.metadata_check_passed << '\n';
    std::cout << "solver_success_check_passed: " << summary.solver_success_check_passed << '\n';
    std::cout << "finite_output_check_passed: " << summary.finite_output_check_passed << '\n';
    std::cout << "rotation_matrix_check_passed: " << summary.rotation_matrix_check_passed << '\n';
    std::cout << "reprojection_check_passed: " << summary.reprojection_check_passed << '\n';
    std::cout << "final_status: " << (summary.final_status_passed ? "passed" : "failed") << '\n';
}

}  // namespace

int main() {
    const ValidationSummary summary = run_adapter_validation();
    print_validation_summary(summary);
    return summary.final_status_passed ? 0 : 1;
}