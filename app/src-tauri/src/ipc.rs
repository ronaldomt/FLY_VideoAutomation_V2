//! Tauri commands exposed to the frontend + initial sidecar-config injection.

use anyhow::{anyhow, Context, Result};
use serde::{Deserialize, Serialize};
use std::env;
use std::path::PathBuf;
use std::time::Duration;
use tauri::{AppHandle, Manager, Runtime};
use tokio::fs;
use tokio::time::sleep;

const RUNTIME_FILE: &str = "sidecar.port";

#[derive(Debug, Deserialize, Serialize, Clone)]
pub struct SidecarConfig {
    pub url: String,
    pub token: String,
}

#[derive(Debug, Deserialize)]
struct RuntimeFilePayload {
    port: u16,
    token: String,
}

fn runtime_path() -> PathBuf {
    let home = env::var_os("HOME")
        .or_else(|| env::var_os("USERPROFILE"))
        .map(PathBuf::from)
        .unwrap_or_else(|| PathBuf::from("."));
    home.join(".fly-video-automation").join(RUNTIME_FILE)
}

async fn read_runtime_file() -> Result<SidecarConfig> {
    let path = runtime_path();
    let bytes = fs::read(&path)
        .await
        .with_context(|| format!("could not read {}", path.display()))?;
    let payload: RuntimeFilePayload = serde_json::from_slice(&bytes)
        .context("runtime file is not valid JSON")?;
    Ok(SidecarConfig {
        url: format!("http://127.0.0.1:{}", payload.port),
        token: payload.token,
    })
}

/// Wait up to ~15s for the sidecar runtime file to appear, then inject
/// `window.__FLY_SIDECAR__` into the main webview so the React HTTP client
/// can pick it up on first request.
pub async fn inject_sidecar_config<R: Runtime>(app: &AppHandle<R>) -> Result<()> {
    let mut last_err: Option<anyhow::Error> = None;
    for _ in 0..75 {
        match read_runtime_file().await {
            Ok(cfg) => {
                let payload = serde_json::to_string(&cfg).context("encode sidecar config")?;
                let script =
                    format!("window.__FLY_SIDECAR__ = {payload};");
                if let Some(window) = app.get_webview_window("main") {
                    if let Err(e) = window.eval(&script) {
                        last_err = Some(anyhow!("eval failed: {e}"));
                        continue;
                    }
                }
                return Ok(());
            }
            Err(e) => last_err = Some(e),
        }
        sleep(Duration::from_millis(200)).await;
    }
    Err(last_err.unwrap_or_else(|| anyhow!("sidecar config never became available")))
}

#[tauri::command]
pub async fn get_sidecar_config() -> Result<SidecarConfig, String> {
    read_runtime_file().await.map_err(|e| e.to_string())
}
