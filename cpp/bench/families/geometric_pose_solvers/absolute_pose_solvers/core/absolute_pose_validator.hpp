#pragma once

#include <algorithm>
#include <cmath>
#include <limits>

#include "absolute_pose_types.hpp"

namespace benchmark::geometric_pose::absolute_pose {
namespace detail {

inline bool is_finite_value(double value) {
    return std::isfinite(value);
}

inline Vec3 transform_point_to_camera(const Vec3& point_world, const Pose& pose) {
    return {
        pose.R[0] * point_world.x + pose.R[1] * point_world.y + pose.R[2] * point_world.z + pose.t[0],
        pose.R[3] * point_world.x + pose.R[4] * point_world.y + pose.R[5] * point_world.z + pose.t[1],
        pose.R[6] * point_world.x + pose.R[7] * point_world.y + pose.R[8] * point_world.z + pose.t[2],
    };
}

inline double dot_columns(const Pose& pose, int left_column, int right_column) {
    return pose.R[left_column] * pose.R[right_column]
           + pose.R[3 + left_column] * pose.R[3 + right_column]
           + pose.R[6 + left_column] * pose.R[6 + right_column];
}

inline double rotation_determinant(const Pose& pose) {
    return pose.R[0] * (pose.R[4] * pose.R[8] - pose.R[5] * pose.R[7])
           - pose.R[1] * (pose.R[3] * pose.R[8] - pose.R[5] * pose.R[6])
           + pose.R[2] * (pose.R[3] * pose.R[7] - pose.R[4] * pose.R[6]);
}

}  // namespace detail

inline bool is_finite_pose(const Pose& pose) {
    for (const double value : pose.R) {
        if (!detail::is_finite_value(value)) {
            return false;
        }
    }
    for (const double value : pose.t) {
        if (!detail::is_finite_value(value)) {
            return false;
        }
    }
    return true;
}

inline bool is_rotation_matrix_reasonable(const Pose& pose, double tolerance) {
    if (!is_finite_pose(pose)) {
        return false;
    }

    for (int column = 0; column < 3; ++column) {
        if (std::abs(detail::dot_columns(pose, column, column) - 1.0) > tolerance) {
            return false;
        }
    }
    for (int left_column = 0; left_column < 3; ++left_column) {
        for (int right_column = left_column + 1; right_column < 3; ++right_column) {
            if (std::abs(detail::dot_columns(pose, left_column, right_column)) > tolerance) {
                return false;
            }
        }
    }

    return std::abs(detail::rotation_determinant(pose) - 1.0) <= tolerance;
}

inline Vec2 project_point(const Vec3& point_world, const Pose& pose, const CameraIntrinsics& intrinsics) {
    const Vec3 point_camera = detail::transform_point_to_camera(point_world, pose);
    if (!detail::is_finite_value(point_camera.z) || std::abs(point_camera.z) <= 1e-15) {
        const double quiet_nan = std::numeric_limits<double>::quiet_NaN();
        return {quiet_nan, quiet_nan};
    }

    return {
        intrinsics.fx * (point_camera.x / point_camera.z) + intrinsics.cx,
        intrinsics.fy * (point_camera.y / point_camera.z) + intrinsics.cy,
    };
}

inline double reprojection_error(const AbsolutePoseCase& test_case, const Pose& pose) {
    if (test_case.points3d.size() != test_case.points2d.size()
        || test_case.points3d.empty()
        || !is_rotation_matrix_reasonable(pose, 1e-5)) {
        return std::numeric_limits<double>::infinity();
    }

    double squared_error_sum = 0.0;
    for (std::size_t index = 0; index < test_case.points3d.size(); ++index) {
        const Vec2 projected = project_point(test_case.points3d[index], pose, test_case.intrinsics);
        if (!detail::is_finite_value(projected.x) || !detail::is_finite_value(projected.y)) {
            return std::numeric_limits<double>::infinity();
        }

        const double dx = projected.x - test_case.points2d[index].x;
        const double dy = projected.y - test_case.points2d[index].y;
        squared_error_sum += dx * dx + dy * dy;
    }

    return std::sqrt(squared_error_sum / static_cast<double>(test_case.points3d.size()));
}

inline double best_reprojection_error(const AbsolutePoseCase& test_case, const AbsolutePoseResult& result) {
    if (!result.success || result.poses.empty()) {
        return std::numeric_limits<double>::infinity();
    }

    double best_error = std::numeric_limits<double>::infinity();
    for (const Pose& pose : result.poses) {
        best_error = std::min(best_error, reprojection_error(test_case, pose));
    }
    return best_error;
}

inline bool has_valid_solution(
    const AbsolutePoseCase& test_case,
    const AbsolutePoseResult& result,
    double threshold
) {
    return best_reprojection_error(test_case, result) <= threshold;
}

}  // namespace benchmark::geometric_pose::absolute_pose
