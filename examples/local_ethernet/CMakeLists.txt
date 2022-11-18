set(CMAKE_C_COMPILER "gcc")
set(CMAKE_CXX_COMPILER "g++")

set(CMAKE_BUILD_TYPE Debug)

set_property(TARGET ${PROJECT_NAME} PROPERTY CXX_STANDARD 11)

cmake_minimum_required(VERSION 3.20)

project(local_ethernet VERSION 0.1)

include(ProcessorCount)
ProcessorCount(N)
if(NOT N EQUAL 0)
  set(CTEST_BUILD_FLAGS -j${N})
  set(ctest_test_args ${ctest_test_args} PARALLEL_LEVEL ${N})
endif()

include_directories("${CMAKE_CURRENT_SOURCE_DIR}/../../include")
file(GLOB LIB_SOURCES CONFIGURE_DEPENDS ../../src/*.cpp)
file(GLOB LIB_HEADERS CONFIGURE_DEPENDS ../../include/*.h)


add_library(syndesi_host ${LIB_SOURCES} ${LIB_HEADERS})
add_library(syndesi_device ${LIB_SOURCES} ${LIB_HEADERS})


add_executable(host)
target_sources(host
  PRIVATE
    host/host.cpp
)
target_include_directories(syndesi_host PUBLIC host)
set_target_properties(host PROPERTIES RUNTIME_OUTPUT_DIRECTORY host)
target_compile_features(host PRIVATE cxx_std_17)
target_link_libraries(host syndesi_host)

add_executable(device)
target_sources(device
  PRIVATE
    device/device.cpp
)
target_include_directories(syndesi_device PUBLIC device)
set_target_properties(device PROPERTIES RUNTIME_OUTPUT_DIRECTORY device)
target_compile_features(device PRIVATE cxx_std_17)
target_link_libraries(device syndesi_device)