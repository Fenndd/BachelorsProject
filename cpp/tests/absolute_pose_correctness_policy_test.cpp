#include <cmath>
#include <iostream>
#include <limits>

#include "absolute_pose_benchmark.hpp"
#include "absolute_pose_types.hpp"

int main() {
    using namespace benchmark::geometric_pose::absolute_pose;

    bool all_tests_passed = true;

    // --- Test 1: default options, perfect metrics ---
    {
        AbsolutePoseBenchmarkMetrics metrics;
        metrics.num_cases = 100;
        metrics.valid_cases = 100;
        metrics.success_rate = 1.0;
        metrics.mean_best_reprojection_error = 1e-8;
        metrics.max_best_reprojection_error = 1e-8;

        BenchmarkOptions options;

        const bool passed = correctness_policy_passed(metrics, options);
        if (!passed) {
            std::cout << "FAIL: Test 1 - perfect metrics should pass with default options.\n";
            all_tests_passed = false;
        } else {
            std::cout << "PASS: Test 1 - perfect metrics pass with default options.\n";
        }
    }

    // --- Test 2: borderline success rate just at threshold ---
    {
        AbsolutePoseBenchmarkMetrics metrics;
        metrics.num_cases = 100;
        metrics.valid_cases = 99;
        metrics.success_rate = 0.99;
        metrics.mean_best_reprojection_error = 1e-8;
        metrics.max_best_reprojection_error = 1e-8;

        BenchmarkOptions options;
        options.min_success_rate = 0.99;

        const bool passed = correctness_policy_passed(metrics, options);
        if (!passed) {
            std::cout << "FAIL: Test 2 - success rate at threshold (0.99) should pass.\n";
            all_tests_passed = false;
        } else {
            std::cout << "PASS: Test 2 - success rate at threshold (0.99) passes.\n";
        }
    }

    // --- Test 3: success rate below threshold ---
    {
        AbsolutePoseBenchmarkMetrics metrics;
        metrics.num_cases = 100;
        metrics.valid_cases = 98;
        metrics.success_rate = 0.98;
        metrics.mean_best_reprojection_error = 1e-8;
        metrics.max_best_reprojection_error = 1e-8;

        BenchmarkOptions options;
        options.min_success_rate = 0.99;

        const bool passed = correctness_policy_passed(metrics, options);
        if (passed) {
            std::cout << "FAIL: Test 3 - success rate (0.98) below threshold (0.99) should fail.\n";
            all_tests_passed = false;
        } else {
            std::cout << "PASS: Test 3 - success rate below threshold correctly fails.\n";
        }
    }

    // --- Test 4: mean reprojection error above threshold ---
    {
        AbsolutePoseBenchmarkMetrics metrics;
        metrics.num_cases = 100;
        metrics.valid_cases = 100;
        metrics.success_rate = 1.0;
        metrics.mean_best_reprojection_error = 1e-4;
        metrics.max_best_reprojection_error = 2e-4;

        BenchmarkOptions options;
        options.reprojection_error_threshold = 1e-6;

        const bool passed = correctness_policy_passed(metrics, options);
        if (passed) {
            std::cout << "FAIL: Test 4 - mean error above threshold should fail.\n";
            all_tests_passed = false;
        } else {
            std::cout << "PASS: Test 4 - mean error above threshold correctly fails.\n";
        }
    }

    // --- Test 5: require_all_cases_valid enabled, all valid ---
    {
        AbsolutePoseBenchmarkMetrics metrics;
        metrics.num_cases = 100;
        metrics.valid_cases = 100;
        metrics.success_rate = 1.0;
        metrics.mean_best_reprojection_error = 1e-8;
        metrics.max_best_reprojection_error = 1e-8;

        BenchmarkOptions options;
        options.require_all_cases_valid = true;

        const bool passed = correctness_policy_passed(metrics, options);
        if (!passed) {
            std::cout << "FAIL: Test 5 - require_all_cases_valid with all valid should pass.\n";
            all_tests_passed = false;
        } else {
            std::cout << "PASS: Test 5 - require_all_cases_valid with all valid passes.\n";
        }
    }

    // --- Test 6: require_all_cases_valid enabled, not all valid ---
    {
        AbsolutePoseBenchmarkMetrics metrics;
        metrics.num_cases = 100;
        metrics.valid_cases = 99;
        metrics.success_rate = 0.99;
        metrics.mean_best_reprojection_error = 1e-8;
        metrics.max_best_reprojection_error = 1e-8;

        BenchmarkOptions options;
        options.require_all_cases_valid = true;

        const bool passed = correctness_policy_passed(metrics, options);
        if (passed) {
            std::cout << "FAIL: Test 6 - require_all_cases_valid with 99/100 should fail.\n";
            all_tests_passed = false;
        } else {
            std::cout << "PASS: Test 6 - require_all_cases_valid with 99/100 correctly fails.\n";
        }
    }

    // --- Test 7: use_max_reprojection_error_as_hard_gate, max below threshold ---
    {
        AbsolutePoseBenchmarkMetrics metrics;
        metrics.num_cases = 100;
        metrics.valid_cases = 100;
        metrics.success_rate = 1.0;
        metrics.mean_best_reprojection_error = 1e-8;
        metrics.max_best_reprojection_error = 5e-7;

        BenchmarkOptions options;
        options.use_max_reprojection_error_as_hard_gate = true;
        options.reprojection_error_threshold = 1e-6;

        const bool passed = correctness_policy_passed(metrics, options);
        if (!passed) {
            std::cout << "FAIL: Test 7 - max error (5e-7) below threshold (1e-6) should pass.\n";
            all_tests_passed = false;
        } else {
            std::cout << "PASS: Test 7 - max error below threshold passes.\n";
        }
    }

    // --- Test 8: use_max_reprojection_error_as_hard_gate, max above threshold ---
    {
        AbsolutePoseBenchmarkMetrics metrics;
        metrics.num_cases = 100;
        metrics.valid_cases = 100;
        metrics.success_rate = 1.0;
        metrics.mean_best_reprojection_error = 1e-8;
        metrics.max_best_reprojection_error = 5e-5;

        BenchmarkOptions options;
        options.use_max_reprojection_error_as_hard_gate = true;
        options.reprojection_error_threshold = 1e-6;

        const bool passed = correctness_policy_passed(metrics, options);
        if (passed) {
            std::cout << "FAIL: Test 8 - max error (5e-5) above threshold (1e-6) should fail.\n";
            all_tests_passed = false;
        } else {
            std::cout << "PASS: Test 8 - max error above threshold correctly fails.\n";
        }
    }

    // --- Test 9: num_cases == 0 ---
    {
        AbsolutePoseBenchmarkMetrics metrics;
        metrics.num_cases = 0;
        metrics.valid_cases = 0;
        metrics.success_rate = 0.0;
        metrics.mean_best_reprojection_error = std::numeric_limits<double>::infinity();
        metrics.max_best_reprojection_error = std::numeric_limits<double>::infinity();

        BenchmarkOptions options;

        const bool passed = correctness_policy_passed(metrics, options);
        if (passed) {
            std::cout << "FAIL: Test 9 - num_cases == 0 should always fail.\n";
            all_tests_passed = false;
        } else {
            std::cout << "PASS: Test 9 - num_cases == 0 correctly fails.\n";
        }
    }

    std::cout << "\nOverall: " << (all_tests_passed ? "ALL PASSED" : "SOME FAILED") << std::endl;
    return all_tests_passed ? 0 : 1;
}