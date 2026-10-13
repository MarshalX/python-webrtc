//
//  Copyright 2022-2026 Ilya (Marshal) <https://github.com/MarshalX>. All rights reserved.
//
//  Use of this source code is governed by a BSD-style license
//  that can be found in the LICENSE.md file in the root of the project.
//

// Passes the locked version of webrtc to the driver, for hello.

fn main() {
    println!("cargo:rerun-if-changed=Cargo.lock");
    let lock = std::fs::read_to_string("Cargo.lock").unwrap_or_default();
    let mut lines = lock.lines();
    let version = lines
        .by_ref()
        .find(|line| *line == "name = \"webrtc\"")
        .and_then(|_| lines.next())
        .map_or("unknown", |line| {
            line.trim_start_matches("version = ").trim_matches('"')
        });
    println!("cargo:rustc-env=WEBRTC_VERSION={version}");
}
