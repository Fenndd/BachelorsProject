#include <iostream>
#include <vector>

#include "absolute_pose_problem_generator.hpp"
#include "lambdatwist_p3p_adapter.hpp"

int main() {
    using benchmark::geometric_pose::absolute_pose::BenchmarkOptions;
    using benchmark::geometric_pose::absolute_pose::Pose;
    using benchmark::geometric_pose::absolute_pose::generate_absolute_pose_problems;
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
    options.num_problems = 1;
    options.timed_iterations = 1;
    options.camera_fov = 75.0;
    options.n_point_point = 3;
    options.n_point_line = 0;

    const auto problems = generate_absolute_pose_problems(options);
    if (problems.empty()) {
        std::cout << "Absolute pose adapter smoke test failed: no generated problems." << std::endl;
        return 1;
    }

    std::vector<Pose> solutions;
    const int solution_count = adapter.solve(problems.front(), &solutions);
    if (solution_count <= 0 || solutions.empty()) {
        std::cout << "Absolute pose adapter smoke test failed: solver returned no solutions." << std::endl;
        return 1;
    }

    std::cout << "Absolute pose adapter smoke test passed: solver returned "
              << solutions.size() << " solution(s)." << std::endl;
    return 0;
}
