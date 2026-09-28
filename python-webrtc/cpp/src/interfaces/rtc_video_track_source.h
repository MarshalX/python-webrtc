//
// Copyright 2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#pragma once

#include <atomic>
#include <condition_variable>
#include <mutex>
#include <optional>
#include <thread>

#include <api/media_stream_interface.h>
#include <api/notifier.h>
#include <api/video/video_broadcaster.h>
#include <api/video/video_frame.h>

namespace python_webrtc {

  // A video source fed with frames by the application (webrtc.RTCVideoSource), or by its own synthetic camera
  // (the video of webrtc.get_user_media), which draws a moving pattern on a thread of its own.
  class RTCVideoTrackSource : public webrtc::Notifier<webrtc::VideoTrackSourceInterface> {
  public:
    RTCVideoTrackSource(bool isScreencast, std::optional<bool> needsDenoising);

    ~RTCVideoTrackSource() override;

    // Starts the synthetic camera
    void StartCamera(int width, int height, double frameRate);

    void PushFrame(const webrtc::VideoFrame &frame);

    SourceState state() const override { return kLive; }

    bool remote() const override { return false; }

    bool is_screencast() const override { return _isScreencast; }

    std::optional<bool> needs_denoising() const override { return _needsDenoising; }

    bool GetStats(Stats *stats) override;

    void AddOrUpdateSink(webrtc::VideoSinkInterface<webrtc::VideoFrame> *sink,
                         const webrtc::VideoSinkWants &wants) override;

    void RemoveSink(webrtc::VideoSinkInterface<webrtc::VideoFrame> *sink) override;

    bool SupportsEncodedOutput() const override { return false; }

    void GenerateKeyFrame() override {}

    void AddEncodedSink(webrtc::VideoSinkInterface<webrtc::RecordableEncodedFrame> *sink) override {}

    void RemoveEncodedSink(webrtc::VideoSinkInterface<webrtc::RecordableEncodedFrame> *sink) override {}

  private:
    void RunCamera(int width, int height, double frameRate);

    const bool _isScreencast;
    const std::optional<bool> _needsDenoising;
    webrtc::VideoBroadcaster _broadcaster;
    std::atomic<int> _width{0};
    std::atomic<int> _height{0};

    std::mutex _cameraMutex;
    std::condition_variable _cameraStop;
    bool _stopping = false;
    std::thread _camera;
  };

} // namespace python_webrtc
