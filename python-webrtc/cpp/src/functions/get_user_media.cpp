//
// Copyright 2022 Il`ya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#include "get_user_media.h"

#include <rtc_base/crypto_random.h>

#include "../interfaces/rtc_audio_track_source.h"
#include "../interfaces/rtc_video_track_source.h"
#include "../media/source_control.h"

namespace python_webrtc {

  namespace {

    // a synthetic microphone, as the audio device of the factory records nothing
    webrtc::scoped_refptr<webrtc::AudioTrackInterface> CreateMicrophoneTrack(
        const std::shared_ptr<PeerConnectionFactory> &factory) {
      auto source = webrtc::make_ref_counted<RTCAudioTrackSource>();
      source->StartMicrophone();
      auto track = factory->factory()->CreateAudioTrack(webrtc::CreateRandomUuid(), source.get());
      SourceControl::Register(track.get(), track->id(), source->control());
      return track;
    }

    webrtc::scoped_refptr<webrtc::VideoTrackInterface> CreateCameraTrack(
        const std::shared_ptr<PeerConnectionFactory> &factory, int width, int height, double frameRate) {
      auto source = webrtc::make_ref_counted<RTCVideoTrackSource>(false, std::nullopt);
      source->StartCamera(width, height, frameRate);
      auto track = factory->factory()->CreateVideoTrack(source, webrtc::CreateRandomUuid());
      SourceControl::Register(track.get(), track->id(), source->control());
      return track;
    }

  } // namespace

  std::shared_ptr<MediaStream> GetUserMedia(bool audio, bool video, int width, int height, double frameRate) {
    auto factory = PeerConnectionFactory::GetOrCreateDefault();
    auto stream = factory->factory()->CreateLocalMediaStream(webrtc::CreateRandomUuid());

    if (audio) {
      stream->AddTrack(CreateMicrophoneTrack(factory));
    }

    if (video) {
      stream->AddTrack(CreateCameraTrack(factory, width, height, frameRate));
    }

    return MediaStream::holder().GetOrCreate(factory, stream);
  }

} // namespace python_webrtc
