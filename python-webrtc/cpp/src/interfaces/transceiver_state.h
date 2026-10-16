//
// Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
// Use of this source code is governed by a BSD-style license
// that can be found in the LICENSE.md file in the root of the project.
//

#ifndef PYTHON_WEBRTC_INTERFACES_TRANSCEIVER_STATE_H_
#define PYTHON_WEBRTC_INTERFACES_TRANSCEIVER_STATE_H_

#include <optional>
#include <string>

#include <api/rtp_transceiver_interface.h>

namespace python_webrtc {

  struct TransceiverState {
    std::optional<std::string> mid;
    std::optional<webrtc::RtpTransceiverDirection> currentDirection;
    bool stopping = false;
    bool stopped = false;

    static TransceiverState Of(const webrtc::RtpTransceiverInterface &transceiver) {
      return {.mid = transceiver.mid(),
              .currentDirection = transceiver.current_direction(),
              .stopping = transceiver.stopping(),
              .stopped = transceiver.stopped()};
    }

    static TransceiverState Gone() { return {.stopping = true, .stopped = true}; }
  };

} // namespace python_webrtc

#endif // PYTHON_WEBRTC_INTERFACES_TRANSCEIVER_STATE_H_
