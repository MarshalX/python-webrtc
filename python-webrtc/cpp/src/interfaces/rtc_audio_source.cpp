//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "rtc_audio_source.h"
#include "../utils/gil.h"

#include <rtc_base/crypto_random.h>

#include <rtc_base/ref_counted_object.h>

namespace python_webrtc {

  RTCAudioSource::RTCAudioSource()
      : _factory(PeerConnectionFactory::GetOrCreateDefault()), _source(webrtc::make_ref_counted<RTCAudioTrackSource>()) {}

  void RTCAudioSource::Init(pybind11::module &m) {
    pybind11::class_<RTCAudioSource, std::shared_ptr<RTCAudioSource>>(m, "RTCAudioSource")
        .def(pybind11::init<>(), nogil())
        .def("createTrack", &RTCAudioSource::CreateTrack, nogil())
        .def("onData", &RTCAudioSource::OnData, nogil());
  }

  std::shared_ptr<MediaStreamTrack> RTCAudioSource::CreateTrack() {
    auto track = _factory->factory()->CreateAudioTrack(webrtc::CreateRandomUuid(), _source.get());
    return MediaStreamTrack::holder().GetOrCreate(_factory, track);
  }

  void RTCAudioSource::OnData(RTCOnDataEvent &data) {
    _source->PushData(data);
  }

} // namespace python_webrtc
