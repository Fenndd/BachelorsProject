#include <iostream>
#include <vector>

#include "p3p.h"

int main() {
    std::cout << "Baseline runner started." << std::endl;

    // Minimal fixed sample for compile/run-time wiring of the baseline target.
    const std::vector<Eigen::Vector3d> x = {
        Eigen::Vector3d(0.0, 0.0, 1.0),
        Eigen::Vector3d(1.0, 0.0, 5.0).normalized(),
        Eigen::Vector3d(0.0, 1.0, 5.0).normalized()
    };

    const std::vector<Eigen::Vector3d> X = {
        Eigen::Vector3d(0.0, 0.0, 5.0),
        Eigen::Vector3d(1.0, 0.0, 5.0),
        Eigen::Vector3d(0.0, 1.0, 5.0)
    };

    std::vector<lambdatwist::CameraPose> poses;
    const int solution_count = lambdatwist::p3p(x, X, &poses);

    std::cout << "Lambda Twist returned " << solution_count << " solution(s)." << std::endl;
    std::cout << "Baseline runner wiring is ready for the next integration step." << std::endl;
    return 0;
}
