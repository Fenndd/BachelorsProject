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

# ---------------------------------------------------------------------------
# Helper: extract a string value from a JSON manifest, stripping quotes.
# CMake < 3.31 returns strings with surrounding double-quotes.
# ---------------------------------------------------------------------------
function(_manifest_string out_var manifest)
    string(JSON _raw GET "${manifest}" ${ARGN})
    string(REGEX REPLACE "^\"(.*)\"$" "\\1" _stripped "${_raw}")
    set(${out_var} "${_stripped}" PARENT_SCOPE)
endfunction()

# Imported third-party baseline target.
set(LAMBDATWIST_DIR "${CMAKE_CURRENT_SOURCE_DIR}/external/lambdatwist")
add_library(lambdatwist_baseline STATIC
    "${LAMBDATWIST_DIR}/p3p.cc"
)
target_include_directories(lambdatwist_baseline
    PUBLIC
        "${LAMBDATWIST_DIR}"
        "${EIGEN3_INCLUDE_DIR}"
)

# ---------------------------------------------------------------------------
# Absolute-pose family infrastructure
# ---------------------------------------------------------------------------
set(ABSOLUTE_POSE_SOLVERS_DIR
    "${CMAKE_CURRENT_SOURCE_DIR}/bench/absolute_pose"
)

add_library(absolute_pose_core STATIC
    "${ABSOLUTE_POSE_SOLVERS_DIR}/core/absolute_pose_benchmark.cpp"
)
target_include_directories(absolute_pose_core
    PUBLIC
        "${ABSOLUTE_POSE_SOLVERS_DIR}/core"
        "${EIGEN3_INCLUDE_DIR}"
)

# ---------------------------------------------------------------------------
# Discover solver manifests and generate targets
# ---------------------------------------------------------------------------
set(_GEN_DIR "${CMAKE_CURRENT_BINARY_DIR}/generated")

file(GLOB _SOLVER_MANIFESTS "${ABSOLUTE_POSE_SOLVERS_DIR}/solvers/*.json")

foreach(_MANIFEST_PATH ${_SOLVER_MANIFESTS})
    file(READ "${_MANIFEST_PATH}" _M)

    # --- top-level strings ------------------------------------------------
    _manifest_string(_family           "${_M}" "family")
    _manifest_string(_solver_id        "${_M}" "solver_id")
    _manifest_string(_adapter_class    "${_M}" "adapter_class")
    _manifest_string(_adapter_ns       "${_M}" "adapter_namespace")
    _manifest_string(_adapter_header   "${_M}" "adapter_header")
    _manifest_string(_runner_mode      "${_M}" "runner_mode")

    # --- metadata ----------------------------------------------------------
    string(JSON _meta_min_pts  GET "${_M}" "metadata" "min_points")
    string(JSON _meta_def_pts  GET "${_M}" "metadata" "default_case_points")
    string(JSON _meta_ret_ms   GET "${_M}" "metadata" "returns_multiple_solutions")

    # --- targets -----------------------------------------------------------
    _manifest_string(_tgt_adapter      "${_M}" "targets" "adapter")
    _manifest_string(_tgt_benchmark    "${_M}" "targets" "benchmark")
    _manifest_string(_tgt_validator    "${_M}" "targets" "adapter_validator")

    # --- adapter sources (array iteration via error-based bounds check) ----
    set(_adapter_srcs "")
    set(_src_idx 0)
    while(TRUE)
        string(JSON _src ERROR_VARIABLE _src_err
               MEMBER "${_M}" "adapter_sources" ${_src_idx})
        if(_src_err)
            break()
        endif()
        string(REGEX REPLACE "^\"(.*)\"$" "\\1" _src_stripped "${_src}")
        string(REPLACE "cpp/" "" _src_relative "${_src_stripped}")
        list(APPEND _adapter_srcs "${_src_relative}")
        math(EXPR _src_idx "${_src_idx} + 1")
    endwhile()

    # --- extra libs (array iteration) --------------------------------------
    set(_extra_libs "")
    set(_lib_idx 0)
    while(TRUE)
        string(JSON _lib ERROR_VARIABLE _lib_err
               MEMBER "${_M}" "extra_libs" ${_lib_idx})
        if(_lib_err)
            break()
        endif()
        string(REGEX REPLACE "^\"(.*)\"$" "\\1" _lib_stripped "${_lib}")
        list(APPEND _extra_libs "${_lib_stripped}")
        math(EXPR _lib_idx "${_lib_idx} + 1")
    endwhile()

    # --- adapter library ---------------------------------------------------
    add_library(${_tgt_adapter} STATIC ${_adapter_srcs})

    target_include_directories(${_tgt_adapter}
        PUBLIC
            "${ABSOLUTE_POSE_SOLVERS_DIR}/core"
            "${ABSOLUTE_POSE_SOLVERS_DIR}/adapters/${_solver_id}"
            "${EIGEN3_INCLUDE_DIR}"
    )
    target_link_libraries(${_tgt_adapter}
        PUBLIC
            absolute_pose_core
        PRIVATE
            ${_extra_libs}
    )

    # --- generated runner executables (only for generated_absolute_pose) ---
    if(_runner_mode STREQUAL "generated_absolute_pose")
        # -- benchmark runner template --------------------------------------
        string(JSON _bm_camera_fov    GET "${_M}" "benchmark_options" "camera_fov")
        string(JSON _bm_npp           GET "${_M}" "benchmark_options" "n_point_point")
        string(JSON _bm_npl           GET "${_M}" "benchmark_options" "n_point_line")
        string(JSON _bm_tol           GET "${_M}" "benchmark_options" "tolerance")
        string(JSON _bm_num_problems  GET "${_M}" "benchmark_options" "num_problems")
        string(JSON _bm_timed_iter    GET "${_M}" "benchmark_options" "timed_iterations")

        set(SOLVER_ID                    "${_solver_id}")
        set(ADAPTER_CLASS                "${_adapter_class}")
        set(ADAPTER_NAMESPACE            "${_adapter_ns}")
        set(ADAPTER_HEADER               "${_adapter_header}")
        set(BENCHMARK_CAMERA_FOV         "${_bm_camera_fov}")
        set(BENCHMARK_N_POINT_POINT      "${_bm_npp}")
        set(BENCHMARK_N_POINT_LINE       "${_bm_npl}")
        set(BENCHMARK_TOLERANCE          "${_bm_tol}")
        set(BENCHMARK_NUM_PROBLEMS       "${_bm_num_problems}")
        set(BENCHMARK_TIMED_ITERATIONS   "${_bm_timed_iter}")

        configure_file(
            "${ABSOLUTE_POSE_SOLVERS_DIR}/runners/absolute_pose_benchmark.cpp.in"
            "${_GEN_DIR}/${_solver_id}_benchmark.cpp"
            @ONLY
        )

        add_executable(${_tgt_benchmark}
            "${_GEN_DIR}/${_solver_id}_benchmark.cpp"
        )
        target_include_directories(${_tgt_benchmark}
            PRIVATE
                "${ABSOLUTE_POSE_SOLVERS_DIR}/core"
                "${ABSOLUTE_POSE_SOLVERS_DIR}/adapters/${_solver_id}"
        )
        target_link_libraries(${_tgt_benchmark}
            PRIVATE
                absolute_pose_core
                ${_tgt_adapter}
        )

        # -- adapter validator template -------------------------------------
        string(JSON _val_num_problems   GET "${_M}" "validator_options" "num_problems")
        string(JSON _val_tol            GET "${_M}" "validator_options" "tolerance")
        string(JSON _val_camera_fov     GET "${_M}" "validator_options" "camera_fov")
        string(JSON _val_npp            GET "${_M}" "validator_options" "n_point_point")
        string(JSON _val_npl            GET "${_M}" "validator_options" "n_point_line")
        string(JSON _val_timed_iter     GET "${_M}" "validator_options" "timed_iterations")
        string(JSON _val_min_gt_pct     GET "${_M}" "validator_options" "min_gt_found_percent")
        string(JSON _val_min_valid_pct  GET "${_M}" "validator_options" "min_valid_solutions_percent")
        string(JSON _val_rot_tol        GET "${_M}" "validator_options" "rotation_tolerance")

        set(SOLVER_ID                        "${_solver_id}")
        set(ADAPTER_CLASS                    "${_adapter_class}")
        set(ADAPTER_NAMESPACE                "${_adapter_ns}")
        set(ADAPTER_HEADER                   "${_adapter_header}")
        set(MIN_POINTS                       "${_meta_min_pts}")
        set(DEFAULT_CASE_POINTS              "${_meta_def_pts}")
        set(RETURNS_MULTIPLE_SOLUTIONS       "${_meta_ret_ms}")
        set(VALIDATOR_NUM_PROBLEMS           "${_val_num_problems}")
        set(VALIDATOR_TOLERANCE              "${_val_tol}")
        set(VALIDATOR_CAMERA_FOV             "${_val_camera_fov}")
        set(VALIDATOR_N_POINT_POINT          "${_val_npp}")
        set(VALIDATOR_N_POINT_LINE           "${_val_npl}")
        set(VALIDATOR_TIMED_ITERATIONS       "${_val_timed_iter}")
        set(VALIDATOR_MIN_GT_FOUND_PERCENT   "${_val_min_gt_pct}")
        set(VALIDATOR_MIN_VALID_SOLUTIONS_PERCENT "${_val_min_valid_pct}")
        set(VALIDATOR_ROTATION_TOLERANCE     "${_val_rot_tol}")

        configure_file(
            "${ABSOLUTE_POSE_SOLVERS_DIR}/runners/absolute_pose_adapter_validator.cpp.in"
            "${_GEN_DIR}/${_solver_id}_adapter_validator.cpp"
            @ONLY
        )

        add_executable(${_tgt_validator}
            "${_GEN_DIR}/${_solver_id}_adapter_validator.cpp"
        )
        target_include_directories(${_tgt_validator}
            PRIVATE
                "${ABSOLUTE_POSE_SOLVERS_DIR}/core"
                "${ABSOLUTE_POSE_SOLVERS_DIR}/adapters/${_solver_id}"
        )
        target_link_libraries(${_tgt_validator}
            PRIVATE
                absolute_pose_core
                ${_tgt_adapter}
        )

        message(STATUS "Registered solver '${_solver_id}' "
                       "(adapter=${_tgt_adapter} "
                       "benchmark=${_tgt_benchmark} "
                       "validator=${_tgt_validator})")
    endif()

    unset(SOLVER_ID)
    unset(ADAPTER_CLASS)
    unset(ADAPTER_NAMESPACE)
    unset(ADAPTER_HEADER)
    unset(MIN_POINTS)
    unset(DEFAULT_CASE_POINTS)
    unset(RETURNS_MULTIPLE_SOLUTIONS)
    unset(BENCHMARK_CAMERA_FOV)
    unset(BENCHMARK_N_POINT_POINT)
    unset(BENCHMARK_N_POINT_LINE)
    unset(BENCHMARK_TOLERANCE)
    unset(BENCHMARK_NUM_PROBLEMS)
    unset(BENCHMARK_TIMED_ITERATIONS)
    unset(VALIDATOR_NUM_PROBLEMS)
    unset(VALIDATOR_TOLERANCE)
    unset(VALIDATOR_CAMERA_FOV)
    unset(VALIDATOR_N_POINT_POINT)
    unset(VALIDATOR_N_POINT_LINE)
    unset(VALIDATOR_TIMED_ITERATIONS)
    unset(VALIDATOR_MIN_GT_FOUND_PERCENT)
    unset(VALIDATOR_MIN_VALID_SOLUTIONS_PERCENT)
    unset(VALIDATOR_ROTATION_TOLERANCE)
endforeach()
