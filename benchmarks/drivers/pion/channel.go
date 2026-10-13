//
//  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
//  Use of this source code is governed by a BSD-style license
//  that can be found in the LICENSE.md file in the root of the project.
//

package main

import (
	"encoding/binary"
	"sync"
	"sync/atomic"
	"time"

	"github.com/pion/webrtc/v4"
)

// channel is a data channel that counts what it receives, and echoes, floods or pings.
type channel struct {
	dc       *webrtc.DataChannel
	bytes    atomic.Int64
	messages atomic.Int64
	echo     atomic.Bool
	pinging  atomic.Bool
	low      chan struct{}

	mu       sync.Mutex
	pings    map[uint32]time.Time
	rtts     []float64
	answered chan struct{}
}

func newChannel(dc *webrtc.DataChannel) *channel {
	c := &channel{dc: dc, low: make(chan struct{}, 1), pings: map[uint32]time.Time{}}
	dc.OnMessage(c.onMessage)
	dc.OnBufferedAmountLow(func() {
		select {
		case c.low <- struct{}{}:
		default:
		}
	})
	return c
}

func (c *channel) onMessage(msg webrtc.DataChannelMessage) {
	c.bytes.Add(int64(len(msg.Data)))
	c.messages.Add(1)
	if c.echo.Load() {
		_ = c.dc.Send(msg.Data)
	}
	if c.pinging.Load() && len(msg.Data) >= 4 {
		c.answer(binary.BigEndian.Uint32(msg.Data))
	}
}

func (c *channel) answer(number uint32) {
	c.mu.Lock()
	defer c.mu.Unlock()
	sent, ok := c.pings[number]
	if !ok {
		return
	}

	delete(c.pings, number)
	c.rtts = append(c.rtts, float64(time.Since(sent))/float64(time.Millisecond))
	if len(c.pings) == 0 && c.answered != nil {
		close(c.answered)
		c.answered = nil
	}
}

// flood sends messages for a while, keeping the buffered amount between the watermarks.
func (c *channel) flood(size int, duration time.Duration, low, high uint64) error {
	c.dc.SetBufferedAmountLowThreshold(low)
	payload := make([]byte, size)
	deadline := time.Now().Add(duration)

	for {
		remaining := time.Until(deadline)
		if remaining <= 0 {
			return nil
		}
		if c.dc.BufferedAmount() >= high {
			select {
			case <-c.low:
			case <-time.After(remaining):
			}
			continue
		}

		if err := c.dc.Send(payload); err != nil {
			return err
		}
	}
}

// ping sends numbered messages at a rate to an echoing peer, and returns their round trip times in ms.
func (c *channel) ping(size int, rate float64, duration time.Duration) ([]float64, error) {
	c.mu.Lock()
	c.rtts = []float64{}
	c.mu.Unlock()
	c.pinging.Store(true)
	defer c.pinging.Store(false)
	start := time.Now()
	count := int(rate*duration.Seconds() + 0.5)
	for number := range count {
		time.Sleep(time.Until(start.Add(time.Duration(float64(number) / rate * float64(time.Second)))))
		payload := make([]byte, size)
		binary.BigEndian.PutUint32(payload, uint32(number))
		c.mu.Lock()
		c.pings[uint32(number)] = time.Now()
		c.mu.Unlock()
		if err := c.dc.Send(payload); err != nil {
			return nil, err
		}
	}
	c.mu.Lock()
	answered := make(chan struct{})
	if len(c.pings) == 0 {
		close(answered)
	} else {
		c.answered = answered
	}
	c.mu.Unlock()
	select {
	case <-answered:
	case <-time.After(pingDrain):
	}
	c.mu.Lock()
	defer c.mu.Unlock()
	clear(c.pings)
	c.answered = nil
	return c.rtts, nil
}
