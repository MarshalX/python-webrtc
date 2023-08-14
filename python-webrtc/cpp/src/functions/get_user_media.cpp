//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "../interfaces/media_stream.h"

namespace python_webrtc {

  static MediaStream *GetUserMedia() {
    auto factory = PeerConnectionFactory::GetOrCreateDefault();
    auto stream = factory->factory()->CreateLocalMediaStream(rtc::CreateRandomUuid());

    // TODO (MarshalX) get from bound MediaStreamConstraints
    // https://github.com/MarshalX/python-webrtc/issues/169
    auto audio = true;
    auto video = false;

    if (audio) {
      cricket::AudioOptions options;
      auto source = factory->factory()->CreateAudioSource(options);
      auto track = factory->factory()->CreateAudioTrack(rtc::CreateRandomUuid(), source);
      stream->AddTrack(track);
    }

    if (video) {
//      TODO (MarshalX) create RTCVideoTrackSource
//      https://github.com/MarshalX/python-webrtc/issues/170
//      auto source = ... RTCVideoTrackSource()
//      auto track = factory->factory()->CreateVideoTrack(rtc::CreateRandomUuid(), source);
//      stream->AddTrack(track);
    }

    return MediaStream::holder()->GetOrCreate(factory, stream);
  }

} // namespace python_webrtc
