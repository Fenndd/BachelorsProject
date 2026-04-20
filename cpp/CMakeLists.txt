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

# Minimal project-owned executable wired to the imported baseline library.
add_executable(baseline_runner
    "${CMAKE_CURRENT_SOURCE_DIR}/src/baseline_runner.cpp"
)

target_link_libraries(baseline_runner
    PRIVATE
        lambdatwist_baseline
)
