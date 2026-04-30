#pragma once

#include <Eigen/Dense>
#include <vector>

namespace baseline_sample_data {

struct BaselineSampleData {
    std::vector<Eigen::Vector3d> image_points;
    std::vector<Eigen::Vector3d> world_points;
};

BaselineSampleData make_baseline_sample_data();

}  // namespace baseline_sample_data
