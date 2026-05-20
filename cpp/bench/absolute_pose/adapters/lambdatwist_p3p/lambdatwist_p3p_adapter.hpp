#pragma once

#include "absolute_pose_adapter.hpp"

namespace benchmark::geometric_pose::absolute_pose::adapters {

class LambdaTwistP3PAdapter final : public AbsolutePoseSolverAdapter {
public:
    std::string name() const override;
    AdapterInfo info() const override;
    int solve(
        const AbsolutePoseProblemInstance& instance,
        std::vector<Pose>* solutions
    ) const override;
};

}  // namespace benchmark::geometric_pose::absolute_pose::adapters
