//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_MEDIA_RELAYED_VIDEO_TRACK_H_
#define PYTHON_WEBRTC_MEDIA_RELAYED_VIDEO_TRACK_H_

#include <map>
#include <memory>
#include <string>

#include <api/media_stream_interface.h>
#include <api/scoped_refptr.h>
#include <api/sequence_checker.h>
#include <api/video/video_adapter.h>
#include <api/video/video_frame.h>
#include <api/video/video_sink_interface.h>
#include <rtc_base/timestamp_aligner.h>

namespace python_webrtc {

  // A track with a remote source as its sender sees it: frames restamped on the local clock without their remote NTP
  // time, since encoders drop frames whose capture time goes back, and adapted to what the encoder wants
  class RelayedVideoTrack : public webrtc::VideoTrackInterface {
  public:
    explicit RelayedVideoTrack(webrtc::scoped_refptr<webrtc::VideoTrackInterface> track);

    ~RelayedVideoTrack() override;

    RelayedVideoTrack(const RelayedVideoTrack &) = delete;
    RelayedVideoTrack &operator=(const RelayedVideoTrack &) = delete;

    [[nodiscard]] const webrtc::scoped_refptr<webrtc::VideoTrackInterface> &track() const { return _track; }

    [[nodiscard]] std::string kind() const override { return _track->kind(); }

    [[nodiscard]] std::string id() const override { return _track->id(); }

    [[nodiscard]] bool enabled() const override { return _track->enabled(); }

    bool set_enabled(bool enable) override { return _track->set_enabled(enable); }

    [[nodiscard]] TrackState state() const override { return _track->state(); }

    void RegisterObserver(webrtc::ObserverInterface *observer) override { _track->RegisterObserver(observer); }

    void UnregisterObserver(webrtc::ObserverInterface *observer) override { _track->UnregisterObserver(observer); }

    [[nodiscard]] webrtc::VideoTrackSourceInterface *GetSource() const override { return _track->GetSource(); }

    [[nodiscard]] ContentHint content_hint() const override { return _track->content_hint(); }

    void set_content_hint(ContentHint hint) override { _track->set_content_hint(hint); }

    void AddOrUpdateSink(webrtc::VideoSinkInterface<webrtc::VideoFrame> *sink,
                         const webrtc::VideoSinkWants &wants) override;

    void RemoveSink(webrtc::VideoSinkInterface<webrtc::VideoFrame> *sink) override;

    void RequestRefreshFrame() override { _track->RequestRefreshFrame(); }

  private:
    class Restamper : public webrtc::VideoSinkInterface<webrtc::VideoFrame> {
    public:
      explicit Restamper(webrtc::VideoSinkInterface<webrtc::VideoFrame> *sink) : _sink(sink) {}

      void OnSinkWants(const webrtc::VideoSinkWants &wants) { _adapter.OnSinkWants(wants); }

      void OnFrame(const webrtc::VideoFrame &frame) override;

      void OnDiscardedFrame() override { _sink->OnDiscardedFrame(); }

      void OnConstraintsChanged(const webrtc::VideoTrackSourceConstraints &constraints) override {
        _sink->OnConstraintsChanged(constraints);
      }

    private:
      webrtc::VideoSinkInterface<webrtc::VideoFrame> *const _sink;
      webrtc::TimestampAligner _aligner;
      webrtc::VideoAdapter _adapter;
    };

    const webrtc::scoped_refptr<webrtc::VideoTrackInterface> _track;
    webrtc::SequenceChecker _worker{webrtc::SequenceChecker::kDetached};
    std::map<webrtc::VideoSinkInterface<webrtc::VideoFrame> *, std::unique_ptr<Restamper>>
        _sinks RTC_GUARDED_BY(_worker);
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_MEDIA_RELAYED_VIDEO_TRACK_H_
