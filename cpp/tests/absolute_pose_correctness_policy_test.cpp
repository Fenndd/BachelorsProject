#include <iostream>

#include "absolute_pose_benchmark.hpp"
#include "absolute_pose_metrics.hpp"

namespace {

bool expect_policy(
    const char* name,
    const benchmark::geometric_pose::absolute_pose::AbsolutePoseBenchmarkMetrics& metrics,
    bool expected
) {
    const bool actual =
        benchmark::geometric_pose::absolute_pose::correctness_policy_passed(metrics);
    if (actual != expected) {
        std::cout << "FAIL: " << name << " expected "
                  << std::boolalpha << expected << " got " << actual << '\n';
        return false;
    }
    std::cout << "PASS: " << name << '\n';
    return true;
}

benchmark::geometric_pose::absolute_pose::AbsolutePoseBenchmarkMetrics passing_metrics() {
    benchmark::geometric_pose::absolute_pose::AbsolutePoseBenchmarkMetrics metrics;
    metrics.num_problems = 100;
    metrics.total_solutions = 300;
    metrics.valid_solutions = 300;
    metrics.valid_solutions_percent = 100.0;
    metrics.gt_found = 100;
    metrics.gt_found_percent = 100.0;
    metrics.runtime_ns_per_problem_median = 1000.0;
    return metrics;
}

}  // namespace

int main() {
    bool all_tests_passed = true;

    all_tests_passed &= expect_policy("valid PoseLib-style metrics pass", passing_metrics(), true);

    {
        auto metrics = passing_metrics();
        metrics.num_problems = 0;
        all_tests_passed &= expect_policy("zero problems fail", metrics, false);
    }
    {
        auto metrics = passing_metrics();
        metrics.gt_found_percent = 98.99;
        all_tests_passed &= expect_policy("low GT-found percent fails", metrics, false);
    }
    {
        auto metrics = passing_metrics();
        metrics.valid_solutions_percent = 0.0;
        all_tests_passed &= expect_policy("zero valid-solution percent fails", metrics, false);
    }
    {
        auto metrics = passing_metrics();
        metrics.runtime_ns_per_problem_median = 0.0;
        all_tests_passed &= expect_policy("zero runtime fails", metrics, false);
    }

    std::cout << "\nOverall: " << (all_tests_passed ? "ALL PASSED" : "SOME FAILED") << '\n';
    return all_tests_passed ? 0 : 1;
}
