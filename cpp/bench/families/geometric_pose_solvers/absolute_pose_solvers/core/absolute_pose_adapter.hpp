#pragma once

#include <string>

#include "absolute_pose_types.hpp"

namespace benchmark::geometric_pose::absolute_pose {

class AbsolutePoseSolverAdapter {
public:
    virtual ~AbsolutePoseSolverAdapter() = default;

    virtual std::string name() const = 0;
    virtual AdapterInfo info() const = 0;
    virtual AbsolutePoseResult solve(const AbsolutePoseCase& test_case) const = 0;
};

}  // namespace benchmark::geometric_pose::absolute_pose
