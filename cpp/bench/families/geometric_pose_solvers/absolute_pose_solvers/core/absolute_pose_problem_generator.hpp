#pragma once

#include <algorithm>
#include <cmath>
#include <random>
#include <utility>
#include <vector>

#include "absolute_pose_types.hpp"

namespace benchmark::geometric_pose::absolute_pose {
namespace detail {

inline Vec3 rotate_world_to_camera(const std::array<double, 9>& rotation, const Vec3& point) {
    return {
        rotation[0] * point.x + rotation[1] * point.y + rotation[2] * point.z,
        rotation[3] * point.x + rotation[4] * point.y + rotation[5] * point.z,
        rotation[6] * point.x + rotation[7] * point.y + rotation[8] * point.z,
    };
}

inline Vec3 rotate_camera_to_world(const std::array<double, 9>& rotation, const Vec3& point) {
    return {
        rotation[0] * point.x + rotation[3] * point.y + rotation[6] * point.z,
        rotation[1] * point.x + rotation[4] * point.y + rotation[7] * point.z,
        rotation[2] * point.x + rotation[5] * point.y + rotation[8] * point.z,
    };
}

inline std::array<double, 9> make_rotation_from_euler(double roll, double pitch, double yaw) {
    const double cr = std::cos(roll);
    const double sr = std::sin(roll);
    const double cp = std::cos(pitch);
    const double sp = std::sin(pitch);
    const double cy = std::cos(yaw);
    const double sy = std::sin(yaw);

    return {
        cy * cp,
        cy * sp * sr - sy * cr,
        cy * sp * cr + sy * sr,
        sy * cp,
        sy * sp * sr + cy * cr,
        sy * sp * cr - cy * sr,
        -sp,
        cp * sr,
        cp * cr,
    };
}

}  // namespace detail

inline std::vector<AbsolutePoseCase> generate_absolute_pose_cases(const BenchmarkOptions& options) {
    std::mt19937 random_engine(options.random_seed);
    std::uniform_real_distribution<double> angle_distribution(-0.45, 0.45);
    std::uniform_real_distribution<double> translation_distribution(-1.0, 1.0);
    std::uniform_real_distribution<double> normalized_xy_distribution(-0.45, 0.45);
    std::uniform_real_distribution<double> depth_distribution(3.0, 9.0);

    const std::size_t points_per_case = std::max<std::size_t>(3, options.points_per_case);
    std::vector<AbsolutePoseCase> cases;
    cases.reserve(options.num_cases);

    for (std::size_t case_index = 0; case_index < options.num_cases; ++case_index) {
        AbsolutePoseCase test_case;
        test_case.intrinsics = {
            800.0 + static_cast<double>(case_index % 7) * 3.0,
            835.0 + static_cast<double>(case_index % 5) * 4.0,
            320.0 + static_cast<double>(case_index % 3) * 2.0,
            240.0 - static_cast<double>(case_index % 4) * 1.5,
        };

        const double roll = 0.12 + angle_distribution(random_engine);
        const double pitch = -0.08 + angle_distribution(random_engine);
        const double yaw = 0.18 + angle_distribution(random_engine);
        test_case.ground_truth_pose.R = detail::make_rotation_from_euler(roll, pitch, yaw);
        test_case.ground_truth_pose.t = {
            0.35 + 0.25 * translation_distribution(random_engine),
            -0.20 + 0.25 * translation_distribution(random_engine),
            1.10 + 0.25 * translation_distribution(random_engine),
        };

        test_case.points3d.reserve(points_per_case);
        test_case.points2d.reserve(points_per_case);

        for (std::size_t point_index = 0; point_index < points_per_case; ++point_index) {
            const double x_norm = normalized_xy_distribution(random_engine)
                                  + 0.08 * static_cast<double>(point_index);
            const double y_norm = normalized_xy_distribution(random_engine)
                                  - 0.05 * static_cast<double>(point_index);
            const double depth = depth_distribution(random_engine)
                                 + 0.15 * static_cast<double>(point_index);

            const Vec3 point_camera{
                x_norm * depth,
                y_norm * depth,
                depth,
            };
            const Vec3 shifted_camera{
                point_camera.x - test_case.ground_truth_pose.t[0],
                point_camera.y - test_case.ground_truth_pose.t[1],
                point_camera.z - test_case.ground_truth_pose.t[2],
            };
            const Vec3 point_world =
                detail::rotate_camera_to_world(test_case.ground_truth_pose.R, shifted_camera);

            test_case.points3d.push_back(point_world);
            test_case.points2d.push_back({
                test_case.intrinsics.fx * (point_camera.x / point_camera.z) + test_case.intrinsics.cx,
                test_case.intrinsics.fy * (point_camera.y / point_camera.z) + test_case.intrinsics.cy,
            });
        }

        cases.push_back(std::move(test_case));
    }

    return cases;
}

}  // namespace benchmark::geometric_pose::absolute_pose
