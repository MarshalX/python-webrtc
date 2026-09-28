//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "get_user_media.h"

#include <rtc_base/crypto_random.h>

#include "../interfaces/rtc_video_source.h"
#include "../interfaces/rtc_audio_track_source.h"

namespace python_webrtc {

  std::shared_ptr<MediaStream> GetUserMedia(bool audio, bool video, int width, int height, double frameRate) {
    auto factory = PeerConnectionFactory::GetOrCreateDefault();
    auto stream = factory->factory()->CreateLocalMediaStream(webrtc::CreateRandomUuid());

    if (audio) {
      // a synthetic microphone, as the audio device of the factory is a dummy one
      auto source = webrtc::make_ref_counted<RTCAudioTrackSource>();
      source->StartMicrophone();
      auto track = factory->factory()->CreateAudioTrack(webrtc::CreateRandomUuid(), source.get());
      stream->AddTrack(track);
    }

    if (video) {
      stream->AddTrack(RTCVideoSource::CreateCameraTrack(factory, width, height, frameRate));
    }

    return MediaStream::holder().GetOrCreate(factory, stream);
  }

} // namespace python_webrtc
