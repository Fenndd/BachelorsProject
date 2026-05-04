#pragma once

#include <array>
#include <cstddef>
#include <string>
#include <vector>

namespace benchmark::geometric_pose::absolute_pose {

struct Vec2 {
    double x = 0.0;
    double y = 0.0;
};

struct Vec3 {
    double x = 0.0;
    double y = 0.0;
    double z = 0.0;
};

struct CameraIntrinsics {
    double fx = 800.0;
    double fy = 820.0;
    double cx = 320.0;
    double cy = 240.0;
};

struct Pose {
    // Canonical absolute-pose convention used by every adapter:
    // X_cam = R * X_world + t
    // R is stored as a row-major 3x3 rotation matrix.
    std::array<double, 9> R = {
        1.0, 0.0, 0.0,
        0.0, 1.0, 0.0,
        0.0, 0.0, 1.0,
    };
    std::array<double, 3> t = {0.0, 0.0, 0.0};
};

struct AbsolutePoseCase {
    std::vector<Vec3> points3d;
    std::vector<Vec2> points2d;
    CameraIntrinsics intrinsics;
    Pose ground_truth_pose;
};

struct AbsolutePoseResult {
    std::vector<Pose> poses;
    bool success = false;
};

struct AdapterInfo {
    std::string solver_name;
    int min_points = 0;
    int default_case_points = 0;
    bool returns_multiple_solutions = false;
};

struct BenchmarkOptions {
    std::size_t num_cases = 1000;
    std::size_t warmup_iterations = 3;
    std::size_t timed_iterations = 10;
    std::size_t points_per_case = 3;
    double reprojection_error_threshold = 1e-6;
    unsigned int random_seed = 42;
};

}  // namespace benchmark::geometric_pose::absolute_pose
