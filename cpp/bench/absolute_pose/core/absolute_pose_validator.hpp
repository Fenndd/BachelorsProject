#pragma once

// Closely adapted from PoseLib's benchmark/problem_generator.{h,cc}.
// Copyright (c) 2020, Viktor Larsson. BSD 3-Clause License.

#include <cmath>

#include <Eigen/Dense>

#include "absolute_pose_types.hpp"

namespace benchmark::geometric_pose::absolute_pose {
namespace detail {

inline bool is_finite_value(double value) {
    return std::isfinite(value);
}

}  // namespace detail

inline bool is_finite_pose(const Pose& pose) {
    return pose.R.allFinite() && pose.t.allFinite();
}

inline bool is_rotation_matrix_reasonable(const Pose& pose, double tolerance) {
    if (!is_finite_pose(pose)) {
        return false;
    }

    const Eigen::Matrix3d identity = Eigen::Matrix3d::Identity();
    return (pose.R.transpose() * pose.R - identity).norm() <= tolerance
           && std::abs(pose.R.determinant() - 1.0) <= tolerance;
}

inline double compute_pose_error(
    const AbsolutePoseProblemInstance& instance,
    const Pose& pose,
    double scale
) {
    return (instance.pose_gt.R - pose.R).norm()
           + (instance.pose_gt.t - pose.t).norm()
           + std::abs(instance.scale_gt - scale);
}

inline bool is_valid_calibrated_pose(
    const AbsolutePoseProblemInstance& instance,
    const Pose& pose,
    double scale,
    double tolerance
) {
    if (!is_finite_pose(pose)) {
        return false;
    }
    if (instance.x_point_.size() != instance.X_point_.size()
        || instance.x_point_.size() != instance.p_point_.size()) {
        return false;
    }

    for (std::size_t i = 0; i < instance.x_point_.size(); ++i) {
        const Eigen::Vector3d transformed =
            pose.R * instance.X_point_[i] + pose.t - scale * instance.p_point_[i];
        if (!transformed.allFinite() || transformed.norm() <= 0.0) {
            return false;
        }

        const double err =
            1.0 - std::abs(instance.x_point_[i].dot(transformed.normalized()));
        if (!detail::is_finite_value(err) || err > tolerance) {
            return false;
        }
    }

    return true;
}

}  // namespace benchmark::geometric_pose::absolute_pose
