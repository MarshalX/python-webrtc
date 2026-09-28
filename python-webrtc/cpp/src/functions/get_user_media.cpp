//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "../interfaces/media_stream.h"
#include "../interfaces/rtc_video_source.h"
#include "../interfaces/rtc_audio_track_source.h"

#include <rtc_base/crypto_random.h>

namespace python_webrtc {

  // A stream of a synthetic microphone and camera
  // (https://github.com/MarshalX/python-webrtc/issues/169, https://github.com/MarshalX/python-webrtc/issues/170)
  static std::shared_ptr<MediaStream> GetUserMedia(bool audio, bool video, int width, int height, double frameRate) {
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
      auto track = RTCVideoSource::CreateCameraTrack(factory, width, height, frameRate)->track();
      stream->AddTrack(webrtc::scoped_refptr<webrtc::VideoTrackInterface>(
          static_cast<webrtc::VideoTrackInterface *>(track.get())));
    }

    return MediaStream::holder().GetOrCreate(factory, stream);
  }

} // namespace python_webrtc
