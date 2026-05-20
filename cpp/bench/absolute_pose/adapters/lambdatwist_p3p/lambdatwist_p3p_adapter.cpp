#include "lambdatwist_p3p_adapter.hpp"

#include <vector>

#include "p3p.h"

namespace benchmark::geometric_pose::absolute_pose::adapters {
namespace {

Pose make_pose(const lambdatwist::CameraPose& lambda_twist_pose) {
    Pose pose;
    pose.R = lambda_twist_pose.R;
    pose.t = lambda_twist_pose.t;
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

int LambdaTwistP3PAdapter::solve(
    const AbsolutePoseProblemInstance& instance,
    std::vector<Pose>* solutions
) const {
    if (solutions == nullptr) {
        return 0;
    }
    solutions->clear();
    if (instance.x_point_.size() < 3 || instance.X_point_.size() < 3) {
        return 0;
    }

    std::vector<lambdatwist::CameraPose> lambda_twist_poses;
    const int solution_count =
        lambdatwist::p3p(instance.x_point_, instance.X_point_, &lambda_twist_poses);

    solutions->reserve(lambda_twist_poses.size());
    for (const lambdatwist::CameraPose& lambda_twist_pose : lambda_twist_poses) {
        solutions->push_back(make_pose(lambda_twist_pose));
    }

    return solution_count;
}

}  // namespace benchmark::geometric_pose::absolute_pose::adapters
