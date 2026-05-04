#pragma once

#include "absolute_pose_adapter.hpp"

namespace benchmark::geometric_pose::absolute_pose::adapters {

class LambdaTwistP3PAdapter final : public AbsolutePoseSolverAdapter {
public:
    std::string name() const override;
    AdapterInfo info() const override;
    AbsolutePoseResult solve(const AbsolutePoseCase& test_case) const override;
};

}  // namespace benchmark::geometric_pose::absolute_pose::adapters
