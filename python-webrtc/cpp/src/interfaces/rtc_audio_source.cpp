//
// Created by Il'ya Semyonov on 1/14/22.
//

#include "rtc_audio_source.h"

#include <webrtc/rtc_base/ref_counted_object.h>

namespace python_webrtc {

  RTCAudioSource::RTCAudioSource() {
    _source = new rtc::RefCountedObject<RTCAudioTrackSource>();
  }

  void RTCAudioSource::Init(pybind11::module &m) {
    pybind11::class_<RTCAudioSource>(m, "RTCAudioSource")
        .def(pybind11::init<>())
        .def("createTrack", &RTCAudioSource::CreateTrack)
        .def("onData", &RTCAudioSource::OnData);
  }

  std::unique_ptr<MediaStreamTrack> RTCAudioSource::CreateTrack() {
    // TODO(mroberts): Again, we have some implicit factory we are threading around. How to handle?
    auto factory = PeerConnectionFactory::GetOrCreateDefault();
    auto track = factory->factory()->CreateAudioTrack(rtc::CreateRandomUuid(), _source.get());
    return std::make_unique<MediaStreamTrack>(factory, track);
  }

  void RTCAudioSource::OnData(RTCOnDataEvent &data) {
     _source->PushData(data);
  }

} // namespace python_webrtc
