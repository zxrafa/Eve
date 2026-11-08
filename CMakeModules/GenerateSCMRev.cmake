# SPDX-FileCopyrightText: Copyright 2026 Eden Emulator Project
# SPDX-License-Identifier: GPL-3.0-or-later

# SPDX-FileCopyrightText: 2019 yuzu Emulator Project
# SPDX-License-Identifier: GPL-2.0-or-later

# generate git/build information
include(GetSCMRev)

function(get_timestamp _var)
    string(TIMESTAMP timestamp UTC)
    set(${_var} "${timestamp}" PARENT_SCOPE)
endfunction()

get_timestamp(BUILD_DATE)

# Eve fork releases are numbered v1, v2, ...: dist/eve_version.txt holds the number.
set(EVE_VERSION_FILE "${CMAKE_SOURCE_DIR}/dist/eve_version.txt")
if (EXISTS "${EVE_VERSION_FILE}")
    file(STRINGS "${EVE_VERSION_FILE}" EVE_VERSION LIMIT_COUNT 1 REGEX "^[0-9]+$")
    set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${EVE_VERSION_FILE}")
    # The log names the commit: reconfigure when HEAD moves (commit, checkout, merge, revert).
    if (EXISTS "${CMAKE_SOURCE_DIR}/.git/logs/HEAD")
        set_property(DIRECTORY APPEND PROPERTY CMAKE_CONFIGURE_DEPENDS "${CMAKE_SOURCE_DIR}/.git/logs/HEAD")
    endif()
endif()

if (EVE_BUILD_TAG MATCHES "^build-[0-9]+$")
    set(BUILD_VERSION "${EVE_BUILD_TAG}")
    set(IS_DEV_BUILD false)
elseif (EVE_VERSION)
    set(BUILD_VERSION "v${EVE_VERSION}")
    set(IS_DEV_BUILD false)
elseif (DEFINED GIT_RELEASE)
    set(BUILD_VERSION "${GIT_TAG}")
    set(GIT_REFSPEC "${GIT_RELEASE}")
    set(IS_DEV_BUILD false)
else()
    string(SUBSTRING ${GIT_COMMIT} 0 10 BUILD_VERSION)
    set(BUILD_VERSION "${BUILD_VERSION}-${GIT_REFSPEC}")
    set(IS_DEV_BUILD true)
endif()

if (NIGHTLY_BUILD)
    set(IS_NIGHTLY_BUILD true)
else()
    set(IS_NIGHTLY_BUILD false)
endif()

if (EVE_VERSION AND NOT EVE_BUILD_TAG MATCHES "^build-[0-9]+$")
    # Logs keep the commit: "Eve vN | <branch>-<commit>".
    string(SUBSTRING ${GIT_COMMIT} 0 10 GIT_DESC)
else()
    set(GIT_DESC ${BUILD_VERSION})
endif()

# Generate cpp with Git revision from template

set(BUILD_AUTO_UPDATE_STABLE_REPO "zxrafa/Eve")
set(BUILD_AUTO_UPDATE_STABLE_API "api.github.com")
set(BUILD_AUTO_UPDATE_API_PATH "/repos/zxrafa/Eve/releases?per_page=100")
set(BUILD_AUTO_UPDATE_WEBSITE "https://github.com")
set(BUILD_AUTO_UPDATE_REPO "zxrafa/Eve")
if (NIGHTLY_BUILD)
    set(REPO_NAME "Eve Nightly")
else()
    set(REPO_NAME "Eve")
endif()

set(BUILD_ID ${GIT_REFSPEC})
set(BUILD_FULLNAME "${REPO_NAME} ${BUILD_VERSION} ")
set(CXX_COMPILER "${CMAKE_CXX_COMPILER_ID} ${CMAKE_CXX_COMPILER_VERSION}")

configure_file(scm_rev.cpp.in scm_rev.cpp @ONLY)
