#pragma once

// Closely adapted from PoseLib's benchmark/problem_generator.{h,cc}.
// Copyright (c) 2020, Viktor Larsson. BSD 3-Clause License.

#include <cmath>
#include <random>
#include <vector>

#include <Eigen/Dense>
#include <Eigen/Geometry>

#include "absolute_pose_types.hpp"

namespace benchmark::geometric_pose::absolute_pose {
namespace detail {

inline constexpr double kPi = 3.14159265358979323846;

inline double random_uniform(std::default_random_engine& random_engine, double min, double max) {
    std::uniform_real_distribution<double> distribution(min, max);
    return distribution(random_engine);
}

inline Eigen::Matrix3d random_rotation(std::default_random_engine& random_engine) {
    const double u1 = random_uniform(random_engine, 0.0, 1.0);
    const double u2 = random_uniform(random_engine, 0.0, 1.0);
    const double u3 = random_uniform(random_engine, 0.0, 1.0);
    const double sqrt_u1 = std::sqrt(u1);
    const double sqrt_one_minus_u1 = std::sqrt(1.0 - u1);
    const double theta1 = 2.0 * kPi * u2;
    const double theta2 = 2.0 * kPi * u3;
    const Eigen::Quaterniond quaternion{
        sqrt_u1 * std::cos(theta2),
        sqrt_one_minus_u1 * std::sin(theta1),
        sqrt_one_minus_u1 * std::cos(theta1),
        sqrt_u1 * std::sin(theta2),
    };
    return quaternion.normalized().toRotationMatrix();
}

inline void set_random_pose(Pose& pose, std::default_random_engine& random_engine, bool upright = false, bool planar = false) {
    if (upright) {
        const double angle = random_uniform(random_engine, -kPi, kPi);
        const double c = std::cos(angle);
        const double s = std::sin(angle);
        pose.R << c, 0.0, s,
                  0.0, 1.0, 0.0,
                 -s, 0.0, c;
    } else {
        pose.R = random_rotation(random_engine);
    }

    pose.t = Eigen::Vector3d{
        random_uniform(random_engine, -1.0, 1.0),
        random_uniform(random_engine, -1.0, 1.0),
        random_uniform(random_engine, -1.0, 1.0),
    };
    if (planar) {
        pose.t.y() = 0.0;
    }
}

}  // namespace detail

inline std::vector<AbsolutePoseProblemInstance> generate_absolute_pose_problems(
    const BenchmarkOptions& options
) {
    std::vector<AbsolutePoseProblemInstance> problem_instances;
    problem_instances.reserve(options.num_problems);

    const double fov_scale =
        std::tan(options.camera_fov / 2.0 * detail::kPi / 180.0);

    std::default_random_engine random_engine;
    std::uniform_real_distribution<double> depth_gen(options.min_depth, options.max_depth);
    std::uniform_real_distribution<double> coord_gen(-fov_scale, fov_scale);

    for (std::size_t i = 0; i < options.num_problems; ++i) {
        AbsolutePoseProblemInstance instance;
        detail::set_random_pose(instance.pose_gt, random_engine);

        instance.x_point_.reserve(static_cast<std::size_t>(options.n_point_point));
        instance.X_point_.reserve(static_cast<std::size_t>(options.n_point_point));
        instance.p_point_.reserve(static_cast<std::size_t>(options.n_point_point));

        for (int j = 0; j < options.n_point_point; ++j) {
            const Eigen::Vector3d p = Eigen::Vector3d::Zero();
            Eigen::Vector3d x{coord_gen(random_engine), coord_gen(random_engine), 1.0};
            x.normalize();

            Eigen::Vector3d X = instance.scale_gt * p + x * depth_gen(random_engine);
            X = instance.pose_gt.R.transpose() * (X - instance.pose_gt.t);

            instance.x_point_.push_back(x);
            instance.X_point_.push_back(X);
            instance.p_point_.push_back(p);
        }

        problem_instances.push_back(instance);
    }

    return problem_instances;
}

}  // namespace benchmark::geometric_pose::absolute_pose
