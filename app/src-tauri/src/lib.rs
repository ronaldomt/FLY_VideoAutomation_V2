//! Tauri shell entrypoint.
//!
//! Responsibilities:
//! 1. (optionally) spawn the Python sidecar binary; otherwise expect an
//!    already-running sidecar (dev mode).
//! 2. Watch for new mass-storage volumes; POST `/cards/detected` on insert.
//! 3. Inject `window.__FLY_SIDECAR__` into the webview so the frontend's
//!    typed HTTP client picks up the per-launch port + token.
//!
//! See CLAUDE.md §5, §10.

mod disk_watcher;
mod ipc;
mod sidecar;

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .plugin(tauri_plugin_clipboard_manager::init())
        .plugin(tauri_plugin_opener::init())
        .setup(|app| {
            // 1. (Best-effort) spawn the bundled sidecar.
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(err) = sidecar::ensure_running(&handle).await {
                    eprintln!("sidecar_bootstrap_failed: {err:?}");
                }
            });

            // 2. Inject `window.__FLY_SIDECAR__` once the runtime file is readable.
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(err) = ipc::inject_sidecar_config(&handle).await {
                    eprintln!("inject_sidecar_config_failed: {err:?}");
                }
            });

            // 3. Start the disk-mount watcher.
            let handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                disk_watcher::watch(handle).await;
            });

            Ok(())
        })
        .invoke_handler(tauri::generate_handler![ipc::get_sidecar_config])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
