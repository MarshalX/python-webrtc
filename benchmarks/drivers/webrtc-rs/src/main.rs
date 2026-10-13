//
//  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
//  Use of this source code is governed by a BSD-style license
//  that can be found in the LICENSE.md file in the root of the project.
//

//! The driver of webrtc-rs for the benchmarks, speaking benchmarks/protocol.py; data channels only.

mod channel;

use std::collections::{HashMap, HashSet};
use std::io::Write;
use std::sync::atomic::Ordering;
use std::sync::{Arc, Mutex};
use std::time::{Duration, Instant};

use serde::Deserialize;
use serde_json::{Value, json};
use tokio::io::{AsyncBufReadExt, BufReader};
use tokio::sync::watch;
use webrtc::data_channel::{
    DataChannel, DataChannelEvent, RTCDataChannelInit, RTCDataChannelState,
};
use webrtc::peer_connection::{
    PeerConnection, PeerConnectionBuilder, PeerConnectionEventHandler, RTCConfigurationBuilder,
    RTCIceCandidateInit, RTCIceConnectionState, RTCIceGatheringState, RTCPeerConnectionIceEvent,
    RTCPeerConnectionState, RTCSessionDescription,
};

use crate::channel::Channel;

const DATA_CHANNEL_LABEL: &str = "bench";
// every interface but loopback (the wildcard skips it), and loopback, like python-webrtc with WRTC_ALLOW_LOOPBACK=1
const UDP_ADDRS: [&str; 2] = ["0.0.0.0:0", "127.0.0.1:0"];

pub type Result<T> = std::result::Result<T, Box<dyn std::error::Error + Send + Sync>>;

#[derive(Deserialize, Default)]
#[serde(default)]
struct Command {
    id: Value,
    cmd: String,
    pc: i64,
    role: String,
    trickle: bool,
    ordered: bool,
    sdp: String,
    candidate: Option<RTCIceCandidateInit>,
    size: usize,
    seconds: f64,
    low: u32,
    high: u32,
    rate: f64,
}

/// What a connection's event handler shares with the driver.
struct Peer {
    id: i64,
    trickle: bool,
    channel: Mutex<Option<Arc<Channel>>>,
    gathered: watch::Sender<bool>,
}

struct Connection {
    pc: Arc<dyn PeerConnection>,
    peer: Arc<Peer>,
}

struct Driver {
    origin: Instant,
    out: Mutex<std::io::Stdout>,
    connections: Mutex<HashMap<i64, Arc<Connection>>>,
    sent: Mutex<HashSet<(i64, String)>>,
}

impl Driver {
    fn now(&self) -> f64 {
        self.origin.elapsed().as_secs_f64()
    }

    fn send(&self, message: &Value) {
        let mut out = self.out.lock().unwrap();
        if writeln!(out, "{message}")
            .and_then(|()| out.flush())
            .is_err()
        {
            eprintln!("write failed");
        }
    }

    fn emit(&self, pc: i64, name: &str) {
        if self.sent.lock().unwrap().insert((pc, name.to_owned())) {
            self.send(&json!({"event": name, "pc": pc, "t": self.now()}));
        }
    }

    fn connection(&self, pc: i64) -> Result<Arc<Connection>> {
        let connections = self.connections.lock().unwrap();
        Ok(connections
            .get(&pc)
            .ok_or(format!("no connection {pc}"))?
            .clone())
    }

    fn channel(&self, pc: i64) -> Result<Arc<Channel>> {
        let connection = self.connection(pc)?;
        let channel = connection.peer.channel.lock().unwrap().clone();
        Ok(channel.ok_or(format!("no open data channel on connection {pc}"))?)
    }
}

/// Reads the events of a data channel until it closes; open, it becomes the connection's channel.
fn watch_channel(driver: Arc<Driver>, peer: Arc<Peer>, dc: Arc<dyn DataChannel>) {
    tokio::spawn(async move {
        let channel = Arc::new(Channel::new(dc.clone()));
        let opened = || {
            *peer.channel.lock().unwrap() = Some(channel.clone());
            driver.emit(peer.id, "dc_open");
        };
        if matches!(dc.ready_state().await, Ok(RTCDataChannelState::Open)) {
            opened();
        }

        while let Some(event) = dc.poll().await {
            match event {
                DataChannelEvent::OnOpen => opened(),
                DataChannelEvent::OnClose => break,
                event => channel.on_event(event).await,
            }
        }
    });
}

struct Handler {
    driver: Arc<Driver>,
    peer: Arc<Peer>,
}

#[async_trait::async_trait]
impl PeerConnectionEventHandler for Handler {
    async fn on_ice_candidate(&self, event: RTCPeerConnectionIceEvent) {
        if !self.peer.trickle {
            return;
        }
        if let Ok(candidate) = event.candidate.to_json() {
            let d = &self.driver;
            d.send(&json!({"event": "candidate", "pc": self.peer.id, "t": d.now(), "candidate": candidate}));
        }
    }

    async fn on_ice_connection_state_change(&self, state: RTCIceConnectionState) {
        if matches!(
            state,
            RTCIceConnectionState::Connected | RTCIceConnectionState::Completed
        ) {
            self.driver.emit(self.peer.id, "ice_connected");
        }
    }

    async fn on_ice_gathering_state_change(&self, state: RTCIceGatheringState) {
        if state == RTCIceGatheringState::Complete {
            self.peer.gathered.send_replace(true);
            self.driver.emit(self.peer.id, "gathered");
        }
    }

    async fn on_connection_state_change(&self, state: RTCPeerConnectionState) {
        match state {
            RTCPeerConnectionState::Connected => self.driver.emit(self.peer.id, "connected"),
            RTCPeerConnectionState::Failed => self.driver.emit(self.peer.id, "failed"),
            _ => {}
        }
    }

    async fn on_data_channel(&self, dc: Arc<dyn DataChannel>) {
        watch_channel(self.driver.clone(), self.peer.clone(), dc);
    }
}

fn hello() -> Value {
    json!({
        "library": "webrtc-rs",
        "version": env!("WEBRTC_VERSION"),
        "trickle": true,
    })
}

async fn create(d: &Arc<Driver>, c: &Command) -> Result<Value> {
    let start = d.now();
    let peer = Arc::new(Peer {
        id: c.pc,
        trickle: c.trickle,
        channel: Mutex::new(None),
        gathered: watch::Sender::new(false),
    });

    let pc = PeerConnectionBuilder::new()
        .with_configuration(RTCConfigurationBuilder::new().build())
        .with_handler(Arc::new(Handler {
            driver: d.clone(),
            peer: peer.clone(),
        }))
        .with_udp_addrs(UDP_ADDRS.to_vec())
        .build()
        .await?;
    let pc: Arc<dyn PeerConnection> = Arc::new(pc);

    if c.role == "offerer" {
        let init = RTCDataChannelInit {
            ordered: c.ordered,
            ..Default::default()
        };
        let dc = pc
            .create_data_channel(DATA_CHANNEL_LABEL, Some(init))
            .await?;
        watch_channel(d.clone(), peer.clone(), dc);
    }

    d.connections
        .lock()
        .unwrap()
        .insert(c.pc, Arc::new(Connection { pc, peer }));
    Ok(json!({"t_start": start, "t_end": d.now()}))
}

/// Sets a local description and returns its SDP, with the candidates unless they trickle.
async fn set_local(connection: &Connection, description: RTCSessionDescription) -> Result<String> {
    let mut gathered = connection.peer.gathered.subscribe();
    connection.pc.set_local_description(description).await?;
    if !connection.peer.trickle {
        gathered.wait_for(|done| *done).await?;
    }

    let local = connection
        .pc
        .local_description()
        .await
        .ok_or("no local description")?;
    Ok(local.sdp)
}

async fn offer(d: &Driver, c: &Command) -> Result<Value> {
    let connection = d.connection(c.pc)?;
    let start = d.now();
    let offer = connection.pc.create_offer(None).await?;
    let created = d.now();
    let sdp = set_local(&connection, offer).await?;
    Ok(json!({"sdp": sdp, "t_start": start, "t_offer": created}))
}

async fn answer(d: &Driver, c: &Command) -> Result<Value> {
    let connection = d.connection(c.pc)?;
    connection
        .pc
        .set_remote_description(RTCSessionDescription::offer(c.sdp.clone())?)
        .await?;
    let answer = connection.pc.create_answer(None).await?;
    Ok(json!({"sdp": set_local(&connection, answer).await?}))
}

async fn accept(d: &Driver, c: &Command) -> Result<Value> {
    let connection = d.connection(c.pc)?;
    connection
        .pc
        .set_remote_description(RTCSessionDescription::answer(c.sdp.clone())?)
        .await?;
    Ok(json!({}))
}

async fn add_candidate(d: &Driver, c: &Command) -> Result<Value> {
    let connection = d.connection(c.pc)?;
    let candidate = c.candidate.clone().ok_or("no candidate")?;
    // an empty candidate ends the candidates, which webrtc-rs doesn't need
    if !candidate.candidate.is_empty() {
        connection.pc.add_ice_candidate(candidate).await?;
    }
    Ok(json!({}))
}

async fn close(d: &Driver, c: &Command) -> Result<Value> {
    let connection = d
        .connections
        .lock()
        .unwrap()
        .remove(&c.pc)
        .ok_or(format!("no connection {}", c.pc))?;
    connection.peer.channel.lock().unwrap().take();
    connection.pc.close().await?;
    Ok(json!({}))
}

fn count(d: &Driver, c: &Command) -> Result<Value> {
    let channel = d.channel(c.pc)?;
    Ok(json!({"bytes": channel.bytes.load(Ordering::Relaxed),
              "messages": channel.messages.load(Ordering::Relaxed),
              "t": d.now()}))
}

fn echo(d: &Driver, c: &Command) -> Result<Value> {
    d.channel(c.pc)?.echo.store(true, Ordering::Relaxed);
    Ok(json!({}))
}

async fn flood(d: &Driver, c: &Command) -> Result<Value> {
    d.channel(c.pc)?
        .flood(c.size, Duration::from_secs_f64(c.seconds), c.low, c.high)
        .await?;
    Ok(json!({}))
}

async fn ping(d: &Driver, c: &Command) -> Result<Value> {
    let channel = d.channel(c.pc)?;
    let rtts = channel
        .ping(c.size, c.rate, Duration::from_secs_f64(c.seconds))
        .await?;
    Ok(json!({"rtts_ms": rtts}))
}

#[cfg(target_os = "macos")]
unsafe extern "C" {
    fn malloc_zone_pressure_relief(zone: *mut std::ffi::c_void, goal: usize) -> usize;
}

#[cfg(all(target_os = "linux", target_env = "gnu"))]
unsafe extern "C" {
    fn malloc_trim(pad: usize) -> std::ffi::c_int;
}

/// Returns freed memory to the OS where the allocator can; Rust has no collector.
fn collect() -> Value {
    #[cfg(target_os = "macos")]
    unsafe {
        malloc_zone_pressure_relief(std::ptr::null_mut(), 0);
    }
    #[cfg(all(target_os = "linux", target_env = "gnu"))]
    unsafe {
        malloc_trim(0);
    }
    json!({})
}

async fn handle(d: &Arc<Driver>, c: &Command) -> Result<Value> {
    match c.cmd.as_str() {
        "hello" => Ok(hello()),
        "create" => create(d, c).await,
        "offer" => offer(d, c).await,
        "answer" => answer(d, c).await,
        "accept" => accept(d, c).await,
        "add_candidate" => add_candidate(d, c).await,
        "count" => count(d, c),
        "echo" => echo(d, c),
        "flood" => flood(d, c).await,
        "ping" => ping(d, c).await,
        "close" => close(d, c).await,
        "collect" => Ok(collect()),
        // no event loop of its own to lag
        "probe" => Ok(json!({})),
        other => Err(format!("unknown command {other:?}").into()),
    }
}

async fn run(d: Arc<Driver>, c: Command) {
    match handle(&d, &c).await {
        Ok(result) => d.send(&json!({"id": c.id, "result": result})),
        Err(error) => d.send(&json!({"id": c.id, "error": error.to_string()})),
    }
}

#[tokio::main]
async fn main() -> Result<()> {
    let driver = Arc::new(Driver {
        origin: Instant::now(),
        out: Mutex::new(std::io::stdout()),
        connections: Mutex::new(HashMap::new()),
        sent: Mutex::new(HashSet::new()),
    });

    let mut lines = BufReader::new(tokio::io::stdin()).lines();
    while let Some(line) = lines.next_line().await? {
        let Ok(c) = serde_json::from_str::<Command>(&line) else {
            continue;
        };
        if c.cmd == "exit" {
            driver.send(&json!({"id": c.id, "result": {}}));
            // exits without tearing down the connections left: the runner is done with them
            std::process::exit(0);
        }
        tokio::spawn(run(driver.clone(), c));
    }
    std::process::exit(0);
}
