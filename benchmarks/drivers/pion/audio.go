//
//  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
//  Use of this source code is governed by a BSD-style license
//  that can be found in the LICENSE.md file in the root of the project.
//

package main

import (
	"time"

	"github.com/pion/webrtc/v4"
	"github.com/pion/webrtc/v4/pkg/media"
)

const audioFrame = 20 * time.Millisecond

// opusSilence is an Opus packet of 20 ms of silence: Pion has no encoder, so it sends this.
var opusSilence = []byte{0xf8, 0xff, 0xfe}

// addAudio sends the one audio track of the process on a connection, starting it on the first.
func (d *driver) addAudio(pc *webrtc.PeerConnection) error {
	var err error
	d.audioOnce.Do(func() {
		capability := webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeOpus, ClockRate: 48000, Channels: 2}
		d.audio, err = webrtc.NewTrackLocalStaticSample(capability, "audio", "bench")
		if err == nil {
			go writeSilence(d.audio)
		}
	})
	if err != nil {
		return err
	}

	sender, err := pc.AddTrack(d.audio)
	if err != nil {
		return err
	}
	go drainRTCP(sender)
	return nil
}

func writeSilence(track *webrtc.TrackLocalStaticSample) {
	ticker := time.NewTicker(audioFrame)
	defer ticker.Stop()
	for range ticker.C {
		_ = track.WriteSample(media.Sample{Data: opusSilence, Duration: audioFrame})
	}
}

// drainRTCP reads the RTCP of a sender, which the interceptors need to run.
func drainRTCP(sender *webrtc.RTPSender) {
	buffer := make([]byte, 1500)
	for {
		if _, _, err := sender.Read(buffer); err != nil {
			return
		}
	}
}
