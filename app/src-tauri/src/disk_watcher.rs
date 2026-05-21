//! Cross-platform mount-point watcher.
//!
//! Polls `sysinfo::Disks` every second and POSTs to `/cards/detected` on the
//! sidecar whenever a new removable disk shows up. Polling beats native
//! callbacks here because (a) we already need to talk to the sidecar via
//! HTTP, and (b) the SLA is "<3 seconds" (CLAUDE.md §16), which polling
//! easily meets.
//!
//! We only forward *removable* disks: SD cards, USB drives, GoPros mounted as
//! mass storage. Boot disks and time-machine drives stay invisible.

use std::collections::HashSet;
use std::path::PathBuf;
use std::time::Duration;

use serde::Serialize;
use sysinfo::Disks;
use tauri::AppHandle;
use tokio::time::sleep;

use crate::ipc::get_sidecar_config;

#[derive(Debug, Serialize)]
struct CardDetectedPayload {
    mount_path: PathBuf,
    volume_id: String,
    label: Option<String>,
}

pub async fn watch(_app: AppHandle) {
    let mut seen: HashSet<PathBuf> = HashSet::new();

    loop {
        let mut disks = Disks::new_with_refreshed_list();
        disks.refresh();
        let current: HashSet<PathBuf> = disks
            .iter()
            .filter(|d| d.is_removable())
            .map(|d| d.mount_point().to_path_buf())
            .collect();

        for new_mount in current.difference(&seen).cloned().collect::<Vec<_>>() {
            // The matching disk row, for the label.
            let label = disks
                .iter()
                .find(|d| d.mount_point() == new_mount.as_path())
                .map(|d| d.name().to_string_lossy().to_string());

            let payload = CardDetectedPayload {
                mount_path: new_mount.clone(),
                volume_id: derive_volume_id(&new_mount),
                label,
            };
            if let Err(err) = post_card_detected(&payload).await {
                eprintln!("post_card_detected_failed: {err:?}");
            }
        }

        // Replace seen with current (forgets unmounted disks too).
        seen = current;
        sleep(Duration::from_secs(1)).await;
    }
}

fn derive_volume_id(mount: &std::path::Path) -> String {
    // On macOS / Linux, the mount path uniquely identifies the volume for a
    // session. On Windows it's the drive letter. Good enough for v1's
    // "already ingested in the last hour" check.
    mount.to_string_lossy().to_string()
}

async fn post_card_detected(payload: &CardDetectedPayload) -> anyhow::Result<()> {
    let cfg = get_sidecar_config().await.map_err(anyhow::Error::msg)?;
    let client = reqwest::Client::builder()
        .timeout(Duration::from_secs(5))
        .build()?;
    let res = client
        .post(format!("{}/cards/detected", cfg.url))
        .header("X-Sidecar-Token", &cfg.token)
        .json(payload)
        .send()
        .await?;
    if !res.status().is_success() {
        anyhow::bail!("sidecar replied {}", res.status());
    }
    Ok(())
}
