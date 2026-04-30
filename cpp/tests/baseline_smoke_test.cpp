#include <iostream>
#include <vector>

#include "p3p.h"

int main() {
    std::cout << "Baseline smoke test started." << std::endl;

    const Eigen::Vector3d y1 = Eigen::Vector3d(0.0, 0.0, 1.0).normalized();
    const Eigen::Vector3d y2 = Eigen::Vector3d(1.0, 0.0, 1.0).normalized();
    const Eigen::Vector3d y3 = Eigen::Vector3d(2.0, 1.0, 1.0).normalized();

    const Eigen::Vector3d x1(0.0, 0.0, 2.0);
    const Eigen::Vector3d x2(1.41421356237309, 0.0, 1.41421356237309);
    const Eigen::Vector3d x3(1.63299316185545, 0.816496580927726, 0.816496580927726);

    const std::vector<Eigen::Vector3d> image_points = {y1, y2, y3};
    const std::vector<Eigen::Vector3d> world_points = {x1, x2, x3};

    std::vector<lambdatwist::CameraPose> poses;
    const int solution_count = lambdatwist::p3p(image_points, world_points, &poses);

    if (solution_count <= 0) {
        std::cout << "Baseline smoke test failed: solver returned no solutions." << std::endl;
        return 1;
    }

    std::cout << "Baseline smoke test passed: solver returned "
              << solution_count << " solution(s)." << std::endl;
    return 0;
}
