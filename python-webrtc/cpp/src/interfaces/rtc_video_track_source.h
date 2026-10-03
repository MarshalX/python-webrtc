//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_RTC_VIDEO_TRACK_SOURCE_H_
#define PYTHON_WEBRTC_INTERFACES_RTC_VIDEO_TRACK_SOURCE_H_

#include <atomic>
#include <cstdint>
#include <memory>
#include <mutex>
#include <optional>

#include <api/media_stream_interface.h>
#include <api/notifier.h>
#include <api/video/video_broadcaster.h>
#include <api/video/video_frame.h>

#include "../media/source_control.h"
#include "../utils/paced_thread.h"

namespace python_webrtc {

  // A video source fed with frames by the application (webrtc.VideoTrackGenerator), or by its own synthetic camera
  // (the video of webrtc.get_user_media), which draws a moving pattern on a thread of its own.
  class RTCVideoTrackSource : public webrtc::Notifier<webrtc::VideoTrackSourceInterface> {
  public:
    RTCVideoTrackSource(bool isScreencast, std::optional<bool> needsDenoising);

    ~RTCVideoTrackSource() override;

    RTCVideoTrackSource(const RTCVideoTrackSource &) = delete;
    RTCVideoTrackSource &operator=(const RTCVideoTrackSource &) = delete;

    // Starts the synthetic camera, or restarts it with another size and frame rate
    void StartCamera(int width, int height, double frameRate);

    // whether it's the synthetic camera, and its size and frame rate
    bool IsCamera(int *width, int *height, double *frameRate);

    // what reaches the camera from its tracks, once started
    std::shared_ptr<SourceControl> control() { return _control; }

    void PushFrame(const webrtc::VideoFrame &frame);

    SourceState state() const override { return _ended ? kEnded : kLive; }

    // ends the tracks of the source; must be called on the signaling thread, where they observe it
    void End();

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
    void DrawFrame(int width, int height, uint32_t frame);

    const bool _isScreencast;
    const std::optional<bool> _needsDenoising;
    webrtc::VideoBroadcaster _broadcaster;
    std::atomic<int> _width{0};
    std::atomic<int> _height{0};
    std::atomic<bool> _ended{false};

    std::shared_ptr<SourceControl> _control;
    // guards the camera thread and what it was started with
    std::mutex _cameraMutex;
    int _cameraWidth = 0;
    int _cameraHeight = 0;
    double _cameraFrameRate = 0;
    // last, to be stopped before the rest is destroyed
    std::unique_ptr<PacedThread> _camera;
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_RTC_VIDEO_TRACK_SOURCE_H_
