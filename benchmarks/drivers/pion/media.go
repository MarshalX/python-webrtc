//
//  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
//  Use of this source code is governed by a BSD-style license
//  that can be found in the LICENSE.md file in the root of the project.
//

package main

import (
	"bytes"
	"errors"
	"fmt"
	"io"
	"os"
	"sync/atomic"
	"time"

	"github.com/pion/rtcp"
	"github.com/pion/webrtc/v4"
	"github.com/pion/webrtc/v4/pkg/media"
	"github.com/pion/webrtc/v4/pkg/media/h264reader"
	"github.com/pion/webrtc/v4/pkg/media/ivfreader"
	"github.com/pion/webrtc/v4/pkg/media/oggreader"
)

const rembInterval = time.Second

var (
	annexBStartCode = []byte{0, 0, 0, 1}
	opusTags        = []byte("OpusTags")
	videoFeedback   = []webrtc.RTCPFeedback{
		{Type: webrtc.TypeRTCPFBGoogREMB}, {Type: webrtc.TypeRTCPFBCCM, Parameter: "fir"},
		{Type: webrtc.TypeRTCPFBNACK}, {Type: webrtc.TypeRTCPFBNACK, Parameter: "pli"},
	}
	opus = webrtc.RTPCodecCapability{
		MimeType: webrtc.MimeTypeOpus, ClockRate: 48000, Channels: 2, SDPFmtpLine: "minptime=10;useinbandfec=1",
	}
	// the video codecs a connection can be limited to, so the offer has only the one sent
	videoCodecs = map[string]webrtc.RTPCodecParameters{
		"VP8": {RTPCodecCapability: webrtc.RTPCodecCapability{MimeType: webrtc.MimeTypeVP8, ClockRate: 90000}, PayloadType: 96},
		"H264": {RTPCodecCapability: webrtc.RTPCodecCapability{
			MimeType: webrtc.MimeTypeH264, ClockRate: 90000,
			SDPFmtpLine: "level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=42e01f",
		}, PayloadType: 102},
		"H264-High": {RTPCodecCapability: webrtc.RTPCodecCapability{
			MimeType: webrtc.MimeTypeH264, ClockRate: 90000,
			SDPFmtpLine: "level-asymmetry-allowed=1;packetization-mode=1;profile-level-id=64001f",
		}, PayloadType: 104},
	}
)

// sink counts the RTP of the tracks a connection receives.
type sink struct {
	bytes  atomic.Int64
	frames atomic.Int64
	remb   uint64
}

// apiFor is an API whose media engine has only one video codec, and Opus.
func (d *driver) apiFor(codec string) (*webrtc.API, error) {
	video, ok := videoCodecs[codec]
	if !ok {
		return nil, fmt.Errorf("unknown codec %q", codec)
	}
	video.RTCPFeedback = videoFeedback

	engine := &webrtc.MediaEngine{}
	if err := engine.RegisterCodec(video, webrtc.RTPCodecTypeVideo); err != nil {
		return nil, err
	}
	audio := webrtc.RTPCodecParameters{RTPCodecCapability: opus, PayloadType: 111}
	if err := engine.RegisterCodec(audio, webrtc.RTPCodecTypeAudio); err != nil {
		return nil, err
	}

	return webrtc.NewAPI(webrtc.WithMediaEngine(engine), webrtc.WithSettingEngine(d.settings)), nil
}

// videoSend sends a pre-encoded file on a connection, looping, a frame every 1/fps.
func (d *driver) videoSend(c command) (message, error) {
	p, err := d.peer(c.PC)
	if err != nil {
		return nil, err
	}
	video, ok := videoCodecs[p.codec]
	if !ok {
		return nil, fmt.Errorf("the connection has no video codec, not %q", p.codec)
	}
	frames, err := loadVideo(c.Path, video.MimeType)
	if err != nil {
		return nil, err
	}

	track, err := webrtc.NewTrackLocalStaticSample(video.RTPCodecCapability, "video", "bench")
	if err != nil {
		return nil, err
	}
	sender, err := p.pc.AddTrack(track)
	if err != nil {
		return nil, err
	}

	go drainRTCP(sender)
	go play(track, frames, time.Duration(float64(time.Second)/c.FPS), p.stop, &p.sent)
	return message{}, nil
}

// audioSend sends the one Ogg Opus file of the process on a connection.
func (d *driver) audioSend(c command) (message, error) {
	p, err := d.peer(c.PC)
	if err != nil {
		return nil, err
	}

	// one track for every connection, as the libraries send one source
	d.oggOnce.Do(func() { d.ogg, d.oggErr = d.startOgg(c.Path) })
	if d.oggErr != nil {
		return nil, d.oggErr
	}

	sender, err := p.pc.AddTrack(d.ogg)
	if err != nil {
		return nil, err
	}
	go drainRTCP(sender)
	return message{}, nil
}

func (d *driver) startOgg(path string) (*webrtc.TrackLocalStaticSample, error) {
	pages, err := loadOgg(path)
	if err != nil {
		return nil, err
	}
	track, err := webrtc.NewTrackLocalStaticSample(opus, "audio", "bench")
	if err != nil {
		return nil, err
	}

	go play(track, pages, audioFrame, nil, nil)
	return track, nil
}

// mediaSink counts what the connection receives, and asks the sender for at most remb bits a second.
func (d *driver) mediaSink(c command) (message, error) {
	p, err := d.peer(c.PC)
	if err != nil {
		return nil, err
	}
	d.mu.Lock()
	p.sink = &sink{remb: c.Remb}
	d.mu.Unlock()
	return message{}, nil
}

func (d *driver) mediaStats(c command) (message, error) {
	p, err := d.peer(c.PC)
	if err != nil {
		return nil, err
	}

	d.mu.Lock()
	s := p.sink
	d.mu.Unlock()
	if s == nil {
		return message{"t": d.now(), "frames": 0, "bytes": p.sent.Load(), "implementation": "file"}, nil
	}
	return message{"t": d.now(), "frames": s.frames.Load(), "bytes": s.bytes.Load(), "implementation": "RTP only"}, nil
}

// receive reads a remote track, counting it if the connection has a sink.
func (d *driver) receive(p *peer, track *webrtc.TrackRemote) {
	d.mu.Lock()
	s := p.sink
	d.mu.Unlock()
	if s != nil && s.remb > 0 {
		go sendREMB(p.pc, uint32(track.SSRC()), s.remb, p.stop)
	}

	// a video frame ends with the packet that has the marker bit, an audio one is a packet
	video := track.Kind() == webrtc.RTPCodecTypeVideo
	for {
		packet, _, err := track.ReadRTP()
		if err != nil {
			return
		}
		if s == nil {
			continue
		}

		s.bytes.Add(int64(len(packet.Payload)))
		if !video || packet.Marker {
			s.frames.Add(1)
		}
	}
}

func sendREMB(pc *webrtc.PeerConnection, ssrc uint32, bitrate uint64, stop <-chan struct{}) {
	ticker := time.NewTicker(rembInterval)
	defer ticker.Stop()

	for {
		remb := &rtcp.ReceiverEstimatedMaximumBitrate{Bitrate: float32(bitrate), SSRCs: []uint32{ssrc}}
		if err := pc.WriteRTCP([]rtcp.Packet{remb}); err != nil {
			return
		}

		select {
		case <-ticker.C:
		case <-stop:
			return
		}
	}
}

// play writes the samples in a loop, one every duration, until stopped, counting the bytes if asked.
func play(
	track *webrtc.TrackLocalStaticSample, samples [][]byte, duration time.Duration, stop <-chan struct{}, sent *atomic.Int64,
) {
	ticker := time.NewTicker(duration)
	defer ticker.Stop()

	for i := 0; ; i++ {
		sample := samples[i%len(samples)]
		_ = track.WriteSample(media.Sample{Data: sample, Duration: duration})
		if sent != nil {
			sent.Add(int64(len(sample)))
		}

		select {
		case <-ticker.C:
		case <-stop:
			return
		}
	}
}

func loadVideo(path, mimeType string) ([][]byte, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()
	if mimeType == webrtc.MimeTypeH264 {
		return accessUnits(file)
	}

	reader, _, err := ivfreader.NewWith(file)
	if err != nil {
		return nil, err
	}

	var frames [][]byte
	for {
		frame, _, err := reader.ParseNextFrame()
		if errors.Is(err, io.EOF) {
			return frames, nil
		}
		if err != nil {
			return nil, err
		}
		frames = append(frames, frame)
	}
}

// accessUnits groups the NAL units of an Annex B stream into frames, each ending with its one slice.
func accessUnits(in io.Reader) ([][]byte, error) {
	reader, err := h264reader.NewReader(in)
	if err != nil {
		return nil, err
	}

	var frames [][]byte
	var unit []byte
	for {
		nal, err := reader.NextNAL()
		if errors.Is(err, io.EOF) {
			return frames, nil
		}
		if err != nil {
			return nil, err
		}

		unit = append(append(unit, annexBStartCode...), nal.Data...)
		if nal.UnitType == h264reader.NalUnitTypeCodedSliceIdr || nal.UnitType == h264reader.NalUnitTypeCodedSliceNonIdr {
			frames = append(frames, unit)
			unit = nil
		}
	}
}

// loadOgg reads the pages of an Ogg Opus file written with one packet a page.
func loadOgg(path string) ([][]byte, error) {
	file, err := os.Open(path)
	if err != nil {
		return nil, err
	}
	defer file.Close()

	reader, _, err := oggreader.NewWith(file)
	if err != nil {
		return nil, err
	}

	var pages [][]byte
	for {
		page, _, err := reader.ParseNextPage()
		if errors.Is(err, io.EOF) {
			return pages, nil
		}
		if err != nil {
			return nil, err
		}
		if !bytes.HasPrefix(page, opusTags) {
			pages = append(pages, page)
		}
	}
}
