#include <iostream>

#include "absolute_pose_problem_generator.hpp"
#include "lambdatwist_p3p_adapter.hpp"

int main() {
    using benchmark::geometric_pose::absolute_pose::BenchmarkOptions;
    using benchmark::geometric_pose::absolute_pose::generate_absolute_pose_cases;
    using benchmark::geometric_pose::absolute_pose::adapters::LambdaTwistP3PAdapter;

    const LambdaTwistP3PAdapter adapter;
    const auto info = adapter.info();

    if (adapter.name().empty()
        || info.min_points != 3
        || info.default_case_points != 3
        || !info.returns_multiple_solutions) {
        std::cout << "Absolute pose adapter smoke test failed: invalid metadata." << std::endl;
        return 1;
    }

    BenchmarkOptions options;
    options.num_cases = 1;
    options.warmup_iterations = 0;
    options.timed_iterations = 1;

    const auto cases = generate_absolute_pose_cases(options);
    if (cases.empty()) {
        std::cout << "Absolute pose adapter smoke test failed: no generated cases." << std::endl;
        return 1;
    }

    const auto result = adapter.solve(cases.front());
    std::cout << "Absolute pose adapter smoke test passed: solver returned "
              << result.poses.size() << " solution(s)." << std::endl;
    return 0;
}
