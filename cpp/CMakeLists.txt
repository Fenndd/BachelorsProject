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

file(GLOB _SOLVER_MANIFESTS CONFIGURE_DEPENDS
     "${ABSOLUTE_POSE_SOLVERS_DIR}/solvers/*.json")

if(NOT _SOLVER_MANIFESTS)
    message(FATAL_ERROR "No solver manifest JSON files found under "
                        "${ABSOLUTE_POSE_SOLVERS_DIR}/solvers/")
endif()

foreach(_MANIFEST_PATH ${_SOLVER_MANIFESTS})
    file(READ "${_MANIFEST_PATH}" _M)

    # --- top-level strings ------------------------------------------------
    _manifest_string(_family           "${_M}" "family")
    _manifest_string(_solver_id        "${_M}" "solver_id")
    _manifest_string(_adapter_dir      "${_M}" "adapter_dir")
    _manifest_string(_adapter_class    "${_M}" "adapter_class")
    _manifest_string(_adapter_ns       "${_M}" "adapter_namespace")
    _manifest_string(_adapter_header   "${_M}" "adapter_header")
    _manifest_string(_runner_mode      "${_M}" "runner_mode")

    # --- metadata ----------------------------------------------------------
    string(JSON _meta_min_pts  GET "${_M}" "metadata" "min_points")
    string(JSON _meta_def_pts  GET "${_M}" "metadata" "default_case_points")
    string(JSON _meta_ret_ms   GET "${_M}" "metadata" "returns_multiple_solutions")

    # Normalize to valid C++ boolean literal (true / false).
    # CMake's string(JSON GET) for booleans may return true/false/ON/OFF/1/0
    # depending on CMake version; accept all truthy forms, reject everything else.
    string(TOLOWER "${_meta_ret_ms}" _meta_ret_ms)
    if(_meta_ret_ms MATCHES "^(true|on|1|yes)$")
        set(_meta_ret_ms "true")
    else()
        set(_meta_ret_ms "false")
    endif()

    # --- targets -----------------------------------------------------------
    _manifest_string(_tgt_adapter      "${_M}" "targets" "adapter")
    _manifest_string(_tgt_benchmark    "${_M}" "targets" "benchmark")
    _manifest_string(_tgt_validator    "${_M}" "targets" "adapter_validator")

    # --- adapter sources (array iteration) ---------------------------------
    set(_adapter_srcs "")
    string(JSON _src_len LENGTH "${_M}" "adapter_sources")
    if(_src_len GREATER 0)
        math(EXPR _src_max "${_src_len} - 1")
        foreach(_src_idx RANGE 0 ${_src_max})
            string(JSON _src GET "${_M}" "adapter_sources" ${_src_idx})
            string(REGEX REPLACE "^\"(.*)\"$" "\\1" _src_stripped "${_src}")
            string(REPLACE "cpp/" "" _src_relative "${_src_stripped}")
            list(APPEND _adapter_srcs "${_src_relative}")
        endforeach()
    endif()

    # --- extra libs (array iteration) --------------------------------------
    set(_extra_libs "")
    string(JSON _lib_len LENGTH "${_M}" "extra_libs")
    if(_lib_len GREATER 0)
        math(EXPR _lib_max "${_lib_len} - 1")
        foreach(_lib_idx RANGE 0 ${_lib_max})
            string(JSON _lib GET "${_M}" "extra_libs" ${_lib_idx})
            string(REGEX REPLACE "^\"(.*)\"$" "\\1" _lib_stripped "${_lib}")
            list(APPEND _extra_libs "${_lib_stripped}")
        endforeach()
    endif()

    # --- adapter library ---------------------------------------------------
    string(REPLACE "cpp/" "" _adapter_dir_relative "${_adapter_dir}")
    set(_adapter_dir_cmake "${CMAKE_CURRENT_SOURCE_DIR}/${_adapter_dir_relative}")

    add_library(${_tgt_adapter} STATIC ${_adapter_srcs})

    target_include_directories(${_tgt_adapter}
        PUBLIC
            "${ABSOLUTE_POSE_SOLVERS_DIR}/core"
            "${_adapter_dir_cmake}"
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
                "${_adapter_dir_cmake}"
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
                "${_adapter_dir_cmake}"
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
    elseif(_runner_mode STREQUAL "static")
        message(STATUS "Registered solver '${_solver_id}' "
                       "(adapter=${_tgt_adapter}, runner_mode=static)")
    else()
        message(FATAL_ERROR "Solver '${_solver_id}' has unsupported "
                            "runner_mode '${_runner_mode}'. "
                            "Supported modes: generated_absolute_pose")
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
