#include "solver_benchmark.h"

#include "problem_generator.h"

#include <algorithm>
#include <chrono>
#include <functional>
#include <iomanip>
#include <iostream>
#include <random>
#include <sstream>
#include <stdexcept>
#include <utility>

namespace poselib {

template <typename Solver> BenchmarkResult benchmark(int n_problems, const ProblemOptions &options, double tol = 1e-6) {

    std::vector<AbsolutePoseProblemInstance> problem_instances;
    generate_abspose_problems(n_problems, &problem_instances, options);

    BenchmarkResult result;
    result.instances_ = n_problems;
    result.name_ = Solver::name();
    if (options.additional_name_ != "") {
        result.name_ += options.additional_name_;
    }
    result.options_ = options;
    std::cout << "Running benchmark: " << result.name_ << std::flush;

    // Run benchmark where we check solution quality
    for (const AbsolutePoseProblemInstance &instance : problem_instances) {
        CameraPoseVector solutions;

        int sols = Solver::solve(instance, &solutions);

        double pose_error = std::numeric_limits<double>::max();

        result.solutions_ += sols;
        // std::cout << "\nGt: " << instance.pose_gt.R() << "\n"<< instance.pose_gt.t << "\n";
        // std::cout << "gt valid = " << Solver::validator::is_valid(instance, instance.pose_gt, 1.0, tol) << "\n";
        for (const CameraPose &pose : solutions) {
            if (Solver::validator::is_valid(instance, pose, 1.0, tol))
                result.valid_solutions_++;
            // std::cout << "Pose: " << pose.R() << "\n" << pose.t << "\n";
            pose_error = std::min(pose_error, Solver::validator::compute_pose_error(instance, pose, 1.0));
        }
        if (pose_error < tol)
            result.found_gt_pose_++;
    }

    std::vector<long> runtimes;
    CameraPoseVector solutions;
    for (int iter = 0; iter < 10; ++iter) {
        auto start_time = std::chrono::high_resolution_clock::now();
        for (const AbsolutePoseProblemInstance &instance : problem_instances) {
            solutions.clear();
            Solver::solve(instance, &solutions);
        }

        auto end_time = std::chrono::high_resolution_clock::now();
        runtimes.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - start_time).count());
    }

    std::sort(runtimes.begin(), runtimes.end());
    result.runtime_ns_ = runtimes[runtimes.size() / 2];
    std::cout << "\r                                                                                \r";
    return result;
}

template <typename Solver>
BenchmarkResult benchmark_w_extra(int n_problems, const ProblemOptions &options, double tol = 1e-6) {

    std::vector<AbsolutePoseProblemInstance> problem_instances;
    generate_abspose_problems(n_problems, &problem_instances, options);

    BenchmarkResult result;
    result.instances_ = n_problems;
    result.name_ = Solver::name();
    if (options.additional_name_ != "") {
        result.name_ += options.additional_name_;
    }
    result.options_ = options;
    std::cout << "Running benchmark: " << result.name_ << std::flush;

    // Run benchmark where we check solution quality
    for (const AbsolutePoseProblemInstance &instance : problem_instances) {
        CameraPoseVector solutions;
        std::vector<double> extra;

        int sols = Solver::solve(instance, &solutions, &extra);

        double pose_error = std::numeric_limits<double>::max();

        result.solutions_ += sols;
        for (size_t k = 0; k < solutions.size(); ++k) {
            if (Solver::validator::is_valid(instance, solutions[k], extra[k], tol))
                result.valid_solutions_++;
            pose_error = std::min(pose_error, Solver::validator::compute_pose_error(instance, solutions[k], extra[k]));
        }

        if (pose_error < tol)
            result.found_gt_pose_++;
    }

    std::vector<long> runtimes;
    CameraPoseVector solutions;
    std::vector<double> extra;
    for (int iter = 0; iter < 10; ++iter) {
        auto start_time = std::chrono::high_resolution_clock::now();
        for (const AbsolutePoseProblemInstance &instance : problem_instances) {
            solutions.clear();
            extra.clear();

            Solver::solve(instance, &solutions, &extra);
        }

        auto end_time = std::chrono::high_resolution_clock::now();
        runtimes.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - start_time).count());
    }

    std::sort(runtimes.begin(), runtimes.end());
    result.runtime_ns_ = runtimes[runtimes.size() / 2];
    std::cout << "\r                                                                                \r";
    return result;
}

template <typename Solver>
BenchmarkResult benchmark_w_extra2(int n_problems, const ProblemOptions &options, double tol = 1e-6) {

    std::vector<AbsolutePoseProblemInstance> problem_instances;
    generate_abspose_problems(n_problems, &problem_instances, options);

    BenchmarkResult result;
    result.instances_ = n_problems;
    result.name_ = Solver::name();
    if (options.additional_name_ != "") {
        result.name_ += options.additional_name_;
    }
    result.options_ = options;
    std::cout << "Running benchmark: " << result.name_ << std::flush;

    // Run benchmark where we check solution quality
    for (const AbsolutePoseProblemInstance &instance : problem_instances) {
        CameraPoseVector solutions;
        std::vector<double> extra1, extra2;

        int sols = Solver::solve(instance, &solutions, &extra1, &extra2);

        double pose_error = std::numeric_limits<double>::max();

        result.solutions_ += sols;
        for (size_t k = 0; k < solutions.size(); ++k) {
            if (Solver::validator::is_valid(instance, solutions[k], extra1[k], extra2[k], tol))
                result.valid_solutions_++;
            pose_error = std::min(pose_error,
                                  Solver::validator::compute_pose_error(instance, solutions[k], extra1[k], extra2[k]));
        }

        if (pose_error < tol)
            result.found_gt_pose_++;
    }

    std::vector<long> runtimes;
    CameraPoseVector solutions;
    std::vector<double> extra1, extra2;
    for (int iter = 0; iter < 10; ++iter) {
        auto start_time = std::chrono::high_resolution_clock::now();
        for (const AbsolutePoseProblemInstance &instance : problem_instances) {
            solutions.clear();
            extra1.clear();
            extra2.clear();

            Solver::solve(instance, &solutions, &extra1, &extra2);
        }

        auto end_time = std::chrono::high_resolution_clock::now();
        runtimes.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - start_time).count());
    }

    std::sort(runtimes.begin(), runtimes.end());
    result.runtime_ns_ = runtimes[runtimes.size() / 2];
    std::cout << "\r                                                                                \r";
    return result;
}

template <typename Solver>
BenchmarkResult benchmark_relative(int n_problems, const ProblemOptions &options, double tol = 1e-6) {

    std::vector<RelativePoseProblemInstance> problem_instances;
    generate_relpose_problems(n_problems, &problem_instances, options);

    BenchmarkResult result;
    result.instances_ = n_problems;
    result.name_ = Solver::name();
    if (options.additional_name_ != "") {
        result.name_ += options.additional_name_;
    }
    result.options_ = options;
    std::cout << "Running benchmark: " << result.name_ << std::flush;

    // Run benchmark where we check solution quality
    for (const RelativePoseProblemInstance &instance : problem_instances) {
        // CameraPoseVector solutions;
        std::vector<typename Solver::Solution> solutions;

        int sols = Solver::solve(instance, &solutions);

        double pose_error = std::numeric_limits<double>::max();

        result.solutions_ += sols;
        // std::cout << "Gt: " << instance.pose_gt.R << "\n"<< instance.pose_gt.t << "\n";
        for (const typename Solver::Solution &pose : solutions) {
            if (Solver::validator::is_valid(instance, pose, tol))
                result.valid_solutions_++;
            // std::cout << "Pose: " << pose.R << "\n" << pose.t << "\n";
            pose_error = std::min(pose_error, Solver::validator::compute_pose_error(instance, pose));
        }

        if (pose_error < tol)
            result.found_gt_pose_++;
    }

    std::vector<long> runtimes;
    std::vector<typename Solver::Solution> solutions;
    for (int iter = 0; iter < 10; ++iter) {
        auto start_time = std::chrono::high_resolution_clock::now();
        for (const RelativePoseProblemInstance &instance : problem_instances) {
            solutions.clear();

            Solver::solve(instance, &solutions);
        }

        auto end_time = std::chrono::high_resolution_clock::now();
        runtimes.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - start_time).count());
    }

    std::sort(runtimes.begin(), runtimes.end());

    result.runtime_ns_ = runtimes[runtimes.size() / 2];
    std::cout << "\r                                                                                \r";
    return result;
}

template <typename Solver>
BenchmarkResult benchmark_homography(int n_problems, const ProblemOptions &options, double tol = 1e-6) {

    std::vector<RelativePoseProblemInstance> problem_instances;
    generate_homography_problems(n_problems, &problem_instances, options);

    BenchmarkResult result;
    result.instances_ = n_problems;
    result.name_ = Solver::name();
    if (options.additional_name_ != "") {
        result.name_ += options.additional_name_;
    }
    result.options_ = options;
    std::cout << "Running benchmark: " << result.name_ << std::flush;

    // Run benchmark where we check solution quality
    for (const RelativePoseProblemInstance &instance : problem_instances) {
        std::vector<Eigen::Matrix3d> solutions;

        int sols = Solver::solve(instance, &solutions);

        double hom_error = std::numeric_limits<double>::max();

        result.solutions_ += sols;
        // std::cout << "Gt: " << instance.pose_gt.R << "\n"<< instance.pose_gt.t << "\n";
        for (const Eigen::Matrix3d &H : solutions) {
            if (Solver::validator::is_valid(instance, H, tol))
                result.valid_solutions_++;
            // std::cout << "Pose: " << pose.R << "\n" << pose.t << "\n";
            hom_error = std::min(hom_error, Solver::validator::compute_pose_error(instance, H));
        }

        if (hom_error < tol)
            result.found_gt_pose_++;
    }

    std::vector<long> runtimes;
    std::vector<Eigen::Matrix3d> solutions;
    for (int iter = 0; iter < 10; ++iter) {
        auto start_time = std::chrono::high_resolution_clock::now();
        for (const RelativePoseProblemInstance &instance : problem_instances) {
            solutions.clear();

            Solver::solve(instance, &solutions);
        }

        auto end_time = std::chrono::high_resolution_clock::now();
        runtimes.push_back(std::chrono::duration_cast<std::chrono::nanoseconds>(end_time - start_time).count());
    }

    std::sort(runtimes.begin(), runtimes.end());

    result.runtime_ns_ = runtimes[runtimes.size() / 2];
    std::cout << "\r                                                                                \r";
    return result;
}

} // namespace poselib

void print_runtime(double runtime_ns) {
    if (runtime_ns < 1e3) {
        std::cout << runtime_ns << " ns";
    } else if (runtime_ns < 1e6) {
        std::cout << runtime_ns / 1e3 << " us";
    } else if (runtime_ns < 1e9) {
        std::cout << runtime_ns / 1e6 << " ms";
    } else {
        std::cout << runtime_ns / 1e9 << " s";
    }
}

std::string poselib_info() {
#ifdef NDEBUG
    const std::string build_type = "RELEASE";
#else
    const std::string build_type = "DEBUG";
#endif
    return "PoseLib native benchmark (" + build_type + ")";
}

void display_result(const std::vector<poselib::BenchmarkResult> &results) {
    // Print PoseLib version and buidling type
    std::cout << "\n" << poselib_info() << "\n\n";

    int w = 13;
    // display header
    std::cout << std::setw(2 * w) << "Solver";
    std::cout << std::setw(w) << "Solutions";
    std::cout << std::setw(w) << "Valid";
    std::cout << std::setw(w) << "GT found";
    std::cout << std::setw(w) << "Runtime\n";
    for (int i = 0; i < w * 6; ++i)
        std::cout << "-";
    std::cout << "\n";

    int prec = 6;

    for (const poselib::BenchmarkResult &result : results) {
        double num_tests = static_cast<double>(result.instances_);
        double solutions = result.solutions_ / num_tests;
        double valid_sols = result.valid_solutions_ / static_cast<double>(result.solutions_) * 100.0;
        double gt_found = result.found_gt_pose_ / num_tests * 100.0;
        double runtime_ns = result.runtime_ns_ / num_tests;

        std::cout << std::setprecision(prec) << std::setw(2 * w) << result.name_;
        std::cout << std::setprecision(prec) << std::setw(w) << solutions;
        std::cout << std::setprecision(prec) << std::setw(w) << valid_sols;
        std::cout << std::setprecision(prec) << std::setw(w) << gt_found;
        std::cout << std::setprecision(prec) << std::setw(w - 3);
        print_runtime(runtime_ns);
        std::cout << "\n";
    }
}


namespace {

using BenchmarkRunner = std::function<poselib::BenchmarkResult(int, const poselib::ProblemOptions &, double)>;

struct BenchmarkCase {
    std::string solver_key;
    std::string benchmark_kind;
    int default_instances;
    poselib::ProblemOptions options;
    BenchmarkRunner runner;
};

struct CliOptions {
    bool list_solvers = false;
    bool json = false;
    std::string solver_key;
    int num_problems_override = -1;
    double tolerance = 1e-6;
};

poselib::ProblemOptions base_options() {
    poselib::ProblemOptions options;
    options.camera_fov_ = 75;
    return options;
}

template <typename Solver>
BenchmarkRunner absolute_runner() {
    return [](int n, const poselib::ProblemOptions &options, double tol) {
        return poselib::benchmark<Solver>(n, options, tol);
    };
}

template <typename Solver>
BenchmarkRunner absolute_extra_runner() {
    return [](int n, const poselib::ProblemOptions &options, double tol) {
        return poselib::benchmark_w_extra<Solver>(n, options, tol);
    };
}

template <typename Solver>
BenchmarkRunner absolute_extra2_runner() {
    return [](int n, const poselib::ProblemOptions &options, double tol) {
        return poselib::benchmark_w_extra2<Solver>(n, options, tol);
    };
}

template <typename Solver>
BenchmarkRunner relative_runner() {
    return [](int n, const poselib::ProblemOptions &options, double tol) {
        return poselib::benchmark_relative<Solver>(n, options, tol);
    };
}

template <typename Solver>
BenchmarkRunner homography_runner() {
    return [](int n, const poselib::ProblemOptions &options, double tol) {
        return poselib::benchmark_homography<Solver>(n, options, tol);
    };
}

void add_case(std::vector<BenchmarkCase> *cases, std::string solver_key, std::string benchmark_kind,
              int default_instances, const poselib::ProblemOptions &options, BenchmarkRunner runner) {
    cases->push_back(BenchmarkCase{std::move(solver_key), std::move(benchmark_kind), default_instances, options,
                                   std::move(runner)});
}

std::vector<BenchmarkCase> build_cases() {
    std::vector<BenchmarkCase> cases;
    const poselib::ProblemOptions options = base_options();

    poselib::ProblemOptions p3p_opt = options;
    p3p_opt.n_point_point_ = 3;
    add_case(&cases, "p3p", "absolute_pose", 100000, p3p_opt, absolute_runner<poselib::SolverP3P>());
    add_case(&cases, "p3p_lambdatwist", "absolute_pose", 100000, p3p_opt,
             absolute_runner<poselib::SolverP3P_lambdatwist>());

    poselib::ProblemOptions gp3p_opt = options;
    gp3p_opt.n_point_point_ = 3;
    gp3p_opt.generalized_ = true;
    add_case(&cases, "gp3p", "absolute_pose", 10000, gp3p_opt, absolute_runner<poselib::SolverGP3P>());

    poselib::ProblemOptions gp4p_opt = options;
    gp4p_opt.n_point_point_ = 4;
    gp4p_opt.generalized_ = true;
    gp4p_opt.unknown_scale_ = true;
    add_case(&cases, "gp4ps", "absolute_pose_extra", 10000, gp4p_opt,
             absolute_extra_runner<poselib::SolverGP4PS>());
    gp4p_opt.generalized_duplicate_obs_ = true;
    gp4p_opt.additional_name_ = "(Deg.)";
    add_case(&cases, "gp4ps_degenerate", "absolute_pose_extra", 10000, gp4p_opt,
             absolute_extra_runner<poselib::SolverGP4PS>());

    poselib::ProblemOptions p4pf_opt = options;
    p4pf_opt.n_point_point_ = 4;
    p4pf_opt.unknown_focal_ = true;
    add_case(&cases, "p4pf", "absolute_pose_extra", 10000, p4pf_opt,
             absolute_extra_runner<poselib::SolverP4PF>());

    poselib::ProblemOptions p5pfr_opt = options;
    p5pfr_opt.n_point_point_ = 5;
    p5pfr_opt.unknown_focal_ = true;
    p5pfr_opt.unknown_dist_ = true;
    add_case(&cases, "p5pfr", "absolute_pose_extra2", 10000, p5pfr_opt,
             absolute_extra2_runner<poselib::SolverP5PFR>());

    poselib::ProblemOptions p2p2pl_opt = options;
    p2p2pl_opt.n_point_point_ = 2;
    p2p2pl_opt.n_point_line_ = 2;
    add_case(&cases, "p2p2pl", "absolute_pose", 1000, p2p2pl_opt,
             absolute_runner<poselib::SolverP2P2PL>());

    poselib::ProblemOptions p6lp_opt = options;
    p6lp_opt.n_line_point_ = 6;
    add_case(&cases, "p6lp", "absolute_pose", 10000, p6lp_opt, absolute_runner<poselib::SolverP6LP>());

    poselib::ProblemOptions p5lp_radial_opt = options;
    p5lp_radial_opt.n_line_point_ = 5;
    p5lp_radial_opt.radial_lines_ = true;
    add_case(&cases, "p5lp_radial", "absolute_pose", 100000, p5lp_radial_opt,
             absolute_runner<poselib::SolverP5LP_Radial>());

    poselib::ProblemOptions p3p1llf_opt = options;
    p3p1llf_opt.n_point_point_ = 3;
    p3p1llf_opt.n_line_line_ = 1;
    p3p1llf_opt.unknown_focal_ = true;
    add_case(&cases, "p3p1llf", "absolute_pose_extra", 10000, p3p1llf_opt,
             absolute_extra_runner<poselib::SolverP3P1LLF>());

    poselib::ProblemOptions p2p2llf_opt = options;
    p2p2llf_opt.n_point_point_ = 2;
    p2p2llf_opt.n_line_line_ = 2;
    p2p2llf_opt.unknown_focal_ = true;
    add_case(&cases, "p2p2llf", "absolute_pose_extra", 10000, p2p2llf_opt,
             absolute_extra_runner<poselib::SolverP2P2LLF>());

    poselib::ProblemOptions p1p3llf_opt = options;
    p1p3llf_opt.n_point_point_ = 1;
    p1p3llf_opt.n_line_line_ = 3;
    p1p3llf_opt.unknown_focal_ = true;
    add_case(&cases, "p1p3llf", "absolute_pose_extra", 10000, p1p3llf_opt,
             absolute_extra_runner<poselib::SolverP1P3LLF>());

    poselib::ProblemOptions p4llf_opt = options;
    p4llf_opt.n_line_line_ = 4;
    p4llf_opt.unknown_focal_ = true;
    add_case(&cases, "p4llf", "absolute_pose_extra", 10000, p4llf_opt,
             absolute_extra_runner<poselib::SolverP4LLF>());

    poselib::ProblemOptions p2p1ll_opt = options;
    p2p1ll_opt.n_point_point_ = 2;
    p2p1ll_opt.n_line_line_ = 1;
    add_case(&cases, "p2p1ll", "absolute_pose", 10000, p2p1ll_opt,
             absolute_runner<poselib::SolverP2P1LL>());

    poselib::ProblemOptions p1p2ll_opt = options;
    p1p2ll_opt.n_point_point_ = 1;
    p1p2ll_opt.n_line_line_ = 2;
    add_case(&cases, "p1p2ll", "absolute_pose", 10000, p1p2ll_opt,
             absolute_runner<poselib::SolverP1P2LL>());

    poselib::ProblemOptions p3ll_opt = options;
    p3ll_opt.n_line_line_ = 3;
    add_case(&cases, "p3ll", "absolute_pose", 10000, p3ll_opt, absolute_runner<poselib::SolverP3LL>());

    poselib::ProblemOptions up2p_opt = options;
    up2p_opt.n_point_point_ = 2;
    up2p_opt.upright_ = true;
    add_case(&cases, "up2p", "absolute_pose", 1000000, up2p_opt, absolute_runner<poselib::SolverUP2P>());

    poselib::ProblemOptions up1p1ll_opt = options;
    up1p1ll_opt.n_point_point_ = 1;
    up1p1ll_opt.n_line_line_ = 1;
    up1p1ll_opt.upright_ = true;
    add_case(&cases, "up1p1ll", "absolute_pose", 1000000, up1p1ll_opt,
             absolute_runner<poselib::SolverUP1P1LL>());

    poselib::ProblemOptions ugp2p_opt = options;
    ugp2p_opt.n_point_point_ = 2;
    ugp2p_opt.upright_ = true;
    ugp2p_opt.generalized_ = true;
    add_case(&cases, "ugp2p", "absolute_pose", 1000000, ugp2p_opt,
             absolute_runner<poselib::SolverUGP2P>());

    poselib::ProblemOptions ugp3ps_opt = options;
    ugp3ps_opt.n_point_point_ = 3;
    ugp3ps_opt.upright_ = true;
    ugp3ps_opt.generalized_ = true;
    ugp3ps_opt.unknown_scale_ = true;
    add_case(&cases, "ugp3ps", "absolute_pose_extra", 100000, ugp3ps_opt,
             absolute_extra_runner<poselib::SolverUGP3PS>());

    poselib::ProblemOptions up1p2pl_opt = options;
    up1p2pl_opt.n_point_point_ = 1;
    up1p2pl_opt.n_point_line_ = 2;
    up1p2pl_opt.upright_ = true;
    add_case(&cases, "up1p2pl", "absolute_pose", 10000, up1p2pl_opt,
             absolute_runner<poselib::SolverUP1P2PL>());

    poselib::ProblemOptions up4pl_opt = options;
    up4pl_opt.n_point_line_ = 4;
    up4pl_opt.upright_ = true;
    add_case(&cases, "up4pl", "absolute_pose", 10000, up4pl_opt, absolute_runner<poselib::SolverUP4PL>());

    poselib::ProblemOptions ugp4pl_opt = options;
    ugp4pl_opt.n_point_line_ = 4;
    ugp4pl_opt.upright_ = true;
    ugp4pl_opt.generalized_ = true;
    add_case(&cases, "ugp4pl", "absolute_pose", 10000, ugp4pl_opt,
             absolute_runner<poselib::SolverUGP4PL>());

    poselib::ProblemOptions relupright3pt_opt = options;
    relupright3pt_opt.n_point_point_ = 3;
    relupright3pt_opt.upright_ = true;
    add_case(&cases, "relpose_upright_3pt", "relative_pose", 10000, relupright3pt_opt,
             relative_runner<poselib::SolverRelUpright3pt>());

    poselib::ProblemOptions genrelupright4pt_opt = options;
    genrelupright4pt_opt.n_point_point_ = 4;
    genrelupright4pt_opt.upright_ = true;
    genrelupright4pt_opt.generalized_ = true;
    add_case(&cases, "gen_relpose_upright_4pt", "relative_pose", 10000, genrelupright4pt_opt,
             relative_runner<poselib::SolverGenRelUpright4pt>());

    poselib::ProblemOptions rel8pt_opt = options;
    rel8pt_opt.n_point_point_ = 8;
    add_case(&cases, "relpose_8pt", "relative_pose", 10000, rel8pt_opt,
             relative_runner<poselib::SolverRel8pt>());
    rel8pt_opt.additional_name_ = "(100 pts)";
    rel8pt_opt.n_point_point_ = 100;
    add_case(&cases, "relpose_8pt_100pts", "relative_pose", 10000, rel8pt_opt,
             relative_runner<poselib::SolverRel8pt>());

    poselib::ProblemOptions rel5pt_opt = options;
    rel5pt_opt.n_point_point_ = 5;
    add_case(&cases, "relpose_5pt", "relative_pose", 10000, rel5pt_opt,
             relative_runner<poselib::SolverRel5pt>());

    poselib::ProblemOptions monodepth_rel3pt_opt = options;
    monodepth_rel3pt_opt.n_point_point_ = 3;
    monodepth_rel3pt_opt.use_monodepth_ = true;
    add_case(&cases, "monodepth_relpose_3pt", "relative_pose", 10000, monodepth_rel3pt_opt,
             relative_runner<poselib::SolverMonodepthRel3pt>());

    poselib::ProblemOptions rel_focal_6pt_opt = options;
    rel_focal_6pt_opt.n_point_point_ = 6;
    rel_focal_6pt_opt.min_focal_ = 0.1;
    rel_focal_6pt_opt.max_focal_ = 5.0;
    rel_focal_6pt_opt.unknown_focal_ = true;
    add_case(&cases, "shared_focal_relpose_6pt", "relative_pose", 10000, rel_focal_6pt_opt,
             relative_runner<poselib::SolverSharedFocalRel6pt>());

    poselib::ProblemOptions rel_monodepth_shared_focal_3pt_opt = options;
    rel_monodepth_shared_focal_3pt_opt.n_point_point_ = 3;
    rel_monodepth_shared_focal_3pt_opt.min_focal_ = 0.1;
    rel_monodepth_shared_focal_3pt_opt.max_focal_ = 5.0;
    rel_monodepth_shared_focal_3pt_opt.unknown_focal_ = true;
    rel_monodepth_shared_focal_3pt_opt.use_monodepth_ = true;
    add_case(&cases, "monodepth_shared_focal_relpose_3pt", "relative_pose", 10000,
             rel_monodepth_shared_focal_3pt_opt,
             relative_runner<poselib::SolverMonodepthSharedFocalRel3pt>());

    poselib::ProblemOptions rel_monodepth_varying_focal_3pt_opt = options;
    rel_monodepth_varying_focal_3pt_opt.n_point_point_ = 3;
    rel_monodepth_varying_focal_3pt_opt.min_focal_ = 0.1;
    rel_monodepth_varying_focal_3pt_opt.max_focal_ = 5.0;
    rel_monodepth_varying_focal_3pt_opt.unknown_focal_ = true;
    rel_monodepth_varying_focal_3pt_opt.varying_focal_ = true;
    rel_monodepth_varying_focal_3pt_opt.use_monodepth_ = true;
    add_case(&cases, "monodepth_varying_focal_relpose_3pt", "relative_pose", 10000,
             rel_monodepth_varying_focal_3pt_opt,
             relative_runner<poselib::SolverMonodepthVaryingFocalRel3pt>());

    poselib::ProblemOptions reluprightplanar2pt_opt = options;
    reluprightplanar2pt_opt.n_point_point_ = 2;
    reluprightplanar2pt_opt.upright_ = true;
    reluprightplanar2pt_opt.planar_ = true;
    add_case(&cases, "relpose_upright_planar_2pt", "relative_pose", 10000, reluprightplanar2pt_opt,
             relative_runner<poselib::SolverRelUprightPlanar2pt>());

    poselib::ProblemOptions reluprightplanar3pt_opt = options;
    reluprightplanar3pt_opt.n_point_point_ = 3;
    reluprightplanar3pt_opt.upright_ = true;
    reluprightplanar3pt_opt.planar_ = true;
    add_case(&cases, "relpose_upright_planar_3pt", "relative_pose", 10000, reluprightplanar3pt_opt,
             relative_runner<poselib::SolverRelUprightPlanar3pt>());

    poselib::ProblemOptions genrel5p1pt_opt = options;
    genrel5p1pt_opt.n_point_point_ = 6;
    genrel5p1pt_opt.generalized_ = true;
    genrel5p1pt_opt.generalized_first_cam_obs_ = 5;
    add_case(&cases, "gen_relpose_5p1pt", "relative_pose", 10000, genrel5p1pt_opt,
             relative_runner<poselib::SolverGenRel5p1pt>());

    poselib::ProblemOptions genrel6pt_opt = options;
    genrel6pt_opt.n_point_point_ = 6;
    genrel6pt_opt.generalized_ = true;
    add_case(&cases, "gen_relpose_6pt", "relative_pose", 1000, genrel6pt_opt,
             relative_runner<poselib::SolverGenRel6pt>());

    poselib::ProblemOptions homo4pt_opt = options;
    homo4pt_opt.n_point_point_ = 4;
    add_case(&cases, "homography_4pt", "homography", 100000, homo4pt_opt,
             homography_runner<poselib::SolverHomography4pt<false>>());
    add_case(&cases, "homography_4pt_cheirality", "homography", 100000, homo4pt_opt,
             homography_runner<poselib::SolverHomography4pt<true>>());

    return cases;
}

const BenchmarkCase *find_case(const std::vector<BenchmarkCase> &cases, const std::string &solver_key) {
    for (const BenchmarkCase &benchmark_case : cases) {
        if (benchmark_case.solver_key == solver_key) {
            return &benchmark_case;
        }
    }
    return nullptr;
}

CliOptions parse_args(int argc, char **argv) {
    CliOptions options;
    for (int i = 1; i < argc; ++i) {
        const std::string arg = argv[i];
        if (arg == "--list-solvers") {
            options.list_solvers = true;
        } else if (arg == "--json") {
            options.json = true;
        } else if (arg == "--solver") {
            if (++i >= argc) {
                throw std::invalid_argument("--solver requires a solver key");
            }
            options.solver_key = argv[i];
        } else if (arg == "--num-problems") {
            if (++i >= argc) {
                throw std::invalid_argument("--num-problems requires a value");
            }
            options.num_problems_override = std::stoi(argv[i]);
            if (options.num_problems_override <= 0) {
                throw std::invalid_argument("--num-problems must be positive");
            }
        } else if (arg == "--tol") {
            if (++i >= argc) {
                throw std::invalid_argument("--tol requires a value");
            }
            options.tolerance = std::stod(argv[i]);
            if (!(options.tolerance > 0.0)) {
                throw std::invalid_argument("--tol must be positive");
            }
        } else {
            throw std::invalid_argument("unknown argument: " + arg);
        }
    }
    return options;
}

void print_json_result(const BenchmarkCase &benchmark_case, const poselib::BenchmarkResult &result, double tolerance) {
    const double instances = static_cast<double>(result.instances_);
    const double solutions_total = static_cast<double>(result.solutions_);
    const double solutions_per_problem = instances > 0.0 ? solutions_total / instances : 0.0;
    const double valid_solutions_percent = solutions_total > 0.0
                                               ? static_cast<double>(result.valid_solutions_) / solutions_total * 100.0
                                               : 0.0;
    const double gt_found_percent = instances > 0.0
                                        ? static_cast<double>(result.found_gt_pose_) / instances * 100.0
                                        : 0.0;
    const double runtime_per_problem = instances > 0.0 ? static_cast<double>(result.runtime_ns_) / instances : 0.0;
    const bool correctness_passed = valid_solutions_percent >= 99.0 && gt_found_percent >= 99.0;

    std::ostringstream json;
    json << std::boolalpha << std::setprecision(12);
    json << "POSELIB_BENCHMARK_JSON={";
    json << "\"solver_key\":\"" << benchmark_case.solver_key << "\",";
    json << "\"benchmark_kind\":\"" << benchmark_case.benchmark_kind << "\",";
    json << "\"instances\":" << result.instances_ << ",";
    json << "\"solutions_total\":" << result.solutions_ << ",";
    json << "\"solutions_per_problem\":" << solutions_per_problem << ",";
    json << "\"valid_solutions\":" << result.valid_solutions_ << ",";
    json << "\"valid_solutions_percent\":" << valid_solutions_percent << ",";
    json << "\"gt_found\":" << result.found_gt_pose_ << ",";
    json << "\"gt_found_percent\":" << gt_found_percent << ",";
    json << "\"runtime_ns_total_median\":" << result.runtime_ns_ << ",";
    json << "\"runtime_ns_per_problem_median\":" << runtime_per_problem << ",";
    json << "\"tolerance\":" << tolerance << ",";
    json << "\"correctness_passed\":" << correctness_passed;
    json << "}";
    std::cout << json.str() << "\n";
}

} // namespace

int main(int argc, char **argv) {
    std::vector<BenchmarkCase> cases = build_cases();
    CliOptions cli;
    try {
        cli = parse_args(argc, argv);
    } catch (const std::exception &exc) {
        std::cerr << "Argument error: " << exc.what() << "\n";
        return 2;
    }

    if (cli.list_solvers) {
        for (const BenchmarkCase &benchmark_case : cases) {
            std::cout << benchmark_case.solver_key << "\n";
        }
        return 0;
    }

    std::vector<poselib::BenchmarkResult> results;
    if (!cli.solver_key.empty()) {
        const BenchmarkCase *benchmark_case = find_case(cases, cli.solver_key);
        if (benchmark_case == nullptr) {
            std::cerr << "Unknown solver key: " << cli.solver_key << "\n";
            std::cerr << "Run --list-solvers to see supported keys.\n";
            return 2;
        }
        const int n_problems = cli.num_problems_override > 0 ? cli.num_problems_override : benchmark_case->default_instances;
        poselib::BenchmarkResult result = benchmark_case->runner(n_problems, benchmark_case->options, cli.tolerance);
        results.push_back(result);
        if (cli.json) {
            print_json_result(*benchmark_case, result, cli.tolerance);
        } else {
            display_result(results);
        }
        return 0;
    }

    for (const BenchmarkCase &benchmark_case : cases) {
        const int n_problems = cli.num_problems_override > 0 ? cli.num_problems_override : benchmark_case.default_instances;
        results.push_back(benchmark_case.runner(n_problems, benchmark_case.options, cli.tolerance));
    }
    display_result(results);
    return 0;
}
