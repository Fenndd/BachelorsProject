#include <chrono>
#include <iostream>
#include <vector>

#include "p3p.h"

int main() {
    std::cout << "Baseline benchmark started." << std::endl;

    constexpr int iteration_count = 10000;

    const Eigen::Vector3d y1 = Eigen::Vector3d(0.0, 0.0, 1.0).normalized();
    const Eigen::Vector3d y2 = Eigen::Vector3d(1.0, 0.0, 1.0).normalized();
    const Eigen::Vector3d y3 = Eigen::Vector3d(2.0, 1.0, 1.0).normalized();

    const Eigen::Vector3d x1(0.0, 0.0, 2.0);
    const Eigen::Vector3d x2(1.41421356237309, 0.0, 1.41421356237309);
    const Eigen::Vector3d x3(1.63299316185545, 0.816496580927726, 0.816496580927726);

    const std::vector<Eigen::Vector3d> image_points = {y1, y2, y3};
    const std::vector<Eigen::Vector3d> world_points = {x1, x2, x3};

    std::vector<lambdatwist::CameraPose> poses;
    int total_solution_count = 0;

    const auto start_time = std::chrono::steady_clock::now();

    for (int iteration = 0; iteration < iteration_count; ++iteration) {
        poses.clear();
        const int solution_count = lambdatwist::p3p(image_points, world_points, &poses);

        if (solution_count <= 0) {
            std::cout << "Baseline benchmark failed: solver returned no solutions."
                      << std::endl;
            return 1;
        }

        total_solution_count += solution_count;
    }

    const auto end_time = std::chrono::steady_clock::now();
    const std::chrono::duration<double, std::milli> elapsed = end_time - start_time;
    const double average_microseconds =
        (elapsed.count() * 1000.0) / static_cast<double>(iteration_count);

    std::cout << "Iterations: " << iteration_count << std::endl;
    std::cout << "Total elapsed time: " << elapsed.count() << " ms" << std::endl;
    std::cout << "Average time per iteration: " << average_microseconds << " us"
              << std::endl;
    std::cout << "Total solutions produced: " << total_solution_count << std::endl;
    std::cout << "Baseline benchmark completed successfully." << std::endl;

    return 0;
}
