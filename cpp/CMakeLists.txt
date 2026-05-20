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

# Imported third-party baseline target (no project-owned wrappers yet).
set(LAMBDATWIST_DIR "${CMAKE_CURRENT_SOURCE_DIR}/external/lambdatwist")
add_library(lambdatwist_baseline STATIC
    "${LAMBDATWIST_DIR}/p3p.cc"
)

target_include_directories(lambdatwist_baseline
    PUBLIC
        "${LAMBDATWIST_DIR}"
        "${EIGEN3_INCLUDE_DIR}"
)

# Project-owned absolute pose benchmark family infrastructure.
set(ABSOLUTE_POSE_SOLVERS_DIR
    "${CMAKE_CURRENT_SOURCE_DIR}/bench/families/geometric_pose_solvers/absolute_pose_solvers"
)

# --- Core library: generic absolute pose family, no Lambda Twist dependency ---
add_library(absolute_pose_core STATIC
    "${ABSOLUTE_POSE_SOLVERS_DIR}/core/absolute_pose_benchmark.cpp"
)

target_include_directories(absolute_pose_core
    PUBLIC
        "${ABSOLUTE_POSE_SOLVERS_DIR}/core"
        "${EIGEN3_INCLUDE_DIR}"
)

# --- Lambda Twist adapter library: depends on core + Lambda Twist ---
add_library(absolute_pose_lambdatwist_adapter STATIC
    "${ABSOLUTE_POSE_SOLVERS_DIR}/adapters/lambdatwist_p3p/lambdatwist_p3p_adapter.cpp"
)

target_include_directories(absolute_pose_lambdatwist_adapter
    PUBLIC
        "${ABSOLUTE_POSE_SOLVERS_DIR}/core"
        "${ABSOLUTE_POSE_SOLVERS_DIR}/adapters/lambdatwist_p3p"
        "${EIGEN3_INCLUDE_DIR}"
)

target_link_libraries(absolute_pose_lambdatwist_adapter
    PUBLIC
        absolute_pose_core
    PRIVATE
        lambdatwist_baseline
)

# --- Compatibility alias: absolute_pose_benchmark = core + adapter ---
add_library(absolute_pose_benchmark INTERFACE)
target_link_libraries(absolute_pose_benchmark
    INTERFACE
        absolute_pose_core
        absolute_pose_lambdatwist_adapter
)
target_include_directories(absolute_pose_benchmark
    INTERFACE
        "${ABSOLUTE_POSE_SOLVERS_DIR}/core"
        "${ABSOLUTE_POSE_SOLVERS_DIR}/adapters/lambdatwist_p3p"
        "${EIGEN3_INCLUDE_DIR}"
)

# --- Runner executables ---
add_executable(absolute_pose_lambdatwist_benchmark
    "${ABSOLUTE_POSE_SOLVERS_DIR}/runners/lambdatwist_p3p_benchmark.cpp"
)

target_link_libraries(absolute_pose_lambdatwist_benchmark
    PRIVATE
        absolute_pose_core
        absolute_pose_lambdatwist_adapter
)

add_executable(absolute_pose_lambdatwist_adapter_validator
    "${ABSOLUTE_POSE_SOLVERS_DIR}/runners/lambdatwist_p3p_adapter_validator.cpp"
)

target_link_libraries(absolute_pose_lambdatwist_adapter_validator
    PRIVATE
        absolute_pose_core
        absolute_pose_lambdatwist_adapter
)

# --- Tests ---
add_executable(absolute_pose_correctness_policy_test
    "${CMAKE_CURRENT_SOURCE_DIR}/tests/absolute_pose_correctness_policy_test.cpp"
)

target_link_libraries(absolute_pose_correctness_policy_test
    PRIVATE
        absolute_pose_core
)
