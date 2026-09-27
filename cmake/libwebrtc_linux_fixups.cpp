// Definitions missing from the libwebrtc-bin Linux archive.
//
// Its `linux_clang_optional.patch` adds out-of-line default constructors to these
// structs (they are declared in the shipped headers), but the objects defining them
// don't make it into libwebrtc.a. Remove once the prebuilt is fixed upstream.

#include <call/rtp_config.h>
#include <modules/congestion_controller/goog_cc/loss_based_bwe_v2.h>

namespace webrtc {

  LossBasedBweV2::Config::Config() = default;

  RtpStreamConfig::Rtx::Rtx() = default;

}  // namespace webrtc
