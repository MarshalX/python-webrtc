//
//  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
//  Use of this source code is governed by a BSD-style license
//  that can be found in the LICENSE.md file in the root of the project.
//

// Command pion is the driver of pion/webrtc for the benchmarks, speaking benchmarks/protocol.py.
package main

import (
	"bufio"
	"encoding/json"
	"fmt"
	"os"
	"runtime"
	"runtime/debug"
	"sync"
	"sync/atomic"
	"time"

	"github.com/pion/webrtc/v4"
)

const (
	dataChannelLabel = "bench"
	modulePath       = "github.com/pion/webrtc/v4"
	pingDrain        = time.Second
)

type message map[string]any

type command struct {
	ID        int                     `json:"id"`
	Cmd       string                  `json:"cmd"`
	PC        int                     `json:"pc"`
	Role      string                  `json:"role"`
	Trickle   bool                    `json:"trickle"`
	Ordered   bool                    `json:"ordered"`
	Audio     bool                    `json:"audio"`
	SDP       string                  `json:"sdp"`
	Candidate webrtc.ICECandidateInit `json:"candidate"`
	Size      int                     `json:"size"`
	Seconds   float64                 `json:"seconds"`
	Low       uint64                  `json:"low"`
	High      uint64                  `json:"high"`
	Rate      float64                 `json:"rate"`
	Codec     string                  `json:"codec"`
	Path      string                  `json:"path"`
	FPS       float64                 `json:"fps"`
	Remb      uint64                  `json:"remb"`
}

type event struct {
	pc   int
	name string
}

type peer struct {
	pc      *webrtc.PeerConnection
	trickle bool
	codec   string
	channel *channel
	sink    *sink
	stop    chan struct{}
	// the bytes of the samples written to the connection's own track
	sent atomic.Int64
}

type driver struct {
	settings webrtc.SettingEngine
	api      *webrtc.API
	origin   time.Time

	outMu sync.Mutex
	out   *json.Encoder

	audioOnce sync.Once
	audio     *webrtc.TrackLocalStaticSample
	oggOnce   sync.Once
	ogg       *webrtc.TrackLocalStaticSample
	oggErr    error

	mu    sync.Mutex
	peers map[int]*peer
	sent  map[event]bool
}

func newDriver() *driver {
	settings := webrtc.SettingEngine{}
	// like python-webrtc with WRTC_ALLOW_LOOPBACK=1
	settings.SetIncludeLoopbackCandidate(true)
	return &driver{
		settings: settings,
		api:      webrtc.NewAPI(webrtc.WithSettingEngine(settings)),
		origin:   time.Now(),
		out:      json.NewEncoder(os.Stdout),
		peers:    map[int]*peer{},
		sent:     map[event]bool{},
	}
}

func (d *driver) now() float64 {
	return time.Since(d.origin).Seconds()
}

func (d *driver) send(m message) {
	d.outMu.Lock()
	defer d.outMu.Unlock()
	if err := d.out.Encode(m); err != nil {
		fmt.Fprintln(os.Stderr, "write:", err)
	}
}

func (d *driver) emit(pc int, name string) {
	d.mu.Lock()
	key := event{pc, name}
	first := !d.sent[key]
	d.sent[key] = true
	d.mu.Unlock()
	if first {
		d.send(message{"event": name, "pc": pc, "t": d.now()})
	}
}

func (d *driver) peer(pc int) (*peer, error) {
	d.mu.Lock()
	defer d.mu.Unlock()
	p, ok := d.peers[pc]
	if !ok {
		return nil, fmt.Errorf("no connection %d", pc)
	}
	return p, nil
}

func (d *driver) channel(pc int) (*channel, error) {
	p, err := d.peer(pc)
	if err != nil {
		return nil, err
	}
	d.mu.Lock()
	defer d.mu.Unlock()
	if p.channel == nil {
		return nil, fmt.Errorf("no open data channel on connection %d", pc)
	}
	return p.channel, nil
}

func hello() (message, error) {
	version := "unknown"
	if info, ok := debug.ReadBuildInfo(); ok {
		for _, dep := range info.Deps {
			if dep.Path == modulePath {
				version = dep.Version
			}
		}
	}
	return message{"library": "pion", "version": version, "trickle": true}, nil
}

func (d *driver) create(c command) (message, error) {
	start := d.now()
	api := d.api
	if c.Codec != "" {
		var err error
		if api, err = d.apiFor(c.Codec); err != nil {
			return nil, err
		}
	}

	pc, err := api.NewPeerConnection(webrtc.Configuration{})
	if err != nil {
		return nil, err
	}
	p := &peer{pc: pc, trickle: c.Trickle, codec: c.Codec, stop: make(chan struct{})}
	d.mu.Lock()
	d.peers[c.PC] = p
	d.mu.Unlock()
	d.watch(c.PC, p)

	if c.Role == "offerer" {
		ordered := c.Ordered
		dc, err := pc.CreateDataChannel(dataChannelLabel, &webrtc.DataChannelInit{Ordered: &ordered})
		if err != nil {
			return nil, err
		}
		d.watchChannel(c.PC, p, dc)
		if c.Audio {
			if err := d.addAudio(pc); err != nil {
				return nil, err
			}
		}
	} else {
		pc.OnDataChannel(func(dc *webrtc.DataChannel) { d.watchChannel(c.PC, p, dc) })
	}

	pc.OnTrack(func(track *webrtc.TrackRemote, _ *webrtc.RTPReceiver) {
		d.emit(c.PC, "track")
		go d.receive(p, track)
	})

	return message{"t_start": start, "t_end": d.now()}, nil
}

func (d *driver) watch(id int, p *peer) {
	p.pc.OnICEConnectionStateChange(func(state webrtc.ICEConnectionState) {
		if state == webrtc.ICEConnectionStateConnected || state == webrtc.ICEConnectionStateCompleted {
			d.emit(id, "ice_connected")
		}
	})

	p.pc.OnConnectionStateChange(func(state webrtc.PeerConnectionState) {
		if state == webrtc.PeerConnectionStateConnected || state == webrtc.PeerConnectionStateFailed {
			d.emit(id, state.String())
		}
	})

	p.pc.OnICEGatheringStateChange(func(state webrtc.ICEGatheringState) {
		if state == webrtc.ICEGatheringStateComplete {
			d.emit(id, "gathered")
		}
	})

	p.pc.OnICECandidate(func(candidate *webrtc.ICECandidate) {
		if p.trickle && candidate != nil {
			d.send(message{"event": "candidate", "pc": id, "t": d.now(), "candidate": candidate.ToJSON()})
		}
	})
}

func (d *driver) watchChannel(id int, p *peer, dc *webrtc.DataChannel) {
	c := newChannel(dc)
	opened := func() {
		d.mu.Lock()
		p.channel = c
		d.mu.Unlock()
		d.emit(id, "dc_open")
	}

	dc.OnOpen(opened)
	if dc.ReadyState() == webrtc.DataChannelStateOpen {
		opened()
	}
}

// setLocal sets a local description and returns its SDP, with the candidates unless they trickle.
func setLocal(p *peer, description webrtc.SessionDescription) (string, error) {
	gathered := webrtc.GatheringCompletePromise(p.pc)
	if err := p.pc.SetLocalDescription(description); err != nil {
		return "", err
	}
	if !p.trickle {
		<-gathered
	}
	return p.pc.LocalDescription().SDP, nil
}

func (d *driver) offer(c command) (message, error) {
	p, err := d.peer(c.PC)
	if err != nil {
		return nil, err
	}

	start := d.now()
	offer, err := p.pc.CreateOffer(nil)
	if err != nil {
		return nil, err
	}
	created := d.now()

	sdp, err := setLocal(p, offer)
	if err != nil {
		return nil, err
	}
	return message{"sdp": sdp, "t_start": start, "t_offer": created}, nil
}

func (d *driver) answer(c command) (message, error) {
	p, err := d.peer(c.PC)
	if err != nil {
		return nil, err
	}

	offer := webrtc.SessionDescription{Type: webrtc.SDPTypeOffer, SDP: c.SDP}
	if err := p.pc.SetRemoteDescription(offer); err != nil {
		return nil, err
	}

	answer, err := p.pc.CreateAnswer(nil)
	if err != nil {
		return nil, err
	}
	sdp, err := setLocal(p, answer)
	if err != nil {
		return nil, err
	}
	return message{"sdp": sdp}, nil
}

func (d *driver) accept(c command) (message, error) {
	p, err := d.peer(c.PC)
	if err != nil {
		return nil, err
	}
	answer := webrtc.SessionDescription{Type: webrtc.SDPTypeAnswer, SDP: c.SDP}
	return message{}, p.pc.SetRemoteDescription(answer)
}

func (d *driver) addCandidate(c command) (message, error) {
	p, err := d.peer(c.PC)
	if err != nil {
		return nil, err
	}
	return message{}, p.pc.AddICECandidate(c.Candidate)
}

func (d *driver) close(c command) (message, error) {
	p, err := d.peer(c.PC)
	if err != nil {
		return nil, err
	}
	d.mu.Lock()
	delete(d.peers, c.PC)
	d.mu.Unlock()
	close(p.stop)
	return message{}, p.pc.Close()
}

func (d *driver) count(c command) (message, error) {
	ch, err := d.channel(c.PC)
	if err != nil {
		return nil, err
	}
	return message{"bytes": ch.bytes.Load(), "messages": ch.messages.Load(), "t": d.now()}, nil
}

func (d *driver) echo(c command) (message, error) {
	ch, err := d.channel(c.PC)
	if err != nil {
		return nil, err
	}
	ch.echo.Store(true)
	return message{}, nil
}

func (d *driver) flood(c command) (message, error) {
	ch, err := d.channel(c.PC)
	if err != nil {
		return nil, err
	}
	return message{}, ch.flood(c.Size, seconds(c.Seconds), c.Low, c.High)
}

func (d *driver) ping(c command) (message, error) {
	ch, err := d.channel(c.PC)
	if err != nil {
		return nil, err
	}
	rtts, err := ch.ping(c.Size, c.Rate, seconds(c.Seconds))
	return message{"rtts_ms": rtts}, err
}

func seconds(value float64) time.Duration {
	return time.Duration(value * float64(time.Second))
}

func (d *driver) handle(c command) (message, error) {
	switch c.Cmd {
	case "hello":
		return hello()
	case "create":
		return d.create(c)
	case "offer":
		return d.offer(c)
	case "answer":
		return d.answer(c)
	case "accept":
		return d.accept(c)
	case "add_candidate":
		return d.addCandidate(c)
	case "count":
		return d.count(c)
	case "echo":
		return d.echo(c)
	case "flood":
		return d.flood(c)
	case "ping":
		return d.ping(c)
	case "close":
		return d.close(c)
	case "video_send":
		return d.videoSend(c)
	case "audio_send":
		return d.audioSend(c)
	case "media_sink":
		return d.mediaSink(c)
	case "media_stats":
		return d.mediaStats(c)
	case "collect":
		runtime.GC()
		debug.FreeOSMemory()
		return message{}, nil
	case "probe":
		// no event loop to lag
		return message{}, nil
	}
	return nil, fmt.Errorf("unknown command %q", c.Cmd)
}

func (d *driver) run(c command) {
	result, err := d.handle(c)
	if err != nil {
		d.send(message{"id": c.ID, "error": err.Error()})
		return
	}
	d.send(message{"id": c.ID, "result": result})
}

func main() {
	d := newDriver()
	lines := bufio.NewScanner(os.Stdin)
	lines.Buffer(make([]byte, 1<<20), 1<<24)
	for lines.Scan() {
		var c command
		if err := json.Unmarshal(lines.Bytes(), &c); err != nil {
			continue
		}
		if c.Cmd == "exit" {
			d.send(message{"id": c.ID, "result": message{}})
			return
		}
		go d.run(c)
	}
}
