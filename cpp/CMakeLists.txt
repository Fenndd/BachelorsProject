cmake_minimum_required(VERSION 3.20)

project(P3POptimizationScaffold LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 20)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# Header-only Eigen include path provided by the user.
set(EIGEN3_INCLUDE_DIR "" CACHE PATH "Path to Eigen include directory (folder containing Eigen/)")
if(NOT EIGEN3_INCLUDE_DIR)
    message(FATAL_ERROR "EIGEN3_INCLUDE_DIR is not set. Please provide the Eigen include path.")
endif()
if(NOT EXISTS "${EIGEN3_INCLUDE_DIR}/Eigen/Core")
    message(FATAL_ERROR "EIGEN3_INCLUDE_DIR is invalid. Expected to find Eigen/Core under: ${EIGEN3_INCLUDE_DIR}")
endif()

# Copied PoseLib minimal-solver sources used by the native PoseLib benchmark.
set(POSELIB_DIR "${CMAKE_CURRENT_SOURCE_DIR}/external/poselib")
set(POSELIB_NATIVE_SOURCES
    "${POSELIB_DIR}/PoseLib/solvers/gp3p.cc"
    "${POSELIB_DIR}/PoseLib/solvers/gp4ps.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p1p2ll.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p2p1ll.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p2p2pl.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p3ll.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p3p.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p3p_lambdatwist.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p4pf.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p35pf.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p5pf.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p5pfr.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p3p1llf.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p2p2llf.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p1p3llf.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p4llf.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p5lp_radial.cc"
    "${POSELIB_DIR}/PoseLib/solvers/p6lp.cc"
    "${POSELIB_DIR}/PoseLib/solvers/ugp2p.cc"
    "${POSELIB_DIR}/PoseLib/solvers/ugp3ps.cc"
    "${POSELIB_DIR}/PoseLib/solvers/up1p2pl.cc"
    "${POSELIB_DIR}/PoseLib/solvers/up2p.cc"
    "${POSELIB_DIR}/PoseLib/solvers/up1p1ll.cc"
    "${POSELIB_DIR}/PoseLib/solvers/up4pl.cc"
    "${POSELIB_DIR}/PoseLib/solvers/ugp4pl.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_upright_3pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_upright_planar_2pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_upright_planar_3pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_8pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_5pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_monodepth_3pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_7pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_6pt_focal.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_k2Fk1_10pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_kFk_9pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_monodepth_3pt_shared_focal.cc"
    "${POSELIB_DIR}/PoseLib/solvers/relpose_monodepth_3pt_varying_focal.cc"
    "${POSELIB_DIR}/PoseLib/solvers/gen_relpose_upright_4pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/gen_relpose_5p1pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/gen_relpose_6pt.cc"
    "${POSELIB_DIR}/PoseLib/solvers/homography_4pt.cc"
    "${POSELIB_DIR}/PoseLib/misc/qep.cc"
    "${POSELIB_DIR}/PoseLib/misc/univariate.cc"
    "${POSELIB_DIR}/PoseLib/misc/essential.cc"
    "${POSELIB_DIR}/PoseLib/misc/re3q3.cc"
    "${POSELIB_DIR}/PoseLib/misc/camera_models.cc"
    "${POSELIB_DIR}/PoseLib/misc/decompositions.cc"
)

add_library(poselib_native_core STATIC ${POSELIB_NATIVE_SOURCES})
target_include_directories(poselib_native_core
    PUBLIC
        "${POSELIB_DIR}"
        "${POSELIB_DIR}/PoseLib"
        "${EIGEN3_INCLUDE_DIR}"
)

add_executable(poselib_solver_benchmark
    "${POSELIB_DIR}/benchmark/solver_benchmark.cc"
    "${POSELIB_DIR}/benchmark/problem_generator.cc"
)
target_include_directories(poselib_solver_benchmark
    PRIVATE
        "${POSELIB_DIR}/benchmark"
)
target_link_libraries(poselib_solver_benchmark
    PRIVATE
        poselib_native_core
)
