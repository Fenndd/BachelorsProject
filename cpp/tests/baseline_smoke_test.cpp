#include <iostream>
#include <vector>

#include "baseline_sample_data.h"
#include "p3p.h"

int main() {
    std::cout << "Baseline smoke test started." << std::endl;

    const baseline_sample_data::BaselineSampleData sample =
        baseline_sample_data::make_baseline_sample_data();

    std::vector<lambdatwist::CameraPose> poses;
    const int solution_count =
        lambdatwist::p3p(sample.image_points, sample.world_points, &poses);

    if (solution_count <= 0) {
        std::cout << "Baseline smoke test failed: solver returned no solutions." << std::endl;
        return 1;
    }

    std::cout << "Baseline smoke test passed: solver returned "
              << solution_count << " solution(s)." << std::endl;
    return 0;
}
