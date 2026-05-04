#include "lambdatwist_p3p_adapter.hpp"

#include <Eigen/Dense>

#include <vector>

#include "p3p.h"

namespace benchmark::geometric_pose::absolute_pose::adapters {
namespace {

Eigen::Vector3d make_bearing_vector(const Vec2& pixel, const CameraIntrinsics& intrinsics) {
    const double x_normalized = (pixel.x - intrinsics.cx) / intrinsics.fx;
    const double y_normalized = (pixel.y - intrinsics.cy) / intrinsics.fy;
    return Eigen::Vector3d(x_normalized, y_normalized, 1.0).normalized();
}

Eigen::Vector3d make_world_point(const Vec3& point) {
    return Eigen::Vector3d(point.x, point.y, point.z);
}

Pose make_pose(const lambdatwist::CameraPose& lambda_twist_pose) {
    Pose pose;
    for (int row = 0; row < 3; ++row) {
        for (int column = 0; column < 3; ++column) {
            pose.R[static_cast<std::size_t>(row * 3 + column)] =
                lambda_twist_pose.R(row, column);
        }
        pose.t[static_cast<std::size_t>(row)] = lambda_twist_pose.t(row);
    }
    return pose;
}

}  // namespace

std::string LambdaTwistP3PAdapter::name() const {
    return "lambdatwist_p3p";
}

AdapterInfo LambdaTwistP3PAdapter::info() const {
    return {
        name(),
        3,
        3,
        true,
    };
}

AbsolutePoseResult LambdaTwistP3PAdapter::solve(const AbsolutePoseCase& test_case) const {
    AbsolutePoseResult result;
    if (test_case.points3d.size() < 3 || test_case.points2d.size() < 3) {
        return result;
    }

    std::vector<Eigen::Vector3d> bearing_vectors;
    std::vector<Eigen::Vector3d> world_points;
    bearing_vectors.reserve(3);
    world_points.reserve(3);

    for (std::size_t index = 0; index < 3; ++index) {
        bearing_vectors.push_back(make_bearing_vector(test_case.points2d[index], test_case.intrinsics));
        world_points.push_back(make_world_point(test_case.points3d[index]));
    }

    std::vector<lambdatwist::CameraPose> lambda_twist_poses;
    const int solution_count =
        lambdatwist::p3p(bearing_vectors, world_points, &lambda_twist_poses);

    result.success = solution_count > 0 && !lambda_twist_poses.empty();
    result.poses.reserve(lambda_twist_poses.size());
    for (const lambdatwist::CameraPose& lambda_twist_pose : lambda_twist_poses) {
        result.poses.push_back(make_pose(lambda_twist_pose));
    }

    return result;
}

}  // namespace benchmark::geometric_pose::absolute_pose::adapters
