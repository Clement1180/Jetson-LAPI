#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include "pipeline.hpp"

namespace py = pybind11;

PYBIND11_MODULE(lapi_cpp, m) {
    m.doc() = "LAPI C++/TensorRT pipeline module";

    py::class_<lapi::BBox>(m, "BBox")
        .def(py::init<>())
        .def_readwrite("x1", &lapi::BBox::x1)
        .def_readwrite("y1", &lapi::BBox::y1)
        .def_readwrite("x2", &lapi::BBox::x2)
        .def_readwrite("y2", &lapi::BBox::y2)
        .def("w", &lapi::BBox::w)
        .def("h", &lapi::BBox::h)
        .def("cx", &lapi::BBox::cx)
        .def("cy", &lapi::BBox::cy);

    py::class_<lapi::Point2f>(m, "Point2f")
        .def(py::init<>())
        .def_readwrite("x", &lapi::Point2f::x)
        .def_readwrite("y", &lapi::Point2f::y);

    py::class_<lapi::TrackOutput>(m, "TrackOutput")
        .def(py::init<>())
        .def_readonly("id", &lapi::TrackOutput::id)
        .def_readonly("vehicle_box", &lapi::TrackOutput::vehicle_box)
        .def_readonly("vx", &lapi::TrackOutput::vx)
        .def_readonly("vy", &lapi::TrackOutput::vy)
        .def_readonly("has_plate", &lapi::TrackOutput::has_plate)
        .def_readonly("plate_box", &lapi::TrackOutput::plate_box)
        .def_readonly("plate_keypoints", &lapi::TrackOutput::plate_keypoints)
        .def_readonly("plate_text", &lapi::TrackOutput::plate_text)
        .def_readonly("track_age", &lapi::TrackOutput::track_age)
        .def_readonly("detection_hits", &lapi::TrackOutput::detection_hits)
        .def_readonly("is_confirmed", &lapi::TrackOutput::is_confirmed);

    py::class_<lapi::PipelineConfig>(m, "PipelineConfig")
        .def(py::init<>())
        .def_readwrite("car_engine_path", &lapi::PipelineConfig::car_engine_path)
        .def_readwrite("plate_engine_path", &lapi::PipelineConfig::plate_engine_path)
        .def_readwrite("ocr_engine_path", &lapi::PipelineConfig::ocr_engine_path)
        .def_readwrite("ocr_dict_path", &lapi::PipelineConfig::ocr_dict_path)
        .def_readwrite("car_conf_thresh", &lapi::PipelineConfig::car_conf_thresh)
        .def_readwrite("car_iou_thresh", &lapi::PipelineConfig::car_iou_thresh)
        .def_readwrite("plate_conf_thresh", &lapi::PipelineConfig::plate_conf_thresh);

    py::class_<lapi::Pipeline>(m, "Pipeline")
        .def(py::init<>())
        .def("init", &lapi::Pipeline::init)
        .def("frame_count", &lapi::Pipeline::frame_count)
        .def("process_frame", [](lapi::Pipeline& self, py::array_t<uint8_t> frame) {
            auto buf = frame.request();
            if (buf.ndim != 3 || buf.shape[2] != 3)
                throw std::runtime_error("Expected BGR image (H, W, 3)");

            int height = static_cast<int>(buf.shape[0]);
            int width = static_cast<int>(buf.shape[1]);
            const uint8_t* data = static_cast<const uint8_t*>(buf.ptr);

            return self.process_frame(data, width, height);
        }, py::arg("frame"),
        "Process a BGR frame (numpy array H x W x 3) and return track outputs");
}
