#pragma once

#include <cstddef>
#include <string>
#include <vector>

#include <Eigen/Dense>

namespace benchmark::geometric_pose::absolute_pose {

struct Pose {
    // Canonical absolute-pose convention:
    // X_cam = R * X_world + t
    Eigen::Matrix3d R = Eigen::Matrix3d::Identity();
    Eigen::Vector3d t = Eigen::Vector3d::Zero();
};

struct AbsolutePoseProblemInstance {
    Pose pose_gt;
    double scale_gt = 1.0;

    std::vector<Eigen::Vector3d> x_point_;
    std::vector<Eigen::Vector3d> X_point_;
    std::vector<Eigen::Vector3d> p_point_;
};

struct AdapterInfo {
    std::string solver_name;
    int min_points = 0;
    int default_case_points = 0;
    bool returns_multiple_solutions = false;
};

struct BenchmarkOptions {
    std::size_t num_problems = 100000;
    std::size_t timed_iterations = 10;
    double tolerance = 1e-6;
    double camera_fov = 75.0;
    double min_depth = 0.1;
    double max_depth = 10.0;
    int n_point_point = 3;
    int n_point_line = 0;
};

}  // namespace benchmark::geometric_pose::absolute_pose
