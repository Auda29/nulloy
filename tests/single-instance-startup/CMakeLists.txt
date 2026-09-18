cmake_minimum_required(VERSION 3.24)
project(NulloySingleInstanceStartupTests LANGUAGES CXX)

set(CMAKE_CXX_STANDARD 17)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_AUTOMOC ON)

find_package(Qt6 6.8 COMPONENTS Widgets Network Test QUIET)
if(Qt6_FOUND)
    set(NULLOY_TEST_QT Qt6)
else()
    find_package(Qt5 5.15 REQUIRED COMPONENTS Widgets Network Test)
    set(NULLOY_TEST_QT Qt5)
endif()

set(SINGLE_DIR "${PROJECT_SOURCE_DIR}/../../3rdParty/qtsingleapplication-8fd81b2/src")
add_executable(testSingleInstanceStartup
    testSingleInstanceStartup.cpp
    "${PROJECT_SOURCE_DIR}/../../src/singleInstanceStartup.cpp"
    "${PROJECT_SOURCE_DIR}/../../src/singleInstanceStartup.h"
    "${SINGLE_DIR}/qtsingleapplication.cpp"
    "${SINGLE_DIR}/qtlocalpeer.cpp"
    "${SINGLE_DIR}/qtsingleapplication.h"
    "${SINGLE_DIR}/qtlocalpeer.h"
)
target_include_directories(testSingleInstanceStartup PRIVATE
    "${PROJECT_SOURCE_DIR}/../../src"
    "${SINGLE_DIR}")
target_link_libraries(testSingleInstanceStartup PRIVATE
    ${NULLOY_TEST_QT}::Widgets
    ${NULLOY_TEST_QT}::Network
    ${NULLOY_TEST_QT}::Test)
if(WIN32)
    # Match the production Windows build: QtLockedFile calls wide Win32 APIs.
    target_compile_definitions(testSingleInstanceStartup PRIVATE UNICODE _UNICODE)
endif()

enable_testing()
add_test(NAME testSingleInstanceStartup COMMAND testSingleInstanceStartup
    -o "${CMAKE_BINARY_DIR}/testSingleInstanceStartup-results.txt,txt")
set_tests_properties(testSingleInstanceStartup PROPERTIES
    ENVIRONMENT "QT_QPA_PLATFORM=offscreen"
    TIMEOUT 30)
