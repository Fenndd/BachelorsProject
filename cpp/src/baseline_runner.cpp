#include <iostream>
#include <vector>

#include "baseline_sample_data.h"
#include "p3p.h"

int main() {
    std::cout << "Baseline runner started." << std::endl;

    const baseline_sample_data::BaselineSampleData sample =
        baseline_sample_data::make_baseline_sample_data();

    std::vector<lambdatwist::CameraPose> poses;
    const int solution_count =
        lambdatwist::p3p(sample.image_points, sample.world_points, &poses);

    std::cout << "Lambda Twist returned " << solution_count << " solution(s)." << std::endl;
    std::cout << "Baseline runner wiring is ready for the next integration step." << std::endl;
    return 0;
}
