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

  RTCAudioSource::RTCAudioSource() {
    _source = webrtc::make_ref_counted<RTCAudioTrackSource>();
  }

  void RTCAudioSource::Init(pybind11::module &m) {
    pybind11::class_<RTCAudioSource>(m, "RTCAudioSource")
        .def(pybind11::init<>(), nogil())
        .def("createTrack", &RTCAudioSource::CreateTrack, pybind11::return_value_policy::reference, nogil())
        .def("onData", &RTCAudioSource::OnData, nogil());
  }

  MediaStreamTrack *RTCAudioSource::CreateTrack() {
    // TODO(mroberts): Again, we have some implicit factory we are threading around. How to handle?
    auto factory = PeerConnectionFactory::GetOrCreateDefault();
    auto track = factory->factory()->CreateAudioTrack(webrtc::CreateRandomUuid(), _source.get());
    return MediaStreamTrack::holder()->GetOrCreate(factory, track);
  }

  void RTCAudioSource::OnData(RTCOnDataEvent &data) {
    _source->PushData(data);
  }

} // namespace python_webrtc
