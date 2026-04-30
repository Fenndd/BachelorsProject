#include <chrono>
#include <iostream>
#include <vector>

#include "baseline_sample_data.h"
#include "p3p.h"

int main() {
    std::cout << "Baseline benchmark started." << std::endl;

    constexpr int iteration_count = 10000;

    const baseline_sample_data::BaselineSampleData sample =
        baseline_sample_data::make_baseline_sample_data();

    std::vector<lambdatwist::CameraPose> poses;
    int total_solution_count = 0;

    const auto start_time = std::chrono::steady_clock::now();

    for (int iteration = 0; iteration < iteration_count; ++iteration) {
        poses.clear();
        const int solution_count =
            lambdatwist::p3p(sample.image_points, sample.world_points, &poses);

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
