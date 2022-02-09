//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
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
        .def("createTrack", &RTCAudioSource::CreateTrack, pybind11::return_value_policy::reference)
        .def("onData", &RTCAudioSource::OnData);
  }

  MediaStreamTrack *RTCAudioSource::CreateTrack() {
    // TODO(mroberts): Again, we have some implicit factory we are threading around. How to handle?
    auto factory = PeerConnectionFactory::GetOrCreateDefault();
    auto track = factory->factory()->CreateAudioTrack(rtc::CreateRandomUuid(), _source.get());
    return MediaStreamTrack::holder()->GetOrCreate(factory, track);
  }

  void RTCAudioSource::OnData(RTCOnDataEvent &data) {
    _source->PushData(data);
  }

} // namespace python_webrtc
