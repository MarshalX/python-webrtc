//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "../interfaces/media_stream.h"

namespace python_webrtc {

  static std::unique_ptr<MediaStream> GetUserMedia() {
    // TODO GetUserMediaImpl should be asynced method ?
    auto factory = PeerConnectionFactory::GetOrCreateDefault();
    auto stream = factory->factory()->CreateLocalMediaStream(rtc::CreateRandomUuid());

    // TODO get from bound MediaStreamConstraints
    auto audio = true;
    auto video = false;

    if (audio) {
      cricket::AudioOptions options;
      auto source = factory->factory()->CreateAudioSource(options);
      auto track = factory->factory()->CreateAudioTrack(rtc::CreateRandomUuid(), source);
      stream->AddTrack(track);
    }

    if (video) {
//      TODO create RTCVideoTrackSource
//      auto source = ... RTCVideoTrackSource()
//      auto track = factory->factory()->CreateVideoTrack(rtc::CreateRandomUuid(), source);
//      stream->AddTrack(track);
    }

    return std::make_unique<MediaStream>(factory, stream);
  }

} // namespace python_webrtc
