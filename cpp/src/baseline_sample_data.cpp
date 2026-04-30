#include "baseline_sample_data.h"

namespace baseline_sample_data {

BaselineSampleData make_baseline_sample_data() {
    const Eigen::Vector3d y1 = Eigen::Vector3d(0.0, 0.0, 1.0).normalized();
    const Eigen::Vector3d y2 = Eigen::Vector3d(1.0, 0.0, 1.0).normalized();
    const Eigen::Vector3d y3 = Eigen::Vector3d(2.0, 1.0, 1.0).normalized();

    const Eigen::Vector3d x1(0.0, 0.0, 2.0);
    const Eigen::Vector3d x2(1.41421356237309, 0.0, 1.41421356237309);
    const Eigen::Vector3d x3(1.63299316185545, 0.816496580927726, 0.816496580927726);

    return {
        {y1, y2, y3},
        {x1, x2, x3},
    };
}

}  // namespace baseline_sample_data
