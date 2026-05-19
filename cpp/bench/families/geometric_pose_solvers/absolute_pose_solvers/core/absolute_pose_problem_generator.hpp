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

inline void set_random_pose(Pose& pose, bool upright = false, bool planar = false) {
    if (upright) {
        Eigen::Vector2d r;
        r.setRandom().normalize();
        pose.R << r(0), 0.0, r(1),
                  0.0, 1.0, 0.0,
                 -r(1), 0.0, r(0);
    } else {
        pose.R = Eigen::Quaterniond::UnitRandom().toRotationMatrix();
    }

    pose.t.setRandom();
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
        detail::set_random_pose(instance.pose_gt);

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
