//! Spawn / supervise the bundled Python sidecar binary.
//!
//! In dev, the sidecar is started independently by `scripts/dev.sh`. In that
//! case `ensure_running` finds the runtime file already present and returns
//! without spawning anything.
//!
//! In production builds the sidecar lives next to the Tauri binary as
//! `fly-backend` (`.exe` on Windows). PyInstaller bundles it via
//! `scripts/build-sidecar.sh`.

use anyhow::{Context, Result};
use std::env;
use std::path::PathBuf;
use std::time::Duration;
use tauri::AppHandle;
use tokio::fs;
use tokio::process::Command;
use tokio::time::sleep;

const RUNTIME_FILE: &str = "sidecar.port";

fn runtime_dir() -> PathBuf {
    dirs_home()
        .map(|h| h.join(".fly-video-automation"))
        .unwrap_or_else(|| PathBuf::from(".fly-video-automation"))
}

fn dirs_home() -> Option<PathBuf> {
    env::var_os("HOME").map(PathBuf::from).or_else(|| {
        env::var_os("USERPROFILE").map(PathBuf::from)
    })
}

pub async fn ensure_running(_app: &AppHandle) -> Result<()> {
    let runtime_path = runtime_dir().join(RUNTIME_FILE);

    // If the runtime file is already there (dev mode), we're done.
    if fs::metadata(&runtime_path).await.is_ok() {
        return Ok(());
    }

    // Otherwise, try to launch the bundled sidecar.
    let exe = sidecar_binary_path()?;
    if fs::metadata(&exe).await.is_err() {
        // The binary isn't bundled — likely a dev build without sidecar baked in.
        // Don't crash; the user is expected to launch the sidecar manually.
        eprintln!(
            "no sidecar binary at {} — assuming external sidecar (dev mode)",
            exe.display()
        );
        return Ok(());
    }

    let mut cmd = Command::new(&exe);
    cmd.env("FLY_WRITE_RUNTIME_FILE", "1");
    cmd.spawn()
        .with_context(|| format!("failed to spawn sidecar at {}", exe.display()))?;

    // Wait up to ~10s for the sidecar to write its runtime file.
    for _ in 0..50 {
        sleep(Duration::from_millis(200)).await;
        if fs::metadata(&runtime_path).await.is_ok() {
            return Ok(());
        }
    }
    anyhow::bail!("sidecar did not write runtime file within 10s");
}

fn sidecar_binary_path() -> Result<PathBuf> {
    let mut exe = env::current_exe().context("no current_exe")?;
    exe.pop(); // drop the binary name
    #[cfg(target_os = "windows")]
    exe.push("fly-backend.exe");
    #[cfg(not(target_os = "windows"))]
    exe.push("fly-backend");
    Ok(exe)
}
