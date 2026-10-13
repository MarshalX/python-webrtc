//
//  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
//  Use of this source code is governed by a BSD-style license
//  that can be found in the LICENSE.md file in the root of the project.
//

use std::collections::HashMap;
use std::sync::Arc;
use std::sync::Mutex;
use std::sync::atomic::{AtomicBool, AtomicI64, Ordering};
use std::time::Duration;

use bytes::BytesMut;
use tokio::sync::Notify;
use tokio::time::{Instant, sleep_until, timeout_at};
use webrtc::data_channel::{DataChannel, DataChannelEvent};

use crate::Result;

const PING_DRAIN: Duration = Duration::from_secs(1);

/// A data channel that counts what it receives, and echoes, floods or pings.
pub struct Channel {
    dc: Arc<dyn DataChannel>,
    pub bytes: AtomicI64,
    pub messages: AtomicI64,
    pub echo: AtomicBool,
    pinging: AtomicBool,
    // set by bufferedamounthigh, cleared by bufferedamountlow: the library has no bufferedAmount getter
    full: AtomicBool,
    low: Notify,
    pings: Mutex<HashMap<u32, Instant>>,
    rtts: Mutex<Vec<f64>>,
    answered: Notify,
}

impl Channel {
    pub fn new(dc: Arc<dyn DataChannel>) -> Self {
        Self {
            dc,
            bytes: AtomicI64::new(0),
            messages: AtomicI64::new(0),
            echo: AtomicBool::new(false),
            pinging: AtomicBool::new(false),
            full: AtomicBool::new(false),
            low: Notify::new(),
            pings: Mutex::new(HashMap::new()),
            rtts: Mutex::new(Vec::new()),
            answered: Notify::new(),
        }
    }

    /// Handles an event of the channel other than its opening.
    pub async fn on_event(&self, event: DataChannelEvent) {
        match event {
            DataChannelEvent::OnMessage(message) => self.on_message(message.data).await,
            DataChannelEvent::OnBufferedAmountHigh => self.full.store(true, Ordering::SeqCst),
            DataChannelEvent::OnBufferedAmountLow => {
                self.full.store(false, Ordering::SeqCst);
                self.low.notify_one();
            }
            _ => {}
        }
    }

    async fn on_message(&self, data: BytesMut) {
        self.bytes.fetch_add(data.len() as i64, Ordering::Relaxed);
        self.messages.fetch_add(1, Ordering::Relaxed);
        if self.pinging.load(Ordering::SeqCst) && data.len() >= 4 {
            self.answer(u32::from_be_bytes([data[0], data[1], data[2], data[3]]));
        }
        if self.echo.load(Ordering::Relaxed) {
            let _ = self.dc.send(data).await;
        }
    }

    fn answer(&self, number: u32) {
        let mut pings = self.pings.lock().unwrap();
        let Some(sent) = pings.remove(&number) else {
            return;
        };
        self.rtts
            .lock()
            .unwrap()
            .push(sent.elapsed().as_secs_f64() * 1000.0);
        if pings.is_empty() {
            self.answered.notify_one();
        }
    }

    /// Sends messages for a while, keeping the buffered amount between the watermarks.
    pub async fn flood(&self, size: usize, duration: Duration, low: u32, high: u32) -> Result<()> {
        self.dc.set_buffered_amount_low_threshold(low).await?;
        self.dc.set_buffered_amount_high_threshold(high).await?;
        let payload = BytesMut::zeroed(size);
        let deadline = Instant::now() + duration;

        while Instant::now() < deadline {
            if self.full.load(Ordering::SeqCst) {
                let _ = timeout_at(deadline, self.low.notified()).await;
                continue;
            }
            self.dc.send(payload.clone()).await?;
        }
        Ok(())
    }

    /// Sends numbered messages at a rate to an echoing peer, and returns their round trip times in ms.
    pub async fn ping(&self, size: usize, rate: f64, duration: Duration) -> Result<Vec<f64>> {
        self.rtts.lock().unwrap().clear();
        self.pinging.store(true, Ordering::SeqCst);
        let start = Instant::now();
        let count = (rate * duration.as_secs_f64() + 0.5) as u32;

        for number in 0..count {
            sleep_until(start + Duration::from_secs_f64(f64::from(number) / rate)).await;
            let mut payload = BytesMut::zeroed(size);
            payload[..4].copy_from_slice(&number.to_be_bytes());
            self.pings.lock().unwrap().insert(number, Instant::now());
            self.dc.send(payload).await?;
        }

        // the replies still in flight
        let drained = Instant::now() + PING_DRAIN;
        while !self.pings.lock().unwrap().is_empty() {
            if timeout_at(drained, self.answered.notified()).await.is_err() {
                break;
            }
        }

        self.pinging.store(false, Ordering::SeqCst);
        self.pings.lock().unwrap().clear();
        Ok(std::mem::take(&mut *self.rtts.lock().unwrap()))
    }
}
